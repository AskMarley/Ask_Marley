# Branching and Repository Standards

## Branching Model
- main: release-ready branch
- feature/<scope>-<short-name>: feature work
- fix/<scope>-<short-name>: bug fixes
- chore/<scope>-<short-name>: maintenance/docs

## Commit Guidelines
- Keep commits focused and small.
- Use imperative subject lines.
- Include migration changes in same PR when schema changes.

## Pull Request Rules
- PR template is mandatory.
- At least one reviewer required.
- CI must pass before merge.
- No direct pushes to main.

## Definition of Ready
- Acceptance criteria clear.
- Dependencies identified.
- Test plan defined.

## Definition of Done
- Feature complete and manually validated.
- Tests added/updated and passing.
- Docs updated if behavior changed.
- Rollback path noted for risky changes.
