# Accessibility QA Matrix

Scope: client accessibility validation for desktop and mobile variants.

## Test Rules

- Each scenario is `Pass` or `Fail`.
- Any `Fail` in Priority 0 blocks release candidate sign-off.
- Capture device, build version, and settings profile in each report.

## Priority 0 (Release Blocking)

## A. Low Vision Readability

1. Scenario: Maximum text scale readability
- Steps:
  - Enable max text scale preset.
  - Complete core loop: connect, look, move, inspect inventory, save.
- Pass Criteria:
  - No clipped critical text.
  - Command output remains readable and scrollable.
  - Core actions remain discoverable.

2. Scenario: High contrast profile
- Steps:
  - Enable high-contrast preset.
  - Repeat core loop actions.
- Pass Criteria:
  - Critical text/UI controls remain distinguishable.
  - No essential control blends into background.

## B. Color Blindness Safety

3. Scenario: Color-independent status cues
- Steps:
  - Trigger statuses (buff/debuff/hazard/combat state).
  - Verify UI with color filter simulation (deuteranopia/protanopia/tritanopia).
- Pass Criteria:
  - Every critical status has icon/text redundancy.
  - No state requires color-only interpretation.

## C. Motion/Distortion Safety

4. Scenario: Reduced motion mode
- Steps:
  - Enable reduced motion.
  - Traverse areas with weather/effects/transitions.
- Pass Criteria:
  - Motion-heavy effects are disabled/reduced.
  - Gameplay remains fully functional.

5. Scenario: Atmospheric text effects disabled
- Steps:
  - Disable text distortion/corruption effects.
  - Trigger server metadata that would normally animate text.
- Pass Criteria:
  - Text remains plain, stable, and readable.
  - Information content is unchanged.

## D. Keyboard/Controller-Only Navigation

6. Scenario: Keyboard-only full session
- Steps:
  - Complete full session without mouse/touch.
- Pass Criteria:
  - All core actions and settings are reachable.
  - Visible focus state is always present.

7. Scenario: Controller-only core loop (desktop client)
- Steps:
  - Complete core loop using controller only.
- Pass Criteria:
  - Navigation and confirm/cancel actions are consistent.
  - No dead-end UI screens.

## Priority 1 (Required Before Public Launch)

## E. Mobile-Specific Accessibility

8. Scenario: Large text on phone form factor
- Steps:
  - Enable large-text preset on smallest supported phone profile.
- Pass Criteria:
  - No blocking overlap of command input/log/status.
  - Critical buttons remain tappable.

9. Scenario: High contrast on mobile in bright environment
- Steps:
  - Enable high-contrast profile and test outdoors/bright display setting.
- Pass Criteria:
  - Essential text and controls remain legible.

## F. Error/Recovery Accessibility

10. Scenario: Disconnect/reconnect messaging clarity
- Steps:
  - Force disconnect during active play.
  - Observe reconnect prompts and errors.
- Pass Criteria:
  - Error language is plain and actionable.
  - Focus lands on recovery action controls.

## Regression Checklist

- [ ] Text scaling still works after each UI layout change.
- [ ] High contrast still passes after theme/styling updates.
- [ ] Reduced motion still suppresses targeted effects after shader updates.
- [ ] Color-independent cues remain present after status UI changes.
- [ ] Keyboard/controller navigation still reaches all core panels after menu changes.

## Sign-Off Template

- Build:
- Platform:
- Device/Profile:
- Tester:
- Date:
- Priority 0 Result: Pass/Fail
- Priority 1 Result: Pass/Fail
- Notes:

