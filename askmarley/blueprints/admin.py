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


@admin_bp.route("/dashboard", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def dashboard():
    current_user = get_current_user()
    admin_ctx = get_admin_context(session, current_user)
    provider_registry = get_provider_registry(session)
    moderation_cases = get_moderation_cases(session)
    taxonomy_registry = get_taxonomy_registry(session)

    if request.method == "POST":
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
        return redirect(url_for("admin.dashboard"))

    analytics = build_admin_analytics(session)
    return render_template(
        "admin_dashboard.html",
        provider_signups=provider_registry,
        admin_ctx=admin_ctx,
        audit_trail=get_admin_audit_trail(session),
        flagged_chats=moderation_cases,
        moderation_statuses=["open", "reviewing", "resolved", "dismissed"],
        taxonomy=taxonomy_registry,
        taxonomy_versions=get_taxonomy_versions(session),
        analytics=analytics,
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
