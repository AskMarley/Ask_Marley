import json
from datetime import datetime, timezone

from askmarley.data import FLAGGED_CHATS, PROVIDER_SIGNUPS, SERVICE_INTENTS, TAXONOMY
from askmarley.extensions import db
from askmarley.models import (
    AdminAuditLog,
    ModerationCase,
    Provider,
    ProviderCoverage,
    TaxonomyEntry,
    TaxonomyVersion,
)

VALID_MODERATION_STATUSES = {"open", "reviewing", "resolved", "dismissed"}


def _service_slug_for_path(service_path):
    normalized = service_path.strip().lower()
    for slug, payload in SERVICE_INTENTS.items():
        if payload.get("branch", "").strip().lower() == normalized:
            return slug
    return "emergency-plumber"


def _ensure_provider_from_signup(provider_name):
    signup = next(
        (
            item
            for item in PROVIDER_SIGNUPS
            if item.get("name", "").strip().lower() == provider_name.strip().lower()
        ),
        None,
    )
    if not signup:
        return None

    provider = Provider(
        name=signup["name"],
        service_slug=_service_slug_for_path(signup.get("service_path", "")),
        tier="basic",
        billing_status="active",
        verified=False,
        suspended=False,
        marleys_choice=False,
    )
    db.session.add(provider)
    db.session.flush()

    for outward in [segment.strip() for segment in signup.get("postcodes", "").split(",") if segment.strip()]:
        db.session.add(ProviderCoverage(provider_id=provider.id, outward_code=outward))

    db.session.commit()
    return provider


def _ensure_default_moderation_cases():
    existing_ids = {
        case_id
        for (case_id,) in db.session.query(ModerationCase.case_id).all()
    }
    created = False
    for flag in FLAGGED_CHATS:
        if flag["case_id"] in existing_ids:
            continue
        db.session.add(
            ModerationCase(
                case_id=flag["case_id"],
                reason=flag["reason"],
                participants=flag["participants"],
                severity=flag["severity"],
                status="open",
                source="seed",
                reported_by="system",
            )
        )
        created = True
    if created:
        db.session.commit()


def get_admin_context(session, current_user):
    return {
        "id": current_user.get("id") if current_user else None,
        "name": current_user.get("full_name") if current_user else "Unknown",
        "role": current_user.get("role") if current_user else "viewer",
    }


def get_provider_registry(session):
    for signup in PROVIDER_SIGNUPS:
        existing = Provider.query.filter(
            db.func.lower(Provider.name) == signup["name"].strip().lower()
        ).first()
        if not existing:
            _ensure_provider_from_signup(signup["name"])

    registry = []
    providers = Provider.query.order_by(Provider.id.asc()).all()
    for provider in providers:
        coverage_rows = ProviderCoverage.query.filter_by(provider_id=provider.id).all()
        postcodes = [row.outward_code for row in coverage_rows]
        service_path = SERVICE_INTENTS.get(provider.service_slug, {}).get(
            "branch", provider.service_slug
        )
        if provider.suspended:
            status = "suspended"
        elif provider.verified:
            status = "verified"
        else:
            status = "pending"

        registry.append(
            {
                "id": provider.id,
                "name": provider.name,
                "service_path": service_path,
                "postcodes": ", ".join(postcodes),
                "status": status,
                "tier": provider.tier,
                "billing_status": provider.billing_status,
                "verified": provider.verified,
                "suspended": provider.suspended,
            }
        )

    return registry


def get_taxonomy_registry(session):
    if not TaxonomyEntry.query.first():
        for branch in TAXONOMY:
            db.session.add(TaxonomyEntry(branch_path=branch, active=True, version=1))
        db.session.commit()

    entries = TaxonomyEntry.query.order_by(TaxonomyEntry.id.asc()).all()
    return [
        {
            "id": entry.id,
            "branch_path": entry.branch_path,
            "active": entry.active,
            "version": entry.version,
        }
        for entry in entries
    ]


def _validate_taxonomy_path(path):
    parts = [part.strip() for part in path.split(">") if part.strip()]
    return len(parts) >= 3


def _record_taxonomy_version(session, entry_id, actor, reason, before_path, after_path, version):
    db.session.add(
        TaxonomyVersion(
            entry_id=entry_id,
            actor=actor,
            reason=reason,
            before_path=before_path,
            after_path=after_path,
            version=version,
        )
    )
    db.session.commit()


def add_taxonomy_entry(session, branch_path, reason, actor):
    if not _validate_taxonomy_path(branch_path):
        return False, "Taxonomy path must have at least 3 levels: Branch > Category > Service."

    normalized = branch_path.strip()
    duplicate = TaxonomyEntry.query.filter(
        db.func.lower(TaxonomyEntry.branch_path) == normalized.lower()
    ).first()
    if duplicate:
        return False, "Taxonomy path already exists."

    entry = TaxonomyEntry(branch_path=normalized, active=True, version=1)
    db.session.add(entry)
    db.session.commit()
    _record_taxonomy_version(session, entry.id, actor, reason, "", normalized, 1)
    return True, f"Category added: {normalized}"


def update_taxonomy_entry(session, entry_id, branch_path, reason, actor):
    if not _validate_taxonomy_path(branch_path):
        return False, "Taxonomy path must have at least 3 levels: Branch > Category > Service."

    target = TaxonomyEntry.query.filter_by(id=entry_id).first()
    if not target:
        return False, "Taxonomy entry not found."

    normalized = branch_path.strip()
    duplicate = TaxonomyEntry.query.filter(
        TaxonomyEntry.id != entry_id,
        db.func.lower(TaxonomyEntry.branch_path) == normalized.lower(),
    ).first()
    if duplicate:
        return False, "Another taxonomy entry already uses that path."

    before_path = target.branch_path
    target.branch_path = normalized
    target.version += 1
    db.session.commit()
    _record_taxonomy_version(
        session,
        entry_id,
        actor,
        reason,
        before_path,
        normalized,
        target.version,
    )
    return True, f"Taxonomy entry updated to: {normalized}"


def set_taxonomy_active(session, entry_id, active, reason, actor):
    target = TaxonomyEntry.query.filter_by(id=entry_id).first()
    if not target:
        return False, "Taxonomy entry not found."

    before_path = target.branch_path
    target.active = active
    target.version += 1
    db.session.commit()
    _record_taxonomy_version(
        session,
        entry_id,
        actor,
        reason,
        before_path,
        target.branch_path,
        target.version,
    )
    if active:
        return True, f"Taxonomy entry reactivated: {target.branch_path}"
    return True, f"Taxonomy entry deprecated: {target.branch_path}"


def get_taxonomy_versions(session):
    rows = TaxonomyVersion.query.order_by(TaxonomyVersion.created_at.desc()).limit(100).all()
    return [
        {
            "entry_id": row.entry_id,
            "actor": row.actor,
            "reason": row.reason,
            "before_path": row.before_path,
            "after_path": row.after_path,
            "version": row.version,
            "timestamp": row.created_at.isoformat(timespec="seconds"),
        }
        for row in rows
    ]


def get_moderation_cases(session):
    _ensure_default_moderation_cases()

    cases = ModerationCase.query.order_by(ModerationCase.created_at.desc()).all()
    return [
        {
            "case_id": case.case_id,
            "reason": case.reason,
            "participants": case.participants,
            "severity": case.severity,
            "status": case.status,
            "source": case.source,
            "reported_by": case.reported_by,
        }
        for case in cases
    ]


def create_moderation_case(session, reason, participants, severity, source, reported_by):
    last = ModerationCase.query.order_by(ModerationCase.id.desc()).first()
    next_id = (last.id + 1) if last else 1
    case = ModerationCase(
        case_id=f"CASE-{next_id:04d}",
        reason=reason,
        participants=participants,
        severity=severity,
        status="open",
        source=source,
        reported_by=reported_by,
    )
    db.session.add(case)
    db.session.commit()
    return {
        "case_id": case.case_id,
        "reason": case.reason,
        "participants": case.participants,
        "severity": case.severity,
        "status": case.status,
        "source": case.source,
        "reported_by": case.reported_by,
    }


def update_moderation_case_status(session, case_id, new_status):
    if new_status not in VALID_MODERATION_STATUSES:
        return False, "Invalid moderation status."

    case = ModerationCase.query.filter_by(case_id=case_id).first()
    if not case:
        return False, "Moderation case not found."

    case.status = new_status
    db.session.commit()
    return True, f"Case {case_id} moved to {new_status}."


def get_provider_by_name(session, provider_name):
    provider = Provider.query.filter(
        db.func.lower(Provider.name) == provider_name.strip().lower()
    ).first()
    if provider:
        return provider
    return _ensure_provider_from_signup(provider_name)


def _append_session_audit(session, entry):
    return entry


def record_audit(
    session,
    action,
    actor,
    provider_name,
    reason,
    before_state,
    after_state,
):
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    entry = {
        "timestamp": timestamp,
        "actor": actor,
        "action": action,
        "provider_name": provider_name,
        "reason": reason,
        "before": before_state,
        "after": after_state,
    }
    _append_session_audit(session, entry)

    details = json.dumps(entry)
    db.session.add(
        AdminAuditLog(
            admin_user_id=None,
            action=action,
            details=details,
        )
    )
    db.session.commit()


def assert_admin_authorized(admin_ctx):
    return admin_ctx.get("role") in {"super_admin", "admin"}


def verify_provider(session, provider_name, reason, actor):
    provider = get_provider_by_name(session, provider_name)
    if not provider:
        return False, "Provider not found."

    before_state = {
        "verified": provider.verified,
        "suspended": provider.suspended,
        "tier": provider.tier,
        "status": "suspended" if provider.suspended else ("verified" if provider.verified else "pending"),
    }
    provider.verified = True
    provider.suspended = False
    db.session.commit()
    after_state = {
        "verified": provider.verified,
        "suspended": provider.suspended,
        "tier": provider.tier,
        "status": "verified",
    }
    record_audit(
        session,
        action="verify-provider",
        actor=actor,
        provider_name=provider.name,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )
    return True, f"{provider.name} marked as Verified."


def override_provider_tier(session, provider_name, new_tier, reason, actor):
    provider = get_provider_by_name(session, provider_name)
    if not provider:
        return False, "Provider not found."

    before_state = {
        "tier": provider.tier,
        "verified": provider.verified,
        "suspended": provider.suspended,
    }
    provider.tier = new_tier
    db.session.commit()
    after_state = {
        "tier": provider.tier,
        "verified": provider.verified,
        "suspended": provider.suspended,
    }
    record_audit(
        session,
        action="override-tier",
        actor=actor,
        provider_name=provider.name,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )
    return True, f"{provider.name} moved to {new_tier.title()} tier."


def set_provider_suspension(session, provider_name, suspended, reason, actor):
    provider = get_provider_by_name(session, provider_name)
    if not provider:
        return False, "Provider not found."

    before_state = {
        "verified": provider.verified,
        "suspended": provider.suspended,
        "tier": provider.tier,
    }
    provider.suspended = suspended
    if suspended:
        provider.verified = False
    db.session.commit()
    after_state = {
        "verified": provider.verified,
        "suspended": provider.suspended,
        "tier": provider.tier,
    }
    action = "suspend-provider" if suspended else "reactivate-provider"
    record_audit(
        session,
        action=action,
        actor=actor,
        provider_name=provider.name,
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )

    if suspended:
        return True, f"{provider.name} has been suspended."
    return True, f"{provider.name} has been reactivated."


def get_admin_audit_trail(session):
    rows = AdminAuditLog.query.order_by(AdminAuditLog.created_at.desc()).limit(60).all()
    trail = []
    for row in rows:
        try:
            payload = json.loads(row.details)
        except json.JSONDecodeError:
            payload = {
                "timestamp": row.created_at.isoformat(timespec="seconds"),
                "actor": "Unknown",
                "action": row.action,
                "provider_name": "N/A",
                "reason": "N/A",
                "before": {},
                "after": {},
            }
        trail.append(payload)
    return trail
