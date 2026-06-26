from flask_app import app

from askmarley.extensions import db
from askmarley.models import User
from askmarley.services.auth import register_user, role_matches


def _set_auth_user(client, role="consumer", full_name="Alias Test User"):
    with client.session_transaction() as sess:
        sess["auth_user"] = {
            "id": 9999,
            "email": f"{role}.alias@test.local",
            "full_name": full_name,
            "role": role,
        }
        sess["auth_user_id"] = 9999


def _delete_user_by_email(email):
    with app.app_context():
        user = User.query.filter_by(email=email).first()
        if user:
            db.session.delete(user)
            db.session.commit()


def test_role_matches_supports_legacy_and_canonical_labels():
    assert role_matches("consumer", "buyer")
    assert role_matches("buyer", "consumer")
    assert role_matches("provider", "seller")
    assert role_matches("seller", "provider")
    assert not role_matches("admin", "provider")


def test_register_user_accepts_buyer_and_seller_in_legacy_storage_mode():
    buyer_email = "buyer.alias.legacy@askmarley.local"
    seller_email = "seller.alias.legacy@askmarley.local"
    _delete_user_by_email(buyer_email)
    _delete_user_by_email(seller_email)

    with app.app_context():
        app.config["ROLE_STORAGE_MODE"] = "legacy"

        ok_buyer, buyer = register_user(
            buyer_email,
            "Legacy Buyer",
            "buyer",
            "alias-secret",
            consumer_postcode="SW1A 1AA",
        )
        ok_seller, seller = register_user(
            seller_email,
            "Legacy Seller",
            "seller",
            "alias-secret",
            company_name="Alias Services Ltd",
            phone="+44 20 7000 0000",
            service_categories=["electrician"],
            travel_postcodes="SW1A",
        )

        assert ok_buyer is True
        assert ok_seller is True
        assert buyer.role == "consumer"
        assert seller.role == "provider"


def test_register_user_can_store_canonical_roles_when_enabled():
    buyer_email = "buyer.alias.canonical@askmarley.local"
    seller_email = "seller.alias.canonical@askmarley.local"
    _delete_user_by_email(buyer_email)
    _delete_user_by_email(seller_email)

    with app.app_context():
        previous_mode = app.config.get("ROLE_STORAGE_MODE", "legacy")
        app.config["ROLE_STORAGE_MODE"] = "canonical"
        try:
            ok_buyer, buyer = register_user(
                buyer_email,
                "Canonical Buyer",
                "buyer",
                "alias-secret",
                consumer_postcode="SE1 2AA",
            )
            ok_seller, seller = register_user(
                seller_email,
                "Canonical Seller",
                "seller",
                "alias-secret",
                company_name="Canonical Services Ltd",
                phone="+44 20 7000 0001",
                service_categories=["cleaner"],
                travel_postcodes="SE1",
            )
        finally:
            app.config["ROLE_STORAGE_MODE"] = previous_mode

        assert ok_buyer is True
        assert ok_seller is True
        assert buyer.role == "buyer"
        assert seller.role == "seller"


def test_buyer_alias_can_access_consumer_subscription_routes():
    client = app.test_client()
    _set_auth_user(client, role="buyer")

    response = client.get("/consumer/subscription")

    assert response.status_code == 200
    assert b"Subscription" in response.data


def test_seller_alias_can_access_provider_dashboard_route():
    client = app.test_client()
    _set_auth_user(client, role="seller")

    response = client.get("/provider/dashboard")

    assert response.status_code == 200
    assert b"Dashboard" in response.data
