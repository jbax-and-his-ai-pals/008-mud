# Phase 5: Steam Launch Readiness

## Goal

Ship a stable Engine + Toolkit product on Steam with sample packs and support-ready operations.

## Checklist

- [ ] Finalize legal/privacy/account policies.
- [ ] Finalize Steam packaging/depot strategy and release branches.
- [ ] Finalize mobile store packaging/signing strategy (Android and/or iOS).
- [x] Implement entitlement and product gating hooks.
- [x] Add patching, rollback, and incident response runbooks.
- [x] Complete load and soak testing.
- [x] Define support workflow and on-call ownership.
- [x] Finalize onboarding/tutorial flow for creators.
- [ ] Finalize sample game catalog included in release.
- [ ] Complete accessibility sign-off (visual impairment test matrix pass).
- [x] Final launch checklist and go/no-go review.
- [ ] Finalize world-mode release matrix and support tiers (finite/co-op/persistent).
- [ ] Finalize operator diagnostics bundle and incident playbooks for profile/provider/world-mode failures.
- [ ] Finalize compatibility SLA for engine/protocol/pack upgrades.

## Exit Gate

- [ ] Release candidate passes technical, legal, operational, distribution, accessibility, and multi-mode compatibility gates.

## Evidence

- Entitlement guard + session gating: [entitlement.py](../../server/engine/server/entitlement.py)
- Load and soak test suite: [test_load_soak.py](../../server/tests/singles/test_load_soak.py)
- Support workflow and on-call runbook: [support-workflow.md](../support-workflow.md)
- Patching and rollback policy: [support-workflow.md](../support-workflow.md)
- Save content-isolation policy: [save-content-isolation-policy.md](../save-content-isolation-policy.md)
- Onboarding and tutorial flow: [onboarding-tutorial-flow.md](../onboarding-tutorial-flow.md)
- Final launch checklist: [launch-checklist.md](../launch-checklist.md)
