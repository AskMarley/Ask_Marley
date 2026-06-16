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

## 8. Rollback
- Revert to previous git tag/commit.
- Run `flask db downgrade` only if migration requires rollback.
- Reload web app.
