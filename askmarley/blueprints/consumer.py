from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, session, url_for
from uuid import uuid4

from askmarley.data import BILLING_STATUSES, CONSUMER_TIERS, CONSUMER_TIER_PRIORITY, PROVIDERS, SERVICE_INTENTS, TIER_PRIORITY
from askmarley.services.auth import get_current_user, role_matches, role_required
from askmarley.services.collaboration import (
    add_pinboard_item,
    add_thread_pin,
    append_chat_message,
    create_project,
    delete_pinboard_item,
    get_all_provider_names,
    get_project_by_id,
    get_projects,
    get_thread,
    mark_thread_read,
    remove_pinboard_image,
    report_thread_message,
    save_provider_to_project,
    update_project_metadata,
)
from askmarley.services.matching import (
    detect_service_details,
    extract_uk_location_code,
    find_matching_providers,
)
from askmarley.services.subscriptions import (
    can_manage_projects,
    get_consumer_subscription,
    update_consumer_subscription,
)
from askmarley.services.stripe_billing import (
    create_billing_portal_session,
    create_consumer_checkout_session,
)
from askmarley.services.transcript import log_concierge_message

consumer_bp = Blueprint("consumer", __name__, url_prefix="/consumer")


CONSUMER_CRM_ROLES = {"consumer", "buyer", "admin", "super_admin"}
ADMIN_ROLES = {"admin", "super_admin"}


CHAT_COMMANDS_NEW_THREAD = {
    "new chat",
    "start new chat",
    "new thread",
    "reset chat",
}

CHAT_ACKNOWLEDGEMENTS = {
    "ok",
    "okay",
    "thanks",
    "thank you",
    "great",
    "perfect",
    "nice",
    "cool",
    "alright",
}

CHAT_GREETINGS = {
    "hi",
    "hello",
    "hey",
    "hiya",
    "good morning",
    "good afternoon",
    "good evening",
}

CHAT_CONFIRM_YES = {
    "yes",
    "y",
    "yeah",
    "yep",
    "correct",
    "right",
    "that is right",
    "sure",
}

CHAT_CONFIRM_NO = {
    "no",
    "n",
    "nope",
    "nah",
    "wrong",
    "not right",
    "not correct",
}

QUICK_INTENT_MESSAGES = {
    "emergency-plumber": "I have a leaky pipe",
    "cleaner": "I need a cleaner",
    "electrician": "I need an electrician",
    "roofer": "I need a roofer",
    "wedding-planner": "I need a wedding planner",
    "gardener": "I need a gardener",
    "dog-walker": "I need a dog walker",
}


def _welcome_message():
    return "Hi, I'm Marley. Tell me what you need and I will match you with the right local service."


def _has_consumer_crm_access(user):
    if not user:
        return False
    return role_matches(user.get("role"), *CONSUMER_CRM_ROLES)


def _is_admin_request():
    user = get_current_user()
    if not user:
        return False
    return role_matches(user.get("role"), *ADMIN_ROLES)


def _default_chat_state():
    return {
        "step": "service",
        "service_slug": None,
        "options": [],
        "confidence": 0.0,
    }


def _create_chat_thread():
    welcome = _welcome_message()
    return {
        "id": uuid4().hex[:12],
        "title": "New chat",
        "chat_log": [{"sender": "marley", "text": welcome}],
        "chat_state": _default_chat_state(),
        "recommendations": [],
    }


def _sanitize_chat_threads(raw_threads):
    threads = []
    for thread in raw_threads or []:
        if not isinstance(thread, dict):
            continue
        thread_id = thread.get("id") or uuid4().hex[:12]
        title = thread.get("title") or "New chat"
        chat_log = thread.get("chat_log") or []
        chat_state = thread.get("chat_state") or _default_chat_state()
        recommendations = thread.get("recommendations") or []

        if not chat_log:
            chat_log = [{"sender": "marley", "text": _welcome_message()}]

        threads.append(
            {
                "id": thread_id,
                "title": title,
                "chat_log": chat_log,
                "chat_state": chat_state,
                "recommendations": recommendations,
            }
        )

    return threads


def _ensure_chat_threads():
    threads = _sanitize_chat_threads(session.get("chat_threads", []))

    # One-time migration for legacy single-thread session fields.
    if not threads:
        legacy_log = session.get("chat_log", [])
        legacy_state = session.get("chat_state", _default_chat_state())
        legacy_recs = session.get("recommendations", [])

        if legacy_log:
            migrated = _create_chat_thread()
            migrated["title"] = "Previous chat"
            migrated["chat_log"] = legacy_log
            migrated["chat_state"] = legacy_state
            migrated["recommendations"] = legacy_recs
            threads.append(migrated)

        if not threads:
            threads.append(_create_chat_thread())

    session["chat_threads"] = threads
    if session.get("active_chat_thread_id") not in {thread["id"] for thread in threads}:
        session["active_chat_thread_id"] = threads[0]["id"]
    return threads


def _history_preview(chat_log):
    for msg in reversed(chat_log):
        if msg.get("sender") == "user" and msg.get("text"):
            text = msg["text"].strip()
            return text if len(text) <= 45 else f"{text[:42]}..."
    return "No message yet"


def _is_acknowledgement(message):
    normalized = (message or "").strip().lower()
    return normalized in CHAT_ACKNOWLEDGEMENTS


def _is_greeting(message):
    normalized = (message or "").strip().lower()
    return normalized in CHAT_GREETINGS


def _is_service_confirmed(message):
    normalized = (message or "").strip().lower()
    return normalized in CHAT_CONFIRM_YES


def _is_service_rejected(message):
    normalized = (message or "").strip().lower()
    return normalized in CHAT_CONFIRM_NO


@consumer_bp.route("/chat", methods=["GET", "POST"])
def chat():
    current_user = get_current_user()
    if not current_user:
        return render_template(
            "consumer_chat.html",
            auth_gate_required=True,
            login_next=url_for("consumer.chat"),
        )

    if not _has_consumer_crm_access(current_user):
        flash("Your account does not have access to that area.", "error")
        return redirect(url_for("main.home"))

    chat_threads = _ensure_chat_threads()

    if request.method == "POST" and request.form.get("action") == "delete_chat":
        delete_thread_id = (request.form.get("delete_thread_id") or "").strip()
        existing_count = len(chat_threads)
        remaining_threads = [thread for thread in chat_threads if thread["id"] != delete_thread_id]

        if len(remaining_threads) == existing_count:
            flash("Chat not found.", "warning")
            redirect_thread = session.get("active_chat_thread_id") or chat_threads[0]["id"]
            return redirect(url_for("consumer.chat", thread=redirect_thread))

        if not remaining_threads:
            new_thread = _create_chat_thread()
            remaining_threads = [new_thread]
            session["active_chat_thread_id"] = new_thread["id"]
        else:
            active_thread_id = session.get("active_chat_thread_id")
            valid_ids = {thread["id"] for thread in remaining_threads}
            if active_thread_id not in valid_ids:
                session["active_chat_thread_id"] = remaining_threads[0]["id"]

        session["chat_threads"] = remaining_threads
        session.modified = True
        flash("Chat deleted.", "success")
        return redirect(url_for("consumer.chat", thread=session["active_chat_thread_id"]))

    thread_id = request.args.get("thread") or request.form.get("thread_id") or session.get(
        "active_chat_thread_id"
    )
    active_thread = next((t for t in chat_threads if t["id"] == thread_id), chat_threads[0])
    session["active_chat_thread_id"] = active_thread["id"]

    chat_log = active_thread["chat_log"]
    chat_state = active_thread["chat_state"]

    if request.method == "POST" and request.form.get("action") == "new_chat":
        new_thread = _create_chat_thread()
        chat_threads.insert(0, new_thread)
        session["chat_threads"] = chat_threads
        session["active_chat_thread_id"] = new_thread["id"]
        session.modified = True
        flash("Started a new chat.", "success")
        return redirect(url_for("consumer.chat", thread=new_thread["id"]))

    recommendations = active_thread.get("recommendations", [])

    def send_marley_message(text, detected_service_slug=None, confidence=None):
        active_thread["chat_log"].append({"sender": "marley", "text": text})
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
            if user_message.lower() in CHAT_COMMANDS_NEW_THREAD:
                new_thread = _create_chat_thread()
                chat_threads.insert(0, new_thread)
                session["chat_threads"] = chat_threads
                session["active_chat_thread_id"] = new_thread["id"]
                session.modified = True
                flash("Started a new chat.", "success")
                return redirect(url_for("consumer.chat", thread=new_thread["id"]))

            active_thread["chat_log"].append({"sender": "user", "text": user_message})
            if active_thread.get("title") == "New chat":
                active_thread["title"] = (
                    user_message if len(user_message) <= 45 else f"{user_message[:42]}..."
                )
            log_concierge_message(session, "user", user_message)

            if chat_state["step"] == "service":
                detected = detect_service_details(user_message)
                service_slug = detected["service_slug"]

                if service_slug is None:
                    if _is_greeting(user_message):
                        send_marley_message(
                            "Hi. Tell me what needs doing and your UK postcode when ready, "
                            "for example: 'need a cleaner in SW1A 1AA'."
                        )
                    elif _is_acknowledgement(user_message):
                        if recommendations:
                            send_marley_message(
                                "Great. You already have provider recommendations in the panel. "
                                "Tell me another service and postcode anytime if you want a new match."
                            )
                        else:
                            send_marley_message(
                                "No problem. Share your service need and postcode when you're ready, "
                                "for example: 'leaking pipe in SW1A 1AA'."
                            )
                    else:
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
                    chat_state["step"] = "confirm_service"
                    chat_state["options"] = []
                    chat_state["confidence"] = detected["confidence"]
                    service_name = SERVICE_INTENTS[service_slug]["name"]
                    send_marley_message(
                        (
                            f"Perfect. It sounds like you need {service_name} "
                            f"(confidence {detected['confidence']:.0%}). "
                            "Is that correct? Reply yes or no."
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
                    chat_state["step"] = "confirm_service"
                    chat_state["options"] = []
                    chat_state["confidence"] = chat_state.get("confidence", 0.0)
                    service_name = SERVICE_INTENTS[chosen_slug]["name"]
                    send_marley_message(
                        f"Great, {service_name} selected. Is that correct? Reply yes or no.",
                        detected_service_slug=chosen_slug,
                    )
                else:
                    send_marley_message(
                        "I still need clarification. Reply with the number or "
                        "service name shown in the previous message."
                    )

            elif chat_state["step"] == "confirm_service":
                current_slug = chat_state.get("service_slug")
                direct_postcode = extract_uk_location_code(user_message)

                if current_slug and direct_postcode:
                    results = find_matching_providers(current_slug, direct_postcode)
                    active_thread["recommendations"] = results
                    chat_state["step"] = "service"
                    chat_state["service_slug"] = None
                    chat_state["options"] = []
                    chat_state["confidence"] = 0.0
                    if results:
                        top_name = results[0]["name"]
                        send_marley_message(
                            (
                                f"Great. I found {len(results)} providers near "
                                f"{direct_postcode}. Top match: {top_name}. You can "
                                "message them below."
                            ),
                            detected_service_slug=current_slug,
                        )
                    else:
                        send_marley_message(
                            "I could not find a local provider for that postcode "
                            "yet. Try another postcode or use manual search.",
                            detected_service_slug=current_slug,
                        )
                else:
                    redetect = detect_service_details(user_message)
                    detected_slug = redetect["service_slug"]

                    if detected_slug and detected_slug != current_slug and not redetect["ambiguous"]:
                        chat_state["service_slug"] = detected_slug
                        chat_state["step"] = "confirm_service"
                        chat_state["options"] = []
                        chat_state["confidence"] = redetect["confidence"]
                        service_name = SERVICE_INTENTS[detected_slug]["name"]
                        send_marley_message(
                            f"No problem, switched to {service_name}. Is that correct? Reply yes or no.",
                            detected_service_slug=detected_slug,
                            confidence=redetect["confidence"],
                        )
                    elif redetect["ambiguous"]:
                        chat_state["step"] = "clarify_service"
                        chat_state["options"] = redetect["options"]
                        chat_state["confidence"] = redetect["confidence"]
                        options_text = ", ".join(
                            f"{index + 1}) {SERVICE_INTENTS[slug]['name']}"
                            for index, slug in enumerate(redetect["options"])
                        )
                        send_marley_message(
                            f"I found a few likely services ({options_text}). Reply with a number or service name.",
                            detected_service_slug=detected_slug,
                            confidence=redetect["confidence"],
                        )
                    elif _is_service_confirmed(user_message):
                        if not current_slug:
                            chat_state["step"] = "service"
                            send_marley_message(
                                "Please tell me what service you need first, for example plumbing, cleaning, or roofing."
                            )
                        else:
                            chat_state["step"] = "postcode"
                            service_name = SERVICE_INTENTS[current_slug]["name"]
                            send_marley_message(
                                f"Great, {service_name} confirmed. Please share your UK postcode.",
                                detected_service_slug=current_slug,
                                confidence=chat_state.get("confidence"),
                            )
                    elif _is_service_rejected(user_message):
                        chat_state["step"] = "service"
                        chat_state["service_slug"] = None
                        chat_state["options"] = []
                        chat_state["confidence"] = 0.0
                        send_marley_message(
                            "Thanks for clarifying. Tell me the service you need and I will match it."
                        )
                    else:
                        send_marley_message(
                            "Please reply yes or no to confirm the service, or tell me the correct service."
                        )

            elif chat_state["step"] == "postcode":
                redetect = detect_service_details(user_message)
                detected_slug = redetect["service_slug"]
                current_slug = chat_state["service_slug"]

                if detected_slug and detected_slug != current_slug and not redetect["ambiguous"]:
                    chat_state["service_slug"] = detected_slug
                    chat_state["step"] = "postcode"
                    chat_state["options"] = []
                    chat_state["confidence"] = redetect["confidence"]
                    service_name = SERVICE_INTENTS[detected_slug]["name"]
                    send_marley_message(
                        f"No problem, switched to {service_name}. Please share your UK postcode or area code (e.g. SW1A).",
                        detected_service_slug=detected_slug,
                        confidence=redetect["confidence"],
                    )
                else:
                    postcode = extract_uk_location_code(user_message)
                    if postcode:
                        service_slug = chat_state["service_slug"]
                        results = find_matching_providers(service_slug, postcode)
                        active_thread["recommendations"] = results
                        chat_state["step"] = "service"
                        chat_state["service_slug"] = None
                        chat_state["options"] = []
                        chat_state["confidence"] = 0.0
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
                            "That postcode format looks wrong. Please include a valid UK "
                            "postcode such as SW1A 1AA, or an area code like SW1A."
                        )

        active_thread["chat_state"] = chat_state
        session["chat_threads"] = chat_threads
        session["active_chat_thread_id"] = active_thread["id"]
        session.modified = True
        return redirect(url_for("consumer.chat", thread=active_thread["id"]))

    history = [
        {
            "id": thread["id"],
            "title": thread.get("title", "New chat"),
            "preview": _history_preview(thread.get("chat_log", [])),
            "is_active": thread["id"] == active_thread["id"],
        }
        for thread in chat_threads
    ]

    return render_template(
        "consumer_chat.html",
        chat_log=active_thread["chat_log"],
        recommendations=recommendations,
        service_intents=SERVICE_INTENTS,
        quick_intent_messages=QUICK_INTENT_MESSAGES,
        tier_priority=TIER_PRIORITY,
        chat_history=history,
        active_thread_id=active_thread["id"],
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


@consumer_bp.get("/providers/<int:provider_id>")
def provider_detail(provider_id):
    provider = next((entry for entry in PROVIDERS if entry["id"] == provider_id), None)
    if not provider:
        flash("Seller not found.", "error")
        return redirect(url_for("consumer.chat"))

    service = SERVICE_INTENTS.get(provider["service_slug"], {})
    # Buyer view should only receive public profile attributes.
    provider_public = {
        "id": provider["id"],
        "name": provider["name"],
        "service_slug": provider["service_slug"],
        "postcodes": provider.get("postcodes", []),
        "verified": bool(provider.get("verified")),
        "marleys_choice": bool(provider.get("marleys_choice")),
    }
    return render_template(
        "consumer_provider_detail.html",
        provider=provider_public,
        service=service,
    )


@consumer_bp.post("/providers/<int:provider_id>/contact")
@role_required("consumer", "admin", "super_admin")
def provider_contact(provider_id):
    provider = next((entry for entry in PROVIDERS if entry["id"] == provider_id), None)
    if not provider:
        flash("Seller not found.", "error")
        return redirect(url_for("consumer.chat"))

    consumer_sub = get_consumer_subscription(session)
    projects = get_projects(session)
    consumer_location = None
    auth_user_id = session.get("auth_user_id")
    if auth_user_id:
        from askmarley.extensions import db
        from askmarley.models import User

        consumer_user = db.session.get(User, auth_user_id)
        if consumer_user and role_matches(consumer_user.role, "consumer"):
            consumer_location = extract_uk_location_code(consumer_user.consumer_postcode or "")

    if consumer_sub["effective_tier"] == "free" and not _is_admin_request():
        flash("Upgrade your plan to contact sellers in project chat.", "warning")
        return redirect(url_for("consumer.subscription"))

    target_project = None
    for project in projects:
        if provider["name"] in project.get("saved_providers", []):
            target_project = project
            break

    if target_project is None:
        if projects:
            target_project = projects[0]
        else:
            if not can_manage_projects(session, len(projects)) and not _is_admin_request():
                flash("You reached your project limit. Upgrade to start a seller chat.", "warning")
                return redirect(url_for("consumer.subscription"))
            target_project = create_project(
                session,
                f"{provider['name']} enquiry",
                service_slug=provider["service_slug"],
                location_code=consumer_location,
            )

        save_provider_to_project(session, target_project["id"], provider["name"])

    update_project_metadata(
        session,
        target_project["id"],
        service_slug=provider["service_slug"],
        location_code=consumer_location,
    )

    flash(f"Chat opened with {provider['name']}.", "success")
    return redirect(
        url_for(
            "consumer.project_chat",
            project_id=target_project["id"],
            viewer="consumer",
        )
    )


@consumer_bp.route("/clipboard", methods=["GET", "POST"])
@role_required("consumer", "admin", "super_admin")
def clipboard():
    consumer_sub = get_consumer_subscription(session)
    user_tier_slug = consumer_sub["effective_tier"]
    user_tier = consumer_sub["plan"]
    projects = get_projects(session)
    consumer_default_postcode = ""
    auth_user_id = session.get("auth_user_id")
    if auth_user_id:
        from askmarley.extensions import db
        from askmarley.models import User

        consumer_user = db.session.get(User, auth_user_id)
        if consumer_user and role_matches(consumer_user.role, "consumer"):
            consumer_default_postcode = consumer_user.consumer_postcode or ""
    total_saved_providers = sum(len(project["saved_providers"]) for project in projects)
    total_pinboard_items = sum(len(project["pinboard_items"]) for project in projects)
    stats = {
        "project_count": len(projects),
        "saved_provider_count": total_saved_providers,
        "pinboard_count": total_pinboard_items,
    }

    if request.method == "POST":
        project_name = request.form.get("project_name", "").strip()
        service_slug = request.form.get("service_slug", "").strip()
        location_code = extract_uk_location_code(request.form.get("location_code", "").strip())
        if not project_name:
            flash("Project name is required.", "error")
        elif service_slug not in SERVICE_INTENTS:
            flash("Choose the service you need for this project.", "error")
        elif not location_code:
            flash("Enter a valid UK postcode or outward code for this project.", "error")
        else:
            if not can_manage_projects(session, len(projects)):
                flash(
                    "You reached your plan limit. Upgrade to create more active projects.",
                    "warning",
                )
            else:
                created = create_project(
                    session,
                    project_name,
                    service_slug=service_slug,
                    location_code=location_code,
                )
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
        service_options=SERVICE_INTENTS,
        consumer_default_postcode=consumer_default_postcode,
        stats=stats,
    )


@consumer_bp.post("/clipboard/<int:project_id>/details")
@role_required("consumer", "admin", "super_admin")
def clipboard_update_project_details(project_id):
    tier = get_consumer_subscription(session)["effective_tier"]
    service_slug = request.form.get("service_slug", "").strip()
    location_code = extract_uk_location_code(request.form.get("location_code", "").strip())

    if service_slug not in SERVICE_INTENTS:
        flash("Choose the service you need for this project.", "error")
    elif not location_code:
        flash("Enter a valid UK postcode or outward code for this project.", "error")
    elif update_project_metadata(session, project_id, service_slug=service_slug, location_code=location_code):
        flash("Project details updated.", "success")
    else:
        flash("Project not found.", "error")

    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.get("/dashboard")
@role_required("consumer", "admin", "super_admin")
def dashboard():
    consumer_sub = get_consumer_subscription(session)
    projects = get_projects(session)

    total_saved_providers = sum(len(project["saved_providers"]) for project in projects)
    total_pinboard_items = sum(len(project["pinboard_items"]) for project in projects)

    stats = {
        "project_count": len(projects),
        "saved_provider_count": total_saved_providers,
        "pinboard_count": total_pinboard_items,
    }

    recent_projects = projects[:4]
    return render_template(
        "consumer_dashboard.html",
        consumer_sub=consumer_sub,
        stats=stats,
        recent_projects=recent_projects,
    )


@consumer_bp.post("/clipboard/<int:project_id>/save-provider")
@role_required("consumer", "admin", "super_admin")
def clipboard_save_provider(project_id):
    provider_name = request.form.get("provider_name", "").strip()
    tier = get_consumer_subscription(session)["effective_tier"]

    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
        flash("Upgrade your plan to save sellers to projects.", "warning")
        return redirect(url_for("consumer.clipboard", tier=tier))

    if not provider_name:
        flash("Choose a seller before saving.", "error")
    elif save_provider_to_project(session, project_id, provider_name):
        flash(f"Saved provider to project: {provider_name}", "success")
    else:
        flash("Project not found.", "error")
    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.post("/clipboard/<int:project_id>/pin")
@role_required("consumer", "admin", "super_admin")
def clipboard_pinboard_add(project_id):
    pin_label = request.form.get("pin_label", "").strip()
    pin_image = request.files.get("pin_image")
    tier = get_consumer_subscription(session)["effective_tier"]

    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
        flash("Upgrade your plan to add pinboard items.", "warning")
        return redirect(url_for("consumer.clipboard", tier=tier))

    if not pin_label:
        flash("Pinboard item cannot be empty.", "error")
    elif add_pinboard_item(session, project_id, pin_label, image_file=pin_image):
        flash("Added item to pinboard." + (" with image" if pin_image else ""), "success")
    else:
        flash("Project not found.", "error")
    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.post("/clipboard/<int:project_id>/pin/<pin_id>/remove-image")
@role_required("consumer", "admin", "super_admin")
def clipboard_pinboard_remove_image(project_id, pin_id):
    tier = get_consumer_subscription(session)["effective_tier"]
    wants_json = "application/json" in (request.headers.get("Accept") or "")

    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
        if wants_json:
            return jsonify({"status": "error", "message": "Upgrade your plan to manage pinboard images."}), 403
        flash("Upgrade your plan to manage pinboard images.", "warning")
        return redirect(url_for("consumer.clipboard", tier=tier))

    pin_identifier = int(pin_id) if str(pin_id).isdigit() else pin_id
    if remove_pinboard_image(session, project_id, pin_identifier):
        if wants_json:
            return jsonify({"status": "ok", "message": "Uploaded image removed from pinboard item."}), 200
        flash("Uploaded image removed from pinboard item.", "success")
    else:
        if wants_json:
            return jsonify({"status": "error", "message": "Unable to remove that image."}), 400
        flash("Unable to remove that image.", "error")

    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.post("/clipboard/<int:project_id>/pin/<pin_id>/delete")
@role_required("consumer", "admin", "super_admin")
def clipboard_pinboard_delete(project_id, pin_id):
    tier = get_consumer_subscription(session)["effective_tier"]
    wants_json = "application/json" in (request.headers.get("Accept") or "")

    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
        if wants_json:
            return jsonify({"status": "error", "message": "Upgrade your plan to manage pinboard items."}), 403
        flash("Upgrade your plan to manage pinboard items.", "warning")
        return redirect(url_for("consumer.clipboard", tier=tier))

    pin_identifier = int(pin_id) if str(pin_id).isdigit() else pin_id
    if delete_pinboard_item(session, project_id, pin_identifier):
        if wants_json:
            return jsonify({"status": "ok", "message": "Pinboard item deleted."}), 200
        flash("Pinboard item deleted.", "success")
    else:
        if wants_json:
            return jsonify({"status": "error", "message": "Unable to delete that pinboard item."}), 400
        flash("Unable to delete that pinboard item.", "error")

    return redirect(url_for("consumer.clipboard", tier=tier))


@consumer_bp.route("/clipboard/<int:project_id>/chat", methods=["GET", "POST"])
@role_required("consumer", "provider", "admin", "super_admin")
def project_chat(project_id):
    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
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


@consumer_bp.post("/clipboard/<int:project_id>/chat/message")
@role_required("consumer", "provider", "admin", "super_admin")
def project_chat_message(project_id):
    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
        return jsonify({"status": "error", "message": "Upgrade your plan to access project collaboration chat."}), 403

    project = get_project_by_id(session, project_id)
    if not project:
        return jsonify({"status": "error", "message": "Project not found."}), 404

    viewer = request.args.get("viewer", "consumer")
    if viewer not in {"consumer", "provider"}:
        viewer = "consumer"

    message = (request.form.get("message") or "").strip()
    if not message:
        return jsonify({"status": "error", "message": "Message cannot be empty."}), 400

    appended = append_chat_message(session, project_id, viewer, message)
    if not appended:
        return jsonify({"status": "error", "message": "Unable to append message."}), 400

    thread = get_thread(session, project_id) or {"messages": []}
    report_index = max(len(thread.get("messages", [])) - 1, 0)

    return jsonify({
        "status": "ok",
        "message": appended,
        "report_index": report_index,
        "viewer": viewer,
    }), 201


@consumer_bp.post("/clipboard/<int:project_id>/chat/pin")
@role_required("consumer", "provider", "admin", "super_admin")
def project_chat_pin(project_id):
    if get_consumer_subscription(session)["effective_tier"] == "free" and not _is_admin_request():
        return jsonify({"status": "error", "message": "Upgrade your plan to access project collaboration chat."}), 403

    project = get_project_by_id(session, project_id)
    if not project:
        return jsonify({"status": "error", "message": "Project not found."}), 404

    pin_label = (request.form.get("pin_label") or "").strip()
    if not pin_label:
        return jsonify({"status": "error", "message": "Pinboard item cannot be empty."}), 400

    add_thread_pin(session, project_id, pin_label)
    return jsonify({"status": "ok", "pin": {"label": pin_label}}), 201


@consumer_bp.post("/clipboard/<int:project_id>/chat/report")
@role_required("consumer", "provider", "admin", "super_admin")
def project_chat_report(project_id):
    viewer = request.args.get("viewer", "consumer")
    reason = request.form.get("reason", "User reported content").strip()
    message_index = int(request.form.get("message_index", "-1"))
    wants_json = "application/json" in (request.headers.get("Accept") or "")

    reported = report_thread_message(
        session,
        project_id=project_id,
        message_index=message_index,
        reporter=viewer,
        reason=reason or "User reported content",
    )
    if wants_json:
        if reported:
            return jsonify({"status": "ok", "message": "Message reported. Admin moderation queue updated."}), 200
        return jsonify({"status": "error", "message": "Unable to report that message."}), 400

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
        pending_tier = request.form.get("pending_tier")
        update_consumer_subscription(session, tier, billing_status, pending_tier=pending_tier)
        flash("Consumer subscription updated.", "success")
        return redirect(url_for("consumer.subscription"))

    consumer_sub = get_consumer_subscription(session)
    return render_template(
        "consumer_subscription.html",
        consumer_sub=consumer_sub,
        tiers=CONSUMER_TIERS,
        consumer_tier_priority=CONSUMER_TIER_PRIORITY,
        billing_statuses=BILLING_STATUSES,
        stripe_enabled=bool(current_app.config.get("STRIPE_SECRET_KEY")),
    )


@consumer_bp.post("/subscription/checkout")
@role_required("consumer")
def subscription_checkout():
    tier = request.form.get("tier", "free")
    consumer_sub = get_consumer_subscription(session)
    current_tier = consumer_sub["selected_tier"]
    current_rank = CONSUMER_TIER_PRIORITY.get(current_tier, 0)
    requested_rank = CONSUMER_TIER_PRIORITY.get(tier, 0)

    if requested_rank < current_rank:
        if consumer_sub["billing_status"] in {"active", "grace"}:
            update_consumer_subscription(session, current_tier, consumer_sub["billing_status"], pending_tier=tier)
            pending_label = CONSUMER_TIERS[tier]["label"]
            flash(
                f"Downgrade confirmed. Your current plan stays active until the billing period ends, then your next renewal switches to {pending_label}.",
                "success",
            )
        else:
            update_consumer_subscription(session, tier, "active")
            flash("Downgrade applied immediately because the current billing period has already ended.", "success")
        return redirect(url_for("consumer.subscription"))

    if tier == "free":
        flash("Free tier does not require checkout.", "warning")
        return redirect(url_for("consumer.subscription"))

    if requested_rank == current_rank:
        flash("You are already on that plan.", "info")
        return redirect(url_for("consumer.subscription"))

    try:
        checkout = create_consumer_checkout_session(
            secret_key=current_app.config.get("STRIPE_SECRET_KEY", ""),
            publishable_key=current_app.config.get("STRIPE_PUBLISHABLE_KEY", ""),
            tier=tier,
            success_url=url_for("consumer.subscription_success", tier=tier, _external=True),
            cancel_url=url_for("consumer.subscription_cancel", _external=True),
            user=session.get("auth_user"),
        )
    except Exception as exc:  # Keep UX clear for config/setup errors.
        flash(f"Unable to start Stripe checkout: {exc}", "error")
        return redirect(url_for("consumer.subscription"))

    return redirect(checkout["url"])


@consumer_bp.post("/subscription/portal")
@role_required("consumer")
def subscription_portal():
    try:
        portal = create_billing_portal_session(
            secret_key=current_app.config.get("STRIPE_SECRET_KEY", ""),
            return_url=(
                current_app.config.get("STRIPE_BILLING_PORTAL_RETURN_URL")
                or url_for("consumer.subscription", _external=True)
            ),
            user=session.get("auth_user"),
        )
    except Exception as exc:
        flash(f"Unable to open billing portal: {exc}", "error")
        return redirect(url_for("consumer.subscription"))

    return redirect(portal["url"])


@consumer_bp.get("/subscription/success")
@role_required("consumer")
def subscription_success():
    tier = request.args.get("tier", "free")
    if tier in CONSUMER_TIERS and tier != "free":
        update_consumer_subscription(session, tier, "active")
    flash("Payment received. Subscription is now active.", "success")
    return redirect(url_for("consumer.subscription"))


@consumer_bp.get("/subscription/cancel")
@role_required("consumer")
def subscription_cancel():
    flash("Checkout canceled. No changes were made to your subscription.", "warning")
    return redirect(url_for("consumer.subscription"))
