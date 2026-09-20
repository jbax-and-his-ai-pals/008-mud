# archive/

**What was decided before.** Superseded plans, completed phases, abandoned tracks
and history. Nothing here is maintained, built, run, or read by any gate.

| Document | Was | Superseded by |
|---|---|---|
| [`roadmap-2026-09-narratives.md`](roadmap-2026-09-narratives.md) | The P0–P9 phase bodies and both hardening batches — what each phase set out to do and what was found | [`../plan/integrated-roadmap.md`](../plan/integrated-roadmap.md) for what is next; `ROADMAP.md` for the live open items, which were extracted before this was cut |
| [`archive-2026-09.md`](archive-2026-09.md) | The roadmap as it stood before the 2026-09-14 rewrite | everything since |
| [`roadmap-README-superseded.md`](roadmap-README-superseded.md) | The old `docs/roadmap/` index | [`../README.md`](../README.md) |
| [`content-engine-roadmap.md`](content-engine-roadmap.md) | The original product charter and the engine/content boundary rationale | still worth reading for the boundary argument |
| [`next-session.md`](next-session.md), [`HANDOFF.md`](HANDOFF.md), [`handoff-2026-05-04.md`](handoff-2026-05-04.md), [`handoff-2026-09-18-cross-theme-contracts.md`](handoff-2026-09-18-cross-theme-contracts.md) | Session handoff logs | — |
| [`phases/`](phases/) | The six-slice build plan (baseline, headless server, Godot client, multi-theme samples, ecosystem hardening, commercial readiness) | completed or re-scoped; three of them are 20–45-line skeletons |
| [`adr/0000-template.md`](adr/0000-template.md) | The unused ADR template | **still usable** — Track K proposes adopting it, capped at one page |
| [`adr/0002-gmcp-package-contract.md`](adr/0002-gmcp-package-contract.md) | An **Accepted** ADR for a GMCP protocol with zero hits in the server, plus [`mudlet-gmcp-README.md`](mudlet-gmcp-README.md) documenting six handlers for it | nothing — 383 lines of spec for unimplemented work. Kept because it is a design somebody may want back |
| [`world-editor-track.md`](world-editor-track.md), [`world-editor-gap-matrix.md`](world-editor-gap-matrix.md), [`world-editor-evaluation.md`](world-editor-evaluation.md), [`editor-content-source.md`](editor-content-source.md) | The editor's own planning docs | [`../plan/track-roadmaps/track-G-world-editor.md`](../plan/track-roadmaps/track-G-world-editor.md), which judged them and named what is now stale |
| [`party-lifecycle-contract.md`](party-lifecycle-contract.md), [`persistent-shard-contract.md`](persistent-shard-contract.md), [`finite-adventure-contract.md`](finite-adventure-contract.md) | Contracts for features that are not built | — |
| [`mobile-track.md`](mobile-track.md), [`client-track.md`](client-track.md), [`accessibility-track.md`](accessibility-track.md), [`accessibility-qa-matrix.md`](accessibility-qa-matrix.md), [`steam-packaging-track.md`](steam-packaging-track.md), [`server-setup-wizard-track.md`](server-setup-wizard-track.md) | Surface tracks | live as **surfaces** — they consume the engine and can run whenever, they are just not scheduled |
| [`engine-capability-track.md`](engine-capability-track.md) | Runtime capability targets | partly built; its capability *target* list is still the right list |
| [`documentation-track.md`](documentation-track.md), [`documentation-information-architecture.md`](documentation-information-architecture.md) | Two attempts at organising documentation | this folder's structure and [`../README.md`](../README.md) |
| [`deterministic-harness.md`](deterministic-harness.md) | Evidence note | — |

## One correction that has to be visible before you use them

[`HANDOFF.md`](HANDOFF.md) documents test suites that do not exist. It credits
`test_crash_recovery.py`, `test_onboarding.py`, `test_keybindings.py`,
`test_launcher_scene.py`, `test_client_a11y_presets.py` and
`test_client_theme_packs.py` with 24, 24, 37, 24, 15 and 27 tests — 163 in total —
and prescribes running them together at `:71-76`. Every one of those files was
committed **empty** in `e2c0638`, and its `:110` proposes installing `msgpack` to
"activate" eight skipped tests in a `test_msgpack_transport.py` that was empty
too. Its command line would have collected 0 tests each and reported OK.

This is the document's only actively misleading part, so it is called out here
rather than edited there. What replaced them, and what was deleted as redundant,
is recorded under **"2. Give the empty modules a verdict"** of
[`../plan/track-roadmaps/track-H-testing.md`](../plan/track-roadmaps/track-H-testing.md).

## Why these are here rather than deleted

Three reasons, in order of how often they apply:

1. **The reasoning is the useful part.** `roadmap-2026-09-narratives.md` records
   not just what was built but what was found on the way — the defects, the
   dead ends, and the audit that produced the current checks. `ROADMAP.md`'s audit
   reference points into it.
2. **A decision may come back.** `adr/0002` is a full design for a protocol nobody
   implemented. If someone wants GMCP later, that document is the head start.
3. **A track can see it exists.** `git log` is not an archive: code nobody can
   find is code nobody remembers. That is why `archive/` is a visible folder at
   the repo root rather than a branch.

## The rule

**Archived documents do not grow.** A correction, an improvement or a port is a
reason to revive the thing into a real track, not to edit it here. If something in
this folder starts needing maintenance, that is the signal to either delete it or
bring it back.

**And the reason this folder exists at all:** before 2026-09-18, `docs/roadmap/`
held 65 files across three document kinds, 37 of them last touched by two commits
in early September, and five of them opening by claiming to be the active roadmap.
The fix was not to delete them — it was to say which kind each one is.
