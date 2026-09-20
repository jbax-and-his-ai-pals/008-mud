# docs/

Documents are separated **by how fast they change**, because that is the thing
that actually rots. A plan is stale in a week; a manual is stale in a month; an
ADR never goes stale because it records a decision that was made, not a fact that
might have moved.

| Folder | Kind | Ages | Ask of it |
|---|---|---|---|
| [`plan/`](plan/README.md) | **What is next, and how work is divided.** Sequencing, priorities, open decisions | weekly | "what am I doing next?" |
| [`reference/`](reference/README.md) | **How a thing works.** Manuals, contracts, runbooks | monthly | "how does this work?" |
| [`design/`](design/README.md) | **Why a thing is the way it is.** Rationale, pillars, proposals | rarely | "why is it like that?" |
| [`archive/`](archive/README.md) | **What was decided before.** Superseded plans, completed phases, history | never | "what did we used to think?" |

**The rule that makes this work: one question, one folder.** If you cannot tell
which folder a document belongs in, the document has two purposes and should be
split. The failure this fixes is specific: before 2026-09-18 there were five
documents that all opened by claiming to be "the active roadmap", and a reader
had to open each to find out which one still was.

## Where to start

- **New to the project?** [`reference/PLAYER_MANUAL.md`](reference/PLAYER_MANUAL.md)
  for what the game is, then [`design/WORLD_DESIGN.md`](design/WORLD_DESIGN.md)
  for where it is going, then [`plan/integrated-roadmap.md`](plan/integrated-roadmap.md)
  for what happens next.
- **About to do work?** [`plan/work-tracks.md`](plan/work-tracks.md) says which
  track owns the file you are touching, and [`plan/integrated-roadmap.md`](plan/integrated-roadmap.md)
  says whether it is scheduled. `ROADMAP.md` at the repo root holds the standing
  decisions and the live open items.
- **Curious why something is odd?** [`archive/roadmap-2026-09-narratives.md`](archive/roadmap-2026-09-narratives.md)
  is the P0–P9 record; the audit findings it references are in `ROADMAP.md`.

## Two things this folder deliberately does not have

**No `docs/guides/`, no `docs/howto/`.** Ever ask: does an authoring tutorial
belong with the manual or with the contracts? The answer is "reference", and a
third category would only invite the question back.

**No per-topic folders.** Theming docs by subject (editor, content, server) makes
each subject's plan age at a different rate while looking uniform, which is how
`docs/roadmap/` accumulated 37 files from two commits in September.
