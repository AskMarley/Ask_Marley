import csv
import io
import json
from collections import Counter

from askmarley.services.admin_ops import get_moderation_cases, get_provider_registry
from askmarley.services.collaboration import get_projects
from askmarley.services.security import cache_is_fresh, utc_now
from askmarley.services.subscriptions import (
    get_consumer_subscription,
    get_provider_subscription,
)

_ANALYTICS_CACHE = {}


def _analytics_cache_key(session):
    snapshot = {
        "projects": session.get("clipboard_projects", []),
        "provider_registry": session.get("provider_registry", []),
        "moderation_cases": session.get("moderation_cases", []),
        "consumer_subscription": session.get("consumer_subscription", {}),
        "provider_subscription": session.get("provider_subscription", {}),
        "chat_log": session.get("chat_log", []),
        "project_threads": session.get("project_threads", {}),
    }
    return json.dumps(snapshot, sort_keys=True, default=str)


def _parse_postcodes(postcode_text):
    return [segment.strip() for segment in postcode_text.split(",") if segment.strip()]


def build_admin_analytics(session):
    cache_key = _analytics_cache_key(session)
    cached = _ANALYTICS_CACHE.get(cache_key)
    if cached and cache_is_fresh(cached["timestamp"], 30):
        return cached["payload"]

    projects = get_projects(session)
    provider_registry = get_provider_registry(session)
    moderation_cases = get_moderation_cases(session)
    consumer_sub = get_consumer_subscription(session)
    provider_sub = get_provider_subscription(session)
    chat_log = session.get("chat_log", [])
    project_threads = session.get("project_threads", {})

    active_projects = len([project for project in projects if project.get("status") != "archived"])

    consumer_tier_counts = {
        "free": 0,
        "student": 0,
        "individual": 0,
        "business": 0,
        "business-plus": 0,
    }
    consumer_tier_counts[consumer_sub["effective_tier"]] += 1

    provider_tier_counts = Counter(provider.get("tier", "basic") for provider in provider_registry)
    provider_tier_counts[provider_sub["effective_tier"]] += 1

    postcode_counter = Counter()
    for provider in provider_registry:
        for outward in _parse_postcodes(provider.get("postcodes", "")):
            postcode_counter[outward] += 1

    top_location = postcode_counter.most_common(1)[0][0] if postcode_counter else "No postcode data"
    geography_heatmap = [
        {"outward_code": code, "provider_count": count}
        for code, count in postcode_counter.most_common(5)
    ]

    consumer_messages = [msg for msg in chat_log if msg.get("sender") == "user"]
    postcode_prompts = [
        msg for msg in chat_log if "Please share your UK postcode" in msg.get("text", "")
    ]
    recommendation_events = [
        msg for msg in chat_log if "I found" in msg.get("text", "providers near")
    ]

    open_cases = len([case for case in moderation_cases if case.get("status") in {"open", "reviewing"}])
    resolved_cases = len([case for case in moderation_cases if case.get("status") == "resolved"])

    thread_message_counts = [
        len(thread.get("messages", [])) for thread in project_threads.values() if thread.get("messages")
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
            "active_threads": len(project_threads),
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
