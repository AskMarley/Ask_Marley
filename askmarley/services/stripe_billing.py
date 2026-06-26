import logging

from askmarley.extensions import db
from askmarley.models import Subscription, User

logger = logging.getLogger(__name__)

try:
    import stripe
except ImportError:  # pragma: no cover - handled at runtime with clear error
    stripe = None


CONSUMER_TIER_AMOUNTS_PENCE = {
    "student": 299,
    "individual": 499,
    "business": 999,
    "business-plus": 1999,
}


def _require_stripe():
    if stripe is None:
        raise RuntimeError("Stripe SDK not installed. Add 'stripe' to requirements and install deps.")


def _sync_user_subscription(user_id, plan_code, status):
    user = db.session.get(User, user_id)
    if not user:
        logger.warning("Stripe webhook referenced unknown user_id=%s", user_id)
        return False

    sub = (
        Subscription.query.filter_by(user_id=user.id)
        .order_by(Subscription.updated_at.desc())
        .first()
    )
    if not sub:
        sub = Subscription(user_id=user.id, plan_code=plan_code, status=status)
        db.session.add(sub)
    else:
        sub.plan_code = plan_code
        sub.status = status

    if user.role == "consumer":
        user.consumer_tier = plan_code

    db.session.commit()
    return True


def create_consumer_checkout_session(*, secret_key, publishable_key, tier, success_url, cancel_url, user):
    _require_stripe()
    if not secret_key:
        raise RuntimeError("Stripe secret key is missing.")
    if tier not in CONSUMER_TIER_AMOUNTS_PENCE:
        raise ValueError("Unsupported tier for checkout.")

    stripe.api_key = secret_key

    # Host checkout in Stripe to keep PCI scope low and UI integration simple.
    checkout_session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[
            {
                "price_data": {
                    "currency": "gbp",
                    "unit_amount": CONSUMER_TIER_AMOUNTS_PENCE[tier],
                    "recurring": {"interval": "month"},
                    "product_data": {
                        "name": f"AskMarley {tier.title()} Plan",
                    },
                },
                "quantity": 1,
            }
        ],
        success_url=success_url,
        cancel_url=cancel_url,
        customer_email=(user or {}).get("email"),
        metadata={
            "plan_code": tier,
            "user_id": str((user or {}).get("id", "")),
            "role": str((user or {}).get("role", "consumer")),
        },
    )

    return {
        "id": checkout_session.id,
        "url": checkout_session.url,
        "publishable_key": publishable_key,
    }


def process_webhook_event(*, payload, signature, secret_key, webhook_secret):
    _require_stripe()
    if not secret_key:
        raise RuntimeError("Stripe secret key is missing.")
    if not webhook_secret:
        raise RuntimeError("Stripe webhook secret is missing.")

    stripe.api_key = secret_key

    event = stripe.Webhook.construct_event(
        payload=payload,
        sig_header=signature,
        secret=webhook_secret,
    )

    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    if event_type == "checkout.session.completed":
        metadata = data_object.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_code = metadata.get("plan_code", "free")
        if user_id and user_id.isdigit():
            _sync_user_subscription(int(user_id), plan_code, "active")

    elif event_type == "invoice.payment_failed":
        metadata = data_object.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_code = metadata.get("plan_code", "free")
        if user_id and user_id.isdigit():
            _sync_user_subscription(int(user_id), plan_code, "past_due")

    elif event_type == "customer.subscription.deleted":
        metadata = data_object.get("metadata", {})
        user_id = metadata.get("user_id")
        plan_code = metadata.get("plan_code", "free")
        if user_id and user_id.isdigit():
            _sync_user_subscription(int(user_id), plan_code, "canceled")

    return event_type