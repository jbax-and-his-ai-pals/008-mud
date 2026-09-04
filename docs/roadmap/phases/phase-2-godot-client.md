# Phase 2: Client (Desktop+Mobile Base) + Toolkit + Mod SDK Foundation

## Goal

Build the shipped player client (desktop baseline with mobile-ready architecture) and creator-facing toolkit/mod SDK on top of the runtime foundation.

## Checklist

- [x] Create player client shell (Godot) with connect/login/character-select flow.
- [x] Implement 1-bit presentation baseline (SubViewport + 1-bit post-process style path).
- [x] Add subtle atmosphere baseline (weather shader pass and ambient audio channel).
- [x] Implement core gameplay UX in client (command input, log, status, inventory, quest views).
- [x] Implement visual accessibility baseline (text scaling, contrast presets, reduced-effects toggles).
- [x] Implement GUI-first input translation to canonical MUD command stream.
- [x] Implement reconnect/session-resume handling in client.
- [x] Add protocol version negotiation and compatibility warnings in client.
- [x] Add client platform abstraction layer for desktop input and mobile touch/lifecycle.
- [x] Define mobile layout profile and constraints for phone/tablet.
- [x] Define pack manifest and schema validator (`theme-pack-spec-v1`).
- [x] Build toolkit commands for validate/build/export pack.
- [x] Define extension API surface for safe gameplay hooks.
- [x] Implement capability-based mod permission model.
- [x] Add failure-safe load path for invalid mods.
- [x] Ship first toolkit docs and starter templates.
- [x] Build RichTextEffect template for server-driven atmospheric text corruption.
- [ ] Add client UX modes for finite-adventure progress, ending states, and post-run summaries.
- [ ] Add co-op party UX primitives (party panel, shared objectives, loot/reward policy affordances).
- [ ] Add compatibility preflight in toolkit for pack dependency and engine-version checks.
- [ ] Add migration assist commands for pack schema/runtime contract upgrades.

## Exit Gate

- [ ] Playable client is shippable for desktop core loop, accessibility baseline is verified, mobile architecture is validated, and users can create/validate/load custom packs with compatibility checks and migration guidance.
