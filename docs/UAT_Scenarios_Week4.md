# Week 4 UAT Scenarios

## Goal
Validate end-to-end behavior across Consumer, Provider, and Admin portals before deployment.

## Consumer UAT
1. Open Consumer Chat and describe a plumbing problem.
Expected: Marley identifies Emergency Plumbers and asks for postcode.
2. Enter a valid UK postcode.
Expected: ranked providers appear with badges and coverage.
3. Enter an invalid postcode.
Expected: friendly validation prompt appears.
4. Use Manual Search with a keyword and branch filter.
Expected: filtered categories render with empty state when appropriate.
5. Create a project on Clipboard under a paid tier.
Expected: project appears immediately.
6. Switch to Free plan and try to save a provider or open project chat.
Expected: access blocked with upgrade prompt.
7. Post a message in project chat and add a thread pin.
Expected: message and pin appear with unread counters.
8. Report a project chat message.
Expected: success flash appears and admin moderation queue receives a case.

## Provider UAT
1. Open Provider Dashboard.
Expected: lead cards, service mapping, subscription info, and active conversation summary render.
2. Change provider subscription to past_due.
Expected: effective tier degrades and premium benefits disappear.
3. Review conversation summary after consumer sends a project message.
Expected: unread counter increments.

## Admin UAT
1. Open Admin Dashboard.
Expected: analytics, moderation queue, taxonomy manager, and audit trail all render.
2. Verify a provider.
Expected: provider status updates and audit entry records before/after state.
3. Override provider tier.
Expected: success flash and audit trail update.
4. Suspend then reactivate a provider.
Expected: status transitions and audit trail update.
5. Change moderation case status.
Expected: case status updates immediately.
6. Add a valid taxonomy path.
Expected: entry appears with version 1.
7. Attempt invalid taxonomy path with fewer than 3 levels.
Expected: validation error shown.
8. Edit and deprecate a taxonomy entry.
Expected: version history records changes.
9. Export analytics CSV.
Expected: CSV downloads with metric/value rows.

## Sign-off Criteria
- No P0 defects.
- No open P1 security issues.
- All critical routes return 200/expected validation status.
- UAT owner signs off each portal.
