# Track K — Lead Design & Coordination

Roadmap for the structure, sequencing and process track. Nothing here is
implemented by this document. Written 2026-09-21 against `ROADMAP.md`
(2,365 lines), `docs/plan/work-tracks.md` (553 lines) and
`docs/design/duration-primitive.md` (256 lines).

## Assessment

**State.** K owns three files (`work-tracks.md:374–378`): `ROADMAP.md`,
`docs/design/**`, `docs/plan/work-tracks.md`. All three exist and are current;
the deferral ledger at `work-tracks.md:444–475` is the only refusal list in the
repo. What K does not have is any artifact: no sequencing list, no contract index,
no record of which theme currently satisfies the two-theme convention
(`work-tracks.md:459–469`). `docs/roadmap/track-roadmaps/` did not exist before
this file. The phase order stops at P9, which is partly shipped (four batches,
`ROADMAP.md:1578–1777`) and partly open (line 1660).

**Strongest.** The handoff protocol is the best structural writing here and it is
enforced by shape, not sentiment. `work-tracks.md:429–434` names four handoffs;
lines 436–440 attach the obligation that makes parallelism possible — *the
declaring track owns the shape and owes consumers the migration.* The `may not`
clauses are falsifiable: B may not ship an unread declaration (lines 92–94), H may
not fix what it tests (lines 288–290). The D split is grounded in real bug history
(lines 174–178), and `run_content_checks.py` plays all four sets on every gate run
(lines 147–152 of that script) — a live-play gate the document never claims.

**Weakest.** The map and the lane blocks contradict each other, and four live
engine modules belong to nobody. `work-tracks.md:25` gives B "the mechanics inside
`server/engine/**`"; B's lane block (78–83) lists only `contracts/ config/ utils/`,
and E's (189–197) enumerates every other subpackage — so under one line B owns the
tree E owns under another. Separately, `server/engine/conditions.py`,
`game_object.py`, `naming.py` and `presentation.py` have no lane at all. That is
not hypothetical: `ROADMAP.md:349–354` has an open item to consolidate faction
comparison behind `world.is_hostile` — an edit to an unowned file — and `naming.py`
is P3's shared resolver whose call sites span E (`commands/crafting.py`,
`items/inventory/core.py`) and D (`world/world.py`). The map also omits files that
exist and are named nowhere: `.github/workflows/editor-checks.yml` (G's gate, but
`work-tracks.md:118` gives all of `.github/workflows/**` to C),
`toolkit/template_placeholder_validator.py`, `toolkit/region_policy_validator.py`
(both absent from I's lane, 306–318), `run_content_checks.ps1` (line 317 registers
only the `.py`), and the 23 `.gd` checks under `mud-world-editor/tests/`, which no
document inventories. The ledger has no admission rule — it mixes feature refusals,
code policy, heuristics and collaboration rules — and `work-tracks.md:404` says
"Five places" above a table with seven rows (408–416).

**Surprises.** (1) **92 uncommitted paths.** `git status --porcelain` reports 92
entries across `server/engine/**`, `content_sets/**`, `toolkit/` and `ROADMAP.md`;
the last commit is `8c2fb0a 2026-09-18`, while the roadmap describes work dated
2026-09-20 and 2026-09-21. Eleven tracks on one working tree with no commit
discipline is the largest coordination hazard here and no document mentions it.
(2) **The editor is ahead of its own record.** `ROADMAP.md:1503–1505` still lists
backgrounds/titles/collections/discoveries surfaces as open, but
`background_authoring_smoke.gd`, `title_authoring_smoke.gd`,
`collection_authoring_smoke.gd` and `discovery_authoring_smoke.gd` all exist in
`mud-world-editor/tests/`. The editor backlog is stale optimistically — a deferral
that already shipped. (3) **The editor-check count is wrong in three files at
once:** `ROADMAP.md:1425` says 14, `ROADMAP.md:1503` says 18, and
`world-editor-evaluation.md` says 12 (line 186), 18 (419) and 19 (495); the disk
says 23. `run_editor_checks.py` globs the directory (line 69), so the number is
self-maintaining and every prose claim about it rots. (4)
`server/engine/contracts/registry.py` carries one `schema_version` for the whole
registry (`__init__.py:26`, `registry.py:273`), refused on mismatch (325–331) —
which puts the contract-first rule in direct tension with the fail-closed rule: a
consumer declaring against an unimplemented section must ship in the same registry
bump as B's resolver, so "consumers may start early" holds only inside one commit
(see `duration-primitive.md:249–253`). (5)
`docs/design/place_making_and_town_security.md:3` calls itself "postponed (see
ROADMAP.md)", but `postponed` appears nowhere in `ROADMAP.md`, whose only housing
entries are `deliberately later` (line 2267) and a P8 test bullet (line 1318) — a
design doc pointing at a deferral that was never recorded.

## Structural problems found

1. **B/E overlap** — `work-tracks.md:25` vs 189–197. Fix: drop "the mechanics
   inside `server/engine/**`" from B's row; state it positively (B owns
   `contracts/ config/ utils/`; E owns every subpackage not named to another track).
2. **Four unowned modules** — `server/engine/{conditions,naming,game_object,presentation}.py`.
   Fix: one map line — `naming.py`/`conditions.py`/`game_object.py` → E,
   `presentation.py` → C (it resolves per session, `ROADMAP.md:238–245`).
3. **Seven zones labelled five** — `work-tracks.md:404` vs the table at 408–416.
   Also unclassifiable under line 410's rule: `toolkit/complete_gem_merge.py`,
   `merge_editor_gems.py`, `migrate_editor_state.py`, `editor_export_shim.py`.
4. **No ledger admission rule or categories** — lines 449–457 hold a feature
   refusal, a code policy, a heuristic, a modelling decision, two track-internal
   disciplines and a collaboration rule. Fix: a `Kind` column plus one sentence:
   *an entry exists if a reasonable person would re-propose it.*
5. **The ledger is unfindable** — line 445 says it is kept here "because it is
   short", but nothing in `ROADMAP.md` links to it. Fix: one pointer from
   `ROADMAP.md`'s Decisions section.
6. **`ROADMAP.md:360` cites `game_object.py:147`** for the
   `__class__.__name__ == "Player"` check; line 147 is blank and the check is at
   line 171. Fix: cite symbols, not line numbers, in a 2,365-line file.
7. **Stale revision metadata** — `docs/archive/roadmap-README-superseded.md:23` still says "seven
   tracks" after the 2026-09-18 revision added C, D and I. Fix: correct the README
   and add a three-line dated changelog to `work-tracks.md`.
8. **Line 489's "surfaces … can run whenever"** is the only capacity statement in
   the repo and the reason nothing schedules those tracks. Fix: mark them out of
   scope until a theme satisfies the two-theme convention.

## The next five pieces of work, in order

1. **The duration primitive, declared not implemented — B, shape by K.** Ship the
   `timers` property, the `work` section in the schema, and the day-vs-second
   canonical answer (`duration-primitive.md:228–231`); no `work_manager.py`, no
   tick loop (215–222). *Why first:* the design doc names it as what other tracks
   are waiting on (249–253), it has a shipped precedent (`respawn_days`) and
   authored endpoints (`item_barrel_ale`, `item_wild_herbs`). *Unblocks:* E's
   preservation chain, F's winter counterplay, the first honest test of the
   two-theme convention.
2. **The fantasy preservation chain — E, content by F.** Drying rack → dried herbs
   → tonic, then the barrel ferment with its thin/sound/fine gradient
   (`duration-primitive.md:164–176`). *Why here:* one theme must use it before a
   second can be asked to, and it is the smallest vertical slice the design
   commitments require (`ROADMAP.md:43`).
3. **The second consumer in `orbital_salvage` — F and E.** A docking window or
   commodity aging, whichever needs less engine (`work-tracks.md:471–475`). *Why
   here:* the adopted convention (459–469) is the only defence against the engine
   becoming fantasy with different nouns, and a retrofit costs more than designing
   for two now. *Unblocks:* calling the primitive finished at all.
4. **Bring `night_shift` up to contract currency — F, gates by I.** The set is one
   region and three data files; `ROADMAP.md:374–377` still has an unchecked
   definition-of-done item requiring it to exercise chest generation, delivery
   quests and debug stations. *Why here:* the cross-theme claim currently rests on
   one thin reference set, and a verifier that cannot author the thing being tested
   cannot verify it. *Unblocks:* the two-theme convention as a rule rather than an
   aspiration.
5. **Contract-change sweep: editor surface and a falsifying gate for items 1–3 — G
   and I.** *Why here:* every prior contract ship paid this later and more
   expensively (dialogue was the last un-surfaceable system, `ROADMAP.md:1480–1490`),
   and the working discipline — inspector writes, engine validator judges — already
   exists at lines 1441–1452. *Unblocks:* F authoring `work` without hand-edited
   JSON.

**Where the critical path runs.** Not through B: its block is small and
declared-first, which is the point of the contract-first rule. The path runs
**E → F → the second consumer**, and the true constraint is *theme capacity* — the
named filler (F) is also the required verifier, and its second and third sets are
thin. Loading F with low-priority content starves verification. K owns that
arbitration.

## Risk register

1. **Human playtesting never happens.** *Trigger:* another item ships "verified by
   automated coverage" with no session date. Four still-open decisions
   (`ROADMAP.md:2296–2299`), route balance (624–627) and P8's three unchecked items
   (1318–1325) all wait on one missing person; balance is currently K's guess by
   admission (`work-tracks.md:504–506`). *Mitigation:* one protocol, three recorded
   sessions across two playstyles, questions fixed in advance (K-6); a checked box
   is not evidence.
2. **Content-neutrality collapses under theme pressure.** *Trigger:* an
   `if work_id == "ferment"` (the failure named at `duration-primitive.md:218`) or a
   control offering a class that does not exist (`ROADMAP.md:1458–1460`).
   *Mitigation:* keep the neutrality allowlist empty (340–341) and require every
   primitive to name its second consumer before implementation.
3. **Save-format churn.** *Trigger:* a duration/serialization change that violates
   "no new persistence shape" (`duration-primitive.md:219–221`). Saves are at
   version 4 with a refuse-the-future rule (`ROADMAP.md:1848–1870`), and
   `save_manager.py`, `persistence.py` and `save_format.py` are all currently
   modified. *Mitigation:* a format bump ships with a round-trip test, a migration
   entry, and a same-message handoff to C and H.
4. **The editor falls behind the contracts.** *Trigger:* a contract ships with no
   inspector and no ledger entry saying so (the dialogue case). *Mitigation:* the
   check count is self-maintaining and therefore not a signal; require the
   authoring test — inspector writes, engine validator judges — per new section.
5. **Track abandonment.** *Trigger:* a batch series stops with no closing entry.
   Already true once: the editor audit reaches Batch D (`ROADMAP.md:1478`) while
   line 1503 still lists surfaces as open, yet four smoke tests exist.
   *Mitigation:* a weekly staleness sweep over the § Additions list; unowned
   directories assigned or archived within two weeks.

## Proposed roadmap

### K-1: Sequencing note and a capacity rule
**What:** A dated ≤40-line "next five" at the top of `ROADMAP.md`, kept in sync
with `work-tracks.md:394`, naming the critical path and stating that F's
verification workload outranks its filler workload.
**Why now:** the order above lives only in conversation; eleven tracks are each
choosing their own next item.
**Depends on:** nothing. **Scope:** small.
**Done when:** `ROADMAP.md` opens with a dated ordered list of five items with
owners, and the previous list moves to the archive file.
**Risk:** becoming a second roadmap. Mitigate by making it a subset of P-items,
never a new taxonomy.

### K-2: The ledger gets three columns and an admission rule
**What:** Add `Kind` (refused / deferred-until / settled-don't-reopen), `Decided`,
`Revisit when` to `work-tracks.md:449–457`, plus the admission sentence.
**Why now:** six-plus real deferrals are prose in `ROADMAP.md` and will be
re-litigated; "revisit at five" (line 453) is uncheckable without a trigger column.
**Depends on:** nothing. **Scope:** small.
**Done when:** every row has three columns and the § Additions entries are in.
**Risk:** over-population. The admission sentence is the filter.

### K-3: Contract index — one table for every active shape
**What:** One table in `work-tracks.md`: registry `schema_version`, plus
`CONTENT_SET_SCHEMA_VERSION`, `PLUGIN_MANIFEST_SCHEMA_VERSION`,
`MANIFEST_SCHEMA_VERSION`, `save_format_version` and the editor pack format — each
with declaring track, consumer tracks, and editor surface (or ledger row). Add the
rule: *a contract change is a handoff message to every consumer named here.*
**Why now:** the answer to "who consumes this" is currently a grep, and
`registry.py:315–331` refuses unknown versions outright.
**Depends on:** K-2. **Scope:** small.
**Done when:** the table covers all six shapes and one real change — the `work`
section — is announced through it.
**Risk:** rot. Write the grep that regenerates the version column beside it.

### K-4: ADRs — one page, only for decisions that bind
**What:** Use the unused template `docs/archive/adr/0000-template.md` (452 bytes,
referenced only by `docs/archive/roadmap-README-superseded.md:30`; one real ADR exists). Restrict to
decisions a later track cannot cheaply reverse: stopwatch-vs-calendar
(`duration-primitive.md:195–209`), canonical time units, save-format bumps,
contract-version policy. Backfill three: duration models, content-neutrality as
the asset, contract-first with migration owed.
**Why now:** the practice is a stub and the same distinctions are re-derived in
prose. Three backfills cost an hour.
**Depends on:** nothing. **Scope:** small.
**Done when:** three one-page ADRs exist and `work-tracks.md` links the directory.
**Risk:** ceremony. Hard cap: one page, no status workflow, no superseding chain.

### K-5: Ownership cleanup — close the gaps that block edits
**What:** One revision of `work-tracks.md`: the B/E overlap (line 25); lanes for
the four root modules; `editor-checks.yml` under G and the 23 `.gd` checks
registered as G's inventory; `run_content_checks.ps1` added to I; "Five" → "Seven";
and a verdict on `chat_sim/`, `server/mods/`, root `mods/`, `dist/packs/`.
**Why now:** three open roadmap items (349–354, 359–361) name edits to files no
track owns — the deadlock the handoff protocol exists to prevent.
**Depends on:** nothing. **Scope:** small.
**Done when:** every path in the lane blocks resolves to exactly one track and a
root walk finds no unowned directory.
**Risk:** re-litigating lanes. Timebox to one pass; record disagreement as
`Kind: settled`.

### K-6: Playtest validation protocol — replace the checkbox
**What:** The P8 item at `ROADMAP.md:1322–1325`, reduced to one file and one row
per shipped system: `contract verified / content authored / journey demonstrated /
human session (date)`. Questions fixed in advance from the still-open list.
**Why now:** it is risk #1 and it blocks four open decisions.
**Depends on:** K-1. **Scope:** small.
**Done when:** the file exists and at least one row carries a session date.
**Risk:** rows ticked without a session. Only the human column may say "validated".

## Additions to the deferral ledger

| Refused / deferred | Kind | Reason it belongs here |
|---|---|---|
| Sweep of the ~120–150 numeric read sites (`ROADMAP.md:1928–1936`) | deferred-until | "Deliberately not done"; each site needs a judgement. Trigger: the next `min_crafts`-class incident. |
| `max_total_summons` stays written-and-unenforced (`ROADMAP.md:1888–1891`) | refused-for-now | Recorded "rather than fixed" because binding it removes a mechanic players have. Will be re-proposed as a bug. |
| Duplicate-JSON-key check (`ROADMAP.md:396–399`) | deferred-until | Proposed, cheap, unbuilt after a near-miss; without a row it reads as an oversight. |
| `advancement.json` alternate config path (`ROADMAP.md:590–593`) | deferred-until | "Supported but unused" — split the rules out or drop the path. |
| Player-chosen starting towns (`ROADMAP.md:959–963`) | deferred-until | Word-for-word "deliberately deferred"; lives only in P7 prose. |
| Restoring LLM ambient text (`work-tracks.md:531–552`, `archive/ai-conversation/`) | refused-for-now | Idea kept, implementation archived; the README records what must be true, including a content-declared text source. |
| Editor batch E onward — contract editing, campaign authoring (`ROADMAP.md:1503–1505`) | deferred-until → **half un-deferred 2026-09-20** | The A–D series stops with no closing entry while four later smoke tests exist. **Updated:** contract editing is no longer deferred — it is Track G item 9 and `ROADMAP.md` P10, on the condition that the editor asks `ContractRegistry` rather than modelling families. Campaign authoring is still open, as Track G item 11, and it needs this track's build-or-drop call (below). |
| `escort` / `defend-hold` / `timed` / `puzzle` / `theft-smuggling` objectives (`ROADMAP.md:881–882`) | refused-for-now | Each "needs its own subsystem"; `timed` overlaps the duration primitive and must not be built twice. |
| A performance/evaluation-cost track (`work-tracks.md:501–503`) | deferred-until | Already a named gap; as a row it stops being rediscovered. Trigger: the first set with enough timers to matter. |
| `chat_sim/` disposition (`work-tracks.md:512–513`) | deferred-until | On disk with `main.py`, `src/`, `requirements.txt`; give it a lane or archive it. |

Not refusals, just defects: `server/engine/ui/ui_manager.py:65–73` still branches
on `__class__.__name__`, and `ROADMAP.md:360–361` cites a stale line number.

## Handoffs

1. **Campaign authoring: build or drop** (to this track, from G item 11, 2026-09-20).
   The editor loads `data/campaigns/` into a cache no panel shows, no button creates
   and `save_all()` never writes, while the dialogue vocabulary lets an author write a
   `start_campaign` effect naming a campaign the editor cannot list. The decision is
   cheap and it unblocks the item either way: build the graph editor (the quest stage
   view is most of it) or stop loading campaigns and narrow the `start_campaign`
   picker in the same change.
2. **The editor batch's sequencing is this track's call** (G, B, F). Chunk 6 of
   `docs/plan/chunks-of-work.md` is the next batch by the user's direction of
   2026-09-20; the pieces that can run at once are marked there, and the one hard
   dependency is Track B's per-section validation surface. If capacity is one
   conversation, the order in `editor-readiness.md` §7 is the answer and campaigns
   are last.

## Explicitly not proposing

- **No CODEOWNERS or ownership CI gate.** There is no review queue; the tracks are
  parallel conversations in one tree, so the gate would be edited by the agent it
  blocks.
- **No standup or sync document.** The tracks share no calendar; K-1's dated list
  is the substitute.
- **No new tracker, board, or `TODO.md`** — not even a small one. The roadmap is
  already 2,365 lines; the failure mode is dispersion.
- **No branch-per-track policy.** Twelve branches would worsen the shared zones.
  Commit discipline — one finding per commit, roadmap updated in the same commit —
  is the smaller fix for the 92 uncommitted paths.
- **No rewrite of `work-tracks.md`.** Six targeted edits; ten other proposals cite
  it right now.
- **No roadmap renumbering.** Renumbering P-phases or tracks while other proposals
  cite A–K creates the same rot as `game_object.py:147`.

## Unknowns

- **How many of the eleven tracks run concurrently, and at what throughput?** The
  two-theme convention assumes F can adopt a second theme per system; if F is one
  conversation, that convention is a tax it cannot pay.
- **Is human playtesting capacity hours, days, or none?** Risk #1 is ranked first
  on "none yet". If sessions already happen, four open decisions are cheaper than
  assumed.
- **Are the gates green on this exact tree?** The brief states ~4,180 singles; the
  roadmap records 3,751 at P6 (`ROADMAP.md:919`) and 4,077 at P7 (993). I did not
  run them — out of scope for this track — so I cannot say how ~400 tests of growth
  and 92 modified paths coexist.
- **Is `night_shift` or `orbital_salvage` the designated reference set?**
  `ROADMAP.md:374–377` says `night_shift`; P9's proof was built in
  `orbital_salvage`. If that changed, item 4 of the sequence changes.
- **Who owns the rest of `docs/roadmap/`?** J's lane is `docs/**` minus
  `docs/design/`; K's is one file. `HANDOFF.md`, `next-session.md` and
  `world-editor-evaluation.md` are edited and unassigned.
