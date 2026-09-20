# reference/

**How a thing works.** Manuals, contracts, runbooks and checklists. These should
change when the thing changes and not otherwise, so a stale document here is a
bug report rather than a sign of progress.

| Document | Serves | State |
|---|---|---|
| [`PLAYER_MANUAL.md`](PLAYER_MANUAL.md) | players | **Needs an audit.** It tells players to type `titles`; the command is `title` (§429, §621). See Phase 4 of the integrated roadmap |
| [`server-operator-guide.md`](server-operator-guide.md) | operators | Has 13 `C:/python/old/restart/` paths in backslash form and predates the operations doc that should replace it |
| [`boot-warning-codes.md`](boot-warning-codes.md) | operators | **Wrong in four places.** Lists codes that do not exist; the engine emits different names. Operators paste these into `fail_on_warning_codes`, where a wrong code fails *silently* |
| [`support-workflow.md`](support-workflow.md) | operators | Current |
| [`launch-checklist.md`](launch-checklist.md) | operators | Current |
| [`server-feature-matrix.md`](server-feature-matrix.md) | operators | Current; useful for "does this profile do X?" |
| [`platform-architecture.md`](platform-architecture.md) | operators, contributors | Current |
| [`operator-profile-recipes.md`](operator-profile-recipes.md) | operators | Current |
| [`theme-pack-spec-v1.md`](theme-pack-spec-v1.md) | content authors | The versioned contract for presentation packs |
| [`mud-world-editor-export-contract.md`](mud-world-editor-export-contract.md) | editor authors | Current |
| [`content-authoring-and-mod-publishing-guidelines.md`](content-authoring-and-mod-publishing-guidelines.md) | content authors | Current, but **narrow**: covers publishing, not authoring from scratch. The authoring guide does not exist yet |
| [`onboarding-tutorial-flow.md`](onboarding-tutorial-flow.md) | players, docs | Current |
| [`manual-poc-test-checklist.md`](manual-poc-test-checklist.md) | testers | Current |
| [`multi-modal-1bit-brief.md`](multi-modal-1bit-brief.md) | client work | Current |
| [`save-content-isolation-policy.md`](save-content-isolation-policy.md) | operators | **Wrong about every mechanism it names**: a `schema_version: "1.3"` that does not exist and a `save_migrations.py` that was never written. Its *policy* claim is correct. See Phase 4 |

## The gap this folder has

**There is no document that teaches authoring a content set from scratch.** The
minimum shape exists only in code: three required data directories, eleven
capability names, six required manifest strings, and the required `rules/`,
`presentation/` and `opening/` files. A person cannot author a new set from the
docs today, which is the single largest documentation gap in the repo — Track J
proposes `AUTHORING_A_CONTENT_SET.md` for it and no such file is written.

## The standard for a document in here

**It must not describe behaviour that does not exist.** A reference doc that runs
ahead of the engine is a bug report filed against the future — which is exactly
what `boot-warning-codes.md` and `save-content-isolation-policy.md` are, and why
both are listed above with the defect rather than quietly left.

When you find a contradiction between a document here and the code, that is a
finding, not an edit: say which is wrong and let the owning track fix it.
