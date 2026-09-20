# plan/

**What is next, and how work is divided.** Everything here is expected to change
within weeks; if a document in this folder has not been touched in a month,
either the project has stalled or the document has become an archive candidate.

| Document | What it is | Ages |
|---|---|---|
| [`chunks-of-work.md`](chunks-of-work.md) | **Pick up from here.** Five chunks of work with definitions of done, the items that can run in parallel, and the three decisions that gate them | weekly |
| [`integrated-roadmap.md`](integrated-roadmap.md) | The cross-track detail behind the chunks: five phases, the eleven cross-track items and their owners, and the concordance placing every per-track proposal | weekly |
| [`work-tracks.md`](work-tracks.md) | **How work is divided.** Eleven tracks (A–K) plus the archive: what each owns, what each may not do, and the four handoff types | monthly |
| [`track-roadmaps/`](track-roadmaps/README.md) | **A review artifact, not the plan.** Eleven independent evaluations, one per track, plus the findings verified from them | frozen — dated 2026-09-18 |

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
five phases and resolved the three places they disagreed. If you want to know
*why* an item is in Phase 3 and not Phase 1, that reasoning is in the merged
document's "Three sources, one order" section — and the per-track argument it came
from is one directory down.

## What lives here when this folder works

Sequencing, ownership, priorities, gates, and open decisions. **Not** how a system
works (that is [`../reference/`](../reference/README.md)) and **not** why it is
built that way (that is [`../design/`](../design/README.md)).

`ROADMAP.md` at the repo root is the fourth piece: the standing product direction,
the decisions that constrain the plan, and the live open items pulled out of the
archived phase bodies.
