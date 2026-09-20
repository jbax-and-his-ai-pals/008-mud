# Chunks of work

**Status:** proposed 2026-09-18; **chunk 1 done 2026-09-19**. Supersedes the phase
framing as the *working* view. `integrated-roadmap.md` still holds the cross-track
detail and the verification; this is what to actually pick up.

Track parallelism is no longer maintained as an organising principle. Each chunk
below is one coherent piece of work with a definition of done, and the `⚡` marks
the items inside it that can genuinely run at the same time as something else.

**Five chunks, one done.** Chunk 1 below is kept as the record of what was found
and fixed, not as a to-do list. Start at chunk 2.

---

## 1. Correctness sweep — ✅ done 2026-09-19

Nine verified defects, none needing a design decision, nothing on the critical
path. Every item is closed; the outcome of each is in the table.

| Item | Outcome |
|---|---|
| Atomic save write + `.bak` + refuse to clobber an unread save | **Fixed.** Temp file + `fsync` + `os.replace`, one `.bak` per session, refusal unless this session loaded that file. 10 tests in `test_save_write_is_durable.py` |
| `time_of_day` reads `time_period` (`conditions.py:137`) | **Fixed.** Reads `time_period`, falls back to `period`/`time_of_day`. 8 tests |
| Quest loader skips `_` keys and non-objects (`quests/loader.py:17`) | **Fixed.** Per-entry guards, so one bad quest cannot abandon 22. 12 tests |
| Fourteen 0-byte test modules | **Resolved.** Five implemented, ten deleted as redundant (one was outside the discovery pattern). Disposition table in `track-H-testing.md` item 2; `HANDOFF.md` corrected by `archive/README.md` |
| `websockets` pinned, or the WS entry point marked unsupported | **Fixed.** Declared in `requirements.txt` and pinned in `requirements.lock`; `test_transport_entry_points_are_importable.py` guards both |
| `LATEST_REFRESH.json` relative, or the fixture steps documented as skipped | **Fixed.** `resolve_recorded_path` reinterprets the recorded absolute path against this checkout, so the committed fixture is now validated (data integrity + stale audit) instead of skipped |
| `boot-warning-codes.md`: 4 codes that do not exist | **Fixed, and the hole closed.** 5 codes were wrong; the doc now lists the true 20, and `_enforce_boot_warning_policy` **aborts startup** on an unknown code, because a fail-on list that cannot fire is worse than none. `test_boot_warning_codes.py` holds doc, constant and emitters equal |
| `save-content-isolation-policy.md` corrections | **Fixed.** Rewritten against the code — `save_format_version: 4` (int), `MIGRATIONS` in `save_format.py`, and the parts that are policy rather than behaviour marked as such |
| `PLAYER_MANUAL.md`: `titles` → `title` | **Fixed**, and `test_player_manual_commands.py` now fails if the manual and the registry disagree |

**Found while doing it, not on the list:** `client/**/*.gd` is syntax-checked by
nothing (`run_editor_checks.py` globs `mud-world-editor/tests/*.gd` only); 9 of the
11 capability keys the client sends to the server are read by no server code,
which is defensible but was undocumented; and the `default` theme pack omits three
`ui_strings` it reads, so those titles fall back to English.

**Done when:** the three gates are green, and a test kills a save mid-write and
asserts the previous file still loads. **Met** — and the save tests were confirmed
to fail against the old non-atomic write before being accepted.

---

## 2. Seasons and settling — ✅ 2a done, 2b decision done

Two halves, and they are **independent — do them in whatever order, or at once.**

### 2a. Preservation content — ✅ done 2026-09-19

Winter now has an answer, using only the proven chain and no timer work. Authored
into `fantasy_frontier`:

| What | Ids |
|---|---|
| Items | `item_dried_herbs` (Consumable, heal 2, value 4), `item_ale_wort` (material, value 8) |
| Station | `item_drying_rack` — field-for-field the `item_anvil` shape, `crafting_station_type: "drying_rack"` |
| Recipes (instant, `station_required: drying_rack`) | `dry_wild_herbs` (3 herbs → 3 dried), `steep_gruit_wort` (2 dried + vial → 2 wort), `ferment_house_ale` (4 wort → 1 barrel, DC 12) |
| Placements | `farmland:barn_interior` (a room from the authored `node_herb_bed`) and `town:tavern_kitchen` |
| Also | `ruleset.json` `debug.spawnable_stations["drying"]` — required, or `spawnstation` cannot reach it |

The walkable chain is now `node_herb_bed → item_wild_herbs → (rack) dried herbs →
(rack) wort → (rack) barrel of ale`, and the existing `item_wild_herbs →
item_alchemy_kit → brew_minor_heal` chain is untouched. `item_barrel_ale`, which
had no source, now has one.

**Verified** by gate (all four sets clean on the number check, content checks
passed), by 140 targeted tests, and by an end-to-end headless probe: gathered 6
herbs, dried them at the barn, steeped wort at the tavern, fermented a barrel.

**Deliberately left open — a real decision, not an oversight.** The design doc's
stage 2 wants the *alchemy table* to consume `item_dried_herbs`, which would close
the literal `herb bed → rack → alchemy table → tonic` line. Doing it means adding
`item_dried_herbs` to an existing brew's `alternatives` (the set's own
substitution convention) or authoring one more recipe. Both edit existing content
beyond this chunk's brief.

### 2b. Settling the contract — clock decided, read-or-delete gate ✅ built

- **The clock decision — ✅ made.** See "Decisions that gate chunks" below. The
  fix it implied is landed and tested.
- **The read-or-delete gate — ✅ built** as `toolkit/contract_field_audit.py`,
  wired into `run_content_checks.py` as "Audit contract fields for a reader". It
  is a **ledger, not a scanner**, and the module docstring records why: a
  quoted-literal scan gives both false negatives and false positives on this
  codebase, all three measured. It fails when a contract field is declared and
  unclassified, and when a ledger entry outlives its field. Fault injection
  confirmed both directions, and `test_contract_field_audit.py` (13 tests) keeps
  it honest.
- **What the gate found on its first run** — 63 fields, **10 declared and read by
  nothing**:

  | Field | State |
  |---|---|
  | `attack_profiles.cooldown` | declared and type-validated; weapon cooldowns are not implemented |
  | `attack_profiles.resource_cost` (+`resource`, `amount`) | `registry.py` reads it only to check the named resource exists; nothing charges it |
  | `abilities.effect_packet` | see below |
  | `effect_packets.kind`, `.value`, `.duration`, `.tags`, `.payload` | the packet's payload fields; nothing consults them |

  These are recorded as debt with a reason each, pinned in `KNOWN_UNREAD`, which
  can shrink deliberately but not grow by accident.
- **`effect_packets` — verdict now measured: wire it, and it is the last mile of
  work already half-done.** The layer is not inert: abilities declare
  `effect_packet` (`required: True`), the registry validates that the reference
  resolves, and `registry.effect_packet()` is a public accessor. What is missing
  is the final step — `ability_numbers()` reads cost, cooldown, targeting and
  level but **not** the packet, and effect application is per-spell code in
  `magic.py`. `docs/design/cross_theme_engine_contracts.md` §2 "Combat and ability
  seam" is exactly this seam, and its equipment and ability-resource halves are
  already built and tested. The alternatives are to delete the two abilities and
  three packets from both sets (smaller, loses the worked example of a neutral
  ability) or to apply a cast through its packet rather than per-spell code.
- The other three named in this item turned out **not** to be unread, and the
  ledger says who reads each: `debug_only` (three generators exclude those
  templates from loot and generation), `attack_profiles.cooldown` is the genuine
  one of that pair, and the tier weights are **partly** inert — `value_multiplier`
  and `weight_multiplier` are read, while `tier.weight` is not, because
  `instance_generator._weights_for` synthesizes weights from a positional curve.
- `work` declared: id, label, duration, recipe or outputs. **Still open.**

**Done when:** the gate can be shown to fire (re-add `debug_only` with no reader
and watch it go red) — **met**, by injecting `silent_no_op` and by deleting
`debug_only` from the schema to prove the orphan direction — and `work` is
documented enough that E and F can author against it. **`work` remains.**

**⚡ 2a and 2b do not touch each other.** 2a is JSON; 2b is `server/engine/` +
`tools/`. The only collision is if the `work` shape changes how a recipe is
written, which is why 2a ships without timers and gains `duration_days` later as
one data edit. The authored recipes reuse the design doc's own numbers so that
change is one field.

---

## 3. The second consumer

The chunk that decides whether the engine is general or is fantasy with different
nouns. Three pieces, and **each can run alone.**

| Piece | What | Owner | Scope |
|---|---|---|---|
| **Night shift crime loop** | Sources for the two unobtainable items, 2–3 containers, a locked storeroom, an `advancement.grants` table | F (+E for what it exposes) | small–medium |
| **Orbital duration** | A docking window or commodity aging — a set with no winters | F (+B if the shape strains) | small |
| **Environment: one declared value, one reader** | Collapse three expressions to one; orbital fills the `hazards` seat it already left empty | B declares, E reads, F authors | medium |
| **Social declared** | Orbital declares a `social` section instead of silently rendering fantasy's default tiers and a 15% discount | F + E | small |

**Why together:** each is the *second* use of something. Doing one proves the
convention; doing all four is what stops the next system being fantasy-shaped by
default.

**Done when:** for each system touched, two themes declare it — asserted by
content, not claimed.

**Note:** the night shift piece will expose container-theft seams
(`theft.py:40` requires naming an item the container only generates on first
attempt). That is E's, not a content fix.

---

## 4. The thin sets and the front door

Content-only, bounded, and the answer to "are the other three sets games?"

| Piece | What | Owner | Scope |
|---|---|---|---|
| **`night_shift` plays** | It declares crime/custody/locksmithing in its ruleset while its manifest lists none; no container, no income, no reason to be there | F | small–medium |
| **`modern_capsule` gets its repair café** | Its own flyer already advertises an event with no content behind it; quests + dialogue with combat, magic, crafting, gathering and economy all off | F | small |
| **The four unused objective types** | `relationship`, `discover_n`, `craft_quality`, `deliver_multi` have **zero** authored quests | F | medium |
| **Three NPC templates placed** | `forest_hermit`, `wandering_mage`, `wandering_priest` exist in no room and no spawner | F | tiny |

**⚠️ One open question first:** `modern_capsule` is `progression_model: none`. If
that is deliberate, the café item is the wrong work. Decide before authoring.

**⚡ All four are independent.** Nothing here blocks chunk 2 or 3.

**Done when:** a player can finish an errand in `modern_capsule` without touching
a fantasy system, and `night_shift` has a loop rather than a ruleset.

---

## 5. Operations, docs, depth

The chunk you pick up when you do not want to think hard, plus the work that only
matters once the world is bigger.

| Piece | Owner | Scope | Parallel |
|---|---|---|---|
| `AUTHORING_A_CONTENT_SET.md` — the missing document | J | medium | ⚡ |
| Stale-path sweep (52 lines, 8 files) | J | small | ⚡ |
| `README.md` rewrite — it fails at step one | J | small | ⚡ |
| CI runs `run_content_checks.py`; Windows job | C | medium | ⚡ |
| Gate-falsification harness | H+I | medium | ⚡ |
| Whole-state save round-trip + an old-version fixture | H | medium | ⚡ |
| Editor: byte-compare round-trip, nested-property guard, schema parity | G | medium | ⚡ |
| Save-key manifest | C | small | ⚡ |
| Twenty discoveries (5 → 25) | F | medium | — |
| `content_values` widened one loader at a time | B+I | large | — |
| Extract the duplicated command ladder | C | medium | — |

**Why last:** none of it de-risks anything above it, and two items (discoveries,
the command ladder) only pay off once there is more world to walk.

---

## Decisions that gate chunks

**1. The clock anchor — ✅ DECIDED 2026-09-19.** The answer turned out to be
neither (a) nor (b) as written, because both assumed the question was about the
*save*. It is about the **process**:

> "If everything is a server, even when single player, then the world time advances
> continuously for as long as the server is up."

So: `game_time` advances with the server's uptime, with or without sessions. It
does **not** advance while the process is stopped, and a save resumes from the
`game_time` it recorded — no wall-clock stamp, no catch-up, and
`TIME_MAX_CATCHUP_SECONDS` stays irrelevant. A single-player session is a server on
the player's own machine, so it is the same rule rather than an exception.

**This was already wrong in the code, which is why it was worth deciding.** Both
`_run_background_ticks` loops read `if not active_session_ids: continue`, so the
world advanced *only while somebody was connected* — under option (a)'s failure
mode, and invisible in play because the disconnect and the freeze happen together.
Fixed; `test_world_time_is_continuous.py` (13 tests) holds it, and the tests were
confirmed to fail against the old `continue`.

What this settles for authors, recorded in full in
`docs/design/duration-primitive.md`:

- A duration is real elapsed time **while the server runs**.
- A brew finishes while a player is logged out, if the server is up. Three days is
  three days of server time, not three days of play.

**2. Is `modern_capsule` a vignette or a game?** Gates one item in chunk 4. Still
open.

**3. Does world time advance with zero clients?** Folded into decision 1: yes.

---

## What is deliberately not scheduled

- **Economy and skill-curve tuning.** Blocked on human playtesting, which blocks
  four decisions in `ROADMAP.md`. No chunk substitutes for it.
- **Faction and territory work.** A system with no consumer; already refused once.
- **A fourth content set.** Two of the existing three are not games yet.
- **The field grid.** First it needs a decision: give cells a world, or delete the
  system. It is currently persisted, client-rendered, and connected to nothing.
- **In-game tooling ownership.** `tools/` was deleted; no track owns player-facing
  tools or a plugin surface.

---

## If you only do one thing

**Chunk 1.** It is nine small defects, none needing a decision, and one of them
can destroy a player's character today.
