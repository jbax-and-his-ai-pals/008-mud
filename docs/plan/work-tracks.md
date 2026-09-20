# Work Tracks

**Status:** active. Written 2026-09-18, revised same day to add lanes.

The project runs several conversations at once, each working on a different kind
of thing. This document defines what those kinds are, **which files each one
owns**, what each may not do, and — the part that makes parallel work actually
work — **how a track that needs something it does not have gets unblocked.**

The short version:

> **A contract is the handoff.** Once a shape is declared, the track that
> consumes it can start before the track that implements it has finished.

---

## Ownership at a glance

Swimlanes are by *kind of work*, which mostly — not entirely — lines up with
directories. This is the map; the per-track sections give the detail.

| Track | Primary lane | Also owns |
|---|---|---|
| **A** Brainstorm | *nothing.* Writes only to `ROADMAP.md` and `docs/design/` | — |
| **B** Core Engine | `server/engine/contracts/`, `server/engine/config/`, `server/engine/utils/` | the primitives track E composes, wherever they live |
| **C** Runtime & Transport | `server/engine/server/**` (minus `content_set.py`), `server/{poc_server,poc_ws_server,poc_client,launch_content_set}.py`, `server/config/**` | `server/engine/server/transport/**`, the save stack (`world/save_manager.py`, `world/save_format.py`, `player/persistence.py`), `.github/workflows/**` |
| **D** Content Loading & Contracts | `server/engine/server/content_set.py`, `server/engine/world/**` | every cross-file reference between content files |
| **E** Systems | `server/engine/{commands,core,crafting,dialogue,items,magic,npcs,player,social,ui,world}/**` | composition only — never a new primitive |
| **F** Content | `content_sets/**`, `mods/**`, `client/themes/**` | the prose, and the rulesets |
| **G** World Editor | `mud-world-editor/**` | — |
| **H** Testing | `server/tests/**`, `server/data_fixtures/**` | `run_tests.py`, `run_editor_checks.py` |
| **I** Gates & Integrity | `toolkit/*validator*.py`, `toolkit/*check*.py`, `toolkit/*audit*.py`, `server/engine/utils/content_values.py` | `run_content_checks.py` |
| **J** Documentation | `docs/**` (minus `docs/design/`), `README.md`, `docs/reference/PLAYER_MANUAL.md` | — |
| **K** Lead Design | `ROADMAP.md`, `docs/design/**`, `docs/plan/work-tracks.md` | the deferral ledger |
| **—** Archive | `archive/**` | nothing. Retired code lives here and does not grow |

**Two structural facts worth stating plainly:**

1. **`toolkit/` is split.** The *validators* there are Track I. The *authoring
   tools* (`normalize_content_numbers.py`, `materialize_item_class_defaults.py`,
   `fixture_refresh.py`) are not — they are one-shot migrations and content
   utilities, and belong to whoever is doing the content work they serve.
   `toolkit/starter_packs/` is Track F (content).
2. **`server/engine/server/content_set.py` is the engine's front door**, not its
   mechanics. It parses, validates and caches content sets — which is Track D's
   job, and it is why the last month of scaffolding bugs lived there rather than
   in `engine/contracts/`.

---

## Track A — Brainstorm

**Owns:** ideas. Systems we have not thought of, combinations of things that
exist, content that would be interesting, mechanics from other games, "what if
the world did this".

**Lane:** none. This track writes to `ROADMAP.md` and `docs/design/` only, and
only once an idea has survived Track K.

**May:** propose anything, including things that are not possible today. Cross
themes freely. Propose *removal* as readily as addition.

**May not:** commit to an implementation, or assume a proposal is scheduled. An
idea existing here implies nothing about work.

**Needs:** nothing. This track is never blocked, which is its point.

**Outputs:** a proposal with enough shape to be judged — what the player does,
what the world does, what the engine would have to know.

---

## Track B — Core Engine

**Owns:** primitives, and the vocabulary they are expressed in.

**Lane:**
```
server/engine/contracts/**      contract schemas, resolution, the registry
server/engine/config/**         curves and constants, no content names
server/engine/utils/content_values.py   the strict reader  (shared with I)
server/engine/utils/utils.py    shared helpers
```

**Where a primitive lives outside that list.** Some primitives are already
inside a system's module — `conditions.py` is the evaluation language, named by
both dialogue and titles; `naming.py` is P3's shared resolver with call sites in
`commands/crafting.py`, `items/inventory/core.py` and `world/world.py`. Those
files have **no single lane**, deliberately:

> **A file has an owner; a *concern* has an owner.** Where they disagree, the
> concern wins, and the editor of the file is the one who asked. B changing
> `conditions.py` to add an evaluator kind is B's work; E adding a call site to
> it is E's. Neither needs the other's permission, and both add a test.

This is the honest answer rather than a tidier one. Pretending `conditions.py`
belongs to one track would either stop B from growing the condition language or
stop E from using it, and both of those are worse than a shared file.

**May:** add a contract section, add a resolution helper, generalise an existing
special case into a declaration, move a hardcoded name into a contract.

**May not:**
- name anything after content. If `power_grid.py` or `ferment_manager.py`
  appears, the design has failed and this track owns that failure.
- add a special case for one theme. A theme needing a special case is a signal
  that a primitive is missing: that goes to Track K, not into the code.
- ship a primitive with no consumer. An unread declaration is worse than none,
  because content believes it did something.

**Needs:** a shape agreed with Track K. This is the slowest-moving and most
coupled layer, so its interfaces are worth arguing about before they are written.

**Outputs:** a contract (the shape), a resolver, a gate (Track I's), and tests
(Track H's).

---

## Track C — Runtime & Transport

*Added in the 2026-09-18 revision: this was the largest unowned lane.*

**Owns:** the process. Sessions, the protocol the client speaks, save/load,
configuration, entitlements, the headless server, and CI.

**Lane:**
```
server/engine/server/**            except content_set.py (Track D)
server/engine/server/transport/**  the wire: TCP and WebSocket
server/poc_server.py, server/poc_ws_server.py, server/poc_client.py
server/launch_content_set.py, server/server_main.py, server/main.py
server/config/**
.github/workflows/**
```
**Shares `world/` with D, cleanly:** `world/save_manager.py` and
`world/save_format.py` are this track's (they persist state); every other module
in `world/` is D's (they build it from content). `player/persistence.py` is
likewise the save half of a Track E module.

**May:** add a session event, a config knob, a save-format migration, a
transport message, a CI workflow.

**May not:** decide what content *means*. The runtime boots a content set and
carries its sessions; `content_set.py` is where meaning lives and that is Track
D's. It also may not let a transport concern leak into mechanics — a command
handler that branches on `session_id` is the same failure as one that branches
on `item_type`.

**Needs:** the contract (D) for loading, and B's primitives for anything it
persists.

**Outputs:** a booting server, a save format that migrates, a protocol a client
can speak, and a green CI run.

**Watch:** `save_format.py` and `persistence.py` are the two places where a
subtle bug loses player data. Changes here want Track H's reproduction before
they want a merge.

---

## Track D — Content Loading & Contracts

*Split out of "Core Engine" in the 2026-09-18 revision, because it is the layer
that has actually been generating bugs.*

**Owns:** reading content off disk and deciding whether it is valid. The
manifest, the schema, the loader, the world it builds, and every cross-file
reference made between content files.

**Lane:**
```
server/engine/server/content_set.py     the front door: parse, validate, cache
server/engine/world/**                  world, regions, rooms, loaders, housing
```

**May:** add a validation, generalise a loader, make a cross-file reference
checked, refuse something with a message that names the file and the field.

**May not:** decide how content *behaves*. Loading is not mechanics: this track
says "this reference is dangling", not "therefore this does this". It also may
not re-list a vocabulary that B owns — the recipe reader asks `Recipe` what it
refuses rather than keeping its own field list, and that is the pattern.

**Needs:** B's contracts, to know what a valid document is.

**Outputs:** a loader, a validator surface, and — this track's real product —
**an error that tells an author exactly what to fix.**

**Why it is its own track:** every content bug this project has hit in the last
month was a *loading* bug wearing a mechanics costume. A `_comment` loaded as an
NPC template, an id table that counted an authoring note as a real id, a walker
whose path was silently wrong. Those are not core-engine problems and they are
not content problems; they are the seam, and the seam had no owner.

---

## Track E — Systems

**Owns:** higher-level systems built by *composing* what Track B has already
generalised. Crafting, quests, contracts-with-deadlines, environment hazards,
power flow, social graphs.

**Lane:**
```
server/engine/commands/**     the player-facing surface of a system
server/engine/core/**         managers: quests, crafting, crime, weather, time
server/engine/crafting/**     the composition, not the recipe schemaserver/engine/dialogue/**, server/engine/social/**
server/engine/items/**        item classes that carry a mechanic
server/engine/magic/**, server/engine/npcs/**, server/engine/player/**
server/engine/ui/**           the surfaces those systems render into
```

**The defining constraint:** this track works as if it does not know what Track B
is doing. It may only use primitives that **already exist**, and it may not add
one. When it needs a primitive that is missing, that is a handoff, not a detour.

**May:** compose two existing primitives in a way nobody has, declare a new
*contract section* (with B), wire a system to a declaration.

**May not:** add engine behaviour that only its system reads. That is the
special-case failure wearing a system's clothes.

**Needs:** the contract to be **declared**. Not implemented — declared. Once
`work` is a documented section of the contracts file, this track can consume it
while B is still writing the resolver. That single rule is why the tracks can run
in parallel.

---

## Track F — Content

**Owns:** the themes. Rooms, items, NPCs, quests, recipes, rulesets, prose.

**Lane:**
```
content_sets/**        all four themes
mods/**
client/themes/**       presentation packs
toolkit/starter_packs/**
```

**May:** author anything the contracts allow, and — importantly — **discover the
contract's gaps by trying to use it.** Content is where the design is actually
tested.

**May not:** require engine work to land. If an idea needs a new primitive, that
is Track K's call and the content waits or ships a lesser version.

**Needs:** a generalised system to author against. This is why content is the
fastest track: once the shape exists, authoring is unbounded.

**Outputs:** content, and a gate report. **The gates are this track's test
suite** — a finding is either a content bug or a contract gap, and the track must
say which.

---

## Track G — World Editor

**Owns:** authoring tooling.

**Lane:** `mud-world-editor/**`.

**The rule it lives by:** *the editor and the engine read from the same source.*
It does not model content itself; it writes what the engine reads and asks the
engine whether the result is valid.

**May:** add an inspector, a structural editor, a validation surface.

**May not:** hold its own copy of a vocabulary, reimplement a check, or write a
shape the engine does not read. The int→float incident is the cautionary tale:
an editor save silently rewrote authored integers, every check missed it, and
content that had passed every gate stopped loading.

**Needs:** Track D's contracts, to know what a valid document is. An editor
cannot be ahead of the contract, only behind it.

---

## Track H — Testing

**Owns:** coverage, and the *proving* that a check can fail.

**Lane:**
```
server/tests/**            singles, batch, current
server/data_fixtures/**    the editor-migration fixtures
run_tests.py, run_tests.ps1
run_editor_checks.py
```

**The rule that makes this track valuable:** a check that has never been shown to
fail is not known to work. Every gate this project has been burned by reported
success while finding nothing — a validator that resolved an authoring note as a
real id, a walker whose path was silently wrong, an audit whose two skills were
one site. Each passed until someone proved it could fail.

**May:** add coverage, add a fixture, falsify a gate, turn a bug report into a
failing test.

**May not:** chase a coverage number, or test the shape of an implementation
rather than the contract. Coverage of a wrong behaviour is worse than none.
Nor may it *fix* the thing it is testing — a test that patches around a defect is
a test that will not notice the defect returning.

**Needs:** nothing to start; a contract to test *against* once one exists.

---

## Track I — Gates & Integrity

*New in the 2026-09-18 revision. This was previously implicit inside "testing",
and it is genuinely a different job: Track H tests the code, Track I checks the
content and the artifacts.*

**Owns:** the validation gate suite. The tools that read content and artifacts
and say whether they are coherent, and the strict reader the engine uses to read
a number out of authored JSON.

**Lane:**
```
toolkit/content_set_validator.py, toolkit/editor_validate.py
toolkit/reference_integrity_validator.py
toolkit/skill_audit.py
toolkit/content_playability_check.py
toolkit/data_integrity_validator.py
toolkit/content_neutrality_validator.py
toolkit/stale_reference_audit.py
toolkit/pack_tool.py, toolkit/mod_manifest_validator.py
server/engine/utils/content_values.py   (shared with B)
run_content_checks.py, run_content_checks.ps1
```

**May:** add a gate, widen a gate, add an allowlist entry with a reason, make a
finding name the file and the field.

**May not:** become the place correctness lives. A gate is a *second* reader, and
the moment a gate is the only thing that knows a rule, the engine and the gate
will drift. The pattern to copy is `_validate_crafting_quality_contracts`: it
constructs the real `Recipe` and reports what the real reader refuses.

**Needs:** B's contracts and D's loader, because both are what it checks.

**Two standing obligations:**
1. **Every gate must have been shown to fail.** Track H owns the falsification;
   this track owns the gate being falsifiable at all. A gate with no way to
   produce a finding is decoration.
2. **Every finding must be actionable.** A finding that does not name the file,
   the field and the fix trains authors to ignore output, which is worse than no
   gate.

---

## Track J — Documentation

**Owns:** the reader-facing surface. The manual, the guides, the reference, and
the documents that explain why the engine is shaped the way it is.

**Lane:**
```
docs/**                except docs/design/** (Track K)
README.md
docs/reference/PLAYER_MANUAL.md, docs/reference/support-workflow.md, docs/reference/launch-checklist.md
docs/reference/**, docs/mudlet/**
```

**May:** document a system, rewrite a guide, add a reference page, delete a
document that has been superseded.

**May not:** describe behaviour that does not exist. A doc that runs ahead of the
engine is a bug report filed against the future. When it finds a contradiction,
that is a finding, not an edit.

**Needs:** the contract, to describe it; and a working implementation, to verify
the description against.

**Outputs:** prose that a person who was not in the conversation can act on.

---

## Track K — Lead Design & Coordination

This is the track you are in now.

**Owns:** the shape of things.

**Lane:**
```
ROADMAP.md
docs/design/**
docs/plan/work-tracks.md    (this document)
```

**Four jobs:**

1. **Arbitrate the contract.** When B and E disagree about a shape, decide it
   once and write it down. The contract is the interface between parallel work;
   an ambiguous contract is what makes parallel work expensive.

2. **Keep the deferral ledger** (below). A canonical list of *refused* ideas with
   the reason. Without it, the same proposal arrives every few weeks and is
   re-litigated. With it, a refusal is a decision rather than a mood.

3. **Watch for special cases.** The engine's value is entirely in content
   neutrality, and every theme will arrive with "just one special case". This
   track notices, names the missing primitive, and routes it to B.

4. **Sequence capacity.** Roughly: B is the bottleneck, E is the multiplier, F is
   the filler, I is the safety net.

**May not:** do the work of another track inline. If the lead starts writing the
resolver to unblock something, the structure has failed — the correct move is to
hand B a shape and let it land there.

---

## Shared zones

Seven places where lanes legitimately overlap. Named so the overlap is a plan
rather than a collision. (The heading said "Five" while the table listed seven;
Track K caught it, which is the sort of thing a count in prose is for.)

| Zone | Shared by | The rule |
|---|---|---|
| `toolkit/` | I (validators) and F (migrations, packs) | a *validator* is I; a *one-shot content tool* is F |
| root `run_*.py` | H (`run_tests`, `run_editor_checks`) and I (`run_content_checks`) | each runner has one owner; adding a step to someone else's runner is a handoff |
| `server/engine/config/` | B (curves, contracts) and E (`config_display`) | config owns *numbers and names*; a system that needs a rule declares it, it does not add a constant |
| `server/engine/world/` | D (regions, rooms, loaders), E (the systems that read rooms) and C (the save stack) | building the world from content is D; *system behaviour that reads it* is E; persisting it is C |
| `server/engine/player/` | E (`core`, `progression`, `persistence`) | mostly E; the save half follows C's format |
| `server/data_fixtures/` | H (fixtures) and F (the content they mirror) | fixtures are generated, never hand-edited; a fixture that disagrees with content is a finding |
| `client/themes/` | F (packs) and C (the client that reads them) | the pack format is a contract; the reader is runtime |
| `conditions.py`, `naming.py`, `game_object.py` | B and E, on the concern rule above | B grows the language, E calls it; both add a test |

**If you find yourself editing a file another track owns,** the move is to write
the finding down and hand it over — not to make a small exception. Every
exception so far has cost more than the handoff would have.

---

## The handoff

Every cross-track need is one of four handoffs. Naming them is what stops a
conversation from stalling.

| Handoff | From → To | The form it takes |
|---|---|---|
| **Shape request** | E or F → K → B | "We need to declare X. Here is the smallest shape that would serve." |
| **Contract declaration** | B → E, F | A documented section plus its resolver. *Consumers may start here*, before it is finished. |
| **Gap report** | F → K → B or D | "Content cannot express Y properly." Either a primitive is missing or the idea is wrong. |
| **Falsification** | H → whoever | "This gate does not fire." A reproduced failure, not an opinion. |

**The contract-first rule in full:** *a track may consume a declared contract
before the declaring track has finished implementing it.* This is the only reason
these conversations can proceed independently, and it carries one obligation —
the declaring track owns the shape. If B changes a contract after E has consumed
it, B owes E the migration.

---

## The deferral ledger

Kept here because it is short, and because a refusal without a reason gets
re-proposed. Each entry is a decision, not a backlog item.

| Refused / deferred | Reason |
|---|---|
| Bespoke power-grid system for `orbital_salvage` | It wants a general **flow** concept on the resource contract. A `power_grid.py` the fantasy set could never use is the failure mode. |
| Per-theme special cases in general code | The engine's only real asset is that it does not know what a barrel is. |
| A heuristic for "two skills that always roll together" | One shipped instance. A rule with one example is a guess wearing a rule's clothes. Revisit at five. |
| Unifying the stopwatch and calendar duration models | They answer different questions. Poison that ticks while you sleep is a bug, not a simplification. |
| Chasing a coverage number (Track H) | Coverage of the wrong behaviour is worse than none. |
| A gate that is the only place a rule is known (Track I) | A second reader that disagrees with the first is how the engine and the gate drift. |
| Editing a file another track owns "just this once" | Every exception so far has cost more than the handoff would have. Write the finding down instead. |

### Adopted: a system is not finished until two themes use it

Decided 2026-09-18. The engine's only real asset is that it is not fantasy-shaped,
and the way that gets proven is a second consumer — not a claim, not a design
doc, a set that actually declares the thing.

**What it means in practice:** a system that only `fantasy_frontier` uses is at
"proposed" no matter how well it works. Track E should *reach for* a second
theme while building, and Track K should ask for one before calling a system
done. It costs one adoption per system and it is the only defence against
everything slowly becoming fantasy with different nouns.

**The first candidate is already chosen.** The duration primitive's fantasy case
is the preservation chain — drying herbs, brewing tonics, fermenting ale. The
orbital case is nearly free once the primitive exists: commodity aging on a
salvaged crate, or a docking window that opens and closes. If the primitive
cannot express both, it is not a primitive yet.
---

## Existing track documents, and how they relate

Several tracks already have their own documents. They remain the detail; this
document is the map.

| Document | Track |
|---|---|
| [`world-editor-track.md`](world-editor-track.md), [`world-editor-gap-matrix.md`](world-editor-gap-matrix.md), [`world-editor-evaluation.md`](world-editor-evaluation.md) | G |
| [`engine-capability-track.md`](engine-capability-track.md) | B (predates the contract work; its capability *targets* are still the right list) |
| [`content-authoring-and-mod-publishing-guidelines.md`](content-authoring-and-mod-publishing-guidelines.md) | F |
| [`documentation-track.md`](documentation-track.md), [`documentation-information-architecture.md`](documentation-information-architecture.md) | J |
| [`accessibility-track.md`](accessibility-track.md), [`mobile-track.md`](mobile-track.md), [`client-track.md`](client-track.md), [`server-setup-wizard-track.md`](server-setup-wizard-track.md), [`steam-packaging-track.md`](steam-packaging-track.md) | **surfaces** — they consume the engine and can run whenever |
| [`/ROADMAP.md`](../../ROADMAP.md) | K — the active phase order; wins over anything here |

`docs/archive/roadmap-README-superseded.md` marks most of this directory as historical. That is
still true for the phase ordering; these documents are current as *track detail*.

---

## Known gaps in this structure

Written down so they are decisions rather than oversights.

1. **No performance track.** Lazy-vs-scheduled evaluation is a real decision with
   real scale consequences, and it is closest to C without C being accountable
   for load. Revisit when a content set has enough timers to matter.
2. **No economy or balance track.** Gold sinks, XP curves and the ×1.25
   multiplier all wait on human playtesting, which is not a track so much as a
   missing person. Until then, balance decisions belong to K and are guesses.
3. **Track E has no home for a system that spans two themes.** Composing two
   primitives for `orbital_salvage` that fantasy could also use is exactly the
   right shape, and nothing currently rewards doing it. A "second consumer"
   convention would: a system is not finished until two themes use it.
4. **`chat_sim/` has no owner.** It is a UI/simulation experiment, closest to a
   research surface. Either give it a lane or archive it — an unowned directory
   rots.
5. **`server/*.py` at the root is a junk drawer** — `test.py`, `run_coverage.ps1`,
   `run_playtest_lab.py`, `run_snapshot_checks.ps1`, `setup_wizard_cli.py`. Each
   belongs to a track (C mostly, `run_playtest_lab.py` arguably H) but sitting
   loose in `server/` makes the lane boundary invisible. Worth a sweep.
6. **No track owns in-game tools.** `tools/` was deleted on 2026-09-18: two
   pygame map viewers superseded by the Godot editor, plus three one-off repo
   utilities. That removes the *editor* question, not the *tool* question — a
   plugin surface, an in-game authoring command, or a mod-facing tool API has no
   home at all today.

**Closed since the previous revision:** `server/engine/ai/` had no owner. It was
archived to `archive/ai-conversation/` — see below — and `tools/` was deleted.

## Retired: what left the repository and why

| Thing | Date | Fate |
|---|---|---|
| `server/engine/ai/` (LLM ambient text, 3 prompt targets) | 2026-09-18 | archived to `archive/ai-conversation/` with the prompt set and a design note |
| its two test files | 2026-09-18 | archived alongside; they describe the behaviour for a future restore |
| `AI_AMBIENT_*` config keys and the `GameManager` wiring | 2026-09-18 | deleted; all three keys were read only by the archived manager |
| `tools/` (two pygame map viewers, three repo utilities) | 2026-09-18 | deleted; the viewers are superseded by `mud-world-editor/`, the utilities live in `git log` |

**The AI removal is worth recording properly, because the shape recurs:** the
system was *enabled by default and switched off in code*. `LLMInterface._load_model`
opens with an unconditional `return` — `# loading the model takes several seconds,
so disabling for now until we're ready to work more with ai functionality` —
while `AI_AMBIENT_ENABLED` stayed `True`. So `AIManager` was constructed on every
`GameManager`, ran on every world tick, and spawned a worker thread every five
seconds, then returned at its first guard every time, because `pipe` is only
assigned *after* that `return`. Nothing was broken, so no gate could see it; the
only honest signal was a log line reading `Starting new AI generation thread.`,
which looks like progress and was the whole of the work being done.

**The idea is kept, not the implementation.** The goal is a model small and fast
enough to generate conversation from live game context; today's local models do
not do the job. `archive/ai-conversation/prompts.json` is the part worth
preserving, and the README there records what would have to be true to bring it
back — including that a restore should hang off a **content-declared text
source** rather than a manager on `GameManager`, so the engine knows "this text
is generated" rather than "this text is a language model".
