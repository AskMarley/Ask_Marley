from datetime import datetime, timezone
import os
from pathlib import Path
from werkzeug.utils import secure_filename

from askmarley.data import PROVIDERS
from askmarley.services.admin_ops import create_moderation_case
from askmarley.extensions import db
from askmarley.models import (
    ChatMessage,
    ChatThread,
    ChatThreadPin,
    Project,
    ProjectPinboardItem,
    ProjectSavedProvider,
    User,
)

FLAGGED_TERMS = {"scam", "abuse", "idiot", "fraud", "threat"}
ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
UPLOAD_FOLDER = Path(__file__).resolve().parents[2] / "static" / "uploads"


def _ensure_upload_dir():
    """Create upload directory if it doesn't exist."""
    UPLOAD_FOLDER.mkdir(parents=True, exist_ok=True)


def _default_projects():
    return [
        {
            "id": 1,
            "name": "Kitchen Renovation",
            "status": "In progress",
            "service_slug": "emergency-plumber",
            "location_code": "SW1A",
            "saved_providers": ["Royal Flow Plumbing", "Albion Spark Works"],
            "pinboard_items": ["Floor plan v3", "Budget estimate", "Sink leak photo"],
            "timeline": ["Created project", "Saved first providers"],
        },
        {
            "id": 2,
            "name": "Move-out Deep Clean",
            "status": "Shortlisting",
            "service_slug": "cleaner",
            "location_code": "SE1",
            "saved_providers": ["North Star Domestic Care"],
            "pinboard_items": ["Inventory checklist", "Before photos"],
            "timeline": ["Created project", "Pinned inventory checklist"],
        },
    ]


def _get_persistent_consumer(session):
    user_id = session.get("auth_user_id")
    if not user_id:
        return None

    user = db.session.get(User, user_id)
    if not user or user.role != "consumer":
        return None
    return user


def _project_to_dict(project):
    saved_providers = [item.provider_name for item in project.saved_provider_links]
    pinboard_items = [
        {"label": item.label, "image": item.image_path}
        if item.image_path
        else item.label
        for item in project.pinboard_links
    ]
    timeline = ["Created project"]
    if saved_providers:
        timeline.append(f"Saved providers: {len(saved_providers)}")
    if pinboard_items:
        timeline.append(f"Pinned items: {len(pinboard_items)}")

    return {
        "id": project.id,
        "name": project.name,
        "status": project.status,
        "service_slug": project.service_slug,
        "location_code": project.location_code,
        "saved_providers": saved_providers,
        "pinboard_items": pinboard_items,
        "timeline": timeline,
    }


def get_projects(session):
    consumer = _get_persistent_consumer(session)
    if consumer:
        projects = (
            Project.query.filter_by(user_id=consumer.id)
            .order_by(Project.created_at.desc())
            .all()
        )
        return [_project_to_dict(project) for project in projects]

    projects = session.setdefault("clipboard_projects", _default_projects())
    session.modified = True
    return projects


def get_project_by_id(session, project_id):
    consumer = _get_persistent_consumer(session)
    if consumer:
        project = Project.query.filter_by(id=project_id, user_id=consumer.id).first()
        return _project_to_dict(project) if project else None

    for project in get_projects(session):
        if project["id"] == project_id:
            return project
    return None


def create_project(session, project_name, service_slug=None, location_code=None):
    consumer = _get_persistent_consumer(session)
    if consumer:
        new_project = Project(
            user_id=consumer.id,
            name=project_name,
            status="Shortlisting",
            service_slug=service_slug,
            location_code=location_code,
        )
        db.session.add(new_project)
        db.session.commit()
        return _project_to_dict(new_project)

    projects = get_projects(session)
    next_id = max((project["id"] for project in projects), default=0) + 1
    new_project = {
        "id": next_id,
        "name": project_name,
        "status": "Shortlisting",
        "service_slug": service_slug,
        "location_code": location_code,
        "saved_providers": [],
        "pinboard_items": [],
        "timeline": ["Created project"],
    }
    projects.append(new_project)
    session["clipboard_projects"] = projects
    session.modified = True
    return new_project


def save_provider_to_project(session, project_id, provider_name):
    consumer = _get_persistent_consumer(session)
    if consumer:
        project = Project.query.filter_by(id=project_id, user_id=consumer.id).first()
        if not project:
            return False

        exists = ProjectSavedProvider.query.filter_by(
            project_id=project.id,
            provider_name=provider_name,
        ).first()
        if exists:
            return True

        db.session.add(
            ProjectSavedProvider(
                project_id=project.id,
                provider_name=provider_name,
            )
        )
        db.session.commit()
        return True

    project = get_project_by_id(session, project_id)
    if not project:
        return False

    if provider_name not in project["saved_providers"]:
        project["saved_providers"].append(provider_name)
        project["timeline"].append(f"Saved provider: {provider_name}")
        session.modified = True
    return True


def update_project_metadata(session, project_id, service_slug=None, location_code=None):
    consumer = _get_persistent_consumer(session)
    if consumer:
        project = Project.query.filter_by(id=project_id, user_id=consumer.id).first()
        if not project:
            return False

        project.service_slug = service_slug or project.service_slug
        project.location_code = location_code or project.location_code
        db.session.commit()
        return True

    project = get_project_by_id(session, project_id)
    if not project:
        return False

    if service_slug:
        project["service_slug"] = service_slug
    if location_code:
        project["location_code"] = location_code
    session.modified = True
    return True


def add_pinboard_item(session, project_id, item_label, image_file=None):
    """Add a pinboard item with optional image."""
    image_path = None
    
    if image_file:
        image_path = save_pinboard_image(project_id, image_file)
    
    consumer = _get_persistent_consumer(session)
    if consumer:
        project = Project.query.filter_by(id=project_id, user_id=consumer.id).first()
        if not project:
            return False

        db.session.add(
            ProjectPinboardItem(
                project_id=project.id,
                label=item_label,
                image_path=image_path,
            )
        )
        db.session.commit()
        return True

    project = get_project_by_id(session, project_id)
    if not project:
        return False

    # For session-based storage, store as dict with image reference
    project["pinboard_items"].append({
        "label": item_label,
        "image": image_path
    } if image_path else item_label)
    project["timeline"].append(f"Pinned: {item_label}")
    session.modified = True
    return True


def save_pinboard_image(project_id, image_file):
    """Save an uploaded image to the uploads folder and return the relative path."""
    if not image_file or image_file.filename == "":
        return None
    
    _ensure_upload_dir()
    
    filename = secure_filename(image_file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    
    if ext not in ALLOWED_UPLOAD_EXTENSIONS:
        return None
    
    # Create a unique filename with project ID to avoid conflicts
    import uuid
    unique_name = f"pin_{project_id}_{uuid.uuid4().hex[:8]}_{filename}"
    filepath = UPLOAD_FOLDER / unique_name
    
    try:
        image_file.save(str(filepath))
        # Return the relative path for use in HTML
        return f"/static/uploads/{unique_name}"
    except Exception as e:
        print(f"Error saving pinboard image: {e}")
        return None


def get_all_provider_names():
    return sorted({provider["name"] for provider in PROVIDERS})


def get_thread(session, project_id):
    consumer = _get_persistent_consumer(session)
    if consumer:
        project = Project.query.filter_by(id=project_id, user_id=consumer.id).first()
        if not project:
            return None

        thread = ChatThread.query.filter_by(
            project_id=project.id,
            consumer_user_id=consumer.id,
        ).first()
        if not thread:
            thread = ChatThread(
                project_id=project.id,
                consumer_user_id=consumer.id,
                provider_id=None,
            )
            db.session.add(thread)
            db.session.flush()
            db.session.add(
                ChatMessage(
                    thread_id=thread.id,
                    sender_type="marley",
                    message="Thread opened. Use this space to coordinate updates and quotes.",
                    flagged=False,
                )
            )
            db.session.commit()

        messages = (
            ChatMessage.query.filter_by(thread_id=thread.id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        pinboard = [pin.label for pin in ChatThreadPin.query.filter_by(thread_id=thread.id).all()]
        return {
            "messages": [
                {
                    "sender": msg.sender_type,
                    "text": msg.message,
                    "timestamp": msg.created_at.isoformat(timespec="seconds"),
                    "flagged": msg.flagged,
                    "read_by": ["consumer", "provider"],
                }
                for msg in messages
            ],
            "pinboard": pinboard,
            "notifications": {"consumer": 0, "provider": 0},
            "thread_id": thread.id,
        }

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
    consumer = _get_persistent_consumer(session)
    if consumer:
        thread = get_thread(session, project_id)
        if not thread:
            return None

        lowered = text.lower()
        flagged = any(term in lowered for term in FLAGGED_TERMS)
        db.session.add(
            ChatMessage(
                thread_id=thread["thread_id"],
                sender_type=sender,
                message=text,
                flagged=flagged,
            )
        )
        db.session.commit()

        if flagged:
            create_moderation_case(
                session,
                reason="Potential abusive language detected",
                participants=f"Project #{project_id} consumer/provider thread",
                severity="high",
                source="automated-detection",
                reported_by="system",
            )

        return {
            "sender": sender,
            "text": text,
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "flagged": flagged,
            "read_by": [sender],
        }

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
    consumer = _get_persistent_consumer(session)
    if consumer:
        return

    thread = get_thread(session, project_id)
    for message in thread["messages"]:
        if viewer not in message["read_by"]:
            message["read_by"].append(viewer)
    thread["notifications"][viewer] = 0
    session.modified = True


def add_thread_pin(session, project_id, item_label):
    consumer = _get_persistent_consumer(session)
    if consumer:
        thread = get_thread(session, project_id)
        if not thread:
            return
        db.session.add(
            ChatThreadPin(
                thread_id=thread["thread_id"],
                label=item_label,
            )
        )
        db.session.commit()
        return

    thread = get_thread(session, project_id)
    thread["pinboard"].append(item_label)
    session.modified = True


def report_thread_message(session, project_id, message_index, reporter, reason):
    consumer = _get_persistent_consumer(session)
    if consumer:
        thread = get_thread(session, project_id)
        if not thread:
            return False

        messages = (
            ChatMessage.query.filter_by(thread_id=thread["thread_id"])
            .order_by(ChatMessage.id.asc())
            .all()
        )
        if message_index < 0 or message_index >= len(messages):
            return False

        flagged_message = messages[message_index]
        flagged_message.flagged = True
        db.session.commit()
        create_moderation_case(
            session,
            reason=reason,
            participants=f"Project #{project_id} consumer/provider thread",
            severity="medium",
            source="user-report",
            reported_by=reporter,
        )
        return True

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
    provider_user_id = session.get("auth_user_id")
    provider_user = db.session.get(User, provider_user_id) if provider_user_id else None
    if provider_user and provider_user.role in {"provider", "seller"}:
        summaries = []
        threads = ChatThread.query.order_by(ChatThread.updated_at.desc()).all()
        for thread in threads:
            project = db.session.get(Project, thread.project_id)
            if not project:
                continue
            latest = (
                ChatMessage.query.filter_by(thread_id=thread.id)
                .order_by(ChatMessage.id.desc())
                .first()
            )
            if not latest:
                continue
            pin_count = ChatThreadPin.query.filter_by(thread_id=thread.id).count()
            summaries.append(
                {
                    "customer": project.name,
                    "latest": latest.message,
                    "pinboard_count": pin_count,
                    "provider_unread": 0,
                }
            )
        return summaries

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
