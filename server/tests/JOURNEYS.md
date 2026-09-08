# Deterministic Journey Runner

`tests.journey_runner.JourneyRunner` drives a seeded rules-based player over
simulated time and records every command, event type, player location, and
invariant result. It uses `HeadlessServer`, so it needs no Pygame window.

The default explorer is deliberately conservative: it explores exits, looks,
checks nearby state, and talks to each NPC once. `FantasyFrontierFirstSessionPolicy`
adds the authored opening, quest-board, combat/healing, and vendor seams before
continuing with exploration.

`FantasyFrontierSystemSweepPolicy` runs two authored gather → craft → deliver
commissions: starter herbs become a first gift, then its reward buys an entry
hand axe for harvesting orchard wood and carving the trust-gated follow-up. It
does not use debug inventory provisioning, so a failure in that sequence
represents a real player-facing dead end.

`FantasyFrontierFirstHourPolicy` uses that route as an asserted vertical
slice.  Its outcome checks require successful gathering/crafting/delivery and
trade actions, reaching the orchard, completing both commissions, earning
trust, and retaining the purchased tool.  The generic runner exposes reusable
command, destination, and state-predicate checks; only the sample policy
names fantasy content IDs.

Craft outcomes can also carry optional material provenance. Resource nodes may
author a material-quality score; a quality-aware recipe evaluates the limiting
score across its required ingredients. Quality-bearing materials and outputs
remain individual inventory instances, so later gifts and sales keep the
correct value and social effects.

`FantasyFrontierCombatRoutePolicy` takes the north road to a content-authored,
stationary low-threat encounter, resolves it, and returns to town. The
`SimulatedCombatCadenceHook` maps headless action intervals onto the existing
real-time player attack cooldown; it does not change combat calculations or
NPC behavior.

`FantasyFrontierPremiumMaterialPolicy` proves the next maker/economy rung:
it earns the board's trust prerequisite, locates the premium commission by
template on the *live* board, gathers enough fine river clay for two distinct
tokens, then completes both the merchant buy order and Elder's delivery. Its
board acceptance is deliberately adaptive to notice ordering; only the
fantasy-specific policy and outcome checks know Riverside identifiers.

Resource nodes may declare a baseline material grade and yield-table entries
may replace it with a rarer grade. Gathered quality-bearing materials retain
their neutral source provenance and are individually appraisable, allowing a
policy—or a real player—to decide whether to craft, sell, gift, or save an
unusually good find.

`FantasyFrontierOpportunityPolicy` is the first state-driven extension of
those routes. It earns and spends currency for a needed tool, appraises a
regional find, uses one specimen to establish a curator relationship gate,
then accepts and resolves the newly unlocked museum commission with the other.
Its decision markers inspect live inventory, active quests, relationship state,
and board templates rather than relying on board positions or item slots.

`run_commands()` replays a trace on a fresh server. `minimize_failing_commands()`
uses delta debugging with a caller-supplied failure predicate to shrink a long
failing trace into a focused regression case.

## Background lab

`server/run_playtest_lab.py` runs isolated headless journeys and prints one
JSON result per cycle. Passing traces are discarded by default; failing traces
are retained under `server/tmp/playtest_lab/` for replay/minimization.
Use `--verbose` only when diagnosing a failure; normal background output is
one machine-readable JSON summary per cycle.

```bash
cd server
nohup ../.venv/bin/python run_playtest_lab.py \
  --policy guided --duration 1800 --runs 20 --reconnect-at 24 120 240 \
  --repeat 0 --sleep-seconds 5 > tmp/playtest_lab/background.log 2>&1 &
```

For a short, outcome-asserted first-session regression, use the `first-hour`
policy. Its JSON result includes `outcome_errors` separately from state
invariants, so a route that stayed technically alive but failed to deliver its
promised progression is still a failed run.

```bash
cd server
../.venv/bin/python run_playtest_lab.py --policy first-hour --duration 200 --runs 1
```

The combat route has the same outcome assertions:

```bash
cd server
../.venv/bin/python run_playtest_lab.py --policy combat --duration 90 --runs 1
```

The quality-aware commission and merchant route is similarly outcome-asserted:

```bash
cd server
../.venv/bin/python run_playtest_lab.py --policy premium --duration 220 --runs 1
```

The broader opportunity route covers economy, gathering, appraisal, social
access, and a commissioned craft in one outcome-asserted pass:

```bash
cd server
../.venv/bin/python run_playtest_lab.py --policy opportunity --duration 400 --runs 1
```

Use `--agents 2` (or more) to interleave several player-like policies in one
shared world. This is useful for finding state bleed and is the testing seam
from which future NPC behavior can share policy concepts such as observation,
intent selection, memory, and risk evaluation without making NPCs execute
player text commands.

Use repeated `--agent-policy` flags to assign different roles in a shared
world. For example, keep one agent on a commissioning route while another
explores instead of having both contend for the same one-off board notice:

```bash
cd server
../.venv/bin/python run_playtest_lab.py --agents 2 --duration 1800 \
  --agent-policy sweep --agent-policy explorer --keep-passing-traces
```

Use `--keep-passing-traces` when investigating a behavior change. The current
fault hook covers authoritative disconnect/resume; future hooks should add
restart/recovery and inventory-overflow cases only with explicit invariants.

Example for a half-hour simulated journey:

```bash
cd server
../.venv/bin/python -c '\
from tests.fixtures import make_test_server; from tests.journey_runner import JourneyRunner; \
s = make_test_server(); r = JourneyRunner(s, seed=2026).run(1800); r.write_json("journey-2026.json"); s.shutdown(); print(r.passed, len(r.steps))'
```

At the default five seconds per action, this runs 360 replayable actions and
represents 30 simulated minutes. Keep the resulting trace when a run exposes
a defect; add a narrow regression test that replays the failing command
sequence before expanding the policy.
