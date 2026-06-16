from datetime import datetime, timezone

from askmarley.data import PROVIDERS
from askmarley.services.admin_ops import create_moderation_case

FLAGGED_TERMS = {"scam", "abuse", "idiot", "fraud", "threat"}


def _default_projects():
    return [
        {
            "id": 1,
            "name": "Kitchen Renovation",
            "status": "In progress",
            "saved_providers": ["Royal Flow Plumbing", "Albion Spark Works"],
            "pinboard_items": ["Floor plan v3", "Budget estimate", "Sink leak photo"],
            "timeline": ["Created project", "Saved first providers"],
        },
        {
            "id": 2,
            "name": "Move-out Deep Clean",
            "status": "Shortlisting",
            "saved_providers": ["North Star Domestic Care"],
            "pinboard_items": ["Inventory checklist", "Before photos"],
            "timeline": ["Created project", "Pinned inventory checklist"],
        },
    ]


def get_projects(session):
    projects = session.setdefault("clipboard_projects", _default_projects())
    session.modified = True
    return projects


def get_project_by_id(session, project_id):
    for project in get_projects(session):
        if project["id"] == project_id:
            return project
    return None


def create_project(session, project_name):
    projects = get_projects(session)
    next_id = max((project["id"] for project in projects), default=0) + 1
    new_project = {
        "id": next_id,
        "name": project_name,
        "status": "Shortlisting",
        "saved_providers": [],
        "pinboard_items": [],
        "timeline": ["Created project"],
    }
    projects.append(new_project)
    session["clipboard_projects"] = projects
    session.modified = True
    return new_project


def save_provider_to_project(session, project_id, provider_name):
    project = get_project_by_id(session, project_id)
    if not project:
        return False

    if provider_name not in project["saved_providers"]:
        project["saved_providers"].append(provider_name)
        project["timeline"].append(f"Saved provider: {provider_name}")
        session.modified = True
    return True


def add_pinboard_item(session, project_id, item_label):
    project = get_project_by_id(session, project_id)
    if not project:
        return False

    project["pinboard_items"].append(item_label)
    project["timeline"].append(f"Pinned: {item_label}")
    session.modified = True
    return True


def get_all_provider_names():
    return sorted({provider["name"] for provider in PROVIDERS})


def get_thread(session, project_id):
    threads = session.setdefault("project_threads", {})
    thread = threads.get(str(project_id))
    if thread:
        return thread

    thread = {
        "messages": [
            {
                "sender": "marley",
                "text": "Thread opened. Use this space to coordinate updates and quotes.",
                "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "flagged": False,
                "read_by": ["consumer", "provider"],
            }
        ],
        "pinboard": [],
        "notifications": {"consumer": 0, "provider": 0},
    }
    threads[str(project_id)] = thread
    session["project_threads"] = threads
    session.modified = True
    return thread


def append_chat_message(session, project_id, sender, text):
    thread = get_thread(session, project_id)
    lowered = text.lower()
    flagged = any(term in lowered for term in FLAGGED_TERMS)

    message = {
        "sender": sender,
        "text": text,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "flagged": flagged,
        "read_by": [sender],
    }
    thread["messages"].append(message)

    recipient = "provider" if sender == "consumer" else "consumer"
    thread["notifications"][recipient] = thread["notifications"].get(recipient, 0) + 1

    if flagged:
        create_moderation_case(
            session,
            reason="Potential abusive language detected",
            participants=f"Project #{project_id} consumer/provider thread",
            severity="high",
            source="automated-detection",
            reported_by="system",
        )

    session.modified = True
    return message


def mark_thread_read(session, project_id, viewer):
    thread = get_thread(session, project_id)
    for message in thread["messages"]:
        if viewer not in message["read_by"]:
            message["read_by"].append(viewer)
    thread["notifications"][viewer] = 0
    session.modified = True


def add_thread_pin(session, project_id, item_label):
    thread = get_thread(session, project_id)
    thread["pinboard"].append(item_label)
    session.modified = True


def report_thread_message(session, project_id, message_index, reporter, reason):
    thread = get_thread(session, project_id)
    if message_index < 0 or message_index >= len(thread["messages"]):
        return False

    flagged_message = thread["messages"][message_index]
    flagged_message["flagged"] = True
    create_moderation_case(
        session,
        reason=reason,
        participants=f"Project #{project_id} consumer/provider thread",
        severity="medium",
        source="user-report",
        reported_by=reporter,
    )
    session.modified = True
    return True


def build_provider_chat_summary(session):
    summaries = []
    threads = session.get("project_threads", {})
    projects = {project["id"]: project for project in get_projects(session)}

    for project_id, thread in threads.items():
        if not thread["messages"]:
            continue
        latest = thread["messages"][-1]
        project = projects.get(int(project_id))
        project_name = project["name"] if project else f"Project {project_id}"
        summaries.append(
            {
                "customer": project_name,
                "latest": latest["text"],
                "pinboard_count": len(thread.get("pinboard", [])),
                "provider_unread": thread["notifications"].get("provider", 0),
            }
        )

    return sorted(
        summaries,
        key=lambda item: (item["provider_unread"], item["pinboard_count"]),
        reverse=True,
    )
