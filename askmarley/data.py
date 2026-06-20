SERVICE_INTENTS = {
    "emergency-plumber": {
        "name": "Emergency Plumbers",
        "keywords": ["leak", "leaky", "pipe", "boiler", "plumb", "flood"],
        "branch": "Home Trades > Plumbing > Emergency Repair",
    },
    "cleaner": {
        "name": "Domestic Cleaners",
        "keywords": ["clean", "cleaner", "housekeeping", "deep clean"],
        "branch": "Home Services > Cleaning > Domestic",
    },
    "electrician": {
        "name": "Electricians",
        "keywords": ["socket", "wiring", "fuse", "electric", "lights"],
        "branch": "Home Trades > Electrical > Repairs",
    },
    "roofer": {
        "name": "Roofers",
        "keywords": ["roof", "roofing", "tile", "gutter", "chimney", "flashing"],
        "branch": "Home Trades > Roofing > Repairs",
    },
    "wedding-planner": {
        "name": "Wedding Planners",
        "keywords": ["wedding", "venue", "planner", "bridal"],
        "branch": "Events > Weddings > Planning",
    },
    "gardener": {
        "name": "Gardeners",
        "keywords": ["garden", "lawn", "hedge", "landscape", "grass"],
        "branch": "Outdoor Services > Gardening > Maintenance",
    },
    "dog-walker": {
        "name": "Dog Walkers",
        "keywords": ["dog", "pet", "walker", "walk"],
        "branch": "Pet Care > Dog Services > Walking",
    },
}

PROVIDERS = [
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
    },
    {
        "id": 2,
        "name": "Capital Boiler Rescue",
        "service_slug": "emergency-plumber",
        "postcodes": ["SW1A", "E1", "N1"],
        "tier": "plus",
        "billing_status": "active",
        "verified": True,
        "marleys_choice": False,
        "activity_score": 78,
    },
    {
        "id": 3,
        "name": "Albion Spark Works",
        "service_slug": "electrician",
        "postcodes": ["SE1", "E1", "W1"],
        "tier": "plus",
        "billing_status": "grace",
        "verified": False,
        "marleys_choice": False,
        "activity_score": 64,
    },
    {
        "id": 4,
        "name": "Summit Roofing Response",
        "service_slug": "roofer",
        "postcodes": ["SW1A", "SE1", "E1"],
        "tier": "plus",
        "billing_status": "active",
        "verified": True,
        "marleys_choice": False,
        "activity_score": 67,
    },
    {
        "id": 5,
        "name": "North Star Domestic Care",
        "service_slug": "cleaner",
        "postcodes": ["N1", "N4", "E1"],
        "tier": "basic",
        "billing_status": "active",
        "verified": True,
        "marleys_choice": False,
        "activity_score": 55,
    },
    {
        "id": 6,
        "name": "Westminster Moments",
        "service_slug": "wedding-planner",
        "postcodes": ["SW1A", "W1", "NW1"],
        "tier": "premium",
        "billing_status": "active",
        "verified": True,
        "marleys_choice": True,
        "activity_score": 88,
    },
    {
        "id": 7,
        "name": "Thames Garden Collective",
        "service_slug": "gardener",
        "postcodes": ["SE1", "SW1A", "W1"],
        "tier": "plus",
        "billing_status": "active",
        "verified": True,
        "marleys_choice": False,
        "activity_score": 73,
    },
    {
        "id": 8,
        "name": "Paws Across London",
        "service_slug": "dog-walker",
        "postcodes": ["N1", "E1", "NW1"],
        "tier": "basic",
        "billing_status": "past_due",
        "verified": True,
        "marleys_choice": False,
        "activity_score": 61,
    },
]

TIER_PRIORITY = {
    "premium": 3,
    "plus": 2,
    "basic": 1,
}

CONSUMER_TIERS = {
    "free": {"label": "Free", "max_projects": 0, "price": "\u00a30"},
    "student": {"label": "Student", "max_projects": 1, "price": "\u00a32.99/mo"},
    "individual": {"label": "Individual", "max_projects": 3, "price": "\u00a34.99/mo"},
    "business": {"label": "Business", "max_projects": 10, "price": "\u00a39.99/mo"},
    "business-plus": {"label": "Business Plus", "max_projects": 999, "price": "\u00a319.99/mo"},
}

PROVIDER_TIERS = {
    "basic": {
        "label": "Basic",
        "price": "\u00a33/mo",
        "portfolio_images": 0,
        "priority": "low",
    },
    "plus": {
        "label": "Plus",
        "price": "\u00a315/mo",
        "portfolio_images": 6,
        "priority": "medium",
    },
    "premium": {
        "label": "Premium",
        "price": "\u00a350/mo",
        "portfolio_images": 20,
        "priority": "highest",
    },
}

BILLING_STATUSES = {
    "active": "Active",
    "grace": "Grace Period",
    "past_due": "Past Due",
    "canceled": "Canceled",
}

PROVIDER_SIGNUPS = [
    {
        "name": "Prime Heating Guild",
        "service_path": "Home Trades > Plumbing > Boiler Servicing",
        "postcodes": "E1, E2, E3",
        "status": "pending",
    },
    {
        "name": "Hearth & Home Clean",
        "service_path": "Home Services > Cleaning > Domestic",
        "postcodes": "SW1A, SW3",
        "status": "pending",
    },
]

FLAGGED_CHATS = [
    {
        "case_id": "AUD-1043",
        "reason": "Abusive language detected",
        "participants": "User #771 and Provider #22",
        "severity": "high",
    },
    {
        "case_id": "AUD-1049",
        "reason": "Quote dispute escalation",
        "participants": "User #198 and Provider #05",
        "severity": "medium",
    },
]

TAXONOMY = [
    "Home Trades > Plumbing > Emergency Repair",
    "Home Trades > Electrical > Repairs",
    "Home Trades > Roofing > Repairs",
    "Home Services > Cleaning > Domestic",
    "Events > Weddings > Planning",
]
