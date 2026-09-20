# Track roadmaps — 2026-09-18

Eleven evaluators, one per work track, each asked to read its own lane in the code
and propose that track's roadmap. Each wrote one file and touched nothing else.

**Read the per-track files for the reasoning; read this for what they add up to.**

| | Track | File |
|---|---|---|
| A | Brainstorm | [`track-A-brainstorm.md`](track-A-brainstorm.md) |
| B | Core Engine | [`track-B-core-engine.md`](track-B-core-engine.md) |
| C | Runtime & Transport | [`track-C-runtime-transport.md`](track-C-runtime-transport.md) |
| D | Content Loading & Contracts | [`track-D-content-loading.md`](track-D-content-loading.md) |
| E | Systems | [`track-E-systems.md`](track-E-systems.md) |
| F | Content | [`track-F-content.md`](track-F-content.md) |
| G | World Editor | [`track-G-world-editor.md`](track-G-world-editor.md) |
| H | Testing | [`track-H-testing.md`](track-H-testing.md) |
| I | Gates & Integrity | [`track-I-gates-integrity.md`](track-I-gates-integrity.md) |
| J | Documentation | [`track-J-documentation.md`](track-J-documentation.md) |
| K | Lead Design & Coordination | [`track-K-lead-design.md`](track-K-lead-design.md) |

This is a review artifact, not the plan. Accepted items belong in `ROADMAP.md`.

---

## Verified findings

Claims that change a decision were checked against the code before being
accepted. Six have been verified line by line; a seventh was **refuted**. The
numbers in brackets are the track that reported it.

### 1. The save path can destroy the only copy of a character [C]

Worse than it sounds, because three separate facts compose into it. All three
verified:

1. **The write truncates in place.** `save_manager.py:95` is
   `with open(save_path, 'w', encoding='utf-8') as f: json.dump(...)`. Searching
   all of `server/` for `os.replace`, `mkstemp`, `NamedTemporaryFile`, `fsync`,
   `shutil.copy` or `.bak` returns **zero hits**. One copy, truncated before it is
   written, and `default=str` stringifies anything unserialisable rather than
   failing the save.
2. **A failed load replaces the world with a new one.** `save_manager.py:224-229`
   catches everything, logs, and calls `self.world.initialize_new_world()` before
   returning `False`. After a bad load the player is a new character.
3. **The save command still points at the unreadable file.** `load_handler`
   assigns `game.current_save_file` only on success (`commands/system.py:67-68`);
   on failure it is left as it was, and `save_handler` defaults to that name
   (`system.py:45`).

Composed: **load a corrupt save → the world becomes a fresh character → type
`save` → the unreadable file is overwritten.** The recovery path runs backwards.
Nothing is written until a player types `save` — there is no autosave — so this is
the whole durability story.

**Minimal fix, independent of any design:** write to a temporary file, `os.replace`
it, keep a `.bak`. One function, Track C's lane.

### 2. The skill curve is the one exponential content cannot touch — and two sets wrote against it [A]

`core/skill_system.py:7-8` holds `BASE_XP_TO_LEVEL_SKILL = 100` and
`SKILL_XP_MULTIPLIER = 1.5`, read from no ruleset — unlike `advancement.curve`,
which content does author. Verified at those lines.

Cumulative cost: **~7,600 XP to skill 10, ~443,000 to skill 20.** Both crime sets
gate the jail escape at level 20 — `fantasy_frontier/rules/ruleset.json:171-176`
(stealth + lockpicking) and `night_shift/rules/ruleset.json:45-48` (awareness +
security) — while the largest grants to those skills are tens of XP per attempt
(`items/lockpick.py:77,81`). The concealed-pick flavour beat and both emergency
tools are therefore unreachable in play, and no gate can see it because each half
is individually legal. This is a **content-versus-engine numeric mismatch**, the
same class as a reference that resolves to nothing.

### 3. `steal` is ungated, and in one set it mints money [A]

`commands/interaction/theft.py:9` declares `@command("steal", [], "interaction", ...)`
with **no `content_capability`** — unlike almost every other conditional command.
`CrimeManager.attempt_witness` returns immediately when crime is not enabled
(`core/crime_manager.py:35-36`), and `orbital_salvage` declares **no crime section
at all** (verified: fantasy and night_shift declare one, orbital and
modern_capsule do not). Orbital's foreman sells items. So `steal` succeeds there,
unwitnessed, creating a fresh instance each time — an unlimited item and money
source in a set with an economy.

The engine already has the right instinct elsewhere: `quest_generation.delivery_package_item_id`
declines rather than guesses. The fix shape is the same — **a set with no ownership
consequences should refuse, in the world's voice.**

### 4. A registered condition kind that can never be true [A, B]

`conditions.py:137` reads
`data.get("period", data.get("time_of_day", ""))`, while `time_manager.py:127`
publishes the key **`time_period`**. So the lookup always returns `""` and every
`time_of_day` condition evaluates false. The kind is registered in `KNOWN_KINDS`,
typed in the editor's `DialogueSchema.gd`, and used by no content — which is why no
gate has ever had a chance to go red. `season` reads the right key and works.

### 5. Contract fields the engine ignores, today [B]

Not history — live. `registry.effect_packet()` (`registry.py:455`) has **zero call
sites repo-wide** (verified: the only match is its own definition), while
`kind` is `required: True` and authored by two sets; all magic behaviour comes from
`spell.effects`. Also inert: `size_tiers[].weight` and `quality_tiers[].weight`
(rolls come from a hardcoded canonical curve re-sampled by tier count, so
retuning a band changes nothing), `item_families[].debug_only` (consumers read
`template["properties"]["debug_only"]` instead), plus `TIER_FIELDS.weight_multiplier`,
`rarity_tiers[].value_multiplier`, and several `label`/`description` fields.

**Read but never validated:** `defense_profiles[].material` feeds
`WEAPON_VS_ARMOR_MULTIPLIERS.get(..., {}).get(material, 1.0)` — an unvalidated free
string whose only failure mode is a silent ×1.0, while `ARMOR_MATERIALS` sits in
config with no consumer.

### 6. The duration design's clock: three candidates, none a world clock [B, C]

The document was wrong twice in opposite directions and both reviews were partly
right.

| Clock | Advances from | Survives a restart | Works headless |
|---|---|---|---|
| `TimeManager.game_time` | frame delta, 72 game-seconds per real second, clamped by `TIME_MAX_CATCHUP_SECONDS = 5.0` | **yes** — saved `save_manager.py:89`, restored `time_manager.py:145` | no |
| `world.clock` (`WallClock`) | the real system clock; `advance()` is a no-op | no | yes — `World.__init__(clock=...)` |
| `world.clock` (`SimulatedClock`) | only when told | no | yes, and this is how timers get tested |

`world.clock` is the *testable* clock; `game_time` is the *durable* one; neither
keeps running while the process is stopped. Track C found the same thing at the
server level — the world clock only runs while someone is logged in. **So the
document's central claim, "a herb bed recovers whether or not anyone was there to
watch", is false against both**, and the anchor is now written as an open decision
rather than a detail.

### 7. Two false positives in gates written *this session* — both fixed [E, F]

The most uncomfortable findings in the set, and the most useful.

**`skill_audit`** classified a room exit's `skill_name` as "rolls and grants
nothing". It calls `SkillSystem.practice_check` (`world/world.py:402`), which
**awards xp** — so the tool's `only_attempted` warning was one shipped skill exit
away from reporting a working, trainable skill as untrainable. Fixed: the role is
now `threshold` (a `{"skill", "minimum"}` gate, which genuinely rolls nothing),
a room exit is `rolls`, and `test_a_room_exit_rolls_and_trains` is the regression
test.

**`content_playability_check`** reported **16 of 23** fantasy abilities as having
no route to the player. That was wrong by a factor of five. `item_scroll_random`
carries `properties.procedural_type: random_spell_scroll`, and `ItemFactory` fills
it from every spell with `level_required > 0 and mana_cost > 0`
(`items/item_factory.py:161`) — so **one authored template puts twenty of them on
a vendor's shelf**. The check read only static `spell_to_learn` and could not see
a procedural item. Fixed: `_procedural_spell_route` resolves the template and
expands it against the registry.

**The corrected finding is smaller and sharper: 3 of 23, not 16** — `bone_shard`,
`ember_bolt` and `zap`, which have `mana_cost == 0` and are therefore excluded
from every procedural scroll and named by no authored scroll either. That is a
real content gap with a real cause, where the old number was a tool artefact.

**The lesson, which this project keeps relearning:** three checks built in this
session to catch silent failures were themselves silently wrong — a walker whose
path matched nothing, an audit whose two skills were one site, and now these two.
Every one surfaced because somebody read the code the tool was describing. That is
Track H's argument for fault-injection, applied to checks nobody thought to
falsify.

### 8. Refuted: the `work-tracks.md` B/E ownership ambiguity is **fixed**

Track J reported that `work-tracks.md:25` still said B owned "the mechanics inside
`server/engine/**`" while E's lane enumerated every subpackage, and that the
"concern has an owner" rule was absent. Both are present — the table row at line 25
and the rule at lines 91-94. That agent read the file before the edit landed.
**Recorded because a false finding in a report is itself information:** agent
reports need checking in both directions, and this one would have caused a
pointless second fix.

---

## Findings that need no verification to act on

Short, concrete, and each is a one-line change or a one-line decision:

- **`websockets` is in no requirements file**, so `poc_ws_server.py:92` raises at
  startup in the pinned environment. That entry point is untested. [C]
- **`data_fixtures/LATEST_REFRESH.json` points at `C:\python\old\restart\...`**, so
  `run_content_checks.py:166-177` prints SKIP and then "All content checks passed"
  on any other machine. A gate that can never fail. [C, I, J, H — four tracks
  found this independently]
- **Fourteen tracked test modules are 0 bytes** — and `git cat-file -s HEAD:<path>`
  is 0 for all of them, so they were created empty in `e2c0638` and have never had
  content. `docs/archive/HANDOFF.md:29-83` credits five of them with 163 tests that
  do not exist. Discovery imports them, counts zero, and reports green. [C, H —
  reported as five, verified at fourteen]
- **`landmark` is not a declaration.** `world.py:477` pays the 25 XP landmark grant
  on *every* room transition, so all 279 rooms are equivalent and the grant means
  "you moved". [F]
- **CI runs only the unit suites.** `run_content_checks.py` is a local habit;
  nothing in `.github/workflows/` invokes it. [J]
- **`content_neutrality_validator.py` has no test module at all** — the gate
  guarding the engine's only real asset has never been shown to fail. [I]
- **`README.md` fails at step one**: `python main.py` (no root `main.py`),
  `server/launch_from_latest_fixture.py` (does not exist), `python -m unittest
  discover tests` (no root `tests/`), and a PyTorch note explaining
  `server/engine/ai/`, archived on 2026-09-18. [J]
- **`docs/reference/PLAYER_MANUAL.md` tells players to type `titles`.** The command is
  `title`. [J]
- **The NPC properties gap**: `npc.py:236-246` persists no properties and
  `npc_factory.py:195-197` refills from template, so `is_escort_target` and
  `escort_quest_id` evaporate across a save. NPC *inventory* does persist, which is
  why it hid. [C]

---

## Coordination summary

### Where the tracks agree

Four things were reported independently by two or more tracks, which makes them
the safest decisions on this page:

1. **The duration clock needs deciding before duration is written** — B, and C from
   the server side.
2. **The unread-declaration check is the highest-leverage small primitive** — B
   proposes it as a gate; I's gate surface and A's "no primitive without a
   consumer" reflex point at the same thing.
3. **Content gates should run in CI** — C (which owns the workflow), I (which owns
   the gates) and J (which noticed they are undocumented and unrun).
4. **The second-consumer convention is the real test**, and three tracks
   independently nominated the same candidate pair.

### The sequencing question

Tracks were told B is the bottleneck, E the multiplier and F the filler. **Track K
disputes the third**, and the argument is worth weighing: F is also the required
verifier — two-theme proof, contract-gap discovery and "is this playable" all run
through content. Loading F with low-priority content starves verification. Track A
independently reached the same conclusion from the other end, nominating
`night_shift` as the cheapest second consumer because its ruleset *already*
authors the whole crime → custody → escape → release loop in its own vocabulary,
and only the content around it is missing.

Track K's proposed order, with A's addition folded in:

1. **Fix the save write** (C, small) — unrelated to any design, and it is the one
   item here with a data-loss failure mode already reachable.
2. **Duration declared, not implemented** (B, shape by K) — the declaration is what
   unblocks consumers.
3. **The fantasy preservation chain** (E/F) — first real consumer.
4. **The second consumer** (F/E) — `night_shift` for the crime system, and
   `orbital_salvage` for duration. This is where the two-theme convention is won.
5. **Editor surface plus a falsifying check for 1–4** (G/I).

Critical path: **E → F → second consumer.**

### Risks, ranked across the reports

1. **Human playtesting never happens.** It blocks four still-open decisions in
   `ROADMAP.md`. No amount of engine work resolves it. [K]
2. **Neutrality collapsing under theme pressure** — the failure the structure
   exists to prevent. [K]
3. **Save-format churn**, now sharpened by finding 1: changes to a path that can
   destroy data need Track H's reproduction before they need a merge. [C, K]
4. **Content-versus-engine numeric drift** — finding 2 is the first instance, and
   nothing detects the class. [A]
5. Track abandonment — **which has already happened once**: the editor audit
   stopped at Batch D (`ROADMAP.md:1478`). [K]

### Process artifacts proposed

Each deliberately small: a dated "next five" list in `ROADMAP.md`; ledger columns
plus an admission sentence; **one contract index table** with the rule that a
contract change is a handoff to every consumer named in it; use of the existing
but unused `docs/archive/adr/0000-template.md`, capped at one page; an ownership
cleanup; and a playtest validation file to replace the P8 checkbox. Explicitly
rejected: CODEOWNERS, standups, a new tracker, branch-per-track, and rewriting
these documents. [K]

Track A proposes the complementary filter for ideas *entering* the system: name
the player verb and the world verb separately; name the second theme, or admit the
idea is fantasy-shaped; name the existing primitive it composes; state the
falsifiable bar as a headless walk of a shipped set rather than "the content
exists"; and say what would make it decoration, and what gets deleted if it ships
without that.

---

## What to do with this

1. Read the per-track files — each is 700–1400 words and self-contained.
2. Decide the sequencing. This summary is a proposal; Track K's ordering is one
   track's argument, not a decision.
3. Move accepted items into `ROADMAP.md`. This directory is a review artifact.
4. The verified findings above are the ones worth acting on regardless of what
   else is accepted, because each is a defect rather than a plan.
