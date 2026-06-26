from flask import Blueprint, Response, flash, redirect, render_template, request, session, url_for

from askmarley.services.auth import get_current_user, role_required
from askmarley.services.admin_ops import (
    add_taxonomy_entry,
    add_consumer_note,
    assert_admin_authorized,
    get_consumer_crm_detail,
    get_consumer_registry,
    get_admin_audit_trail,
    get_admin_context,
    get_moderation_cases,
    get_provider_registry,
    get_taxonomy_registry,
    get_taxonomy_versions,
    log_consumer_email,
    override_provider_tier,
    set_consumer_account_disabled,
    set_provider_suspension,
    set_taxonomy_active,
    update_consumer_plan_admin,
    update_moderation_case_status,
    update_taxonomy_entry,
    verify_provider,
)
from askmarley.data import BILLING_STATUSES, CONSUMER_TIERS
from askmarley.services.analytics import build_admin_analytics, build_admin_analytics_csv

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


@admin_bp.get("")
@role_required("admin", "super_admin")
def admin_home():
    return redirect(url_for("admin.dashboard"))


def _safe_admin_return_url():
    return_to = request.form.get("return_to", "").strip()
    if return_to.startswith("/admin/"):
        return return_to
    return url_for("admin.dashboard")


def _selected_provider_names():
    names = [name.strip() for name in request.form.getlist("provider_names") if name.strip()]
    csv_value = request.form.get("provider_names_csv", "")
    if csv_value:
        names.extend([name.strip() for name in csv_value.split(",") if name.strip()])

    deduped = []
    seen = set()
    for name in names:
        key = name.lower()
        if key in seen:
            continue
        deduped.append(name)
        seen.add(key)
    return deduped


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
    elif action in {"verify-provider-bulk", "suspend-provider-bulk", "reactivate-provider-bulk"}:
        provider_names = _selected_provider_names()
        if not provider_names:
            flash("Select at least one provider for bulk update.", "error")
            return redirect(_safe_admin_return_url())

        success_count = 0
        failed_messages = []
        for provider_name in provider_names:
            if action == "verify-provider-bulk":
                ok, message = verify_provider(session, provider_name, reason, actor)
            elif action == "suspend-provider-bulk":
                ok, message = set_provider_suspension(
                    session,
                    provider_name,
                    suspended=True,
                    reason=reason,
                    actor=actor,
                )
            else:
                ok, message = set_provider_suspension(
                    session,
                    provider_name,
                    suspended=False,
                    reason=reason,
                    actor=actor,
                )

            if ok:
                success_count += 1
            else:
                failed_messages.append(message)

        action_label = {
            "verify-provider-bulk": "verified",
            "suspend-provider-bulk": "suspended",
            "reactivate-provider-bulk": "reactivated",
        }[action]
        flash(
            f"Bulk action complete: {success_count} provider(s) {action_label}.",
            "success" if success_count else "error",
        )
        if failed_messages:
            flash("; ".join(failed_messages[:3]), "error")
    elif action == "override-tier-bulk":
        provider_names = _selected_provider_names()
        new_tier = request.form.get("new_tier", "basic")
        if not provider_names:
            flash("Select at least one provider for tier override.", "error")
            return redirect(_safe_admin_return_url())

        success_count = 0
        failed_messages = []
        for provider_name in provider_names:
            ok, message = override_provider_tier(
                session,
                provider_name,
                new_tier,
                reason,
                actor,
            )
            if ok:
                success_count += 1
            else:
                failed_messages.append(message)

        flash(
            f"Bulk tier override complete: {success_count} provider(s) moved to {new_tier.title()}.",
            "success" if success_count else "error",
        )
        if failed_messages:
            flash("; ".join(failed_messages[:3]), "error")
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
    elif action == "disable-consumer-account":
        consumer_id = int(request.form.get("consumer_id", "0"))
        ok, message = set_consumer_account_disabled(session, consumer_id, True, reason, actor)
        flash(message, "warning" if ok else "error")
    elif action == "enable-consumer-account":
        consumer_id = int(request.form.get("consumer_id", "0"))
        ok, message = set_consumer_account_disabled(session, consumer_id, False, reason, actor)
        flash(message, "success" if ok else "error")
    elif action == "update-consumer-plan":
        consumer_id = int(request.form.get("consumer_id", "0"))
        new_tier = request.form.get("new_tier", "free")
        billing_status = request.form.get("billing_status", "active")
        ok, message = update_consumer_plan_admin(
            session,
            consumer_id,
            new_tier,
            billing_status,
            reason,
            actor,
        )
        flash(message, "success" if ok else "error")
    elif action == "send-consumer-email":
        consumer_id = int(request.form.get("consumer_id", "0"))
        subject = request.form.get("subject", "")
        message_body = request.form.get("message", "")
        ok, message = log_consumer_email(session, consumer_id, subject, message_body, actor)
        flash(message, "success" if ok else "error")
    elif action == "add-consumer-note":
        consumer_id = int(request.form.get("consumer_id", "0"))
        note = request.form.get("note", "")
        ok, message = add_consumer_note(session, consumer_id, note, actor)
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


@admin_bp.route("/consumers", methods=["GET", "POST"])
@role_required("admin", "super_admin")
def consumers_page():
    frame = _admin_frame_context("consumers")
    if request.method == "POST":
        return _handle_admin_post(frame["admin_ctx"])

    consumers = get_consumer_registry(session)
    selected_consumer_id = request.args.get("consumer_id", type=int)
    if selected_consumer_id is None and consumers:
        selected_consumer_id = consumers[0]["id"]

    selected_consumer = (
        get_consumer_crm_detail(session, selected_consumer_id)
        if selected_consumer_id is not None
        else None
    )

    return render_template(
        "admin_consumers.html",
        consumers=consumers,
        selected_consumer=selected_consumer,
        consumer_tiers=CONSUMER_TIERS,
        billing_statuses=BILLING_STATUSES,
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
