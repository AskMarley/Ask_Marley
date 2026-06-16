# AskMarley Week 1 Focus Execution

## Current Position (as of 2026-06-15)
- Product and UX framing: in progress
- Design system and portal shell: in progress (strong prototype present)
- Backend foundation: in progress (prototype live, modularization pending)
- Data and migrations: not started
- QA/CI/Ops baseline: not started

## Week 1 Objective
Ship a production-ready foundation by end of Friday:
1. Modular Flask architecture
2. Database schema + migrations + seed data
3. Baseline tests + linting + CI
4. Deployment-ready PythonAnywhere runbook

## Day-by-Day Focus

### Monday (Today): Product and Architecture Closure
- Finalize PRD sections: personas, journeys, success metrics, out-of-scope list
- Freeze v1 UX flows for Consumer, Provider, Admin
- Approve system architecture and entity relationship model draft
- Define branch strategy and PR checklist

Done when:
- PRD v1 approved
- Architecture diagram approved
- Backlog items created and tagged by portal

### Tuesday: Design System and App Shell Finalization
- Document all design tokens from current implementation
- Create component inventory: buttons, cards, badges, form fields, alerts, navs, chat bubbles
- Confirm responsive breakpoints and accessibility checks
- Prepare reusable template partials for common UI blocks

Done when:
- Shared UI guideline doc exists
- Portal shell pages all pass responsive smoke tests

### Wednesday: Backend Refactor to Production Structure
- Split app into package structure with app factory
- Add blueprints: consumer, provider, admin
- Move configuration to environment-based classes
- Add central error handlers and structured request logging
- Add health endpoint and basic auth scaffolding placeholders

Done when:
- App runs from package entry point
- Routes are blueprint-based
- Logs include request metadata and error traces

### Thursday: Data and Migration Baseline
- Add SQLAlchemy models for core entities
- Set up Alembic or Flask-Migrate migrations
- Create initial migration and seed script
- Seed taxonomy branches and provider tier fixtures
- Validate schema integrity and indexes for matching queries

Done when:
- Migration up/down works
- Seed command creates deterministic sample data
- Local app can read/write from database

### Friday: QA, CI, and Ops Readiness
- Add formatter/linter config and scripts
- Add unit tests for postcode parsing, intent mapping, ranking
- Add integration tests for key portal routes
- Add GitHub Actions CI pipeline
- Write PythonAnywhere deployment and rollback runbook

Done when:
- CI is green on push
- Tests run locally and in CI
- Deployment checklist is actionable end-to-end

## Priority Risks This Week
- Scope creep from Week 2 features before foundation is stable
- Delayed database work causing downstream blockers
- Missing CI and tests reducing confidence for deployment

## Mitigation
- Freeze Week 1 scope and park all non-foundation asks
- Finish data model by Thursday midday
- Make CI mandatory before merging

## Daily Standup Template
- Yesterday completed:
- Today focus:
- Blockers:
- Risk level (Low/Medium/High):
- Need help from:
