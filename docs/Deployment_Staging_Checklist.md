# Deployment Staging Checklist

## Goal
Produce a staging candidate that is repeatable, testable, and rollback-ready.

## 1. Pre-Deploy
- Ensure main branch is green in CI.
- Confirm migrations folder includes latest schema changes.
- Confirm `.env.example` includes any newly required environment variables.
- Tag the release candidate commit.

## 2. Build and Environment
- Create/activate virtual environment.
- Install dependencies from `requirements.txt`.
- Set required env vars:
  - `SECRET_KEY`
  - `DATABASE_URL`
  - `FLASK_ENV=production`
  - Stripe keys if billing flows need end-to-end checks

## 3. Database
- Run migrations: `flask db upgrade`.
- Seed baseline data if environment is empty: `flask seed`.
- Verify critical tables include latest columns:
  - `subscriptions.pending_plan_code`
  - `projects.service_slug`
  - `projects.location_code`

## 4. App Runtime
- Start app in staging mode.
- Verify `/health` responds successfully.
- Verify static route mapping for `/static/`.

## 5. Smoke Validation
- Run automated smoke script:
  - `python scripts/smoke_routes.py --base-url http://127.0.0.1:5000 --auth-demo-targets provider admin`
  - Expect failures if protected routes redirect to login unexpectedly.
- Manually verify key authenticated workflows:
  - Consumer clipboard create + edit project lead details
  - Provider dashboard lead queue and status transitions
  - Subscription upgrade and scheduled downgrade behavior

## 6. Backup and Recovery Readiness
- Create DB backup before deploy change window:
  - `python scripts/backup_sqlite.py`
- Confirm backup artifact exists and is restorable.

## 7. Signoff
- Record release commit SHA.
- Record migration version head.
- Confirm owner for deployment window and rollback decision.
