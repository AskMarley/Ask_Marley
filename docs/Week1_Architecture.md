# AskMarley Week 1 Architecture Snapshot

## Runtime
- Framework: Flask
- Hosting target: PythonAnywhere
- Entrypoint: flask_app.py
- App style: app factory + blueprints

## Structure
- askmarley/__init__.py: create_app and CLI registration
- askmarley/config.py: environment-specific config
- askmarley/extensions.py: SQLAlchemy and Migrate extension instances
- askmarley/models.py: core relational models
- askmarley/blueprints/: portal route modules
- askmarley/services/matching.py: intent/postcode/provider matching logic
- askmarley/seed.py: seed command for baseline taxonomy/provider data

## Blueprints
- main: home and health routes
- consumer: chat, manual search, clipboard routes
- provider: provider dashboard route
- admin: admin dashboard + actions route

## Data Layer
- SQLAlchemy models for users, providers, coverages, categories, projects, chat, subscriptions, audits, taxonomy
- Alembic migrations initialized in migrations/
- Initial migration generated and applied

## Operational Baseline
- Tests in tests/ using pytest
- CI workflow in .github/workflows/ci.yml
- PythonAnywhere deployment runbook in docs/PythonAnywhere_Deployment_Runbook.md

## Next Technical Step (Week 2 Start)
- Move in-memory demo datasets to database reads/writes in route handlers
- Add auth and role enforcement
- Replace session-only chat log with persisted chat entities
