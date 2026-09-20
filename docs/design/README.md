# design/

**Why a thing is the way it is.** Rationale, pillars, and proposals. Nothing here
is a plan; nothing here is a how-to. A document in this folder argues for a shape,
records the reasoning behind a decision, or describes the world as intended.

| Document | Answers |
|---|---|
| [`WORLD_DESIGN.md`](WORLD_DESIGN.md) | What the world is: concentric difficulty rings, the five towns, the progression spine, and the numbered decisions the rest of the project refers to |
| [`cross_theme_engine_contracts.md`](cross_theme_engine_contracts.md) | How the engine stays content-neutral, and what the P9 contract work has and has not built |
| [`place_making_and_town_security.md`](place_making_and_town_security.md) | Why housing, districts and town security are shaped as they are |
| [`duration-primitive.md`](duration-primitive.md) | **A proposal.** The next primitive: a calendar-anchored timer, why it is not the stopwatch model, and the fantasy preservation chain built on it. Carries two corrections from review |

## Why this folder is separate from `plan/`

Because the two fail differently. A plan that is a month old is *wrong* — it is
describing work that has moved. A design document that is a year old is still
*right*, or it was a bad decision that should be revisited on its merits rather
than because of its date.

`duration-primitive.md` is the clearest case in the repo: it is a proposal with no
implementation, so it is neither stale nor current — it is waiting for a clock
decision that the plan schedules. Putting it in `plan/` would imply it is
scheduled work; putting it in `reference/` would imply it describes something that
exists. It is a proposal, and that is its own kind.

## The convention this folder follows

**An argument names its counter-argument.** Every design doc here that proposes
something states what would make it wrong. `duration-primitive.md` keeps its own
corrections visible rather than editing them away, because the fact that it was
wrong twice in opposite directions is more useful to the next reader than a clean
final version would be.
