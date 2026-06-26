import logging

from askmarley.extensions import db
from askmarley.models import StripeWebhookEvent, Subscription, User

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


def _nested_get(data, *keys, default=None):
    cursor = data
    for key in keys:
        if isinstance(cursor, dict):
            cursor = cursor.get(key)
            continue
        if isinstance(cursor, list) and isinstance(key, int):
            if key < 0 or key >= len(cursor):
                return default
            cursor = cursor[key]
            continue
        return default
    return default if cursor is None else cursor


def _find_subscription_record(*, user_id=None, stripe_customer_id=None, stripe_subscription_id=None):
    if user_id:
        sub = (
            Subscription.query.filter_by(user_id=user_id)
            .order_by(Subscription.updated_at.desc())
            .first()
        )
        if sub:
            return sub

    if stripe_subscription_id:
        sub = (
            Subscription.query.filter_by(stripe_subscription_id=stripe_subscription_id)
            .order_by(Subscription.updated_at.desc())
            .first()
        )
        if sub:
            return sub

    if stripe_customer_id:
        sub = (
            Subscription.query.filter_by(stripe_customer_id=stripe_customer_id)
            .order_by(Subscription.updated_at.desc())
            .first()
        )
        if sub:
            return sub

    return None


def _extract_metadata(data_object):
    metadata = {}
    object_metadata = data_object.get("metadata") if isinstance(data_object, dict) else None
    if isinstance(object_metadata, dict):
        metadata.update(object_metadata)

    # Stripe invoices can nest subscription metadata in parent.subscription_details.metadata.
    parent_metadata = _nested_get(data_object, "parent", "subscription_details", "metadata", default={})
    if isinstance(parent_metadata, dict):
        metadata.update(parent_metadata)

    return metadata


def _resolve_user_id(metadata, data_object, fallback_sub=None):
    raw_user_id = metadata.get("user_id") or data_object.get("client_reference_id")
    if raw_user_id and str(raw_user_id).isdigit():
        return int(raw_user_id)
    if fallback_sub and fallback_sub.user_id:
        return fallback_sub.user_id
    return None


def _extract_plan_code(metadata, data_object, fallback_sub=None):
    plan_code = metadata.get("plan_code")
    if plan_code:
        return plan_code

    lookup_key = _nested_get(data_object, "lines", "data", 0, "price", "lookup_key")
    if isinstance(lookup_key, str) and lookup_key in CONSUMER_TIER_AMOUNTS_PENCE:
        return lookup_key

    if fallback_sub and fallback_sub.plan_code:
        return fallback_sub.plan_code

    return "free"


def _extract_price_id(data_object):
    price_id = _nested_get(data_object, "lines", "data", 0, "price", "id")
    if isinstance(price_id, str) and price_id:
        return price_id
    return None


def _map_subscription_status(stripe_status, fallback_status="active"):
    mapping = {
        "active": "active",
        "trialing": "active",
        "past_due": "past_due",
        "unpaid": "past_due",
        "incomplete": "grace",
        "incomplete_expired": "canceled",
        "canceled": "canceled",
    }
    return mapping.get((stripe_status or "").strip().lower(), fallback_status)


def _sync_user_subscription(
    *,
    user_id,
    plan_code,
    status,
    stripe_customer_id=None,
    stripe_subscription_id=None,
    stripe_price_id=None,
    latest_invoice_id=None,
    latest_checkout_session_id=None,
):
    user = db.session.get(User, user_id) if user_id else None
    if user_id and not user:
        logger.warning("Stripe webhook referenced unknown user_id=%s", user_id)

    sub = _find_subscription_record(
        user_id=user_id,
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    if not sub and not user_id:
        logger.warning(
            "Stripe webhook could not map event to a subscription: customer=%s subscription=%s",
            stripe_customer_id,
            stripe_subscription_id,
        )
        return False

    if not sub:
        sub = Subscription(
            user_id=user_id,
            plan_code=plan_code or "free",
            status=status or "active",
        )
        db.session.add(sub)

    if plan_code:
        sub.plan_code = plan_code
    if status:
        sub.status = status
    if stripe_customer_id:
        sub.stripe_customer_id = stripe_customer_id
    if stripe_subscription_id:
        sub.stripe_subscription_id = stripe_subscription_id
    if stripe_price_id:
        sub.stripe_price_id = stripe_price_id
    if latest_invoice_id:
        sub.latest_invoice_id = latest_invoice_id
    if latest_checkout_session_id:
        sub.latest_checkout_session_id = latest_checkout_session_id

    if user and user.role in {"consumer", "buyer"} and plan_code:
        user.consumer_tier = plan_code

    return True


def _persist_webhook_guard(event_id, event_type):
    existing = StripeWebhookEvent.query.filter_by(stripe_event_id=event_id).first()
    if existing:
        return False

    db.session.add(StripeWebhookEvent(stripe_event_id=event_id, event_type=event_type))
    db.session.flush()
    return True


def create_consumer_checkout_session(*, secret_key, publishable_key, tier, success_url, cancel_url, user):
    _require_stripe()
    if not secret_key:
        raise RuntimeError("Stripe secret key is missing.")
    if tier not in CONSUMER_TIER_AMOUNTS_PENCE:
        raise ValueError("Unsupported tier for checkout.")

    stripe.api_key = secret_key

    # Host checkout in Stripe to keep PCI scope low and UI integration simple.
    user_id = str((user or {}).get("id", ""))
    role = str((user or {}).get("role", "consumer"))
    metadata = {
        "plan_code": tier,
        "user_id": user_id,
        "role": role,
    }

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
        client_reference_id=user_id,
        customer_email=(user or {}).get("email"),
        metadata=metadata,
        subscription_data={"metadata": metadata},
    )

    return {
        "id": checkout_session.id,
        "url": checkout_session.url,
        "publishable_key": publishable_key,
    }


def create_billing_portal_session(*, secret_key, return_url, user):
    _require_stripe()
    if not secret_key:
        raise RuntimeError("Stripe secret key is missing.")

    user_id = (user or {}).get("id")
    if not user_id:
        raise RuntimeError("Missing authenticated user context for billing portal.")

    sub = (
        Subscription.query.filter_by(user_id=user_id)
        .order_by(Subscription.updated_at.desc())
        .first()
    )
    customer_id = sub.stripe_customer_id if sub else None
    if not customer_id:
        raise RuntimeError("No Stripe customer record found for this account yet.")

    stripe.api_key = secret_key
    portal_session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )

    return {"url": portal_session.url}


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

    event_id = event.get("id", "")
    event_type = event.get("type", "")
    data_object = event.get("data", {}).get("object", {})

    if not event_id:
        raise RuntimeError("Stripe event id missing.")

    if not _persist_webhook_guard(event_id, event_type):
        return f"{event_type}:duplicate"

    metadata = _extract_metadata(data_object)
    stripe_customer_id = data_object.get("customer")
    stripe_subscription_id = data_object.get("subscription")
    if event_type.startswith("customer.subscription"):
        stripe_subscription_id = stripe_subscription_id or data_object.get("id")

    fallback_sub = _find_subscription_record(
        stripe_customer_id=stripe_customer_id,
        stripe_subscription_id=stripe_subscription_id,
    )
    user_id = _resolve_user_id(metadata, data_object, fallback_sub=fallback_sub)
    plan_code = _extract_plan_code(metadata, data_object, fallback_sub=fallback_sub)
    stripe_price_id = _extract_price_id(data_object) or (fallback_sub.stripe_price_id if fallback_sub else None)
    latest_invoice_id = data_object.get("id") if event_type.startswith("invoice.") else data_object.get("invoice")
    latest_checkout_session_id = data_object.get("id") if event_type == "checkout.session.completed" else None

    status = None
    if event_type == "checkout.session.completed":
        status = "active"
    elif event_type in {"invoice.paid", "invoice.payment_succeeded"}:
        status = "active"
    elif event_type in {"invoice.payment_failed", "checkout.session.async_payment_failed"}:
        status = "past_due"
    elif event_type == "customer.subscription.deleted":
        status = "canceled"
    elif event_type == "customer.subscription.updated":
        status = _map_subscription_status(data_object.get("status"), fallback_status="active")

    if status:
        _sync_user_subscription(
            user_id=user_id,
            plan_code=plan_code,
            status=status,
            stripe_customer_id=stripe_customer_id,
            stripe_subscription_id=stripe_subscription_id,
            stripe_price_id=stripe_price_id,
            latest_invoice_id=latest_invoice_id,
            latest_checkout_session_id=latest_checkout_session_id,
        )

    db.session.commit()
    return event_type