# plan/

**What is next, and how work is divided.** Everything here is expected to change
within weeks; if a document in this folder has not been touched in a month,
either the project has stalled or the document has become an archive candidate.

| Document | What it is | Ages |
|---|---|---|
| [`chunks-of-work.md`](chunks-of-work.md) | **Canonical execution queue.** §6A's first safety pass is implemented; finish its retest/coverage gates, then continue through §6G's authoring test candidate. Earlier chunks retain their history | weekly |
| [`game-authoring-roadmap.md`](game-authoring-roadmap.md) | **Full author journey and M0–M5 gates.** Setup, systems, fantasy coverage, contrasting games, late rule changes/migrations and production-oriented authoring readiness | weekly |
| [`integrated-roadmap.md`](integrated-roadmap.md) | Historical cross-track merge and ownership concordance; execution order is superseded by chunks, with X12 linked to the expanded authoring plan | historical + handoff updates |
| [`work-tracks.md`](work-tracks.md) | **How work is divided.** Eleven tracks (A–K) plus the archive: what each owns, what each may not do, and the four handoff types | monthly |
| [`editor-readiness.md`](editor-readiness.md) | **Evidence, not promises.** Current source-review addendum and a clearly dated historical audit; distinguishes prototype UI from proven authoring workflows | each authoring batch |
| [`editor-handoff.md`](editor-handoff.md) | **Current handoff.** Milestone estimates, verified commands, known limitations and the next-owner checklist | each handoff |
| [`editor-coverage-ledger.md`](editor-coverage-ledger.md) | **The field-level work list.** One row per engine-read declaration: reader, validator, editor writer, status (absent → read-only → prototype → validated writer → journey-proven), evidence and closing batch | each authoring batch |
| [`track-roadmaps/`](track-roadmaps/README.md) | **A review artifact, not the execution queue.** Eleven evaluations, with dated follow-up findings and handoff pointers | historical + dated annotations |

## The rule that makes parallel work possible

**A contract is the handoff.** Once a shape is declared, the track that consumes
it may start before the track that implements it has finished. Without that rule
every track blocks on every other one, which is why it is written down in
`work-tracks.md` rather than assumed.

Two consequences worth knowing before you start:

- **A track may not add a primitive** (that is B's) **and may not edit a file
  another track owns** (write the finding down and hand it over instead). Every
  exception so far has cost more than the handoff would have.
- **A system is not finished until two themes use it.** One-theme systems sit at
  "proposed" however well they work.

## Where the plan came from

`track-roadmaps/` is the evidence: eleven agents, one per track, each read its own
lane and proposed a roadmap. `integrated-roadmap.md` merged their ~65 items into
phases 0–5 and resolved the three places they disagreed. If you want to know
*why* an item is in Phase 3 and not Phase 1, that reasoning is in the merged
document's "Three sources, one order" section — and the per-track argument it came
from is one directory down.

## What lives here when this folder works

Sequencing, ownership, priorities, gates, and open decisions. **Not** how a system
works (that is [`../reference/`](../reference/README.md)) and **not** why it is
built that way (that is [`../design/`](../design/README.md)).

`ROADMAP.md` at the repo root holds the standing product direction,
the decisions that constrain the plan, and the live open items pulled out of the
archived phase bodies.
