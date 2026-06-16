import json
from datetime import UTC, datetime

from askmarley.data import FLAGGED_CHATS, PROVIDER_SIGNUPS, TAXONOMY
from askmarley.extensions import db
from askmarley.models import AdminAuditLog

VALID_MODERATION_STATUSES = {"open", "reviewing", "resolved", "dismissed"}


def get_admin_context(session, current_user):
    admin_ctx = {
        "id": current_user.get("id") if current_user else None,
        "name": current_user.get("full_name") if current_user else "Unknown",
        "role": current_user.get("role") if current_user else "viewer",
    }
    session["admin_context"] = admin_ctx
    session.modified = True
    return admin_ctx


def get_provider_registry(session):
    if "provider_registry" not in session:
        registry = []
        for idx, provider in enumerate(PROVIDER_SIGNUPS, start=1):
            registry.append(
                {
                    "id": idx,
                    "name": provider["name"],
                    "service_path": provider["service_path"],
                    "postcodes": provider["postcodes"],
                    "status": "pending",
                    "tier": "basic",
                    "verified": False,
                    "suspended": False,
                }
            )
        session["provider_registry"] = registry
        session.modified = True

    return session["provider_registry"]


def get_taxonomy_registry(session):
    if "taxonomy_registry" not in session:
        registry = []
        for idx, branch in enumerate(TAXONOMY, start=1):
            registry.append(
                {
                    "id": idx,
                    "branch_path": branch,
                    "active": True,
                    "version": 1,
                }
            )
        session["taxonomy_registry"] = registry
        session.setdefault("taxonomy_versions", [])
        session.modified = True

    return session["taxonomy_registry"]


def _validate_taxonomy_path(path):
    parts = [part.strip() for part in path.split(">") if part.strip()]
    return len(parts) >= 3


def _record_taxonomy_version(session, entry_id, actor, reason, before_path, after_path, version):
    versions = session.setdefault("taxonomy_versions", [])
    versions.insert(
        0,
        {
            "entry_id": entry_id,
            "actor": actor,
            "reason": reason,
            "before_path": before_path,
            "after_path": after_path,
            "version": version,
            "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        },
    )
    session["taxonomy_versions"] = versions[:100]
    session.modified = True


def add_taxonomy_entry(session, branch_path, reason, actor):
    if not _validate_taxonomy_path(branch_path):
        return False, "Taxonomy path must have at least 3 levels: Branch > Category > Service."

    registry = get_taxonomy_registry(session)
    normalized = branch_path.strip()
    if any(entry["branch_path"].lower() == normalized.lower() for entry in registry):
        return False, "Taxonomy path already exists."

    new_id = max((entry["id"] for entry in registry), default=0) + 1
    entry = {
        "id": new_id,
        "branch_path": normalized,
        "active": True,
        "version": 1,
    }
    registry.append(entry)
    session["taxonomy_registry"] = registry
    _record_taxonomy_version(session, new_id, actor, reason, "", normalized, 1)
    return True, f"Category added: {normalized}"


def update_taxonomy_entry(session, entry_id, branch_path, reason, actor):
    if not _validate_taxonomy_path(branch_path):
        return False, "Taxonomy path must have at least 3 levels: Branch > Category > Service."

    registry = get_taxonomy_registry(session)
    target = next((entry for entry in registry if entry["id"] == entry_id), None)
    if not target:
        return False, "Taxonomy entry not found."

    normalized = branch_path.strip()
    duplicate = next(
        (
            entry
            for entry in registry
            if entry["id"] != entry_id and entry["branch_path"].lower() == normalized.lower()
        ),
        None,
    )
    if duplicate:
        return False, "Another taxonomy entry already uses that path."

    before_path = target["branch_path"]
    target["branch_path"] = normalized
    target["version"] += 1
    session["taxonomy_registry"] = registry
    _record_taxonomy_version(
        session,
        entry_id,
        actor,
        reason,
        before_path,
        normalized,
        target["version"],
    )
    return True, f"Taxonomy entry updated to: {normalized}"


def set_taxonomy_active(session, entry_id, active, reason, actor):
    registry = get_taxonomy_registry(session)
    target = next((entry for entry in registry if entry["id"] == entry_id), None)
    if not target:
        return False, "Taxonomy entry not found."

    before_state = dict(target)
    target["active"] = active
    target["version"] += 1
    session["taxonomy_registry"] = registry
    _record_taxonomy_version(
        session,
        entry_id,
        actor,
        reason,
        before_state["branch_path"],
        target["branch_path"],
        target["version"],
    )
    if active:
        return True, f"Taxonomy entry reactivated: {target['branch_path']}"
    return True, f"Taxonomy entry deprecated: {target['branch_path']}"


def get_taxonomy_versions(session):
    return session.get("taxonomy_versions", [])


def get_moderation_cases(session):
    if "moderation_cases" not in session:
        cases = []
        for flag in FLAGGED_CHATS:
            cases.append(
                {
                    "case_id": flag["case_id"],
                    "reason": flag["reason"],
                    "participants": flag["participants"],
                    "severity": flag["severity"],
                    "status": "open",
                    "source": "seed",
                    "reported_by": "system",
                }
            )
        for event in session.get("moderation_events", []):
            case = dict(event)
            case.setdefault("status", "open")
            case.setdefault("source", "automated")
            case.setdefault("reported_by", "system")
            cases.append(case)
        session["moderation_cases"] = cases
        session.modified = True

    return session["moderation_cases"]


def create_moderation_case(session, reason, participants, severity, source, reported_by):
    cases = get_moderation_cases(session)
    next_id = len(cases) + 1
    case = {
        "case_id": f"CASE-{next_id:04d}",
        "reason": reason,
        "participants": participants,
        "severity": severity,
        "status": "open",
        "source": source,
        "reported_by": reported_by,
    }
    cases.insert(0, case)
    session["moderation_cases"] = cases
    session.modified = True
    return case


def update_moderation_case_status(session, case_id, new_status):
    if new_status not in VALID_MODERATION_STATUSES:
        return False, "Invalid moderation status."

    cases = get_moderation_cases(session)
    case = next((entry for entry in cases if entry["case_id"] == case_id), None)
    if not case:
        return False, "Moderation case not found."

    case["status"] = new_status
    session["moderation_cases"] = cases
    session.modified = True
    return True, f"Case {case_id} moved to {new_status}."


def get_provider_by_name(session, provider_name):
    for provider in get_provider_registry(session):
        if provider["name"].strip().lower() == provider_name.strip().lower():
            return provider
    return None


def _append_session_audit(session, entry):
    logs = session.setdefault("admin_audit_trail", [])
    logs.insert(0, entry)
    session["admin_audit_trail"] = logs[:60]
    session.modified = True


def record_audit(
    session,
    action,
    actor,
    provider_name,
    reason,
    before_state,
    after_state,
):
    timestamp = datetime.now(UTC).isoformat(timespec="seconds")
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
            admin_user_id=1,
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

    before_state = dict(provider)
    provider["verified"] = True
    provider["status"] = "verified"
    after_state = dict(provider)
    record_audit(
        session,
        action="verify-provider",
        actor=actor,
        provider_name=provider["name"],
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )
    return True, f"{provider['name']} marked as Verified."


def override_provider_tier(session, provider_name, new_tier, reason, actor):
    provider = get_provider_by_name(session, provider_name)
    if not provider:
        return False, "Provider not found."

    before_state = dict(provider)
    provider["tier"] = new_tier
    provider["status"] = "verified" if provider["verified"] else provider["status"]
    after_state = dict(provider)
    record_audit(
        session,
        action="override-tier",
        actor=actor,
        provider_name=provider["name"],
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )
    return True, f"{provider['name']} moved to {new_tier.title()} tier."


def set_provider_suspension(session, provider_name, suspended, reason, actor):
    provider = get_provider_by_name(session, provider_name)
    if not provider:
        return False, "Provider not found."

    before_state = dict(provider)
    provider["suspended"] = suspended
    provider["status"] = "suspended" if suspended else "verified"
    after_state = dict(provider)
    action = "suspend-provider" if suspended else "reactivate-provider"
    record_audit(
        session,
        action=action,
        actor=actor,
        provider_name=provider["name"],
        reason=reason,
        before_state=before_state,
        after_state=after_state,
    )

    if suspended:
        return True, f"{provider['name']} has been suspended."
    return True, f"{provider['name']} has been reactivated."


def get_admin_audit_trail(session):
    return session.get("admin_audit_trail", [])
