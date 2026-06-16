import re
from collections import Counter

from askmarley.data import PROVIDERS, SERVICE_INTENTS, TIER_PRIORITY
from askmarley.services.subscriptions import get_effective_provider_tier_for_record

UK_POSTCODE_PATTERN = re.compile(
    r"^([A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2})$",
    re.IGNORECASE,
)


def get_outward_code(postcode):
    normalized = normalize_uk_postcode(postcode)
    return normalized.split()[0]


def normalize_uk_postcode(postcode):
    compact = re.sub(r"\s+", "", postcode.upper())
    if len(compact) < 5:
        return compact
    return f"{compact[:-3]} {compact[-3:]}"


def split_postcode_parts(postcode):
    normalized = normalize_uk_postcode(postcode)
    if " " in normalized:
        outward, inward = normalized.split(" ", 1)
    else:
        outward, inward = normalized, ""
    return outward, inward


def is_valid_uk_postcode(postcode):
    normalized = normalize_uk_postcode(postcode.strip())
    return bool(UK_POSTCODE_PATTERN.match(normalized))


def detect_service_details(message):
    lowered = message.lower()
    match_scores = {}
    for slug, intent in SERVICE_INTENTS.items():
        score = sum(1 for keyword in intent["keywords"] if keyword in lowered)
        if score:
            match_scores[slug] = score

    if not match_scores:
        return {
            "service_slug": None,
            "confidence": 0.0,
            "ambiguous": False,
            "options": [],
        }

    ranked = Counter(match_scores).most_common()
    total_score = sum(match_scores.values())
    top_slug, top_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0
    confidence = round(top_score / total_score, 2)
    ambiguous = second_score == top_score or confidence < 0.45
    options = [slug for slug, _score in ranked[:3]]
    return {
        "service_slug": top_slug,
        "confidence": confidence,
        "ambiguous": ambiguous,
        "options": options,
    }


def detect_service(message):
    return detect_service_details(message)["service_slug"]


def find_matching_providers(service_slug, postcode):
    outward, _inward = split_postcode_parts(postcode)
    matches = [
        provider
        for provider in PROVIDERS
        if provider["service_slug"] == service_slug and outward in provider["postcodes"]
    ]

    enriched_matches = []
    for provider in matches:
        effective_tier = get_effective_provider_tier_for_record(provider)
        enriched = dict(provider)
        enriched["effective_tier"] = effective_tier
        if effective_tier != "premium":
            enriched["marleys_choice"] = False
        enriched_matches.append(enriched)

    return sorted(
        enriched_matches,
        key=lambda p: (
            TIER_PRIORITY[p["effective_tier"]],
            p["verified"],
            p.get("activity_score", 0),
            p["name"].lower(),
        ),
        reverse=True,
    )
