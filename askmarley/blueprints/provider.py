from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from askmarley.data import BILLING_STATUSES, PROVIDER_TIERS
from askmarley.services.auth import role_required
from askmarley.services.collaboration import build_provider_chat_summary
from askmarley.services.subscriptions import (
    get_provider_subscription,
    update_provider_subscription,
)

provider_bp = Blueprint("provider", __name__, url_prefix="/provider")


@provider_bp.get("/dashboard")
@role_required("provider")
def dashboard():
    provider_sub = get_provider_subscription(session)
    provider_profile = {
        "name": "Royal Flow Plumbing",
        "tier": provider_sub["effective_tier"],
        "selected_tier": provider_sub["selected_tier"],
        "billing_status": provider_sub["billing_status"],
        "services": [
            "Home Trades > Plumbing > Emergency Repair",
            "Home Trades > Plumbing > Boiler Servicing",
        ],
        "travel_postcodes": ["SW1A", "SE1", "W1", "E1"],
    }
    leads = [
        {"project": "Leaking Bathroom Pipe", "postcode": "SW1A 2AA", "urgency": "urgent"},
        {"project": "Boiler Pressure Drop", "postcode": "SE1 4TY", "urgency": "medium"},
    ]
    chats = build_provider_chat_summary(session)
    if not chats:
        chats = [
            {
                "customer": "No active project threads yet",
                "latest": "Consumer project chats will appear here once opened.",
                "pinboard_count": 0,
                "provider_unread": 0,
            }
        ]
    return render_template(
        "provider_dashboard.html",
        provider_profile=provider_profile,
        leads=leads,
        chats=chats,
    )


@provider_bp.route("/subscription", methods=["GET", "POST"])
@role_required("provider")
def subscription():
    if request.method == "POST":
        tier = request.form.get("tier", "basic")
        billing_status = request.form.get("billing_status", "active")
        update_provider_subscription(session, tier, billing_status)
        flash("Provider subscription updated.", "success")
        return redirect(url_for("provider.subscription"))

    provider_sub = get_provider_subscription(session)
    return render_template(
        "provider_subscription.html",
        provider_sub=provider_sub,
        tiers=PROVIDER_TIERS,
        billing_statuses=BILLING_STATUSES,
    )
