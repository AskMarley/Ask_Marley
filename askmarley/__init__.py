import click
import os
from pathlib import Path
from flask import Flask
from sqlalchemy import inspect
import sqlalchemy as sa

from askmarley.blueprints.admin import admin_bp
from askmarley.blueprints.auth import auth_bp
from askmarley.blueprints.consumer import consumer_bp
from askmarley.blueprints.main import main_bp
from askmarley.blueprints.provider import provider_bp
from askmarley.extensions import db, migrate
from askmarley.seed import seed_baseline_data
from askmarley.services.auth import ensure_default_users, get_current_user
from askmarley.services.security import (
    enforce_form_limits,
    enforce_rate_limit,
    get_csrf_token,
    security_headers,
    validate_csrf,
)


def _load_local_env():
    """Load key=value pairs from a local .env file for development."""
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and not os.getenv(key):
            os.environ[key] = value


def create_app(config_name=None):
    _load_local_env()
    from askmarley.config import CONFIG_MAP

    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    env_config = (os.getenv("FLASK_ENV") or "development").strip().lower()
    alias_map = {
        "dev": "development",
        "prod": "production",
    }
    selected_config = alias_map.get((config_name or env_config), (config_name or env_config))
    if selected_config not in CONFIG_MAP:
        selected_config = "development"
    app.config.from_object(CONFIG_MAP[selected_config])

    db.init_app(app)
    migrate.init_app(app, db)

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(consumer_bp)
    app.register_blueprint(provider_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def inject_csrf_token():
        current_user = get_current_user()
        return {
            "csrf_token": get_csrf_token,
            "current_user": current_user,
            "is_admin_user": current_user is not None
            and current_user.get("role") in {"admin", "super_admin"},
        }

    @app.before_request
    def apply_security_guards():
        enforce_rate_limit(
            limit=app.config.get("SECURITY_RATE_LIMIT", 120),
            window_seconds=app.config.get("SECURITY_RATE_WINDOW", 60),
        )
        enforce_form_limits()
        validate_csrf()

    @app.after_request
    def apply_security_headers(response):
        return security_headers(response)

    with app.app_context():
        if selected_config in {"development", "testing"}:
            # Keep local/dev bootstrapping simple while production relies on Alembic.
            db.create_all()
            inspector = inspect(db.engine)
            if inspector.has_table("subscriptions"):
                subscription_columns = {column["name"] for column in inspector.get_columns("subscriptions")}
                with db.engine.begin() as connection:
                    if "pending_plan_code" not in subscription_columns:
                        connection.execute(sa.text("ALTER TABLE subscriptions ADD COLUMN pending_plan_code VARCHAR(40)"))
                    if "stripe_customer_id" not in subscription_columns:
                        connection.execute(sa.text("ALTER TABLE subscriptions ADD COLUMN stripe_customer_id VARCHAR(120)"))
                    if "stripe_subscription_id" not in subscription_columns:
                        connection.execute(sa.text("ALTER TABLE subscriptions ADD COLUMN stripe_subscription_id VARCHAR(120)"))
                    if "stripe_price_id" not in subscription_columns:
                        connection.execute(sa.text("ALTER TABLE subscriptions ADD COLUMN stripe_price_id VARCHAR(120)"))
                    if "latest_invoice_id" not in subscription_columns:
                        connection.execute(sa.text("ALTER TABLE subscriptions ADD COLUMN latest_invoice_id VARCHAR(120)"))
                    if "latest_checkout_session_id" not in subscription_columns:
                        connection.execute(sa.text("ALTER TABLE subscriptions ADD COLUMN latest_checkout_session_id VARCHAR(120)"))
            if inspector.has_table("projects"):
                project_columns = {column["name"] for column in inspector.get_columns("projects")}
                with db.engine.begin() as connection:
                    if "service_slug" not in project_columns:
                        connection.execute(sa.text("ALTER TABLE projects ADD COLUMN service_slug VARCHAR(80)"))
                    if "location_code" not in project_columns:
                        connection.execute(sa.text("ALTER TABLE projects ADD COLUMN location_code VARCHAR(12)"))
        inspector = inspect(db.engine)
        if inspector.has_table("users"):
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            with db.engine.begin() as connection:
                if "account_disabled" not in user_columns:
                    connection.execute(sa.text("ALTER TABLE users ADD COLUMN account_disabled BOOLEAN NOT NULL DEFAULT 0"))
                if "account_disabled_reason" not in user_columns:
                    connection.execute(sa.text("ALTER TABLE users ADD COLUMN account_disabled_reason VARCHAR(255)"))
            inspector = inspect(db.engine)
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            required_columns = {
                "password_hash",
                "company_name",
                "phone",
                "business_reg_number",
                "service_categories",
                "travel_postcodes",
                "insurance_verified",
                "provider_status",
                "consumer_phone",
                "consumer_postcode",
                "account_disabled",
                "account_disabled_reason",
            }
            if required_columns.issubset(user_columns):
                ensure_default_users()

    register_cli(app)
    return app


def register_cli(app):
    @app.cli.command("seed")
    def seed_command():
        """Seed baseline taxonomy and provider data."""
        seed_baseline_data()
        click.echo("Seeded baseline AskMarley data.")

    @app.cli.command("migrate-role-labels")
    @click.option(
        "--direction",
        type=click.Choice(["canonical", "legacy"], case_sensitive=False),
        default="canonical",
        show_default=True,
        help="canonical maps consumer/provider to buyer/seller; legacy reverts buyer/seller to consumer/provider.",
    )
    @click.option("--apply", is_flag=True, help="Persist changes. Omit for dry-run.")
    def migrate_role_labels_command(direction, apply):
        """Migrate stored user role labels between legacy and canonical naming."""
        from askmarley.models import User

        canonical_map = {"consumer": "buyer", "provider": "seller"}
        legacy_map = {"buyer": "consumer", "seller": "provider"}
        role_map = canonical_map if direction == "canonical" else legacy_map

        users = User.query.filter(User.role.in_(tuple(role_map.keys()))).order_by(User.id.asc()).all()
        if not users:
            click.echo("No user roles require migration for the selected direction.")
            return

        click.echo(f"Found {len(users)} user(s) to migrate ({direction}).")
        for user in users[:20]:
            click.echo(f"- id={user.id} {user.email}: {user.role} -> {role_map[user.role]}")
        if len(users) > 20:
            click.echo(f"...and {len(users) - 20} more")

        if not apply:
            click.echo("Dry-run only. Re-run with --apply to persist changes.")
            return

        for user in users:
            user.role = role_map[user.role]
        db.session.commit()
        click.echo(f"Role migration applied successfully for {len(users)} user(s).")
