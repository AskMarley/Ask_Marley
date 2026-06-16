import secrets

from sqlalchemy.exc import SQLAlchemyError

from askmarley.extensions import db
from askmarley.models import ConciergeMessage, ConciergeSession


def get_or_create_concierge_session(session):
    session_key = session.get("concierge_session_key")
    if not session_key:
        session_key = secrets.token_hex(16)
        session["concierge_session_key"] = session_key

    try:
        concierge_session = ConciergeSession.query.filter_by(session_key=session_key).first()
        if concierge_session:
            return concierge_session

        concierge_session = ConciergeSession(session_key=session_key)
        db.session.add(concierge_session)
        db.session.commit()
        return concierge_session
    except SQLAlchemyError:
        db.session.rollback()
        return None


def log_concierge_message(session, sender, message, detected_service_slug=None, confidence=None):
    concierge_session = get_or_create_concierge_session(session)
    if concierge_session is None:
        return

    entry = ConciergeMessage(
        concierge_session_id=concierge_session.id,
        sender=sender,
        message=message,
        detected_service_slug=detected_service_slug,
        confidence=confidence,
    )
    if detected_service_slug:
        concierge_session.last_service_slug = detected_service_slug

    try:
        db.session.add(entry)
        db.session.commit()
    except SQLAlchemyError:
        db.session.rollback()
