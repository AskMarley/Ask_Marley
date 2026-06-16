import click
from flask import Flask
from sqlalchemy import inspect

from askmarley.blueprints.admin import admin_bp
from askmarley.blueprints.auth import auth_bp
from askmarley.blueprints.consumer import consumer_bp
from askmarley.blueprints.main import main_bp
from askmarley.blueprints.provider import provider_bp
from askmarley.config import CONFIG_MAP
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


def create_app(config_name=None):
    app = Flask(__name__, template_folder="../templates", static_folder="../static")

    selected_config = config_name or "development"
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
        db.create_all()
        inspector = inspect(db.engine)
        if inspector.has_table("users"):
            user_columns = {column["name"] for column in inspector.get_columns("users")}
            required_columns = {"password_hash", "company_name", "phone", "business_reg_number", "service_categories", "travel_postcodes", "insurance_verified", "provider_status", "consumer_phone", "consumer_postcode"}
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
