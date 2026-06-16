from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from askmarley.data import BILLING_STATUSES, CONSUMER_TIERS, SERVICE_INTENTS, TIER_PRIORITY
from askmarley.services.auth import role_required
from askmarley.services.collaboration import (
    add_pinboard_item,
    add_thread_pin,
    append_chat_message,
    create_project,
    get_all_provider_names,
    get_project_by_id,
    get_projects,
    get_thread,
    mark_thread_read,
    report_thread_message,
    save_provider_to_project,
)
from askmarley.services.matching import (
    detect_service_details,
    find_matching_providers,
    is_valid_uk_postcode,
    normalize_uk_postcode,
)
from askmarley.services.subscriptions import (
    can_manage_projects,
    get_consumer_subscription,
    update_consumer_subscription,
)
from askmarley.services.transcript import log_concierge_message

consumer_bp = Blueprint("consumer", __name__, url_prefix="/consumer")


@consumer_bp.route("/chat", methods=["GET", "POST"])
def chat():
    chat_log = session.setdefault("chat_log", [])
    if not chat_log:
        welcome = (
            "Hi, I'm Marley. Tell me what you need and I will match you "
            "with the right local service."
        )
        chat_log.append({"sender": "marley", "text": welcome})
        log_concierge_message(session, "marley", welcome)

    chat_state = session.setdefault(
        "chat_state",
        {
            "step": "service",
            "service_slug": None,
            "options": [],
            "confidence": 0.0,
        },
    )
    recommendations = session.get("recommendations", [])

    def send_marley_message(text, detected_service_slug=None, confidence=None):
        chat_log.append({"sender": "marley", "text": text})
        log_concierge_message(
            session,
            "marley",
            text,
            detected_service_slug=detected_service_slug,
            confidence=confidence,
        )

    if request.method == "POST":
        user_message = request.form.get("message", "").strip()
        if user_message:
            chat_log.append({"sender": "user", "text": user_message})
            log_concierge_message(session, "user", user_message)

            if chat_state["step"] == "service":
                detected = detect_service_details(user_message)
                service_slug = detected["service_slug"]

                if service_slug is None:
                    send_marley_message(
                        "I could not map that yet. Try details like leak, "
                        "wiring, cleaning, or wedding planning."
                    )
                elif detected["ambiguous"]:
                    chat_state["step"] = "clarify_service"
                    chat_state["options"] = detected["options"]
                    chat_state["confidence"] = detected["confidence"]
                    options_text = ", ".join(
                        f"{index + 1}) {SERVICE_INTENTS[slug]['name']}"
                        for index, slug in enumerate(detected["options"])
                    )
                    send_marley_message(
                        f"I found a few likely services ({options_text}). "
                        "Reply with a number or service name.",
                        detected_service_slug=service_slug,
                        confidence=detected["confidence"],
                    )
                else:
                    chat_state["service_slug"] = service_slug
                    chat_state["step"] = "postcode"
                    chat_state["options"] = []
                    chat_state["confidence"] = detected["confidence"]
                    service_name = SERVICE_INTENTS[service_slug]["name"]
                    send_marley_message(
                        (
                            f"Perfect. It sounds like you need {service_name} "
                            f"(confidence {detected['confidence']:.0%}). "
                            "Please share your UK postcode."
                        ),
                        detected_service_slug=service_slug,
                        confidence=detected["confidence"],
                    )

            elif chat_state["step"] == "clarify_service":
                chosen_slug = None
                options = chat_state.get("options", [])

                if user_message.isdigit():
                    idx = int(user_message) - 1
                    if 0 <= idx < len(options):
                        chosen_slug = options[idx]
                else:
                    lowered = user_message.lower()
                    for slug in options:
                        if lowered in slug or lowered in SERVICE_INTENTS[slug]["name"].lower():
                            chosen_slug = slug
                            break

                if not chosen_slug:
                    redetect = detect_service_details(user_message)
                    if redetect["service_slug"] and not redetect["ambiguous"]:
                        chosen_slug = redetect["service_slug"]

                if chosen_slug:
                    chat_state["service_slug"] = chosen_slug
                    chat_state["step"] = "postcode"
                    chat_state["options"] = []
                    service_name = SERVICE_INTENTS[chosen_slug]["name"]
                    send_marley_message(
                        f"Great, {service_name} selected. Please share your UK postcode.",
                        detected_service_slug=chosen_slug,
                    )
                else:
                    send_marley_message(
                        "I still need clarification. Reply with the number or "
                        "service name shown in the previous message."
                    )

            elif chat_state["step"] == "postcode":
                if is_valid_uk_postcode(user_message):
                    postcode = normalize_uk_postcode(user_message)
                    service_slug = chat_state["service_slug"]
                    results = find_matching_providers(service_slug, postcode)
                    session["recommendations"] = results
                    chat_state["step"] = "service"
                    chat_state["service_slug"] = None
                    chat_state["options"] = []
                    chat_state["confidence"] = 0.0
                    session["chat_state"] = chat_state
                    if results:
                        top_name = results[0]["name"]
                        send_marley_message(
                            (
                                f"Great. I found {len(results)} providers near "
                                f"{postcode}. Top match: {top_name}. You can "
                                "message them below."
                            ),
                            detected_service_slug=service_slug,
                        )
                    else:
                        send_marley_message(
                            "I could not find a local provider for that postcode "
                            "yet. Try another postcode or use manual search.",
                            detected_service_slug=service_slug,
                        )
                else:
                    send_marley_message(
                        "That postcode format looks wrong. Please use a valid UK "
                        "postcode such as SW1A 1AA."
                    )

        session["chat_log"] = chat_log
        session.modified = True
        return redirect(url_for("consumer.chat"))

    return render_template(
        "consumer_chat.html",
        chat_log=chat_log,
        recommendations=recommendations,
        service_intents=SERVICE_INTENTS,
        tier_priority=TIER_PRIORITY,
    )


@consumer_bp.get("/search")
def search():
    query = request.args.get("q", "").strip().lower()
    branch_filter = request.args.get("branch", "all")

    categories = []
    for slug, intent in SERVICE_INTENTS.items():
        top_branch = intent["branch"].split(" > ")[0]
        categories.append(
            {
                "slug": slug,
                "name": intent["name"],
                "branch": intent["branch"],
                "top_branch": top_branch,
            }
        )

    branches = sorted({item["top_branch"] for item in categories})

    filtered = categories
    if branch_filter != "all":
        filtered = [item for item in filtered if item["top_branch"] == branch_filter]

    if query:
        filtered = [
            item
            for item in filtered
            if query in item["name"].lower() or query in item["branch"].lower()
        ]

    return render_template(
        "consumer_search.html",
        categories=filtered,
        branches=branches,
        branch_filter=branch_filter,
        query=query,
    )


@consumer_bp.route("/clipboard", methods=["GET", "POST"])
@role_required("consumer")
def clipboard():
    consumer_sub = get_consumer_subscription(session)
    user_tier_slug = consumer_sub["effective_tier"]
    user_tier = consumer_sub["plan"]
    projects = get_projects(session)

    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        if not project_name:
            flash("Project name is required.", "error")
        else:
            if not can_manage_projects(session, len(projects)):
                flash(
                    "You reached your plan limit. Upgrade to create more active projects.",
                    "warning",
                )
            else:
                created = create_project(session, project_name)
                flash(f"Project created: {created['name']}", "success")
        return redirect(url_for("consumer.clipboard", tier=user_tier_slug))

    over_limit = len(projects) > user_tier["max_projects"]
    return render_template(
        "consumer_clipboard.html",
        projects=projects,
        user_tier=user_tier,
        user_tier_slug=user_tier_slug,
        consumer_tiers=CONSUMER_TIERS,
        over_limit=over_limit,
        all_provider_names=get_all_provider_names(),
        consumer_sub=consumer_sub,
    )


@consumer_bp.post("/clipboard/<int:project_id>/save-provider")
@role_required("consumer")
def clipboard_save_provider(project_id):
    provider_name = request.form.get("provider_name", "").strip()
    tier = get_consumer_subscription(session)["effective_tier"]

    if get_consumer_subscription(session)["effective_tier"] == "free":
        flash("Upgrade your plan to save providers to projects.", "warning")
        return redirect(url_for("consumer.clipboard", tier=tier))

    if not provider_name:
        flash("Choose a provider before saving.", "error")
    elif save_provider_to_project(session, project_id, provider_name):
        flash(f"Saved provider to project: {provider_name}", "success")
    else:
        flash("Project not found.", "error")
    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.post("/clipboard/<int:project_id>/pin")
@role_required("consumer")
def clipboard_pinboard_add(project_id):
    pin_label = request.form.get("pin_label", "").strip()
    tier = get_consumer_subscription(session)["effective_tier"]

    if get_consumer_subscription(session)["effective_tier"] == "free":
        flash("Upgrade your plan to add pinboard items.", "warning")
        return redirect(url_for("consumer.clipboard", tier=tier))

    if not pin_label:
        flash("Pinboard item cannot be empty.", "error")
    elif add_pinboard_item(session, project_id, pin_label):
        flash("Added item to pinboard.", "success")
    else:
        flash("Project not found.", "error")
    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.route("/clipboard/<int:project_id>/chat", methods=["GET", "POST"])
@role_required("consumer", "provider")
def project_chat(project_id):
    if get_consumer_subscription(session)["effective_tier"] == "free":
        flash("Upgrade your plan to access project collaboration chat.", "warning")
        return redirect(url_for("consumer.clipboard"))

    project = get_project_by_id(session, project_id)
    if not project:
        flash("Project not found.", "error")
        return redirect(url_for("consumer.clipboard"))

    viewer = request.args.get("viewer", "consumer")
    if viewer not in {"consumer", "provider"}:
        viewer = "consumer"

    if request.method == "POST":
        message = request.form.get("message", "").strip()
        pin_label = request.form.get("pin_label", "").strip()

        if message:
            append_chat_message(session, project_id, viewer, message)
            flash("Message sent.", "success")
        if pin_label:
            add_thread_pin(session, project_id, pin_label)
            flash("Pinboard item added to thread.", "success")
        return redirect(
            url_for(
                "consumer.project_chat",
                project_id=project_id,
                **{"viewer": viewer},
            )
        )

    thread = get_thread(session, project_id)
    mark_thread_read(session, project_id, viewer)
    return render_template(
        "consumer_project_chat.html",
        project=project,
        thread=thread,
        viewer=viewer,
    )


@consumer_bp.post("/clipboard/<int:project_id>/chat/report")
@role_required("consumer", "provider")
def project_chat_report(project_id):
    viewer = request.args.get("viewer", "consumer")
    reason = request.form.get("reason", "User reported content").strip()
    message_index = int(request.form.get("message_index", "-1"))

    reported = report_thread_message(
        session,
        project_id=project_id,
        message_index=message_index,
        reporter=viewer,
        reason=reason or "User reported content",
    )
    if reported:
        flash("Message reported. Admin moderation queue updated.", "warning")
    else:
        flash("Unable to report that message.", "error")

    return redirect(
        url_for(
            "consumer.project_chat",
            project_id=project_id,
            **{"viewer": viewer},
        )
    )


@consumer_bp.route("/subscription", methods=["GET", "POST"])
@role_required("consumer")
def subscription():
    if request.method == "POST":
        tier = request.form.get("tier", "free")
        billing_status = request.form.get("billing_status", "active")
        update_consumer_subscription(session, tier, billing_status)
        flash("Consumer subscription updated.", "success")
        return redirect(url_for("consumer.subscription"))

    consumer_sub = get_consumer_subscription(session)
    return render_template(
        "consumer_subscription.html",
        consumer_sub=consumer_sub,
        tiers=CONSUMER_TIERS,
        billing_statuses=BILLING_STATUSES,
    )
