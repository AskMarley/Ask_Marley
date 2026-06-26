# Incident Response Playbook

## Severity Levels
- Sev 1: Full outage or security incident impacting all users.
- Sev 2: Core workflow broken for one portal (consumer/provider/admin).
- Sev 3: Partial degradation with workaround available.

## Initial Response (First 15 Minutes)
- Acknowledge incident in team channel.
- Assign incident commander.
- Capture:
  - first seen timestamp
  - impacted routes/features
  - latest deploy SHA
- Freeze non-essential deployments.

## Triage Checklist
- Check app health endpoint: `/health`.
- Run smoke checks:
  - `python scripts/smoke_routes.py --base-url <target>`
  - `python scripts/smoke_routes.py --base-url <target> --auth-demo-targets provider admin`
  - Treat unexpected redirects to login as failures unless intentionally allowed.
- Review latest logs for stack traces and repeated 5xx errors.
- Identify if issue is code, config, dependency, or data.

## Mitigation Paths
- Code regression:
  - Roll back to previous stable commit/tag.
- Data/schema issue:
  - Validate migration state.
  - Restore from latest backup if required.
- Config/secrets issue:
  - Correct env var values and restart app.

## Communication
- Update status every 15 minutes for Sev 1/2.
- Include customer-facing impact and ETA in updates.
- Close incident only after:
  - service stable for agreed observation window
  - root cause documented

## Post-Incident Review
- Record timeline of actions and decisions.
- Document root cause and blast radius.
- Add preventive action items with owners and due dates.
