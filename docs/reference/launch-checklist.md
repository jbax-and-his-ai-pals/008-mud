# Final Launch Checklist

> **Go/No-Go review gate.** All Priority 0 items must be checked before a release candidate is approved.

---

## P0: Technical Gates (Release Blocking)

### Engine & Server
- [ ] All `tests/singles` and `tests/batch` pass with exit code 0.
- [ ] `toolkit/data_integrity_validator.py` reports 0 errors on bundled data.
- [ ] `toolkit/reference_integrity_validator.py` reports 0 errors on bundled data.
- [ ] Load/soak tests pass (`test_load_soak.py` — all scenarios green).
- [ ] No known P0 or P1 open issues in the tracker.
- [ ] Save migration steps tested end-to-end on a production-equivalent save.
- [ ] Entitlement gates validated for all product SKUs.

### Client
- [ ] Client connects successfully to bundled local server and a remote test server.
- [ ] Offline single-player mode works without network.
- [ ] Suspend/resume lifecycle (mobile) tested on target devices.
- [ ] Crash telemetry opt-in flow works and emits correctly.

---

## P0: Operational Gates (Release Blocking)

- [ ] On-call rotation assigned and acknowledged for the launch window.
- [ ] Rollback procedure rehearsed (dry-run on staging save).
- [ ] Support channels open and triaged (GitHub Issues, Steam Discussion).
- [ ] Server monitoring/alerting active on live infrastructure (if applicable).
- [ ] Steam depot and branch configuration verified in Steamworks.

---

## P0: Legal / Privacy Gates (Release Blocking)

- [ ] Privacy policy published and linked from the Steam store page.
- [ ] Terms of service reviewed and published.
- [ ] Telemetry opt-in flow reviewed by legal.
- [ ] Third-party license notices included in install (`NOTICES.txt`).
- [ ] GDPR/CCPA data handling policy reviewed (if collecting any user data).

---

## P0: Accessibility Gate (Release Blocking)

- [ ] Priority 0 scenarios in `docs/roadmap/accessibility-qa-matrix.md` pass on desktop.
- [ ] Priority 0 scenarios pass on the smallest supported mobile form factor.
- [ ] Sign-off template completed and archived in `docs/roadmap/evidence/`.

---

## P1: Required Before Public Launch

### Distribution
- [ ] Steam install layout finalized (`MUD Client`, `Engine + Toolkit`, `Sample Worlds`).
- [ ] Mod folder conventions documented and enforced by installer.
- [ ] Update-safe user content directory defined and tested.
- [ ] Save content-isolation policy published (`docs/save-content-isolation-policy.md`).
- [ ] Workshop strategy decided (if used).

### Quality
- [ ] Onboarding/tutorial flow verified end-to-end (`docs/onboarding-tutorial-flow.md`).
- [ ] Sample game catalog reviewed and bundled.
- [ ] Accessibility Priority 1 scenarios pass.
- [ ] Controller/keyboard UX baseline passes for toolkit launch flow.

### Mobile (if in scope)
- [ ] Android store pipeline, signing, and release channel verified.
- [ ] Mobile performance/battery budgets met on target devices.
- [ ] iOS pipeline verified (if in scope).

---

## Final Sign-Off

| Gate       | Status    | Reviewer | Date |
|------------|-----------|----------|------|
| Technical  | ☐ Pass / ☐ Fail | | |
| Operational| ☐ Pass / ☐ Fail | | |
| Legal      | ☐ Pass / ☐ Fail | | |
| Accessibility | ☐ Pass / ☐ Fail | | |
| **Go/No-Go Decision** | **☐ GO / ☐ NO-GO** | | |

---

> A NO-GO on any P0 gate blocks release. Document the specific failing items, assign owners, and schedule a follow-up review date.
