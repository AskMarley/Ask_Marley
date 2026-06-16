# Secret Management Baseline

## Required Secrets
- SECRET_KEY
- DATABASE_URL

## Local Development
- Copy .env.example to .env
- Populate .env with non-default values
- Never commit .env to version control

## PythonAnywhere
- Set environment variables in web app configuration or WSGI file.
- Rotate SECRET_KEY on compromise or admin turnover.

## Secret Hygiene Rules
- Do not hardcode secrets in source files.
- Do not print secrets to logs.
- Restrict access to deployment accounts.
- Rotate secrets at least quarterly for production.

## Incident Procedure
- Revoke compromised key immediately.
- Roll new key and redeploy.
- Review audit logs and suspicious access windows.
