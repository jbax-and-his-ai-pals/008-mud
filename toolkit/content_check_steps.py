#!/usr/bin/env python3
"""The one definition of what a content check is.

`run_content_checks.py` (the build gate) and `toolkit/editor_validate.py` (what the
world editor's Validate button calls) both claim to run the same checks. They said
so in prose and were wrong: by 2026-09-19 the editor ran five of the gate's
fourteen, so it could report "No issues found" for a content set the build refuses
-- and the two it was missing first were the number gate and the contract-field
audit, both of which exist specifically to catch defects the *editor* produces.

This module is the fix, and the shape of the fix matters:

* **The list is data, not prose.** Every check is one `Check` here with its exact
  argv. Both runners build their steps from this list, so a check cannot be added
  to one side only -- a test asserts that too.
* **A check the editor cannot run is declared, not omitted.** `editor_skips` names
  the ones it deliberately does not run, and `editor_coverage()` reports them, so
  the editor can say what it did *not* check. That is the whole difference between
  a documented limitation and a lie.
* **Nothing here imports the engine.** Importing this module must stay cheap and
  side-effect free, because the editor imports it on the way to doing work. The
  engine is reached by the runners, through a subprocess or an in-process import.

A validator is still free to have its own CLI -- that is what makes it useful by
hand. What it may not have is its own *place in the list*.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Every shipped content set, in the order the gate sweeps them.
CONTENT_SETS: Tuple[str, ...] = (
    "fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage",
)

# The two sets the neutrality gate runs over: the mature fantasy set, and the
# sci-fi proof whose whole purpose is to show the engine reads declarations
# rather than naming content.
NEUTRALITY_SETS: Tuple[str, ...] = ("fantasy_frontier", "orbital_salvage")


def repo_root(start: Optional[Path] = None) -> Path:
    """The repository root, found by walking up to the directory holding `toolkit/`.

    Both entry points need this and each computed it differently -- the gate as
    `Path(__file__).parent`, the editor as `parents[1]`. One definition means a
    moved file fails here, loudly, rather than quietly resolving against the
    wrong root.
    """
    here = (start or Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "toolkit").is_dir() and (candidate / "content_sets").is_dir():
            return candidate
    raise RuntimeError("could not locate the repository root from %s" % here)


@dataclass(frozen=True)
class Check:
    """One content check, as both runners should run it.

    `argv_tail` is the command line *after* the interpreter: the same invocation
    an operator would type. `set_ids` says what it runs against -- no ids for a
    repo-wide check, and `data` says whether the path argument is a content set's
    root or its `data/` directory. Those two fields decide both the gate's
    expansion and the editor's coverage, so neither runner decides for itself.
    """

    id: str
    label: str
    argv_tail: Tuple[str, ...]
    # Empty for a repo-wide check; otherwise the sets it is run over.
    set_ids: Tuple[str, ...] = ()
    # True to run over every shipped set, for the repo-wide sweeps that are still
    # per-set invocations (a check that is not aimed at a particular set).
    expand_all_sets: bool = False
    # True when the path argument is `<set>/data` rather than `<set>`.
    data: bool = False
    # "append" puts the path at the end; "replace" fills a `<path>` placeholder,
    # for the checks whose path argument is not last.
    path_arg: str = "append"
    extra_args: Tuple[str, ...] = ()
    # A step that cannot run without PyYAML is skipped rather than failed, so a
    # missing dependency reads as a setup problem and not a content error.
    needs_yaml: bool = False
    # Why the editor does not run this. None means the editor should run it.
    editor_skips: Optional[str] = None
    note: str = ""

    @property
    def per_set(self) -> bool:
        return bool(self.set_ids) or self.expand_all_sets

    def sets(self, all_sets: Sequence[str] = CONTENT_SETS) -> Tuple[str, ...]:
        if self.expand_all_sets:
            return tuple(all_sets)
        return self.set_ids

    def path_for(self, set_id: str) -> str:
        return _data_path(set_id) if self.data else _set_path(set_id)


def _check(id: str, label: str, *tail: str, **kwargs) -> Check:
    return Check(id=id, label=label, argv_tail=tuple(tail), **kwargs)


def _data_path(set_id: str) -> str:
    return "content_sets/%s/data" % set_id


def _set_path(set_id: str) -> str:
    return "content_sets/%s" % set_id


# -- the list ----------------------------------------------------------------
#
# Ordered as the gate runs them: the old hand-written runner swept all of a set's
# checks together rather than interleaving sets, and this keeps that order without
# repeating the block four times.

CHECKS: Tuple[Check, ...] = (
    _check(
        "theme_packs", "Validate client theme packs",
        "toolkit/pack_tool.py", "validate", "client/themes",
    ),
    _check(
        "starter_packs", "Validate starter theme packs (strict)",
        "toolkit/pack_tool.py", "validate", "toolkit/starter_packs", "--strict",
    ),
    _check(
        "json_integrity", "Validate content-set JSON integrity: ",
        "toolkit/data_integrity_validator.py", "<path>",
        set_ids=("fantasy_frontier",), data=True, path_arg="replace", needs_yaml=True,
        editor_skips="the editor runs the raw-JSON validator over the open set "
                     "directly, rather than this sweep of the fantasy data root",
    ),
    _check(
        "mod_manifests", "Validate mod manifest compatibility",
        "toolkit/mod_manifest_validator.py", "--roots", "server/mods", "mods",
        editor_skips="validates server/mods, not the open content set",
    ),
    _check(
        "content_set_schema", "Validate content set: ",
        "toolkit/content_set_validator.py", "<path>",
        expand_all_sets=True, path_arg="replace",
        editor_skips="the editor runs the engine's own reader "
                     "(engine.server.content_set.validate_content_set) instead, "
                     "which is what this CLI wraps",
    ),
    _check(
        "abilities", "Check every ability builds: ",
        "toolkit/ability_load_check.py", "<path>",
        expand_all_sets=True, data=True, path_arg="replace",
        note="the ability registry builds a whole file inside one try, so an entry "
             "the engine refuses silently drops the rest of that file",
    ),
    _check(
        "number_types", "Check content numbers match their schema types",
        "toolkit/normalize_content_numbers.py",
        note="JSON has one number type, so a writer that only emits floats turns "
             "every authored integer into a float. This is the gate that catches it",
    ),
    _check(
        "reference_integrity", "Validate content-set reference integrity: ",
        "toolkit/reference_integrity_validator.py", "<path>",
        expand_all_sets=True, data=True, path_arg="replace",
    ),
    _check(
        "stale_references", "Audit stale content-set references: ",
        "toolkit/stale_reference_audit.py", "<path>",
        expand_all_sets=True, data=True, path_arg="replace",
        extra_args=("--output", "tmp/stale_audit_<set>.txt"),
    ),
    _check(
        "skill_audit", "Audit content-set skills: ",
        "toolkit/skill_audit.py", "<path>",
        expand_all_sets=True, data=True, path_arg="replace",
        note="skills are named in four places and declared in one; every finding "
             "is a warning on purpose -- a skill no check rolls is a design "
             "question, not a broken build",
    ),
    _check(
        "neutrality", "Validate engine content-neutrality: ",
        "toolkit/content_neutrality_validator.py", "<path>",
        set_ids=NEUTRALITY_SETS, path_arg="replace",
    ),
    _check(
        "contract_fields", "Audit contract fields for a reader",
        "toolkit/contract_field_audit.py",
        note="every contract field needs a read-or-delete verdict on record",
    ),
    _check(
        "playability", "Play every content set",
        "toolkit/content_playability_check.py",
        editor_skips="boots and plays all four sets, which is too slow for a "
                     "button an author presses while working",
        note="everything above reads files; this one boots each set and plays it",
    ),
    _check(
        "fixture_json", "Validate latest refreshed fixture JSON integrity",
        "toolkit/data_integrity_validator.py", "<path>",
        path_arg="replace",
        editor_skips="validates the committed editor fixture, not the open set",
    ),
    _check(
        "fixture_stale", "Audit stale latest refreshed fixture references",
        "toolkit/stale_reference_audit.py", "<path>",
        path_arg="replace",
        extra_args=("--output", "tmp/stale_audit_fixture_selected.txt"),
        editor_skips="validates the committed editor fixture, not the open set",
    ),
)

# The fixture checks take a path resolved from LATEST_REFRESH.json rather than a
# content set, so the gate appends them itself once that path resolves.
FIXTURE_CHECK_IDS = frozenset({"fixture_json", "fixture_stale"})

# Checks the editor runs even though they are not scoped to one set: both read
# every set's data from inside the repository.
_REPO_WIDE_FOR_EDITOR = frozenset({"number_types", "contract_fields"})


@dataclass(frozen=True)
class Step:
    """A concrete invocation: a check resolved against one target."""

    check: Check
    label: str
    argv_tail: Tuple[str, ...]
    target: str = ""

    @property
    def id(self) -> str:
        return self.check.id if not self.target else "%s:%s" % (self.check.id, self.target)


def _argv_tail(check: Check, target: str) -> Tuple[str, ...]:
    tail: List[str] = []
    for token in check.argv_tail:
        if token == "<path>":
            tail.append(check.path_for(target) if check.path_arg == "replace" else token)
        else:
            tail.append(token)
    if check.per_set and check.path_arg == "append":
        tail.append(check.path_for(target))
    for token in check.extra_args:
        tail.append(token.replace("<set>", target) if target else token)
    return tuple(tail)


def steps(sets: Sequence[str] = CONTENT_SETS) -> List[Step]:
    """Every step the gate runs, in order, excluding the fixture checks."""
    out: List[Step] = []
    for check in CHECKS:
        if check.id in FIXTURE_CHECK_IDS:
            continue
        if check.per_set:
            for set_id in check.sets(sets):
                # A per-set label ends in ": " and the set id is appended -- not
                # `% set_id`, because a label may contain "%s" as plain text
                # ("match their schema types") and would then be a format string
                # by accident.
                label = "%s%s" % (check.label, set_id)
                out.append(Step(check=check, label=label,
                                argv_tail=_argv_tail(check, set_id), target=set_id))
        else:
            out.append(Step(check=check, label=check.label, argv_tail=_argv_tail(check, "")))
    return out


def fixture_steps(fixture_path: str) -> List[Step]:
    """The fixture checks, resolved against a recorded path.

    These take a path a tool recorded rather than a content-set id, so the gate
    resolves it from `LATEST_REFRESH.json` and asks for the steps here -- which
    keeps them declared with every other check instead of hard-coded at the call
    site, where they would be the one place the editor and the gate could differ.
    """
    out: List[Step] = []
    for check in CHECKS:
        if check.id not in FIXTURE_CHECK_IDS:
            continue
        tail = tuple(fixture_path if token == "<path>" else token for token in check.argv_tail)
        out.append(Step(check=check, label=check.label, argv_tail=tail + check.extra_args))
    return out


def checks_for_set(set_id: str) -> List[Check]:
    """The checks the editor should run while `set_id` is open, in gate order.

    A check is included when it is run against this set, when it is one of the
    repo-wide checks the editor runs because they bear on what it writes, or when
    it targets this set specifically. A check the editor skips is never included --
    that decision lives in one place, on the check.
    """
    out: List[Check] = []
    for check in CHECKS:
        if check.id in FIXTURE_CHECK_IDS or check.editor_skips:
            continue
        if check.per_set:
            if set_id in check.sets():
                out.append(check)
        elif check.id in _REPO_WIDE_FOR_EDITOR:
            out.append(check)
    return out


def editor_coverage(set_id: str) -> Dict[str, str]:
    """What the editor runs, and what it does not, for one set.

    Returned so the editor can *show* its gaps rather than let an author infer
    that a green light means everything the build checks has been checked.
    """
    wanted = {check.id for check in checks_for_set(set_id)}
    coverage: Dict[str, str] = {}
    for check in CHECKS:
        if check.id in wanted:
            coverage[check.id] = "ran"
        elif check.editor_skips:
            coverage[check.id] = check.editor_skips
        else:
            coverage[check.id] = "not scoped to a single content set"
    return coverage
