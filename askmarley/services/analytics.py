import csv
import io
from collections import Counter

from askmarley.services.admin_ops import get_moderation_cases, get_provider_registry
from askmarley.services.security import cache_is_fresh, utc_now
from askmarley.models import (
    ChatMessage,
    ChatThread,
    ConciergeMessage,
    Project,
    Provider,
    Subscription,
    User,
)

_ANALYTICS_CACHE = {}


def _analytics_cache_key(session):
    stats = {
        "projects": Project.query.count(),
        "providers": Provider.query.count(),
        "threads": ChatThread.query.count(),
        "messages": ChatMessage.query.count(),
        "concierge_messages": ConciergeMessage.query.count(),
        "subscriptions": Subscription.query.count(),
    }
    return "|".join(f"{key}:{value}" for key, value in sorted(stats.items()))


def _parse_postcodes(postcode_text):
    return [segment.strip() for segment in postcode_text.split(",") if segment.strip()]


def build_admin_analytics(session):
    cache_key = _analytics_cache_key(session)
    cached = _ANALYTICS_CACHE.get(cache_key)
    if cached and cache_is_fresh(cached["timestamp"], 30):
        return cached["payload"]

    projects = Project.query.all()
    provider_registry = get_provider_registry(session)
    moderation_cases = get_moderation_cases(session)

    consumers = User.query.filter(User.role.in_(("consumer", "buyer"))).all()
    consumer_tier_counts = {
        "free": 0,
        "student": 0,
        "individual": 0,
        "business": 0,
        "business-plus": 0,
    }
    for consumer in consumers:
        active_sub = (
            Subscription.query.filter_by(user_id=consumer.id)
            .order_by(Subscription.updated_at.desc())
            .first()
        )
        tier = active_sub.plan_code if active_sub else consumer.consumer_tier
        status = active_sub.status if active_sub else "active"
        effective_tier = "free" if status in {"past_due", "canceled"} else tier
        if effective_tier not in consumer_tier_counts:
            effective_tier = "free"
        consumer_tier_counts[effective_tier] += 1

    active_projects = len([project for project in projects if project.status != "archived"])
    provider_tier_counts = Counter(provider.get("tier", "basic") for provider in provider_registry)

    postcode_counter = Counter()
    for provider in provider_registry:
        for outward in _parse_postcodes(provider.get("postcodes", "")):
            postcode_counter[outward] += 1

    top_location = postcode_counter.most_common(1)[0][0] if postcode_counter else "No postcode data"
    geography_heatmap = [
        {"outward_code": code, "provider_count": count}
        for code, count in postcode_counter.most_common(5)
    ]

    concierge_messages = ConciergeMessage.query.all()
    consumer_messages = [msg for msg in concierge_messages if msg.sender == "user"]
    postcode_prompts = [
        msg for msg in concierge_messages if "Please share your UK postcode" in msg.message
    ]
    recommendation_events = [
        msg for msg in concierge_messages if "I found" in msg.message
    ]

    open_cases = len([case for case in moderation_cases if case.get("status") in {"open", "reviewing"}])
    resolved_cases = len([case for case in moderation_cases if case.get("status") == "resolved"])

    threads = ChatThread.query.all()
    thread_message_counts = [
        ChatMessage.query.filter_by(thread_id=thread.id).count() for thread in threads
    ]
    avg_messages_per_thread = (
        round(sum(thread_message_counts) / len(thread_message_counts), 1)
        if thread_message_counts
        else 0.0
    )

    payload = {
        "active_projects": active_projects,
        "student_accounts": consumer_tier_counts["student"],
        "individual_accounts": consumer_tier_counts["individual"],
        "business_accounts": consumer_tier_counts["business"],
        "business_plus_accounts": consumer_tier_counts["business-plus"],
        "free_accounts": consumer_tier_counts["free"],
        "top_location": top_location,
        "provider_tier_counts": dict(provider_tier_counts),
        "conversion_funnel": {
            "conversations_started": len(consumer_messages),
            "service_matches": len(postcode_prompts),
            "postcode_completed": len(recommendation_events),
            "projects_active": active_projects,
        },
        "moderation": {
            "open_cases": open_cases,
            "resolved_cases": resolved_cases,
        },
        "response_metrics": {
            "avg_messages_per_thread": avg_messages_per_thread,
            "active_threads": len(threads),
        },
        "geography_heatmap": geography_heatmap,
    }
    _ANALYTICS_CACHE[cache_key] = {"timestamp": utc_now(), "payload": payload}
    return payload


def build_admin_analytics_csv(session):
    analytics = build_admin_analytics(session)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["metric", "value"])
    writer.writerow(["active_projects", analytics["active_projects"]])
    writer.writerow(["student_accounts", analytics["student_accounts"]])
    writer.writerow(["individual_accounts", analytics["individual_accounts"]])
    writer.writerow(["business_accounts", analytics["business_accounts"]])
    writer.writerow(["business_plus_accounts", analytics["business_plus_accounts"]])
    writer.writerow(["free_accounts", analytics["free_accounts"]])
    writer.writerow(["top_location", analytics["top_location"]])
    writer.writerow([
        "conversations_started",
        analytics["conversion_funnel"]["conversations_started"],
    ])
    writer.writerow(["service_matches", analytics["conversion_funnel"]["service_matches"]])
    writer.writerow([
        "postcode_completed",
        analytics["conversion_funnel"]["postcode_completed"],
    ])
    writer.writerow(["open_cases", analytics["moderation"]["open_cases"]])
    writer.writerow(["resolved_cases", analytics["moderation"]["resolved_cases"]])
    writer.writerow([
        "avg_messages_per_thread",
        analytics["response_metrics"]["avg_messages_per_thread"],
    ])
    writer.writerow([""])
    writer.writerow(["outward_code", "provider_count"])
    for row in analytics["geography_heatmap"]:
        writer.writerow([row["outward_code"], row["provider_count"]])
    return output.getvalue()
