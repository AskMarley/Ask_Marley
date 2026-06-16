from askmarley.data import BILLING_STATUSES, CONSUMER_TIERS, PROVIDER_TIERS


def _ensure_consumer_subscription(session):
    if "consumer_subscription" not in session:
        session["consumer_subscription"] = {
            "tier": "individual",
            "billing_status": "active",
        }
    return session["consumer_subscription"]


def _ensure_provider_subscription(session):
    if "provider_subscription" not in session:
        session["provider_subscription"] = {
            "tier": "premium",
            "billing_status": "active",
        }
    return session["provider_subscription"]


def get_effective_consumer_tier(tier, billing_status):
    if billing_status in {"past_due", "canceled"}:
        return "free"
    return tier if tier in CONSUMER_TIERS else "free"


def get_consumer_subscription(session):
    sub = _ensure_consumer_subscription(session)
    effective_tier = get_effective_consumer_tier(sub["tier"], sub["billing_status"])
    return {
        "selected_tier": sub["tier"],
        "billing_status": sub["billing_status"],
        "effective_tier": effective_tier,
        "plan": CONSUMER_TIERS[effective_tier],
    }


def update_consumer_subscription(session, tier, billing_status):
    if tier not in CONSUMER_TIERS:
        tier = "free"
    if billing_status not in BILLING_STATUSES:
        billing_status = "active"

    session["consumer_subscription"] = {
        "tier": tier,
        "billing_status": billing_status,
    }
    session.modified = True


def can_manage_projects(session, current_projects):
    sub = get_consumer_subscription(session)
    max_projects = sub["plan"]["max_projects"]
    if max_projects == 999:
        return True
    return current_projects < max_projects


def get_effective_provider_tier(tier, billing_status):
    if billing_status in {"past_due", "canceled"}:
        return "basic"
    return tier if tier in PROVIDER_TIERS else "basic"


def get_provider_subscription(session):
    sub = _ensure_provider_subscription(session)
    effective_tier = get_effective_provider_tier(sub["tier"], sub["billing_status"])
    return {
        "selected_tier": sub["tier"],
        "billing_status": sub["billing_status"],
        "effective_tier": effective_tier,
        "plan": PROVIDER_TIERS[effective_tier],
    }


def update_provider_subscription(session, tier, billing_status):
    if tier not in PROVIDER_TIERS:
        tier = "basic"
    if billing_status not in BILLING_STATUSES:
        billing_status = "active"

    session["provider_subscription"] = {
        "tier": tier,
        "billing_status": billing_status,
    }
    session.modified = True


def get_effective_provider_tier_for_record(provider_record):
    return get_effective_provider_tier(
        provider_record.get("tier", "basic"),
        provider_record.get("billing_status", "active"),
    )
