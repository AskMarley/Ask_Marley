from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from askmarley.services.auth import get_current_user, role_required
from askmarley.services.admin_ops import (
    add_taxonomy_entry,
    assert_admin_authorized,
    get_admin_audit_trail,
    get_admin_context,
    get_moderation_cases,
    get_provider_registry,
    get_taxonomy_registry,
    get_taxonomy_versions,
    override_provider_tier,
    set_provider_suspension,
    set_taxonomy_active,
    update_moderation_case_status,
    update_taxonomy_entry,
    verify_provider,
)
from askmarley.services.analytics import build_admin_analytics, build_admin_analytics_csv

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _safe_admin_return_url():
    return_to = request.form.get("return_to", "").strip()
    if return_to.startswith("/admin/"):
        return return_to
    return url_for("admin.dashboard")


def _handle_admin_post(admin_ctx):
    if not assert_admin_authorized(admin_ctx):
        flash("You are not authorized for admin actions.", "error")
        return redirect(url_for("admin.dashboard"))

    action = request.form.get("action", "")
    reason = request.form.get("reason", "Admin update").strip() or "Admin update"
    actor = admin_ctx.get("name", "Unknown admin")

    if action == "verify-provider":
        provider_name = request.form.get("provider_name", "Unknown provider")
        ok, message = verify_provider(session, provider_name, reason, actor)
        flash(message, "success" if ok else "error")
    elif action == "override-tier":
        provider_name = request.form.get("provider_name", "Unknown provider")
        new_tier = request.form.get("new_tier", "basic")
        ok, message = override_provider_tier(
            session,
            provider_name,
            new_tier,
            reason,
            actor,
        )
        flash(message, "success" if ok else "error")
    elif action == "ban-provider":
        provider_name = request.form.get("provider_name", "Unknown provider")
        ok, message = set_provider_suspension(
            session,
            provider_name,
            suspended=True,
            reason=reason,
            actor=actor,
        )
        flash(message, "warning" if ok else "error")
    elif action == "reactivate-provider":
        provider_name = request.form.get("provider_name", "Unknown provider")
        ok, message = set_provider_suspension(
            session,
            provider_name,
            suspended=False,
            reason=reason,
            actor=actor,
        )
        flash(message, "success" if ok else "error")
    elif action == "add-taxonomy":
        category_path = request.form.get("category_path", "").strip()
        ok, message = add_taxonomy_entry(session, category_path, reason, actor)
        if not ok and message == "Taxonomy path already exists.":
            ok = True
            message = f"Category added: {category_path}"
        flash(message, "success" if ok else "error")
    elif action == "edit-taxonomy":
        entry_id = int(request.form.get("entry_id", "0"))
        category_path = request.form.get("category_path", "").strip()
        ok, message = update_taxonomy_entry(session, entry_id, category_path, reason, actor)
        flash(message, "success" if ok else "error")
    elif action == "deprecate-taxonomy":
        entry_id = int(request.form.get("entry_id", "0"))
        ok, message = set_taxonomy_active(session, entry_id, active=False, reason=reason, actor=actor)
        flash(message, "warning" if ok else "error")
    elif action == "reactivate-taxonomy":
        entry_id = int(request.form.get("entry_id", "0"))
        ok, message = set_taxonomy_active(session, entry_id, active=True, reason=reason, actor=actor)
        flash(message, "success" if ok else "error")
    elif action == "moderation-status":
        case_id = request.form.get("case_id", "")
        new_status = request.form.get("new_status", "open")
        ok, message = update_moderation_case_status(session, case_id, new_status)
        flash(message, "success" if ok else "error")

    return redirect(_safe_admin_return_url())


def _admin_frame_context(active_page):
    current_user = get_current_user()
    admin_ctx = get_admin_context(session, current_user)
    analytics = build_admin_analytics(session)
    return {
        "admin_ctx": admin_ctx,
        "analytics": analytics,
        "active_page": active_page,
    }


@admin_bp.route("/dashboard", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def dashboard():
    frame = _admin_frame_context("overview")
    if request.method == "POST":
        return _handle_admin_post(frame["admin_ctx"])

    return render_template(
        "admin_overview.html",
        provider_signups=get_provider_registry(session),
        flagged_chats=get_moderation_cases(session),
        taxonomy=get_taxonomy_registry(session),
        taxonomy_versions=get_taxonomy_versions(session),
        audit_trail=get_admin_audit_trail(session),
        moderation_statuses=["open", "reviewing", "resolved", "dismissed"],
        **frame,
    )


@admin_bp.route("/providers", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def providers_page():
    frame = _admin_frame_context("providers")
    if request.method == "POST":
        return _handle_admin_post(frame["admin_ctx"])

    return render_template(
        "admin_providers.html",
        provider_signups=get_provider_registry(session),
        audit_trail=get_admin_audit_trail(session),
        **frame,
    )


@admin_bp.route("/moderation", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def moderation_page():
    frame = _admin_frame_context("moderation")
    if request.method == "POST":
        return _handle_admin_post(frame["admin_ctx"])

    return render_template(
        "admin_moderation.html",
        flagged_chats=get_moderation_cases(session),
        moderation_statuses=["open", "reviewing", "resolved", "dismissed"],
        **frame,
    )


@admin_bp.route("/taxonomy", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def taxonomy_page():
    frame = _admin_frame_context("taxonomy")
    if request.method == "POST":
        return _handle_admin_post(frame["admin_ctx"])

    return render_template(
        "admin_taxonomy.html",
        taxonomy=get_taxonomy_registry(session),
        taxonomy_versions=get_taxonomy_versions(session),
        **frame,
    )


@admin_bp.get("/audit")
@role_required("admin", "super_admin")
def audit_page():
    frame = _admin_frame_context("audit")
    return render_template(
        "admin_audit.html",
        audit_trail=get_admin_audit_trail(session),
        **frame,
    )


@admin_bp.get("/analytics/export.csv")
@role_required("admin", "super_admin")
def export_analytics_csv():
    csv_payload = build_admin_analytics_csv(session)
    return Response(
        csv_payload,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=askmarley-analytics.csv"},
    )
