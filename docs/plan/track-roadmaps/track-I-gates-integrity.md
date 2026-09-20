# Track I — Gates & Integrity

## Assessment

**State.** `run_content_checks.py` runs 13 tool invocations in 11 steps. `toolkit/` holds 12
`*validator*/*check*/*audit*` modules; three are reachable from no runner
(`template_placeholder_validator.py`, `region_policy_validator.py`, `genre_coupling_audit.py`), and the
first of those only through `toolkit/editor_validate.py`. The engine's own reference validation
(`server/engine/server/content_set.py`, twenty-odd `_validate_*` functions) is a *different* checker
from `toolkit/reference_integrity_validator.py`: they overlap, and neither is a subset.

**Strongest.** The sweep's data shape — `(id table, walker, file globs)` rows at
`reference_integrity_validator.py:582-592`, written out rather than described by a DSL — plus one
falsification test per family in `server/tests/singles/test_reference_coverage.py`. Paired with
`content_set.py:2198-2204`, which constructs the real `Recipe` and reports what the real reader
refuses. That is the pattern to keep copying: the gate asks the reader, and a test proves it can fail.

**Weakest.** The runner. `run_content_checks.py:92-94` runs JSON integrity for `fantasy_frontier` only,
while reference integrity, skill audit and playability run for all four sets; `:133-140` runs
neutrality for fantasy and orbital only, so `modern_capsule` and `night_shift` ids are never checked
against engine string literals; `:91-97` turns a missing PyYAML into a *green* run with one gate
skipped, because `data_integrity_validator.py:135` imports `yaml` at module scope for a YAML path no
content set uses — while `run_tests.py:45` treats the same dependency as exit 2. Nothing tests the
runner: `test_content_playability_check.py:44-46` asserts a tool's *name appears in the source text*.

**Surprises.** (1) `_reference_sweep_issues` builds `tables["campaigns"]` and `tables["discoveries"]`
(`:605-609`) and `REFERENCE_FAMILIES` has no family that consumes either — two tables computed,
discarded, and the walkers they were built for never written. (2) Dialogue conditions and effects
resolve ids against a bucket only `if ids[bucket] and ...` (`content_set.py:1132`, `:1162`), so an empty
bucket silently means "skip" — the failure the comment at `:985-991` calls the worst possible one.
(3) `editor_validate._dedupe` keys on `(severity, message)` (`:177`), so two rooms with the same
message text collapse to one entry keeping the first path. (4) A dialogue check with a `skill` and no
`difficulty` *is* rolled at DC 10 (`dialogue/runner.py:170`, `dialogue/manager.py:455`), but
`skill_audit._block_role:221` files it as a mere naming.

## Gate surface

Running, in order: `pack_tool.py` (client + starter packs, strict); `data_integrity_validator.py`
(**fantasy only**, skipped-green without PyYAML); `mod_manifest_validator.py`; `content_set_validator.py`
(the engine validator, all four sets); `normalize_content_numbers.py` (report-only, exits 1 on
findings); per set `reference_integrity_validator.py`, `stale_reference_audit.py`, `skill_audit.py`
(warnings only, always 0); `content_neutrality_validator.py` (fantasy, orbital);
`content_playability_check.py`; then the editor fixture, if the path in `LATEST_REFRESH.json` exists on
this machine.

No gate looks at, specifically: **campaign ids named outside dialogue** —
`npcs/villagers.json:908` `properties.tariff.campaign_id` (`commands/mercantile.py:51`) and
`knowledge/topics.json:235,262` `campaign_state.campaign_id` / `campaign_outcome.campaign_id`
(`core/knowledge_manager.py:129,143`). **Discovery ids in title conditions** — `titles.json:57`,
evaluated by `conditions.py:266-270`, with `content_set.py:2037` checking the condition's *kind* only.
**The `item_tags` half of a discovery** — `content_set.py:894-895` checks shape but nothing checks that
an item carries the tag, so `discoveries.json:5` `item_tags:["field_material"]` against
`items/materials.json:15` is a match no gate verifies. **Two sets' ids against engine literals**
(neutrality, above). **Placeholders outside the editor** (`template_placeholder_validator.py` has no
runner step). **Region policy in CI** (`region_policy_validator.py`, tested in
`test_region_policy_validator.py`, unrun).

**Gates that could fire but have no test proving it:** `content_neutrality_validator.py` has **no test
module at all** (no `*neutral*` file under `server/tests/`; no test mentions it) — the gate guarding
the engine's only real asset, with an empty allowlist at `:102`, has never been shown to fail.
`run_content_checks.py` likewise. `genre_coupling_audit.py` returns 0 at both exits (`:129`, `:165`): a
report wearing an audit's name.

## Proposed roadmap

### 1. Consume the id tables the sweep already builds

**What.** Add `_campaign_references` and `_discovery_references` walkers and two `REFERENCE_FAMILIES`
rows: campaigns over `npcs/*.json` (`properties.tariff.campaign_id`), `knowledge/*.json`
(`campaign_state`/`campaign_outcome`), `quests/*.json`; discoveries over `titles.json`
(`condition.discovery_id`, `requirements[].discovery_id`).
**Why now.** `reference_integrity_validator.py:605-609` already computes both tables and throws them
away; the `villagers.json`/`topics.json` sites are invisible to every gate today.
**Depends on.** Nothing. **Scope.** Small.
**Done when.** Breaking `villagers.json:908` makes the validator exit 1 naming the field; one new test
per family in `test_reference_coverage.py` reproduces it and no shipped set regresses.
**Risk.** `knowledge/topics.json` is walked by nothing today; a walker that mis-reads its condition
nesting will report working content.

### 2. Resolve condition identifiers where the engine already does

**What.** Extract the bucket check at `content_set.py:1117-1136` into one helper and call it for
`titles.json` conditions and requirements (`:2037-2039`). Move the `(kind, field, bucket)` table next to
`KNOWN_KINDS` in `engine/conditions.py` so evaluator and validator read one list.
**Why now.** One predicate language, one evaluator, id-checked in dialogue and kind-checked only in
titles; `titles.json:57` is a live reference nothing verifies.
**Depends on.** Track D owns `content_set.py`; this is a gap report plus a shape.
**Scope.** Small.
**Done when.** A bogus `discovery_id` in `titles.json` fails `content_set_validator.py` with file and
field in the message; Track H writes the falsification.
**Risk.** Titles may reference ids a set declares later — an empty bucket must be reported (item 3), not
silently skipped.

### 3. An empty id bucket must be reported, not silently skipped

**What.** At `content_set.py:1132/:1162/:1172/:1181/:1191/:1197`, replace `if ids[bucket] and ...` with
a counted skip: one warning per set and family naming how many references of that kind went unchecked.
**Why now.** `modern_capsule` and `night_shift` declare no quests and no abilities
(`reference_integrity_validator.py:68-70`), so every `start_quest`/`spell_known` reference in them is
unchecked while the build reports success.
**Depends on.** D lands it; I supplies the reproduction. **Scope.** Small.
**Done when.** A set with no quests and a bogus `start_quest` id produces the warning; a set with one
quest and a bogus id produces the error; both asserted.
**Risk.** Warning fatigue — printed once per set and family, never per reference.

### 4. The runner must cover every set and be impossible to pass with a gate missing

**What.** Run `data_integrity_validator.py` for all four sets with `--strict-templates`; run
`content_neutrality_validator.py` against all four; publish the step list (a `STEPS` constant or
`--list-steps`) that a test compares against a checked-in expectation; move `import yaml`
(`data_integrity_validator.py:135`) inside `validate_yaml_file` so the JSON gate has nothing to skip.
**Why now.** Three separate ways to be green with a gate absent or narrower than it reads.
**Depends on.** Nothing (both files are I's lane). **Scope.** Medium.
**Done when.** Deleting a step from `STEPS` fails a test; an interpreter without PyYAML still runs the
JSON gate for all four sets and exits 0 or 1, never "green with a skip".
**Risk.** Widening may surface real defects in `modern_capsule`/`night_shift`; the fix is content
(Track F), not an allowlist.

### 5. Make the untested gates falsifiable

**What.** The smallest fixture that makes `content_neutrality_validator.py` fire: a copy of
`orbital_salvage` with one id that also appears as an engine string literal, asserted to exit 1 naming
file and line. Same for the runner. `genre_coupling_audit.py` gains a non-zero exit on `CONTENT_LEAK`
rows or stops calling itself an audit.
**Why now.** Track I owns the gate being falsifiable at all; this gate's failure has never been
observed, and it guards the engine's only real asset.
**Depends on.** Track H writes the test; I supplies the fixture. **Scope.** Small.
**Done when.** `server/tests/singles/test_content_neutrality_validator.py` fails if the gate stops
reporting, and `run_content_checks.py` is executed once, end to end, by a test.
**Risk.** A fixture far from real content passes while the real gate is broken — build it from a real
set.

### 6. Widen `content_values` one loader at a time, starting with the silent drops

**What.** Route the drop-shaped content reads through `content_values`, beginning with
`core/backgrounds.py:169` (`skills={... if isinstance(v,(int,float))}` drops a quoted starting level),
then `player/persistence.py:279` (recipe count), `social/relationships.py:83` (reward quantity),
`player/progression.py:37` (cost). Each conversion follows `content_set.py:2198`: the reader refuses,
the gate reports the refusal.
**Why now.** `content_values` has three importers; the engine has 93 `isinstance` guards and 189
`.get(key, 0)` defaults, and the drop-shaped ones are the bug class the module was written to end.
**Depends on.** B shares the lane; each loader needs its owner. **Scope.** Medium, one module per
change.
**Done when.** A background whose `skills` value is `"2"` refuses with a message naming
`player/backgrounds.json.skills.<name>`, and a test proves the refusal.
**Risk.** Wholesale conversion is the danger: most of those 189 sites read *save files and player
state*, and `required_int` refuses an absent key by design — running the strict reader over
`player/persistence.py:181-236` would turn "load an older save" into a boot failure.

### 7. The tenth skill-audit pattern: a roll the engine gives a default DC

**What.** Treat a check-shaped block (dialogue `check`, quest negotiation objective) that names a
`skill` and omits `difficulty` as a finding rather than a naming — `dialogue/runner.py:170` and
`dialogue/manager.py:455` both read `int(block.get("difficulty", 10) or 10)`, while `_block_role:221`
files that site as `NAMES`. Rider, same loop: a `stat_bonuses` entry with no usable `stat`
(`collect:348-352` leaves `backing_stat` empty, and finding 5 at `:548` fires only when it is non-empty)
is a bonus that is always zero and is reported nowhere.
**Why now.** Both are silent in the same direction as the nine shipped patterns; neither is the
deferred co-occurrence heuristic.
**Depends on.** Nothing (I's file); the role-model change needs H to re-prove findings 3 and 4.
**Scope.** Small.
**Done when.** A dialogue check authored without `difficulty` produces
`[WARNING] dialogue/<file>:<node>.choices[i].check` naming the field and the default DC it silently
gets, asserted on a scratch set.
**Risk.** The ROADMAP records a deliberate decision that a `difficulty`-less block is not a roll
(`:2211-2213`); the finding must be per block kind — a dialogue `check` rolls, a title `condition`
compares — or it reinvents the check it was told not to invent.

## Explicitly not proposing

- **Sharing more code between `editor_validate.py` and `run_content_checks.py`.** They are correctly
  separate entry points; what must be shared is the *list* of gates (item 4). The editor omits the
  reference sweep, damage types, skills and playability, and reports `ran` with no `not_run`, so its
  green is quietly weaker than CI's.
- **Making the editor's skipped sources fatal.** The `try/except → skipped` shape keeps one broken
  validator from hiding the rest; a skipped source must be visible to the author, not fatal.
- **Deriving `normalize_content_numbers.INT_FIELDS_ANYWHERE` from the schemas.** The drift risk is real
  (a field the engine reads as an int but the list lacks makes the number gate pass and the validator
  reject), but the file is an authoring tool another track owns (`work-tracks.md:39-42`) and the runner
  already calls it read-only. Filed as a risk.
- **Widening `content_neutrality_validator`'s id collection to abstract vocabulary.** Factions,
  behaviour types and damage channels are engine-owned by design (`:13-19`) — a Track K question.
- **A `--fix` flag on any gate.** A gate that edits content cannot be the second reader.
- **The co-occurrence skill heuristic.** Already refused in the deferral ledger; unchanged.

## Risks

- **A widened walker that silently finds nothing** is this track's own recurring defect (the `$sigil`
  DSL, the dotted `_at`, the colliding site key). Every new walker ships with a falsification test.
- **Engine and toolkit validators drift.** `content_set.py` resolves dialogue conditions, effects,
  discoveries, salvage and vendor orders that the toolkit does not; adding families in one place widens
  the gap. Item 2's shared table is the pattern to generalise.
- **Widened coverage reddens the build on real defects** in `modern_capsule`/`night_shift` (items 1, 3,
  4). The answer is a fix or an allowlist entry with a reason — never a suppressed check.
- **Warning-only gates stay warning-only.** `skill_audit` returns 0 by design, so its findings live in
  CI scrollback, which is not a review surface.

## Unknowns

- Whether a template's `properties.type`/`item_family` is resolved against a registry with known
  membership or matched as a string in `ItemFactory` — I did not read the factory, so I cannot say
  whether an unregistered type refuses or silently downgrades.
- Whether every set ships `combat/elements.json`: `_damage_type_issues:759-761` returns an empty issue
  list when it is absent, which is "skip", and I checked only `fantasy_frontier`.
- Whether `region_policy_validator` is invoked by the Godot editor or by CI; it is in no Python runner
  and I did not read `mud-world-editor/`.
- Whether the sweep's rooms family is exercised without `catalogs["region_rooms"]`: the CLI sets it at
  `main():888` and every other caller skips the sweep, so that failure mode is untested, not verified.
- How many of the 189 `.get(key, 0)` sites read authored content versus persisted state; the number I
  can prove is the total, not the split.
