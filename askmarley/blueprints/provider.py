from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from askmarley.data import BILLING_STATUSES, PROVIDER_TIERS, SERVICE_INTENTS
from askmarley.extensions import db
from askmarley.models import ChatMessage, ChatThread, Project, User
from askmarley.services.auth import role_required
from askmarley.services.collaboration import build_provider_chat_summary
from askmarley.services.matching import detect_service_details, extract_uk_location_code
from askmarley.services.subscriptions import (
    get_provider_subscription,
    update_provider_subscription,
)

provider_bp = Blueprint("provider", __name__, url_prefix="/provider")


LEAD_STATUS_FLOW = [
    ("shortlisting", "Shortlisting"),
    ("contacted", "Contacted"),
    ("quoted", "Quoted"),
    ("won", "Won"),
    ("archived", "Archived"),
]


def _get_provider_user():
    user_id = session.get("auth_user_id")
    if not user_id:
        return None
    user = db.session.get(User, user_id)
    if not user or user.role != "provider":
        return None
    return user


def _split_csv(value):
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def _service_label(slug):
    return SERVICE_INTENTS.get(slug, {}).get("name", slug.replace("-", " ").title())


def _provider_service_slugs(user):
    slugs = _split_csv(getattr(user, "service_categories", None)) if user else []
    return slugs or ["emergency-plumber", "electrician"]


def _provider_travel_postcodes(user):
    postcodes = _split_csv(getattr(user, "travel_postcodes", None)) if user else []
    return postcodes or ["SW1A", "SE1", "W1", "E1"]


def _lead_matching_text(project, latest_message=None):
    pieces = [project.name or ""]
    if latest_message and latest_message.message:
        pieces.append(latest_message.message)
    if project.status:
        pieces.append(project.status)
    return " ".join(piece for piece in pieces if piece)


def _lead_matches_provider(project, provider_service_slugs, provider_travel_postcodes, latest_message=None):
    matching_text = _lead_matching_text(project, latest_message)
    detected = detect_service_details(matching_text)
    detected_service_slug = project.service_slug or detected.get("service_slug")
    lead_postcode = project.location_code or extract_uk_location_code(matching_text)

    service_match = True
    if detected_service_slug:
        service_match = detected_service_slug in provider_service_slugs

    postcode_match = True
    if lead_postcode:
        postcode_match = lead_postcode in provider_travel_postcodes

    return {
        "matches": service_match and postcode_match,
        "detected_service_slug": detected_service_slug,
        "lead_postcode": lead_postcode,
        "service_match": service_match,
        "postcode_match": postcode_match,
        "confidence": detected.get("confidence", 0.0),
    }


def _build_provider_profile(provider_sub):
    user = _get_provider_user()
    session_user = session.get("auth_user", {})
    service_slugs = _provider_service_slugs(user)
    travel_postcodes = _provider_travel_postcodes(user)

    services = [_service_label(slug) for slug in service_slugs]
    profile_name = (getattr(user, "company_name", None) or session_user.get("full_name") or "Provider Portal")
    onboarding_steps = [
        {
            "label": "Business profile",
            "complete": bool(getattr(user, "company_name", None)),
            "detail": getattr(user, "company_name", None) or "Add your company name and public business details.",
        },
        {
            "label": "Service coverage",
            "complete": bool(service_slugs),
            "detail": ", ".join(services) if services else "Choose the services you want to receive leads for.",
        },
        {
            "label": "Travel area",
            "complete": bool(travel_postcodes),
            "detail": ", ".join(travel_postcodes) if travel_postcodes else "Add the postcode areas you cover.",
        },
        {
            "label": "Verification",
            "complete": bool(getattr(user, "insurance_verified", False)) and getattr(user, "provider_status", "pending") == "verified",
            "detail": "Verification is pending until insurance and business checks are complete.",
        },
    ]

    return {
        "name": profile_name,
        "tier": provider_sub["effective_tier"],
        "selected_tier": provider_sub["selected_tier"],
        "billing_status": provider_sub["billing_status"],
        "service_slugs": service_slugs,
        "services": services,
        "travel_postcodes": travel_postcodes or ["SW1A", "SE1", "W1", "E1"],
        "onboarding_steps": onboarding_steps,
        "onboarding_complete": all(step["complete"] for step in onboarding_steps),
    }


def _lead_stage_label(status):
    return dict(LEAD_STATUS_FLOW).get(status, status.replace("_", " ").title())


def _lead_actions(status):
    if status == "shortlisting":
        return [("contacted", "Mark Contacted"), ("quoted", "Mark Quoted"), ("archived", "Archive")]
    if status == "contacted":
        return [("quoted", "Mark Quoted"), ("won", "Mark Won"), ("archived", "Archive")]
    if status == "quoted":
        return [("won", "Mark Won"), ("archived", "Archive")]
    if status == "won":
        return [("archived", "Archive")]
    return [("shortlisting", "Reopen")]


def _project_status_label(status):
    return status.replace("_", " ").title() if status else "Shortlisting"


def _build_provider_leads():
    provider_user = _get_provider_user()
    provider_service_slugs = _provider_service_slugs(provider_user)
    provider_travel_postcodes = _provider_travel_postcodes(provider_user)
    db_projects = Project.query.order_by(Project.updated_at.desc()).all()
    if db_projects:
        lead_projects = db_projects
        use_db = True
    else:
        lead_projects = []
        use_db = False

    if not lead_projects:
        from askmarley.services.collaboration import get_projects

        fallback_projects = get_projects(session)
        return [
            {
                "id": project["id"],
                "name": project["name"],
                "customer": "Demo Consumer",
                "status": project["status"].lower(),
                "status_label": project["status"],
                "saved_provider_count": len(project.get("saved_providers", [])),
                "pinboard_count": len(project.get("pinboard_items", [])),
                "latest_note": project.get("timeline", ["Created project"])[-1],
                "chat_url": url_for("consumer.project_chat", project_id=project["id"], viewer="provider"),
                "actions": _lead_actions(project["status"].lower()),
                "source": "demo",
            }
            for project in fallback_projects
        ]

    leads = []
    for project in lead_projects:
        latest_thread = ChatThread.query.filter_by(project_id=project.id).order_by(ChatThread.updated_at.desc()).first()
        latest_message = None
        if latest_thread:
            latest_message = (
                ChatMessage.query.filter_by(thread_id=latest_thread.id)
                .order_by(ChatMessage.id.desc())
                .first()
            )

        match_details = _lead_matches_provider(
            project,
            provider_service_slugs,
            provider_travel_postcodes,
            latest_message=latest_message,
        )

        if not match_details["matches"]:
            continue

        consumer_name = project.user.full_name if project.user else "Consumer"
        status = (project.status or "shortlisting").lower()
        leads.append(
            {
                "id": project.id,
                "name": project.name,
                "customer": consumer_name,
                "status": status,
                "status_label": _project_status_label(status),
                "saved_provider_count": len(project.saved_provider_links),
                "pinboard_count": len(project.pinboard_links),
                "latest_note": latest_message.message if latest_message else "No message yet. Open the project chat to introduce yourself.",
                "chat_url": url_for("consumer.project_chat", project_id=project.id, viewer="provider"),
                "actions": _lead_actions(status),
                "detected_service": _service_label(match_details["detected_service_slug"]) if match_details["detected_service_slug"] else None,
                "lead_postcode": match_details["lead_postcode"],
                "match_reason": "Matches your service area" if match_details["lead_postcode"] or match_details["detected_service_slug"] else "Visible because the lead has not provided enough detail yet",
                "source": "database" if use_db else "session",
            }
        )

    if not leads and not use_db:
        from askmarley.services.collaboration import get_projects

        fallback_projects = get_projects(session)
        for project in fallback_projects:
            fallback_status = project["status"].lower()
            leads.append(
                {
                    "id": project["id"],
                    "name": project["name"],
                    "customer": "Demo Consumer",
                    "status": fallback_status,
                    "status_label": project["status"],
                    "saved_provider_count": len(project.get("saved_providers", [])),
                    "pinboard_count": len(project.get("pinboard_items", [])),
                    "latest_note": project.get("timeline", ["Created project"])[-1],
                    "chat_url": url_for("consumer.project_chat", project_id=project["id"], viewer="provider"),
                    "actions": _lead_actions(fallback_status),
                    "detected_service": None,
                    "lead_postcode": None,
                    "match_reason": "Demo lead until enough project details are available",
                    "source": "demo",
                }
            )

    return leads


def _update_project_status(project_id, status):
    normalized_status = (status or "shortlisting").strip().lower()
    valid_statuses = {value for value, _ in LEAD_STATUS_FLOW}
    if normalized_status not in valid_statuses:
        return False

    project = Project.query.filter_by(id=project_id).first()
    if project:
        project.status = normalized_status
        db.session.commit()
        return True

    from askmarley.services.collaboration import get_projects

    projects = get_projects(session)
    for project in projects:
        if project["id"] == project_id:
            project["status"] = normalized_status.title()
            if "timeline" in project:
                project["timeline"].append(f"Lead status changed to {normalized_status.title()}")
            session.modified = True
            return True
    return False


@provider_bp.get("/dashboard")
@role_required("provider")
def dashboard():
    provider_sub = get_provider_subscription(session)
    provider_profile = _build_provider_profile(provider_sub)
    leads = _build_provider_leads()
    chats = build_provider_chat_summary(session)
    if not chats:
        chats = [
            {
                "customer": "No active project threads yet",
                "latest": "Consumer project chats will appear here once opened.",
                "pinboard_count": 0,
                "provider_unread": 0,
            }
        ]
    return render_template(
        "provider_dashboard.html",
        provider_profile=provider_profile,
        onboarding_steps=provider_profile["onboarding_steps"],
        onboarding_complete=provider_profile["onboarding_complete"],
        leads=leads,
        chats=chats,
    )


@provider_bp.get("/onboarding")
@role_required("provider")
def onboarding():
    provider_sub = get_provider_subscription(session)
    provider_profile = _build_provider_profile(provider_sub)
    return render_template(
        "provider_onboarding.html",
        provider_profile=provider_profile,
        onboarding_steps=provider_profile["onboarding_steps"],
        onboarding_complete=provider_profile["onboarding_complete"],
    )


@provider_bp.post("/leads/<int:project_id>/status")
@role_required("provider")
def update_lead_status(project_id):
    status = request.form.get("status", "shortlisting")
    if _update_project_status(project_id, status):
        flash(f"Lead moved to {status.replace('_', ' ').title()}.", "success")
    else:
        flash("Unable to update that lead.", "error")
    return redirect(url_for("provider.dashboard"))


@provider_bp.route("/subscription", methods=["GET", "POST"])
@role_required("provider")
def subscription():
    if request.method == "POST":
        tier = request.form.get("tier", "basic")
        billing_status = request.form.get("billing_status", "active")
        update_provider_subscription(session, tier, billing_status)
        flash("Provider subscription updated.", "success")
        return redirect(url_for("provider.subscription"))

    provider_sub = get_provider_subscription(session)
    return render_template(
        "provider_subscription.html",
        provider_sub=provider_sub,
        tiers=PROVIDER_TIERS,
        billing_statuses=BILLING_STATUSES,
    )
