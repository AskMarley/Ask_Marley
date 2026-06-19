from askmarley.extensions import db
from askmarley.services.security import utc_now


class TimestampMixin:
    created_at = db.Column(db.DateTime, default=utc_now, nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=utc_now,
        onupdate=utc_now,
        nullable=False,
    )


class User(TimestampMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(30), nullable=False, default="consumer")
    consumer_tier = db.Column(db.String(30), nullable=False, default="free")
    password_hash = db.Column(db.String(255), nullable=True)
    # Consumer-specific fields
    consumer_phone = db.Column(db.String(20), nullable=True)
    consumer_postcode = db.Column(db.String(10), nullable=True)
    # Provider-specific fields
    company_name = db.Column(db.String(160), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    business_reg_number = db.Column(db.String(80), nullable=True)
    service_categories = db.Column(db.String(500), nullable=True)  # Comma-separated slugs
    travel_postcodes = db.Column(db.String(255), nullable=True)  # Comma-separated postcodes
    insurance_verified = db.Column(db.Boolean, nullable=False, default=False)
    provider_status = db.Column(db.String(30), nullable=True, default="pending")  # pending, verified, suspended


class Provider(TimestampMixin, db.Model):
    __tablename__ = "providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(140), nullable=False)
    service_slug = db.Column(db.String(80), nullable=False, index=True)
    tier = db.Column(db.String(30), nullable=False, default="basic")
    verified = db.Column(db.Boolean, nullable=False, default=False)
    marleys_choice = db.Column(db.Boolean, nullable=False, default=False)


class ProviderCoverage(TimestampMixin, db.Model):
    __tablename__ = "provider_coverages"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("providers.id"), nullable=False)
    outward_code = db.Column(db.String(8), nullable=False, index=True)

    provider = db.relationship("Provider", backref=db.backref("coverages", lazy=True))


class ServiceCategory(TimestampMixin, db.Model):
    __tablename__ = "service_categories"

    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False)
    name = db.Column(db.String(140), nullable=False)
    branch_path = db.Column(db.String(255), nullable=False)


class Project(TimestampMixin, db.Model):
    __tablename__ = "projects"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    status = db.Column(db.String(40), nullable=False, default="active")

    user = db.relationship("User", backref=db.backref("projects", lazy=True))


class ProjectSavedProvider(TimestampMixin, db.Model):
    __tablename__ = "project_saved_providers"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    provider_name = db.Column(db.String(140), nullable=False)

    project = db.relationship(
        "Project",
        backref=db.backref(
            "saved_provider_links",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )

    __table_args__ = (
        db.UniqueConstraint("project_id", "provider_name", name="uq_project_saved_provider"),
    )


class ProjectPinboardItem(TimestampMixin, db.Model):
    __tablename__ = "project_pinboard_items"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False, index=True)
    label = db.Column(db.String(255), nullable=False)

    project = db.relationship(
        "Project",
        backref=db.backref(
            "pinboard_links",
            lazy=True,
            cascade="all, delete-orphan",
        ),
    )


class ChatThread(TimestampMixin, db.Model):
    __tablename__ = "chat_threads"

    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=False)
    consumer_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    provider_id = db.Column(db.Integer, db.ForeignKey("providers.id"), nullable=True)


class ChatMessage(TimestampMixin, db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("chat_threads.id"), nullable=False)
    sender_type = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    flagged = db.Column(db.Boolean, nullable=False, default=False)


class ChatThreadPin(TimestampMixin, db.Model):
    __tablename__ = "chat_thread_pins"

    id = db.Column(db.Integer, primary_key=True)
    thread_id = db.Column(db.Integer, db.ForeignKey("chat_threads.id"), nullable=False, index=True)
    label = db.Column(db.String(255), nullable=False)

    thread = db.relationship(
        "ChatThread",
        backref=db.backref("pins", lazy=True, cascade="all, delete-orphan"),
    )


class ConciergeSession(TimestampMixin, db.Model):
    __tablename__ = "concierge_sessions"

    id = db.Column(db.Integer, primary_key=True)
    session_key = db.Column(db.String(64), unique=True, nullable=False, index=True)
    last_service_slug = db.Column(db.String(80), nullable=True)


class ConciergeMessage(TimestampMixin, db.Model):
    __tablename__ = "concierge_messages"

    id = db.Column(db.Integer, primary_key=True)
    concierge_session_id = db.Column(
        db.Integer,
        db.ForeignKey("concierge_sessions.id"),
        nullable=False,
        index=True,
    )
    sender = db.Column(db.String(20), nullable=False)
    message = db.Column(db.Text, nullable=False)
    detected_service_slug = db.Column(db.String(80), nullable=True)
    confidence = db.Column(db.Float, nullable=True)

    concierge_session = db.relationship(
        "ConciergeSession",
        backref=db.backref("messages", lazy=True, order_by="ConciergeMessage.id"),
    )


class Subscription(TimestampMixin, db.Model):
    __tablename__ = "subscriptions"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("providers.id"), nullable=True)
    plan_code = db.Column(db.String(40), nullable=False)
    status = db.Column(db.String(30), nullable=False, default="active")


class AdminAuditLog(TimestampMixin, db.Model):
    __tablename__ = "admin_audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    admin_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text, nullable=False)


class TaxonomyEntry(TimestampMixin, db.Model):
    __tablename__ = "taxonomy_entries"

    id = db.Column(db.Integer, primary_key=True)
    branch_path = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
