from flask_app import app
from askmarley.models import User


def _set_csrf(client, token="test-csrf-token"):
    with client.session_transaction() as sess:
        sess["csrf_token"] = token
    return token


def _set_auth_user(client, role="consumer", full_name="Test User"):
    with client.session_transaction() as sess:
        sess["auth_user"] = {
            "id": 99,
            "email": f"{role}@test.local",
            "full_name": full_name,
            "role": role,
        }
        sess["auth_user_id"] = 99


def test_home_route():
    client = app.test_client()
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["X-Frame-Options"] == "DENY"
    assert b"Super Admin" not in response.data


def test_consumer_chat_route():
    client = app.test_client()
    response = client.get("/consumer/chat")
    assert response.status_code == 200


def test_health_route():
    client = app.test_client()
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "ok"


def test_manual_search_query_route():
    client = app.test_client()
    response = client.get("/consumer/search?q=dog")
    assert response.status_code == 200


def test_clipboard_create_project():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    response = client.post(
        "/consumer/clipboard?tier=business",
        data={"project_name": "Bathroom Refit", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Project created" in response.data


def test_consumer_dashboard_route():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    response = client.get("/consumer/dashboard")
    assert response.status_code == 200
    assert b"Consumer Dashboard" in response.data


def test_project_chat_post_message():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    response = client.post(
        "/consumer/clipboard/1/chat?viewer=consumer",
        data={
            "message": "Please upload revised quote",
            "pin_label": "Quote request note",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Message sent" in response.data


def test_consumer_subscription_update():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    response = client.post(
        "/consumer/subscription",
        data={"tier": "student", "billing_status": "active", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Consumer subscription updated" in response.data


def test_free_tier_blocks_project_save_provider():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    client.post(
        "/consumer/subscription",
        data={"tier": "free", "billing_status": "active", "csrf_token": token},
        follow_redirects=True,
    )
    response = client.post(
        "/consumer/clipboard/1/save-provider",
        data={"provider_name": "Royal Flow Plumbing", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Upgrade your plan" in response.data


def test_provider_subscription_update():
    client = app.test_client()
    _set_auth_user(client, role="provider")
    token = _set_csrf(client)
    response = client.post(
        "/provider/subscription",
        data={"tier": "plus", "billing_status": "past_due", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Provider subscription updated" in response.data


def test_admin_verify_provider_creates_audit_entry():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)
    response = client.post(
        "/admin/dashboard",
        data={
            "action": "verify-provider",
            "provider_name": "Prime Heating Guild",
            "reason": "KYC checks complete",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"marked as Verified" in response.data
    assert b"verify-provider" in response.data


def test_admin_override_tier_with_reason():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)
    response = client.post(
        "/admin/dashboard",
        data={
            "action": "override-tier",
            "provider_name": "Prime Heating Guild",
            "new_tier": "premium",
            "reason": "High service quality",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"moved to Premium tier" in response.data


def test_admin_ban_and_reactivate_provider():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)
    ban_response = client.post(
        "/admin/dashboard",
        data={
            "action": "ban-provider",
            "provider_name": "Prime Heating Guild",
            "reason": "Fraud report under review",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert ban_response.status_code == 200
    assert b"has been suspended" in ban_response.data

    reactivate_response = client.post(
        "/admin/dashboard",
        data={
            "action": "reactivate-provider",
            "provider_name": "Prime Heating Guild",
            "reason": "Issue resolved",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert reactivate_response.status_code == 200
    assert b"has been reactivated" in reactivate_response.data


def test_project_chat_report_creates_moderation_case():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    client.post(
        "/consumer/clipboard/1/chat?viewer=consumer",
        data={"message": "Please confirm quote", "pin_label": "", "csrf_token": token},
        follow_redirects=True,
    )
    response = client.post(
        "/consumer/clipboard/1/chat/report?viewer=consumer",
        data={"message_index": "1", "reason": "Abusive wording", "csrf_token": token},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Message reported" in response.data


def test_admin_moderation_status_update():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)
    response = client.post(
        "/admin/dashboard",
        data={
            "action": "moderation-status",
            "case_id": "AUD-1043",
            "new_status": "reviewing",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"moved to reviewing" in response.data


def test_taxonomy_add_validation_and_versioning():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)

    invalid = client.post(
        "/admin/dashboard",
        data={
            "action": "add-taxonomy",
            "category_path": "Dog Walking",
            "reason": "Expansion",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert invalid.status_code == 200
    assert b"must have at least 3 levels" in invalid.data

    valid = client.post(
        "/admin/dashboard",
        data={
            "action": "add-taxonomy",
            "category_path": "Pet Care > Dog Services > Walking",
            "reason": "Expansion",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert valid.status_code == 200
    assert b"Category added" in valid.data

    update = client.post(
        "/admin/dashboard",
        data={
            "action": "edit-taxonomy",
            "entry_id": "5",
            "category_path": "Pet Care > Dog Services > Premium Walking",
            "reason": "Refine service name",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert update.status_code == 200
    assert b"Taxonomy entry updated" in update.data


def test_provider_dashboard_requires_provider_login():
    client = app.test_client()
    response = client.get("/provider/dashboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_admin_dashboard_requires_admin_login():
    client = app.test_client()
    response = client.get("/admin/dashboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_consumer_clipboard_requires_consumer_login():
    client = app.test_client()
    response = client.get("/consumer/clipboard")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_admin_link_visible_for_admin_session():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    response = client.get("/")
    assert response.status_code == 200
    assert b"Super Admin" in response.data


def test_register_persists_password_hash():
    with app.app_context():
        existing = User.query.filter_by(email="persist.check@askmarley.local").first()
        if existing:
            from askmarley.extensions import db

            db.session.delete(existing)
            db.session.commit()

    client = app.test_client()
    token = _set_csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "full_name": "Persist Check",
            "email": "persist.check@askmarley.local",
            "role": "consumer",
            "consumer_postcode": "SW1A 1AA",
            "password": "persist-secret",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Consumer Dashboard" in response.data
    with app.app_context():
        user = User.query.filter_by(email="persist.check@askmarley.local").first()
        assert user is not None
        assert user.password_hash is not None
        assert len(user.password_hash) > 20


def test_provider_registration_captures_business_data():
    client = app.test_client()
    token = _set_csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "full_name": "Jane Smith",
            "email": "jane.smith@providers.local",
            "role": "provider",
            "company_name": "Smith Electrical",
            "phone": "+44 20 7946 0958",
            "business_reg_number": "12345678",
            "service_categories": ["electrician", "emergency-plumber"],
            "travel_postcodes": "SW1A, SE1, W1",
            "insurance_verified": "true",
            "password": "provider-secret",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="jane.smith@providers.local").first()
        assert user is not None
        assert user.company_name == "Smith Electrical"
        assert user.phone == "+44 20 7946 0958"
        assert user.business_reg_number == "12345678"
        assert "electrician" in user.service_categories
        assert "emergency-plumber" in user.service_categories
        assert user.travel_postcodes == "SW1A, SE1, W1"
        assert user.insurance_verified == True
        assert user.provider_status == "pending"
        assert user.password_hash is not None


def test_consumer_registration_captures_profile_data():
    client = app.test_client()
    token = _set_csrf(client)
    response = client.post(
        "/auth/register",
        data={
            "full_name": "John Consumer",
            "email": "john.consumer@local.test",
            "role": "consumer",
            "consumer_phone": "+44 20 7111 2222",
            "consumer_postcode": "W1A 1AA",
            "password": "consumer-secret",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = User.query.filter_by(email="john.consumer@local.test").first()
        assert user is not None
        assert user.consumer_phone == "+44 20 7111 2222"
        assert user.consumer_postcode == "W1A 1AA"
        assert user.password_hash is not None
        assert user.role == "consumer"


def test_admin_dashboard_analytics_render():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)
    client.post(
        "/consumer/chat",
        data={"message": "I have a leaky pipe", "csrf_token": token},
        follow_redirects=True,
    )
    client.post(
        "/consumer/chat",
        data={"message": "SW1A 1AA", "csrf_token": token},
        follow_redirects=True,
    )
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert b"Conversion Funnel" in response.data
    assert b"Geography Heatmap" in response.data
    assert b"Export CSV" in response.data


def test_admin_analytics_csv_export():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    response = client.get("/admin/analytics/export.csv")
    assert response.status_code == 200
    assert response.mimetype == "text/csv"
    assert b"metric,value" in response.data
    assert b"active_projects" in response.data


def test_post_without_csrf_is_rejected():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    response = client.post(
        "/consumer/subscription",
        data={"tier": "student", "billing_status": "active"},
        follow_redirects=False,
    )
    assert response.status_code == 400


def test_admin_action_requires_admin_role():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    response = client.post(
        "/admin/dashboard",
        data={
            "action": "verify-provider",
            "provider_name": "Prime Heating Guild",
            "reason": "Should fail",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"does not have access" in response.data


def test_provider_dashboard_route_renders():
    client = app.test_client()
    _set_auth_user(client, role="provider")
    response = client.get("/provider/dashboard")
    assert response.status_code == 200


def test_admin_dashboard_sets_security_headers():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]
