# AskMarley PRD v1

## Product Vision
AskMarley is a UK local-services directory with a messaging-first concierge experience led by Marley.

## Objectives
- Reduce time-to-match for users seeking local services.
- Improve trust with verification and moderation tooling.
- Monetize through consumer and provider tiered subscriptions.

## Personas
- Consumer: homeowner, renter, student, landlord, estate manager.
- Provider: tradesperson and local service businesses.
- Super Admin: operations and trust/safety team.

## Portal Scope (v1)
- Consumer portal: chat matching, manual search, clipboard projects, provider messaging.
- Provider portal: service mapping, postcode coverage, lead inbox, quote workflow.
- Admin portal: verification, tier override, moderation queue, taxonomy manager, analytics snapshot.

## Non-Goals (Week 1)
- Full payment gateway production integration.
- Advanced ML intent model.
- Native mobile apps.

## Success Metrics (Initial)
- Median time to first provider recommendation under 30 seconds.
- Intent recognition success over 80% in seeded scenarios.
- Provider response initiation under 15 minutes (pilot target).
- Zero high-severity moderation backlog older than 24 hours.

## Functional Requirements (v1)
- UK postcode validation and matching by coverage.
- Tier-based provider ranking and badges.
- Consumer project limits enforced by subscription tier.
- Admin action auditability for provider lifecycle changes.

## Risks
- Taxonomy quality impacts matching relevance.
- Incomplete moderation tooling affects trust.
- Subscription complexity may delay launch if over-scoped.
