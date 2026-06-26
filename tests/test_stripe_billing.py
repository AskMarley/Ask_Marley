import uuid
from unittest.mock import Mock, patch

from flask_app import app

from askmarley.extensions import db
from askmarley.models import StripeWebhookEvent, Subscription, User
from askmarley.services.stripe_billing import process_webhook_event


def _ensure_test_user(email):
    user = User.query.filter_by(email=email).first()
    if user:
        return user
    user = User(
        email=email,
        full_name="Stripe Test User",
        role="buyer",
        consumer_tier="individual",
    )
    db.session.add(user)
    db.session.commit()
    return user


def _stripe_stub(event_payload):
    stripe_stub = Mock()
    stripe_stub.Webhook.construct_event.return_value = event_payload
    return stripe_stub


def test_process_webhook_event_is_idempotent_for_duplicate_event_id():
    with app.app_context():
        user = _ensure_test_user("stripe.idempotent.user@askmarley.local")
        event_id = f"evt_idempotent_{uuid.uuid4().hex}"
        event = {
            "id": event_id,
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_test_1",
                    "customer": "cus_test_1",
                    "subscription": "sub_test_1",
                    "metadata": {"user_id": str(user.id), "plan_code": "business"},
                }
            },
        }

        with patch("askmarley.services.stripe_billing.stripe", _stripe_stub(event)):
            first = process_webhook_event(
                payload=b"{}",
                signature="sig",
                secret_key="sk_test",
                webhook_secret="whsec_test",
            )
            second = process_webhook_event(
                payload=b"{}",
                signature="sig",
                secret_key="sk_test",
                webhook_secret="whsec_test",
            )

        assert first == "checkout.session.completed"
        assert second == "checkout.session.completed:duplicate"
        assert StripeWebhookEvent.query.filter_by(stripe_event_id=event_id).count() == 1


def test_invoice_payment_succeeded_updates_subscription_without_metadata_user_id():
    with app.app_context():
        user = _ensure_test_user("stripe.invoice.user@askmarley.local")
        event_id = f"evt_invoice_paid_{uuid.uuid4().hex}"
        sub = (
            Subscription.query.filter_by(user_id=user.id)
            .order_by(Subscription.updated_at.desc())
            .first()
        )
        if not sub:
            sub = Subscription(
                user_id=user.id,
                plan_code="individual",
                status="past_due",
                stripe_customer_id="cus_invoice_1",
                stripe_subscription_id="sub_invoice_1",
            )
            db.session.add(sub)
            db.session.commit()
        else:
            sub.status = "past_due"
            sub.plan_code = "individual"
            sub.stripe_customer_id = "cus_invoice_1"
            sub.stripe_subscription_id = "sub_invoice_1"
            db.session.commit()

        event = {
            "id": event_id,
            "type": "invoice.payment_succeeded",
            "data": {
                "object": {
                    "id": "in_paid_1",
                    "customer": "cus_invoice_1",
                    "subscription": "sub_invoice_1",
                    "metadata": {},
                }
            },
        }

        with patch("askmarley.services.stripe_billing.stripe", _stripe_stub(event)):
            event_type = process_webhook_event(
                payload=b"{}",
                signature="sig",
                secret_key="sk_test",
                webhook_secret="whsec_test",
            )

        refreshed = db.session.get(Subscription, sub.id)
        assert event_type == "invoice.payment_succeeded"
        assert refreshed.status == "active"
        assert refreshed.latest_invoice_id == "in_paid_1"
