# PythonAnywhere Deployment Runbook

## 1. Create PythonAnywhere Web App
- Create a new manual Python web app.
- Select Python 3.12+ runtime.

## 2. Upload Code
- Clone repository into home directory.
- Create virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 3. Configure Environment Variables
Set these in PythonAnywhere web app settings or WSGI file:
- SECRET_KEY
- DATABASE_URL
- FLASK_ENV=production

## 4. Configure WSGI File
Point to app factory via entrypoint module.

```python
import sys
path = '/home/yourusername/AskMarley'
if path not in sys.path:
    sys.path.append(path)

from flask_app import app as application
```

## 5. Prepare Database
Run migrations and seed data:

```bash
export FLASK_APP=flask_app.py
flask db upgrade
flask seed
```

## 6. Static Assets
- Ensure static folder is mapped in web app static files settings:
  - URL: /static/
  - Directory: /home/yourusername/AskMarley/static

## 7. Smoke Tests
- GET /
- GET /consumer/chat
- GET /provider/dashboard
- GET /admin/dashboard
- GET /health

Automated option:

```bash
python scripts/smoke_routes.py --base-url http://127.0.0.1:5000 --auth-demo-targets provider admin
```

Notes:
- Route checks now fail when a path redirects to an unexpected destination (for example, a login page).
- `--auth-demo-targets provider admin` verifies provider/admin dashboards as authenticated pages using demo accounts.

## 8. Rollback
- Revert to previous git tag/commit.
- Run `flask db downgrade` only if migration requires rollback.
- Reload web app.

## 9. Local Backup Step (Before Risky Changes)

```bash
python scripts/backup_sqlite.py
```

## 10. Related Operational Documents
- `docs/Deployment_Staging_Checklist.md`
- `docs/Incident_Response_Playbook.md`
- `docs/Launch_Handover_Checklist.md`
