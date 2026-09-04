# Accessibility Track (Visual Impairment First)

Accessibility is a release-blocking quality bar across desktop and mobile clients.

Reference QA matrix:
- [Accessibility QA Matrix](C:/python/old/restart/docs/roadmap/accessibility-qa-matrix.md)

## Core Principles

- Accessibility is opt-out, not hidden.
- Visual information must have non-visual or high-clarity alternatives.
- No gameplay-critical state should rely on color alone.

## Visual Impairment Priorities

## A1: Text Legibility Baseline

- [x] Full UI text scaling with sensible min/max presets.
- [x] Dyslexia-friendly and high-legibility font options.
- [x] Adjustable line spacing and text density presets.
- [x] Minimum contrast policy for all text surfaces.

Exit:
- [x] Core gameplay loop is readable at all supported scale presets.

## A2: High Contrast + Color Safety

- [x] Built-in high-contrast themes (light and dark).
- [ ] Color-blind-safe palettes for status/effects.
- [x] Replace color-only indicators with icon/text redundancies.
- [ ] 1-bit style remains readable with accessibility overlays enabled.

Exit:
- [ ] No gameplay-critical meaning depends on color-only cues.

## A3: Motion/Effects Safety

- [x] Toggle and intensity slider for atmospheric text distortion effects.
- [x] Toggle and intensity slider for weather/screen shaders.
- [x] Reduced motion mode for transitions/animations.
- [x] Per-effect disable switches for flicker-prone visuals.

Exit:
- [x] Users can fully play with minimal motion and minimal distortion.

## A4: Assistive Output and Navigation

- [x] Screen-reader-friendly metadata output mode where feasible.
- [ ] Keyboard-only navigation coverage for all primary views.
- [ ] Controller navigation parity for all primary views.
- [ ] Clear focus indicators and navigation landmarks.

Exit:
- [ ] Session can be completed without mouse/touch precision requirements.

## A5: Validation and QA

- [ ] Accessibility test matrix (desktop + mobile).
- [ ] Manual scenario scripts for low-vision and high-contrast workflows.
- [ ] Regression tests for text scaling and contrast policy checks.
- [ ] Release checklist includes accessibility gate sign-off.

Exit:
- [ ] Accessibility gates pass before release candidate is approved.

Evidence:
- Text scaling presets + runtime application: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- High-contrast/low-vision/screen-reader presets: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- Color-independent status markers (`[DEAD]`, `[CRIT]`, `[OOM]`): [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- Reduced-motion capability propagation: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
- Screen-reader metadata mode and alt-text-first asset handling: [main_controller.gd](C:/python/old/restart/client/scripts/ui/main_controller.gd)
