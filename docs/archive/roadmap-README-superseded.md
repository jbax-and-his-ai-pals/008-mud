# Content Engine Roadmap (historical)

> **Superseded (2026-09-16).** The active roadmap is
> [`/ROADMAP.md`](../../ROADMAP.md) (rewritten 2026-09-14 after a full engine +
> content audit), alongside [`docs/design/WORLD_DESIGN.md`](../design/WORLD_DESIGN.md).
> Everything this document lists as "current priority" is done: the
> content-set manifest/loader exists (`engine/server/content_set.py`), Fantasy
> Frontier is the extracted reference content set
> (`content_sets/fantasy_frontier/`), and it has had a real first-session
> player loop since P0. Kept below for implementation history and the
> engine/content-set boundary rationale, which still holds.

The project is building a reusable engine for authored text-first games. A **content set** defines a complete game—its world, rules, structure, scenarios, and presentation. The first canonical content set is a substantial fantasy game; later sets may explore modern, western, space, or other genres.

## Historical "active roadmap" pointer

[Content Engine Roadmap](content-engine-roadmap.md) defined the product charter, content-set boundary, canonical game sequence, delivery milestones, and priorities as of its writing. Read it for the boundary rationale; for current priorities, use `/ROADMAP.md`.

## Historical material

The documents below record prior platform work and remain useful as implementation references. They are not the active phase order or source of priority.

- [Work tracks](work-tracks.md) — **read this first.** How work is divided into eleven tracks (A–K) plus the archive, what each may not do, and the contract-first handoff that lets them run in separate conversations. This one is current, not historical. It also says which of the track documents below are still live.
- [Track roadmaps, 2026-09-18](track-roadmaps/README.md) — one evaluator per track read its own lane and proposed a roadmap. A review artifact, not the plan; the sequencing in it is a proposal.
- [Previous phase documents](phases/)
- [Historical next-session log](next-session.md)
- [Platform architecture notes](platform-architecture.md)
- [World-editor track](world-editor-track.md)
- [Content and mod publishing guidance](content-authoring-and-mod-publishing-guidelines.md)
- [Accessibility track](accessibility-track.md)
- [ADR template](adr/0000-template.md)

When any document here conflicts with `/ROADMAP.md`, `/ROADMAP.md` wins.
