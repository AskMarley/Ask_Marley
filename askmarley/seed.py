from askmarley.data import PROVIDERS, SERVICE_INTENTS, TAXONOMY
from askmarley.extensions import db
from askmarley.models import Provider, ProviderCoverage, ServiceCategory, TaxonomyEntry


def seed_baseline_data():
    if ServiceCategory.query.first():
        return

    for slug, intent in SERVICE_INTENTS.items():
        db.session.add(
            ServiceCategory(
                slug=slug,
                name=intent["name"],
                branch_path=intent["branch"],
            )
        )

    for provider in PROVIDERS:
        p = Provider(
            name=provider["name"],
            service_slug=provider["service_slug"],
            tier=provider["tier"],
            verified=provider["verified"],
            marleys_choice=provider["marleys_choice"],
        )
        db.session.add(p)
        db.session.flush()
        for outward in provider["postcodes"]:
            db.session.add(ProviderCoverage(provider_id=p.id, outward_code=outward))

    for branch in TAXONOMY:
        db.session.add(TaxonomyEntry(branch_path=branch))

    db.session.commit()
