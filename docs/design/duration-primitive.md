# Duration: a primitive, and the first thing built on it

**Status:** proposed. Nothing here is implemented.
**Design rule this follows:** content declares, the engine resolves. If this ever
needs a module named after its content, it has gone wrong.

> **Correction, 2026-09-18 (after review).** The first draft anchored timers to
> `TimeManager.game_time`. A review said that was wrong and pointed at
> `engine/core/clock.py`; a second review said that was wrong too, and the second
> one is right. See "Which clock" below — the short version is that **there are
> three candidate clocks, and not one of them is a world clock that keeps
> running.** The rest of the design is unchanged.

> **Decided, 2026-09-19 — the missing world clock now exists.** The gap identified
> below was real, and it was in the tick loop rather than in the clocks: both
> `_run_background_ticks` loops returned early when no client was connected, so the
> world only aged while somebody was watching it. That is fixed;
> `TimeManager.game_time` now advances for as long as the server process is up,
> with or without sessions, and `test_world_time_is_continuous.py` holds it there.
>
> The decision, in the operator's words: *"if everything is a server, even when
> single player, then the world time advances continuously for as long as the
> server is up."* So:
>
> - **A duration is real elapsed time while the server runs.** `world.clock` is a
>   `WallClock` on a live server, so `now() + duration` is already the right anchor
>   and this design's central choice stands unchanged.
> - **Time does not pass while the server is stopped.** A save carries
>   `game_time`; a restart resumes from it. There is no catch-up, which is why
>   `TIME_MAX_CATCHUP_SECONDS` never has to be reasoned about for long absences.
> - **A brew finishes while a player is logged out, if the server is up.** That is
>   the intended reading of "persistent", and it is the one to author against: a
>   three-day ferment is three days of *server* time, not three days of play.
> - **A single-player session is a server on the player's own machine**, so this is
>   the same rule, not a special case.

---

## The two clocks the engine already has, and why neither is enough

`GameObject.process_active_effects` counts a status effect down:

```python
effect["duration_remaining"] -= time_delta        # decremented by WORLD_UPDATE_INTERVAL
```

That is a **stopwatch**: it runs on elapsed play time, so a sixty-second buff
pauses while you are logged out. For combat that is exactly right — nobody wants
to return from dinner to a dead character because the poison kept ticking.

`ResourceNode` does the opposite:

```python
respawn_days = int(self.get_property("respawn_days", 0))   # compared against the world day
```

That is a **calendar**: it runs on world time, so a herb bed recovers whether or
not anyone was there to watch. This is the only world-anchored duration in the
engine, and it lives inside one item class.

Everything else with a "later" in it — crops, ferments, debts, deadlines,
cooling, decay — needs the calendar. Not because it is more sophisticated, but
because those things are properties of the *world*, not of an entity's
attention. A barrel does not ferment harder while you watch it.

**So: Duration is the second model, generalised.** The stopwatch stays as it is;
combat effects are not the target here.

---

## The shape

A duration is a declared thing with a start, an end, and something that happens
when the world clock reaches the end. Two pieces:

### 1. The timer, as a property

Anything can carry `timers`: a list of records. Rooms, regions, items on the
ground, a container, an entity, a player's property. The engine knows four
fields and nothing else:

```json
{
  "id": "fermenting_batch_3",
  "started_at": 1048576.0,
  "ends_at":    1125376.0,
  "work": "barrel_ferment"
}
```

`started_at` / `ends_at` rather than "remaining" is the whole design. A countdown
has to be ticked; a deadline can be *evaluated on read*. That means:

- no timer loop, no catch-up when a world loads after a week of downtime;
- a save is exact, because the numbers are absolute;
- `ends_at` is inspectable, so "ready in two days" is a subtraction.

**Which clock `now()` means** is not a detail, and the answer already exists.
`engine/core/clock.py` provides exactly this model — its docstring names
"absolute-timestamp cooldowns and expiries … set once as `clock.now() + duration`
and later compared against a fresh `clock.now()`" — with two implementations:

| Clock | Behaviour | What it is for |
|---|---|---|
| `WallClock` | real time passes whether or not `advance()` is called | a live server |
| `SimulatedClock` | advances only when told, and can be `set()` | headless journeys and tests |

Timers anchor to `world.clock`. That is what makes a ferment finish while the
server is down *and* what makes the whole mechanism testable without sleeping
real seconds — `tests/singles/test_simulated_clock_integration.py` is the
existing pattern.

`TimeManager` is a different thing and must not be confused with it:
`game_time` advances only from a caller-supplied frame delta
(`core/time_manager.py`), so it is a *calendar* for display and for
season/time-of-day, and it stops when the process does. Anchoring a duration to
it would mean nothing ever finishes across a restart.

`started_at` earns its place next to `ends_at` because content wants to know how
long something took, and because using a timer as an ingredient ("distil the
mash that has sat at least three days") is a real recipe shape.

### 2. The work, as a declaration

`work` names an entry in a `work` section — the same pattern as
`generation_profiles`, `resources`, and `stats`:

```json
"work": [
  {
    "id": "drying_herbs",
    "label": "Drying herbs",
    "duration_days": 1,
    "inputs": [{"item_id": "item_wild_herbs", "quantity": 3}],
    "outputs": [{"item_id": "item_dried_herbs", "quantity": 3}],
    "skill": "crafting",
    "difficulty": 8
  },
  {
    "id": "barrel_ferment",
    "label": "Fermenting",
    "duration_days": 3,
    "inputs": [{"item_id": "item_ale_wort", "quantity": 1}],
    "outputs": [{"item_id": "item_barrel_ale", "quantity": 2}],
    "skill": "crafting",
    "difficulty": 12
  }
]
```

The engine's job is only: **start it**, **evaluate it on read**, **complete it**.
What the thing *is* comes entirely from the declaration. A moon-phase check, a
skill roll, a quality gradient, a by-product — all of those are fields on that
record, not branches in a manager.

**On `skill` and `difficulty` in those examples.** The first draft of this
document named `herbalism` and `brewing`, and neither is a skill any content set
declares — which would have been this project's own cautionary tale, a
declaration naming something that does not exist. Fantasy declares exactly four
skills (`crafting`, `lockpicking`, `mercantile`, `stealth`, in
`ruleset.skills.stat_bonuses`), and `crafting` is the one the engine hardcodes in
`crafting_manager.py`. So the examples use `crafting` because it is the only
honest answer today, and the *interesting* version of these two records —
`herbalism` and `brewing` as skills in their own right — is exactly the
crafting-discipline gap that `toolkit/skill_audit.py` already reports. Fixing
that is Track B's, not a licence for this document to invent vocabulary.
`SkillSystem` also scores `roll(1..100) + level` against the difficulty, so the
numbers here are a real gate rather than a formality.

---

## Four verbs, and no tick loop

| Verb | What the engine does |
|---|---|
| `start` | Validate inputs, consume them, append a timer with `started_at = now` and `ends_at = now + duration` |
| `observe` | Compare `now` to `ends_at`; report "ready", "two days left", or "finished" |
| `collect` | Resolve output: roll the declared skill, apply the declared quality, produce the items, drop the timer |
| `sweep` (optional) | When a container is opened, finish everything already due so a full barrel reads as a full barrel |

**Completion is lazy and reads the world clock.** Nothing fires at a moment;
everything is *already finished* when next observed, and every observer agrees
because they all compute from the same two numbers. A tick loop would need
catch-up semantics, ordering, and a policy for worlds that load after downtime;
evaluation needs none of that.

---

## Time as a modifier, not a gate

The interesting content is in how *conditions* change a duration rather than in
the duration itself. All of it is the same four fields:

| Shape | Declaration | Effect |
|---|---|---|
| Season | `"condition": {"season": "winter"}, "duration_multiplier": 2.0` | drying herbs takes twice as long in winter |
| Time of day | `"condition": {"time_of_day": "night"}` | bread only proves overnight |
| Temperature | a room property the work reads | a lit fire halves it |
| Presence | `"requires_present": true` | cheese that spoils if you leave it too long |
| Skill | `"skill": "brewing", "difficulty": 12` | rolled at **start**, decides quality at **collect** |
| Ingredient | `"requires_timer": {"work": "mash", "min_age_days": 3}` | distillation needs aged mash |

That last one is worth naming: **a finished timer becomes an ingredient for the
next**, which is what turns a set of timers into a production chain rather than a
set of vending machines.

---

## What this does for the fantasy game

Not "crops take time". The useful framing is the one that fixes an existing
hole: **seasons currently have no counterplay.** Winter is a penalty you cannot
mitigate — `resource_node` gates on season, weather rolls worse, and there is
nothing the player can *do* about it.

Preservation is the counterplay. Autumn's surplus becomes winter's supply:

```
herb bed  →  drying rack (1 day)   →  dried herbs   →  alchemy table  →  tonic
spring/summer                  autumn               keeps all winter
```

and the chain already has its endpoints in shipped content. `brew_minor_heal`
and the other tonics exist as instant recipes at an `alchemy_table`; `item_barrel_ale`
already exists as an item; `item_wild_herbs` and `node_herb_bed` exist. **Brewing
is the one that makes the case best**, because it is already half-specified: a
recipe produces the output, and the only thing missing is the wait.

### The three-stage chain, using what is already there

| Stage | Work | Where | Duration | Gate |
|---|---|---|---|---|
| 1 | Dry the herb | a **drying rack** — a new station item, authored exactly like `item_anvil` and `item_alchemy_kit` are today (`crafting_station_type`) | 1 day | winter doubles it |
| 2 | Brew the tonic | `item_alchemy_kit` (exists) | 2 days | `brewing` skill, quality from the roll |
| 3 | Ferment the ale | `item_barrel_ale` (exists as a plain `Item` whose description already reads "full of … ale", with no `contains` — it would become the first **item that performs work**, and would need to be a real `Container` first) | 3 days | quality gradient: thin / sound / fine |

Stage 1 is the smallest possible demonstration and proves the primitive. Stage 3
is the one that shows a **quality gradient**, which is what makes waiting a
decision rather than a delay: pull it early and you get something drinkable and
cheap; leave it and you get something worth selling. That is the same
`quality_tiers` idea recipes already have, applied to time instead of batches.

Worth noting which endpoints are already authored, because it makes stage 2 the
cheapest possible proof: `brew_minor_heal`, `brew_marshguard_tonic`,
`brew_trailblazer_tonic` and `brew_purifying_draught` already exist as instant
recipes at an `alchemy_table`, and `item_wild_herbs` already drops from
`node_herb_bed`. Nothing new has to be invented for the first version — the
recipe just gains a wait.

### Why this and not the others

| Candidate | Verdict |
|---|---|
| Crops growing in a plot | Right shape, but it wants a *persistent* plot entity and a planting verb; better once `drying_rack` has proven the primitive |
| Rental income from an owned house | Uses `housing_manager`, which already exists — but it is money-per-tick, which is a different primitive (periodic effect, not a duration). Park it. |
| Market restocking | Same: periodic, not durational. And `respawn_days` already approximates it for nodes |
| Summoned creatures expiring | Already covered by the stopwatch model; nothing to add |
| **Damage over time** | **Already works, and is deliberately not this.** See below |

### Why damage-over-time is not this primitive

`dot` effects are the **stopwatch** model: they tick while you are present, from
a `duration_remaining` that decrements by `WORLD_UPDATE_INTERVAL`. That is
correct for combat — an effect that ran on world time would punish players for
logging off, and one that resolves lazily could not deal damage "now".

The two models answer different questions:

- **stopwatch** — "how much longer does this affect the creature fighting me?"
- **calendar** — "how much longer until this barrel is worth something?"

Both are legitimate; conflating them is how you get poison that kills you while
you sleep. Keeping them separate is a design decision worth writing down, because
the temptation to "unify the duration code" will come up.

---

## What must not happen

- **No `work_manager.py` with a tick loop.** Four verbs, resolved on read.
- **No content word in the engine.** The engine resolves `work["outputs"]`; it
  does not know what a barrel is. The moment `if work_id == "ferment"` appears,
  the design has failed.
- **No new persistence shape.** Timers are JSON on an object that already
  serializes. **Which objects those are is narrower than the first draft
  claimed:** `save_manager.py` persists room *items* but not room or region
  properties, and `NPC.to_dict` drops properties. So duration v1 is scoped to
  **items and players** — the two owners that already round-trip — and a timer on
  a room is a Track C question about persisting world state, not something this
  design should assume. A save-format bump should not be needed for the v1 scope.
- **No blocking wait.** Nothing in this design lets a player stand still until
  something finishes. Time passes by playing, or by the world clock advancing.

---

## Open questions, for the tracks to answer

1. **Does `duration_days` or `duration_seconds` win?** `respawn_days` is days and
   `TimeManager` is seconds, but the clock a timer anchors to is `world.clock`,
   which is seconds. Probably both, with seconds canonical on the clock and days
   as authoring sugar — but that is a contract decision, made once, in the
   contract, not per call site. Note that `TIME_REAL_SECONDS_PER_GAME_DAY`
   (`config_game.py:24`) is one global rate with no content override, so
   "a day" currently means the same real duration in every theme.
2. **What happens to a timer whose container is destroyed?** Inputs are already
   consumed. Options: the work is lost, or it is recoverable as a partial. This
   is a content-feel decision and probably wants a declared `on_destroy`.
3. **Do NPCs use work?** A blacksmith who is *actually* forging rather than
   standing at an anvil is a large gain for very little engine, but it needs the
   NPC to be the timer's owner. Worth checking the shape supports it before
   committing.
4. **How does a player discover the mechanic at all, in a text game?** There is
   no progress bar. The answer is probably that the *station* describes what it
   can do and the `recipes` command lists work alongside recipes — but that is a
   content-and-surface question, and it should be answered before the first
   station is authored.

---

## Where this fits

This is a **Track B: Core Engine** deliverable, and it is the one the other
tracks are waiting on: contracts need deadlines, environment hazards need "how
long can you stay", world state needs decay. It has a precedent in the codebase
(`respawn_days`), an existing clock to hang from (`TimeManager`), and its first
content application is already half-built in `alchemy_table` and `item_barrel_ale`.

See [`../roadmap/work-tracks.md`](../roadmap/work-tracks.md) for how the tracks
are meant to interlock around it.
