# Support Workflow and On-Call Ownership

## Scope

This document defines the minimum viable support workflow for the initial Steam launch window.

---

## Tier 1: Self-Service (Community)

All users should be directed here first:

- **In-game**: `help` command lists all available commands with descriptions.
- **README**: `README.md` covers installation, running, and first-play steps.
- **Mod/Creator docs**: `docs/content-authoring-and-mod-publishing-guidelines.md`
- **FAQ** (to be published on Steam store page and/or itch.io)

---

## Tier 2: Bug Reports

- **Channel**: GitHub Issues (or Steam Discussion for store-visible issues).
- **Template**: Players must include:
  - Platform (Windows/Android/etc.)
  - Build version (visible via `version` command in-client)
  - Steps to reproduce
  - Screenshot or log excerpt if applicable
- **Triage SLA**: Acknowledge within 48 hours of report.

---

## Tier 3: Critical Issues / On-Call

Critical issues = data loss, server crash loop, security issue, or total gameplay blocker.

### Incident Response Steps

1. **Detect**: Crash telemetry alert or user report volume spike.
2. **Assess severity**:
   - P0 = data loss or security issue → page on-call immediately
   - P1 = crash loop / unplayable → respond within 2 hours
   - P2 = degraded UX → respond within 24 hours
3. **Communicate**: Post status update to Steam Discussion / Discord within 1 hour of P0/P1 detection.
4. **Rollback if needed**: Follow `docs/save-content-isolation-policy.md` rollback procedure.
5. **Post-mortem**: Within 3 days of resolution, write a brief post-mortem documenting root cause and prevention steps.

---

## On-Call Rotation

For launch window (first 30 days post-launch):

| Week | Primary | Backup |
|------|---------|--------|
| 1    | TBD     | TBD    |
| 2    | TBD     | TBD    |
| 3    | TBD     | TBD    |
| 4    | TBD     | TBD    |

Assign names before go/no-go review.

---

## Patching and Rollback Runbook

### Patch Release Checklist

- [ ] All tests pass (`python -m unittest discover tests.singles -v`)
- [ ] Content integrity validator passes (`python toolkit/data_integrity_validator.py`)
- [ ] Reference integrity validator passes (`python toolkit/reference_integrity_validator.py`)
- [ ] Save migration steps documented and tested
- [ ] Release notes written (new features, bug fixes, breaking changes)
- [ ] Steam branch updated (staging → release)

### Emergency Rollback

1. Switch Steam depot back to previous release branch.
2. Restore server-side world save backup (pre-deployment snapshot).
3. Notify players via Steam Discussion with estimated downtime.
4. Run migration validation on restored save before reopening.

---

## Version Command

Players can always check the running build version:

```
> version
Engine: 1.0.0 | Pack: sample_world 1.0 | Build: 2026-05-04
```

This string is composed at server startup from `server/VERSION` and the active pack manifests.
