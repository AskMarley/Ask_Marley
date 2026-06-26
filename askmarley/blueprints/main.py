import logging

from flask import Blueprint, current_app, jsonify, request, render_template

from askmarley.services.stripe_billing import process_webhook_event

main_bp = Blueprint("main", __name__)
logger = logging.getLogger(__name__)


@main_bp.get("/")
def home():
    return render_template("index.html")


@main_bp.get("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


@main_bp.get("/terms-and-conditions")
def terms_and_conditions():
    return render_template("terms_and_conditions.html")


@main_bp.get("/health")
def health():
    return jsonify({"status": "ok"})


@main_bp.post("/webhooks/stripe")
def stripe_webhook():
    signature = request.headers.get("Stripe-Signature", "")
    payload = request.data

    try:
        event_type = process_webhook_event(
            payload=payload,
            signature=signature,
            secret_key=current_app.config.get("STRIPE_SECRET_KEY", ""),
            webhook_secret=current_app.config.get("STRIPE_WEBHOOK_SECRET", ""),
        )
    except Exception:
        logger.exception("Stripe webhook processing failed")
        return jsonify({"status": "error", "message": "Webhook processing failed."}), 400

    return jsonify({"status": "ok", "event": event_type}), 200
