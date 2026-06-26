from flask_app import app
from askmarley.extensions import db
from askmarley.models import Project, ProjectPinboardItem, User
from askmarley.services.collaboration import _project_to_dict
from unittest.mock import patch


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
    assert b"Login Required" in response.data
    assert b"login or create an account" in response.data


def test_consumer_chat_new_chat_button_keeps_history():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/chat",
        data={"message": "Need a plumber in SW1A 1AA", "csrf_token": token},
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/chat",
        data={"action": "new_chat", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Started a new chat." in response.data
    assert b"Chat History" in response.data
    assert b"Need a plumber in SW1A 1AA" in response.data


def test_consumer_chat_new_chat_command_starts_fresh_thread():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    response = client.post(
        "/consumer/chat",
        data={"message": "new chat", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Started a new chat." in response.data


def test_consumer_chat_greeting_gets_guided_prompt():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    response = client.post(
        "/consumer/chat",
        data={"message": "hi", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Tell me what needs doing and your UK postcode" in response.data
    assert b"I could not map that yet" not in response.data


def test_consumer_chat_can_delete_non_active_thread():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    with client.session_transaction() as sess:
        sess["chat_threads"] = [
            {
                "id": "thread1",
                "title": "First chat",
                "chat_log": [{"sender": "marley", "text": "Welcome"}],
                "chat_state": {
                    "step": "service",
                    "service_slug": None,
                    "options": [],
                    "confidence": 0.0,
                },
                "recommendations": [],
            },
            {
                "id": "thread2",
                "title": "Second chat",
                "chat_log": [{"sender": "marley", "text": "Welcome 2"}],
                "chat_state": {
                    "step": "service",
                    "service_slug": None,
                    "options": [],
                    "confidence": 0.0,
                },
                "recommendations": [],
            },
        ]
        sess["active_chat_thread_id"] = "thread1"

    response = client.post(
        "/consumer/chat",
        data={"action": "delete_chat", "delete_thread_id": "thread2", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Chat deleted." in response.data
    with client.session_transaction() as sess:
        ids = {thread["id"] for thread in sess["chat_threads"]}
        assert "thread2" not in ids
        assert sess["active_chat_thread_id"] == "thread1"


def test_consumer_chat_delete_active_thread_switches_to_remaining():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    with client.session_transaction() as sess:
        sess["chat_threads"] = [
            {
                "id": "thread1",
                "title": "First chat",
                "chat_log": [{"sender": "marley", "text": "Welcome"}],
                "chat_state": {
                    "step": "service",
                    "service_slug": None,
                    "options": [],
                    "confidence": 0.0,
                },
                "recommendations": [],
            },
            {
                "id": "thread2",
                "title": "Second chat",
                "chat_log": [{"sender": "marley", "text": "Welcome 2"}],
                "chat_state": {
                    "step": "service",
                    "service_slug": None,
                    "options": [],
                    "confidence": 0.0,
                },
                "recommendations": [],
            },
        ]
        sess["active_chat_thread_id"] = "thread2"

    response = client.post(
        "/consumer/chat",
        data={"action": "delete_chat", "delete_thread_id": "thread2", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    with client.session_transaction() as sess:
        ids = {thread["id"] for thread in sess["chat_threads"]}
        assert "thread2" not in ids
        assert sess["active_chat_thread_id"] == "thread1"


def test_consumer_chat_confirms_service_before_asking_postcode():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    response = client.post(
        "/consumer/chat",
        data={"message": "need a cleaner", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Is that correct? Reply yes or no" in response.data
    assert b"Please share your UK postcode" not in response.data


def test_consumer_chat_moves_to_postcode_after_confirmation():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/chat",
        data={"message": "need a cleaner", "csrf_token": token},
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/chat",
        data={"message": "yes", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"confirmed. Please share your UK postcode" in response.data


def test_consumer_chat_extracts_postcode_from_sentence():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/chat",
        data={"message": "I have a leaking pipe", "csrf_token": token},
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/chat",
        data={"message": "I need help in M1 1AA please", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Please include a valid UK postcode" not in response.data


def test_consumer_chat_can_switch_service_while_waiting_for_postcode():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/chat",
        data={"message": "leaky pipes", "csrf_token": token},
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/chat",
        data={"message": "no i need a roofer instead", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"switched to Roofers" in response.data


def test_consumer_chat_accepts_outward_area_code():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/chat",
        data={"message": "leaky pipes", "csrf_token": token},
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/chat",
        data={"message": "SW1A", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Top match:" in response.data


def test_consumer_chat_acknowledgement_after_match_is_contextual():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/chat",
        data={"message": "leaky pipes", "csrf_token": token},
        follow_redirects=True,
    )
    client.post(
        "/consumer/chat",
        data={"message": "SW1A", "csrf_token": token},
        follow_redirects=True,
    )
    response = client.post(
        "/consumer/chat",
        data={"message": "okay", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"You already have provider recommendations" in response.data
    assert b"I could not map that yet" not in response.data


def test_consumer_provider_detail_route_loads():
    client = app.test_client()
    response = client.get("/consumer/providers/1")
    assert response.status_code == 200
    assert b"Royal Flow Plumbing" in response.data


def test_consumer_chat_recommended_provider_links_are_clickable():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    with client.session_transaction() as sess:
        sess["chat_threads"] = [
            {
                "id": "thread1",
                "title": "Test chat",
                "chat_log": [
                    {
                        "sender": "marley",
                        "text": "Hi, I'm Marley. Tell me what you need and I will match you with the right local service.",
                    }
                ],
                "chat_state": {
                    "step": "service",
                    "service_slug": None,
                    "options": [],
                    "confidence": 0.0,
                },
                "recommendations": [
                    {
                        "id": 1,
                        "name": "Royal Flow Plumbing",
                        "service_slug": "emergency-plumber",
                        "postcodes": ["SW1A", "SE1", "W1"],
                        "tier": "premium",
                        "billing_status": "active",
                        "verified": True,
                        "marleys_choice": True,
                        "activity_score": 92,
                    }
                ],
            }
        ]
        sess["active_chat_thread_id"] = "thread1"

    response = client.get("/consumer/chat")
    assert response.status_code == 200
    assert b"/consumer/providers/1" in response.data
    assert b"View Profile" in response.data
    assert b"/consumer/providers/1/contact" in response.data
    assert b"Message Now" in response.data
    assert b"quick-intent-btn" in response.data
    assert b"I need an electrician" in response.data


def test_consumer_chat_quick_intent_phrase_triggers_detection_flow():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    response = client.post(
        "/consumer/chat",
        data={"message": "I need an electrician", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"It sounds like you need Electricians" in response.data


def test_provider_contact_route_opens_project_chat():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    response = client.post(
        "/consumer/providers/1/contact",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Chat opened with Royal Flow Plumbing" in response.data
    assert b"Project Chat" in response.data


def test_provider_contact_route_blocks_free_tier():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/subscription",
        data={"tier": "free", "billing_status": "active", "csrf_token": token},
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/providers/1/contact",
        data={"csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Upgrade your plan to contact sellers" in response.data


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
        data={
            "project_name": "Bathroom Refit",
            "service_slug": "emergency-plumber",
            "location_code": "SW1A 1AA",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Project created" in response.data
    assert b"Emergency Plumbers" in response.data


def test_clipboard_create_project_requires_valid_location_and_service():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    response = client.post(
        "/consumer/clipboard?tier=business",
        data={
            "project_name": "Bathroom Refit",
            "service_slug": "",
            "location_code": "not-a-postcode",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Choose the service you need for this project" in response.data


def test_clipboard_update_project_details():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    client.post(
        "/consumer/clipboard?tier=business",
        data={
            "project_name": "Bathroom Refit",
            "service_slug": "emergency-plumber",
            "location_code": "SW1A 1AA",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    response = client.post(
        "/consumer/clipboard/3/details?tier=business",
        data={
            "service_slug": "cleaner",
            "location_code": "SE1 2AA",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Project details updated" in response.data
    assert b"Domestic Cleaners" in response.data
    assert b"SE1 2AA" in response.data


def test_clipboard_renders_pinboard_gallery_modal():
    client = app.test_client()
    _set_auth_user(client, role="consumer")

    response = client.get("/consumer/clipboard")

    assert response.status_code == 200
    assert b"clipboardGalleryModal" in response.data
    assert b"data-gallery-prev" in response.data
    assert b"data-gallery-next" in response.data
    assert b"clipboard-gallery-trigger" in response.data


def test_project_to_dict_includes_pinboard_image_metadata():
    with app.app_context():
        user = User.query.filter_by(email="consumer@test.local").first()
        if user is None:
            user = User(email="consumer@test.local", full_name="Test User", role="consumer")
            db.session.add(user)
            db.session.flush()

        project = Project(user_id=user.id, name="Image metadata test", status="Shortlisting")
        db.session.add(project)
        db.session.flush()

        db.session.add(ProjectPinboardItem(project_id=project.id, label="Text only", image_path=None))
        db.session.add(
            ProjectPinboardItem(
                project_id=project.id,
                label="With image",
                image_path="/static/uploads/example.jpg",
            )
        )
        db.session.commit()

        payload = _project_to_dict(project)

        assert "Text only" in payload["pinboard_items"]
        assert {"label": "With image", "image": "/static/uploads/example.jpg"} in payload[
            "pinboard_items"
        ]


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


def test_consumer_subscription_upgrade_redirects_to_stripe_url():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)
    with patch("askmarley.blueprints.consumer.create_consumer_checkout_session") as mock_checkout:
        mock_checkout.return_value = {
            "id": "cs_test_123",
            "url": "https://checkout.stripe.com/c/pay/cs_test_123",
            "publishable_key": "",
        }
        response = client.post(
            "/consumer/subscription/checkout",
            data={"tier": "business", "csrf_token": token},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert "checkout.stripe.com" in response.headers["Location"]


def test_consumer_subscription_downgrade_is_scheduled_until_renewal():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    token = _set_csrf(client)

    response = client.post(
        "/consumer/subscription/checkout",
        data={"tier": "student", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Downgrade confirmed" in response.data
    assert b"Next billing:" in response.data
    assert b"Student" in response.data


def test_consumer_subscription_success_activates_tier():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    response = client.get("/consumer/subscription/success?tier=business", follow_redirects=True)
    assert response.status_code == 200
    assert b"Subscription is now active" in response.data
    assert b"Business" in response.data


def test_consumer_subscription_cancel_shows_message():
    client = app.test_client()
    _set_auth_user(client, role="consumer")
    response = client.get("/consumer/subscription/cancel", follow_redirects=True)
    assert response.status_code == 200
    assert b"Checkout canceled" in response.data


def test_stripe_webhook_accepts_event_with_valid_processor():
    client = app.test_client()
    with patch("askmarley.blueprints.main.process_webhook_event") as mock_processor:
        mock_processor.return_value = "checkout.session.completed"
        response = client.post(
            "/webhooks/stripe",
            data=b"{}",
            headers={"Stripe-Signature": "t=1,v1=fake"},
        )

    assert response.status_code == 200
    assert response.json["status"] == "ok"
    assert response.json["event"] == "checkout.session.completed"


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
    assert b"Seller subscription updated" in response.data


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


def test_admin_root_requires_admin_login():
    client = app.test_client()
    response = client.get("/admin")
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
        assert user.role in {"consumer", "buyer"}


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


def test_admin_root_redirects_to_dashboard_for_admin():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    response = client.get("/admin", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/dashboard")


def test_admin_section_pages_render_for_admin():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")

    providers = client.get("/admin/providers")
    moderation = client.get("/admin/moderation")
    taxonomy = client.get("/admin/taxonomy")
    audit = client.get("/admin/audit")

    assert providers.status_code == 200
    assert b"Seller Verification Queue" in providers.data

    assert moderation.status_code == 200
    assert b"Safety & Moderation Queue" in moderation.data

    assert taxonomy.status_code == 200
    assert b"Taxonomy Manager" in taxonomy.data

    assert audit.status_code == 200
    assert b"Audit Trail" in audit.data


def test_admin_subpage_post_respects_return_to():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)

    response = client.post(
        "/admin/providers",
        data={
            "action": "verify-provider",
            "provider_name": "Prime Heating Guild",
            "reason": "KYC checks complete",
            "return_to": "/admin/providers",
            "csrf_token": token,
        },
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/providers")


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
    assert b"Provider Dashboard" in response.data
    assert b"Onboarding Progress" in response.data


def test_provider_onboarding_route_renders():
    client = app.test_client()
    _set_auth_user(client, role="provider")
    response = client.get("/provider/onboarding")
    assert response.status_code == 200
    assert b"Complete Your Provider Setup" in response.data


def test_provider_lead_status_update_changes_project_state():
    with app.app_context():
        consumer = User.query.filter_by(email="provider.lead.consumer@askmarley.local").first()
        if not consumer:
            consumer = User(
                email="provider.lead.consumer@askmarley.local",
                full_name="Lead Consumer",
                role="consumer",
                consumer_tier="individual",
            )
            db.session.add(consumer)
            db.session.commit()

        project = Project.query.filter_by(name="Provider Lead Test").first()
        if not project:
            project = Project(user_id=consumer.id, name="Provider Lead Test", status="shortlisting")
            db.session.add(project)
            db.session.commit()

        project_id = project.id

    client = app.test_client()
    _set_auth_user(client, role="provider")
    token = _set_csrf(client)
    response = client.post(
        f"/provider/leads/{project_id}/status",
        data={"status": "contacted", "csrf_token": token},
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"Lead moved to Contacted" in response.data

    with app.app_context():
        updated_project = db.session.get(Project, project_id)
        assert updated_project.status == "contacted"


def test_admin_dashboard_sets_security_headers():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    response = client.get("/admin/dashboard")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert "default-src 'self'" in response.headers["Content-Security-Policy"]


def test_admin_can_access_consumer_crm_pages():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")

    chat = client.get("/consumer/chat")
    dashboard = client.get("/consumer/dashboard")
    clipboard = client.get("/consumer/clipboard")

    assert chat.status_code == 200
    assert b"Marley" in chat.data

    assert dashboard.status_code == 200
    assert b"Consumer Dashboard" in dashboard.data

    assert clipboard.status_code == 200
    assert b"Clipboard Dashboard" in clipboard.data


def test_admin_consumer_crm_page_renders():
    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")

    response = client.get("/admin/consumers")

    assert response.status_code == 200
    assert b"Buyer CRM" in response.data
    assert b"Relationships, plans, activity" in response.data


def test_admin_can_update_consumer_plan_from_crm():
    with app.app_context():
        consumer = User.query.filter_by(email="consumer.demo@askmarley.local").first()
        assert consumer is not None
        consumer_id = consumer.id

    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)

    response = client.post(
        "/admin/consumers",
        data={
            "action": "update-consumer-plan",
            "consumer_id": str(consumer_id),
            "new_tier": "business",
            "billing_status": "active",
            "reason": "VIP upgrade",
            "return_to": "/admin/consumers",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"moved to Business" in response.data


def test_admin_can_disable_and_enable_consumer_account():
    with app.app_context():
        consumer = User.query.filter_by(email="consumer.demo@askmarley.local").first()
        assert consumer is not None
        consumer.account_disabled = False
        consumer.account_disabled_reason = None
        db.session.commit()
        consumer_id = consumer.id

    client = app.test_client()
    _set_auth_user(client, role="super_admin", full_name="Tolu")
    token = _set_csrf(client)

    disable_response = client.post(
        "/admin/consumers",
        data={
            "action": "disable-consumer-account",
            "consumer_id": str(consumer_id),
            "reason": "Fraud review",
            "return_to": "/admin/consumers",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert disable_response.status_code == 200
    assert b"has been disabled" in disable_response.data

    with app.app_context():
        disabled_user = db.session.get(User, consumer_id)
        assert disabled_user.account_disabled is True

    enable_response = client.post(
        "/admin/consumers",
        data={
            "action": "enable-consumer-account",
            "consumer_id": str(consumer_id),
            "reason": "Review cleared",
            "return_to": "/admin/consumers",
            "csrf_token": token,
        },
        follow_redirects=True,
    )
    assert enable_response.status_code == 200
    assert b"re-enabled" in enable_response.data


def test_disabled_consumer_cannot_log_in():
    with app.app_context():
        consumer = User.query.filter_by(email="consumer.demo@askmarley.local").first()
        assert consumer is not None
        consumer.account_disabled = True
        consumer.account_disabled_reason = "Admin lock"
        db.session.commit()

    client = app.test_client()
    token = _set_csrf(client)
    response = client.post(
        "/auth/login",
        data={
            "email": "consumer.demo@askmarley.local",
            "password": "demo-consumer",
            "csrf_token": token,
        },
        follow_redirects=True,
    )

    assert response.status_code == 200
    assert b"This account has been disabled" in response.data

    with app.app_context():
        consumer = User.query.filter_by(email="consumer.demo@askmarley.local").first()
        consumer.account_disabled = False
        consumer.account_disabled_reason = None
        db.session.commit()
