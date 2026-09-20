# Integrated roadmap — after the track reports

**Status:** proposed 2026-09-18, for review. This is the plan the eleven track
roadmaps add up to. Per-track files stay as the reasoning; this is the order.

**How it relates to the rest:**

| Document | Role |
|---|---|
| [`ROADMAP.md`](../../ROADMAP.md) | the phase history (P0–P9) and the standing decisions. **Wins on any conflict.** |
| [`work-tracks.md`](work-tracks.md) | who may do what, and the deferral ledger |
| [`track-roadmaps/`](track-roadmaps/README.md) | eleven independent evaluations, plus the verified findings |
| **this file** | the merge: what happens in what order, and what crosses tracks |

The per-track roadmaps produced ~65 proposed items. This merges them into **five
phases**, each of which ends in a gate you can run, and names the **eleven items
that cross tracks** so they get an owner instead of a committee.

---

## Three sources, one order

The tracks disagreed in exactly three places. Resolved here, with the reasoning,
because an unresolved sequencing argument is how two tracks start the same work.

**1. What comes first: the save fix or the duration primitive?** Track C found a
save path that can destroy a character. It touches nothing else and is one
function. **Resolved: the save fix is Phase 0.** It is the only item on any list
with a known, already-reachable failure mode, and it is not on the critical path
for anything, so it costs a phase nothing.

**2. Is F the filler?** Tracks were told F is the filler; K argued F is also the
required verifier — two-theme proof, contract-gap discovery and "is this
playable" all run through content, so loading F with low-priority work starves
verification. Track A reached the same conclusion from the other end.
**Resolved: F is not filler. F carries verifier work in every phase from 2 on**,
and Phases 3 and 4 are F-loaded deliberately.

**3. Which clock do timers anchor to?** B and C both found the duration document
wrong, in opposite directions. **Resolved as a Phase 1 decision, not a Phase 2
one** — the contract cannot be written without it, and the honest position is that
*there is no running world clock today*: `game_time` is durable but frame-driven,
`world.clock` is real-time but unsaved.

---

## The eleven cross-track items

Everything else in this roadmap sits inside one lane. These do not, so each names
its participating tracks, the handoff type, and what has to be true together.

| # | Item | Tracks | The handoff |
|---|---|---|---|
| **X1** | Atomic save write + `.bak` + refuse-to-clobber | **C** owns; **H** proves | H writes the reproduction — kill a save mid-write, assert the old file survives — before the change merges |
| **X2** | `time_of_day` reads the right key | **D** owns (`conditions.py`); **I** gates; **A/E** are consumers | One-line fix plus the first content that uses it; the gate is that a test asserts the condition *matches* at hour N |
| **X3** | JSON-integrity gate covers every set, and cannot green-skip | **I** owns; **C** may wire CI | I parameterises the runner; C decides whether it runs in CI. Independent halves, one decision |
| **X4** | Runner-level gate falsification harness | **H** owns; **I** supplies one defect per gate | H's item 1 *is* I's item 5's test half. Neither can finish alone |
| **X5** | Duration: contract declared and implemented | **B** owns the shape; **K** ratifies the clock; **C** answers persistence; **E/F** consume | The declaration is the handoff. E and F may start the moment the shape is written, before B's resolver lands |
| **X6** | The fantasy preservation chain | **F** authors; **E** wires the station; **B**'s `work` is the wait | F ships it **with no timers** (Track F's F-5), so E and F proceed while B is still writing. `duration_days` is then one data edit |
| **X7** | The second consumer — orbital duration + night_shift crime | **F** authors both; **E** fixes what they expose; **I** gates | This is where the two-theme convention is won. F cannot do it alone: the night_shift slice will expose the container-theft and `owned_by_npc` seams, which are E's |
| **X8** | Environment as a validated value | **B** owns the primitive; **E** is the first reader; **F** authors orbital's | Three surfaces express environment and one reads it (Track E). B declares, E unifies the readers, F fills the empty `hazards` seat orbital already left |
| **X9** | Empty id buckets must warn, not skip | **I** owns; **F** feels it | Two thin sets have quest/ability families that are unchecked today *because* they declare none. I changes the guard; F's Phase 4 content makes it bite |
| **X10** | A new content set can be created | **G** owns the scaffolding; **J** owns the guide; **F** is the first user | G's item 6 and J's `AUTHORING_A_CONTENT_SET.md` are the same deliverable seen from two sides. Whichever lands first defines the other's contract |
| **X11** | In-game tooling has no home | **K** decides; **G** spikes | `tools/` was deleted on 2026-09-18. Track G's item 7 is explicitly a spike asking where a player-facing tool lives — that question has no owner until K answers it |

---

## Phase 0 — Stop the bleeding

Nothing here is on the critical path and everything here is a defect.

| Item | Track | Done when |
|---|---|---|
| Atomic save write, `.bak`, refuse to clobber an unread save | C | A test kills a save mid-write and asserts the previous file is intact and loadable |
| `time_of_day` reads `time_period` | D | A test asserts the condition **matches** at a matching hour, not merely that it parses |
| Fourteen 0-byte test modules get a verdict each | H | Each is deleted or implemented; `run_tests.py` reports 0-byte modules instead of counting them green |
| `git cat-file` audit of `HANDOFF.md`'s claimed tests | H | The doc's numbers match disk or the doc is corrected |
| `websockets` pinned, or `poc_ws_server.py` marked unsupported | C | The entry point either starts in the pinned env or says why it cannot |
| `LATEST_REFRESH.json` gets a relative target | C | `run_content_checks.py` runs the fixture steps instead of printing SKIP |

**Gate:** the three existing gates, green, plus the new save-recovery test.

---

## Phase 1 — Declare, don't build

The whole phase is declarations plus the checks that keep them honest. This is
deliberately the shortest phase and the one everything else waits on.

**X5 begins here.** Order inside the phase:

1. **The clock decision** (K ratifies, B implements). The three candidates are
   documented in `docs/design/duration-primitive.md`. The two coherent options:
   anchor to `game_time` and accept that timers pause while the game is closed, or
   store `started_at` in game-seconds *and* the wall-clock instant of the save and
   let a load advance the calendar by elapsed real time. **The second is what the
   document claims; the first is what the engine does.**
2. **The `work` contract, declared and documented** — the shape, not the
   resolver. E and F may consume it immediately.
3. **The unread-declaration check** (B's item 2, gated by I). This is the one that
   makes every later declaration trustworthy, and its first run will force a
   read-or-delete decision on `effect_packets`, `item_families[].debug_only`,
   `attack_profiles[].cooldown`/`resource_cost`, and the inert tier weights.
4. **Fix what the check exposes** — Track B's item 3, including the honest answer
   for `effect_packets`: wire it or delete it.

| Item | Track | Done when |
|---|---|---|
| The clock decision, written into the duration doc | K + B | The doc states one clock and the document's own claim is true against it |
| `work` declared | B | E and F can author against it; a consumer test exists |
| Field-with-no-reader check | B + I | Re-adding `debug_only` with no reader turns the gate red |
| `effect_packets` resolved | B | Either retuning it changes what a spell deals, or it is gone |
| Editor: nested-property guard in the room panel | G | An edit to a dict-valued room property round-trips unchanged |
| Editor: byte-compare round-trip over all four sets | G | The int→float class of defect has an editor-level regression check |

**Gate:** three gates green, plus the two new ones (unread-declaration,
byte-compare) each proven to fire.

---

## Phase 2 — First consumer

Track B implements duration; F and E build the case that justifies it.

**X6 is this phase.** The sequencing matters: F ships the chain *without timers*
first, so the content is walkable while B is still writing the resolver.

| Item | Track | Done when |
|---|---|---|
| Duration implemented: timer + `work`, `start`/`observe`/`collect` | B | Two themes complete a timer; a save mid-timer reloads with the same `ends_at`; the whole cycle runs under `SimulatedClock` |
| The preservation chain content, **no wait** | F | `node_herb_bed` → shelf-stable tonic is walkable; three recipes craft; content checks pass |
| The same recipes gain `duration_days` | F | One data edit, no engine change — the test of whether the contract was shaped right |
| Night shift: `night_shift`'s crime loop made playable | F | A player can take what is not theirs, be caught, be held, and get out, in a set with no fantasy nouns |

**Gate:** duration's own tests plus the two-theme proof for `crime`+`custody`+
`locksmithing`.

---

## Phase 3 — Second consumer, and the convention

The phase where the engine either proves it is general or is revealed as
fantasy-shaped. Both second consumers land here.

**X7 and X8 are this phase.**

| Item | Track | Done when |
|---|---|---|
| Orbital consumes duration | F | A docking window or commodity aging, declared by a set that has no winters |
| Environment: one declared, validated value | B | A room's chill is a declared band a hazard reads, replacing `temperature == "cold"` |
| Environment: one reader | E | The three expressions collapse to one; orbital authors its empty `hazards` seat |
| The social graph declared | F + E | Orbital declares a `social` section instead of silently rendering fantasy's default tier labels and a 15% discount |
| Editor: stat form from the ruleset, not 8 hardcoded names | G | A stat the editor does not know is authored without an editor change |

**Gate:** two themes per system, asserted by content rather than claimed. This is
the phase where "a system is not finished until two themes use it" stops being a
slogan.

---

## Phase 4 — Widen

| Item | Track | Done when |
|---|---|---|
| Empty buckets warn instead of skipping | I | The two thin sets' quest and ability families are checked |
| JSON integrity for all four sets, no green-skip | I + C | A malformed file in `night_shift` fails the gate |
| Gate-falsification harness | H + I | Every gate has a fixture that makes it exit non-zero |
| Whole-state save round-trip + an old-version fixture | H | A save the current writer did not produce loads through `SaveManager.load()` |
| Save-key manifest | C | A key written-but-not-restored fails |
| Finish or delete the sqlite entity/cell half | C | Four functions with zero callers either gain one or are gone |
| The four unused objective types get a quest each | F | Each type appears in shipped content |
| `modern_capsule` gets its repair café | F | A player finishes an errand there without touching a fantasy system |
| Doc: `AUTHORING_A_CONTENT_SET.md` + truthful `README.md` | J | A new contributor can author a set from the docs alone |
| Doc: stale-path sweep | J | No `C:/python/old/restart/` in the tree |

**Gate:** all gates, plus CI running `run_content_checks.py`.

---

## Phase 5 — Depth

Lower priority by construction: none of it de-risks anything upstream.

Discoveries from 5 to 25 (F). Extracting the duplicated command ladder in
`poc_server.py`/`poc_ws_server.py` (C). The editor's new-set scaffolding (G+J).
Widening `content_values` one loader at a time (B+I). The tenth `skill_audit`
pattern (I). The 20 discoveries and the sparse-room work (F). In-game tooling
ownership (K+G).

---

## The concordance

~65 proposed items mapped to phases, so nothing is lost silently.

| Track | Items | Where they landed |
|---|---|---|
| A | 6 | Night shift crime → **P2**. Skill curve authored + unreachable-threshold gate → **P4** (I's gate). Theft has no default → **P1**. Fallow/field-grid/opening-contract → **P5**, and the field grid is a *decision* first (give cells a world, or delete the system) |
| B | 7 | Contract hygiene + unread check → **P1**. World-value store → **P3** (it is X8's sibling). Duration → **P2**. Environment → **P3**. Flow → **P5**. Deadlines → **P5** |
| C | 7 | Save atomicity → **P0**. Save-key manifest + sqlite verdict → **P4**. World time with zero clients → **P1, as the clock decision**. CI → **P4**. Command ladder → **P5** |
| D | 7 | Quest loader fix → **P0** (it is a live drop). Id-table type checks → **P1**. `_`-key policy → **P1**. Module split → **P5** |
| E | 5 | Clock as a system → **P1/P2**. One environment reader → **P3**. Authored skill name → **P4**. Social declared → **P3**. `_guilds` → **P4** |
| F | 6 | Reconnect dead content → **P0** (it is ~15 JSON lines). Objective types → **P4**. Night shift → **P2**. Modern capsule → **P4**. Duration endpoints → **P2**. Discoveries → **P5** |
| G | 7 | Nested-property guard + byte-compare → **P1**. Two-way schema parity → **P4**. Stat form → **P3**. New-set scaffolding → **P5**. Link-check → **P4**. Tooling spike → **P5**, pending K |
| H | 7 | 0-byte modules → **P0**. Falsification harness → **P4**. Save round-trip → **P4**. Machine-independence → **P4**. Snapshot guard → **P4** |
| I | 7 | Dead tables + condition ids + empty buckets → **P4**. Runner coverage → **P4**. Falsify untested gates → **P4**. `content_values` → **P5**. Tenth pattern → **P5** |
| J | 7 | Authoring guide + README → **P4**. Path sweep → **P4**. Player manual → **P4**. Operations doc → **P5**. Command reference → **P5** |
| K | 6 | Sequencing list → **this document**. Ledger columns + admission rule → **P1**. Contract index → **P1**. ADR practice → **P1**. Ownership cleanup → **P1**. Playtest file → **P0**, because it blocks four decisions |

### What this ordering defers on purpose

- **Skill curves and economy tuning** wait on human playtesting, which no phase
  can substitute for. Recorded, not scheduled.
- **Faction and territory work** — a system with no consumer is the thing the
  ledger already refuses once.
- **A fourth content set.** Two of the three existing ones are not games yet.

---

## The five structural fixes this roadmap assumes

From Track K, small and independent of every phase above.

1. **`work-tracks.md` lane fixes.** `conditions.py`, `naming.py`,
   `presentation.py` and `game_object.py` had no lane; the concern rule and the
   shared-zone table now cover them. Two remaining: **`presentation.py` and
   `game_object.py` still need an explicit owner.**
2. **The JSON-integrity gate runs one set** and the neutrality gate two. Both are
   Track I's, and both are in the phases above.
3. **`work-tracks.md`'s ledger** needs columns (kind, reason, revisit-when) and an
   admission sentence. Seven entries mixing refusals, policy and heuristics is a
   list, not a ledger.
4. **The contract index.** One table of the versioned contract shapes with the
   rule that *a contract change is a handoff to every consumer named in it*.
   Six sections today; this is what makes the contract-first rule enforceable
   rather than aspirational.
5. **Commit discipline.** 92 uncommitted paths across eleven tracks on one tree.
   Not a branching policy — a habit, and the thing that makes "which of these
   changes is live?" answerable.

---

## Open questions this roadmap does not answer

1. **Is `modern_capsule` a vignette or a game?** `progression_model: none` may be
   deliberate. If so, F's Phase 4 item for it is the wrong work.
2. **Is `night_shift` a shipped theme or the contract-currency exercise?** Its
   ruleset says the former; Track K's sequencing says the latter.
3. **Is `item_scroll_random` the intended ability ladder?** It makes a level-1
   goblin a source of level-6 spells, and nothing says that was on purpose.
4. **How much of the 61.6% sparse-room figure is deliberate?** No gate separates
   "nothing here on purpose" from "nothing here yet".
5. **Does world time advance with zero clients?** The clock decision in Phase 1
   forces this, and it changes what the game *is*.
