#!/usr/bin/env python3
"""Report what a content set's skills are, and what is odd about them.

A skill is a named number with a level and xp that `SkillSystem` rolls against a
difficulty. That mechanism is already general and already content-neutral: nine
systems call it. What is missing is a *declaration* -- nothing says which skills a
set has, so nothing can check the names against anything, and the same idea is
spelled three ways (a per-system `skill` in the ruleset, an inline `skill_name` on
a room exit, and a hardcoded `"crafting"` in the crafting manager).

This tool does not introduce the declaration. It reads what exists and says out
loud what the names are being used for, then flags the seven things that are
currently silent. **Every finding is a warning**, on purpose: a skill that
nothing checks is not an error, it is a design question, and the point of listing
it is to be able to see the instances and decide the pattern.

    python3 toolkit/skill_audit.py content_sets/fantasy_frontier/data

What it reports, per set:

  1. a skill named in content and declared nowhere
  2. a skill granted to a background and declared nowhere
  3. a declared skill no content names
  4. a declared skill with no system that checks it
  5. a skill whose backing stat no stat vocabulary contains
  6. a skill whose name is also a stat name
  7. two skills declared at the same site, which roll as one practice
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
if str(_SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(_SERVER_ROOT))


# How a site contributes to a skill's life.
#
# `rolls` is a check the engine makes *and* grants xp for the attempt. That is
#   `SkillSystem.practice_check` (a dialogue choice, a quest negotiation, a room
#   exit's `skill_name` -- `world/world.py:402`), or `attempt_check` with an
#   explicit `grant_xp` beside it, which is how lockpicking and theft do it.
# `threshold` is a comparison that rolls nothing: `{"skill": ..., "minimum": N}`
#   in the crime custody requirements reads the level and stops. A skill that is
#   only ever gated on can be required forever and never improve, which is why
#   this is worth its own name.
# `named` is a mention that is neither: a title's requirement, a background that
#   starts you with a level.
#
# A room exit was filed as `threshold` in the first version of this tool, on the
# assumption that a requirement "reads the level and passes or fails". It calls
# `practice_check`, so it trains, and the tool was one shipped skill exit away
# from reporting a working skill as untrainable. Track E caught it; the
# regression test is `test_a_room_exit_rolls_and_trains`.
ROLLS = "rolls"
THRESHOLD = "threshold"
NAMES = "named"
CHECKS = (ROLLS, THRESHOLD)
TRAINS = ROLLS


@dataclass
class Finding:
    severity: str
    path: str
    message: str

    def __str__(self) -> str:
        return "[%s] %s - %s" % (self.severity.upper(), self.path, self.message)


@dataclass
class SkillUse:
    """Everything one run of the audit learned about one skill name."""

    name: str
    declared_by: Set[str] = field(default_factory=set)
    backing_stat: str = ""
    sites: Dict[str, str] = field(default_factory=dict)  # site key -> CHECKS/TRAINS/NAMES
    files: Set[str] = field(default_factory=set)

    @property
    def declared(self) -> bool:
        return bool(self.declared_by)

    @property
    def checked(self) -> bool:
        return any(role in CHECKS for role in self.sites.values())

    @property
    def rolls(self) -> bool:
        """A roll happens and the set authored it, so the set can move it."""
        return any(
            role == ROLLS and not site.startswith("engine:")
            for site, role in self.sites.items()
        )

    @property
    def trains(self) -> bool:
        return TRAINS in self.sites.values()

    @property
    def only_attempted(self) -> bool:
        """A roll happens, but nothing beside it grants xp."""
        return self.checked and not self.trains

    @property
    def only_gated(self) -> bool:
        """Every site compares its level; nothing rolls it.

        A threshold is how the jail escape works: `{"skill": ..., "minimum": N}`.
        That reads a number without testing it, so the pairing deserves a look --
        the skill can be a hard requirement that nothing in that system trains.

        `not self.rolls`, not `not (roles & set(CHECKS))`: `THRESHOLD` is itself a
        member of `CHECKS`, so the set-intersection version was false for exactly
        the case it was written to catch.
        """
        return THRESHOLD in set(self.sites.values()) and not self.rolls

    def site_list(self) -> str:
        by_role: Dict[str, List[str]] = {}
        for site, role in sorted(self.sites.items()):
            by_role.setdefault(role, []).append(site)
        return "; ".join(
            "%s: %s" % (role, ", ".join(names)) for role, names in sorted(by_role.items())
        )


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def _walk_paths(node: Any, prefix: str = ""):
    """Every (dotted path, key, value) anywhere in one parsed file.

    The path is carried because a site key made only of the key name collides:
    `locksmithing.skill` and `combat.retreat.skill` are both a `skill` key, and
    reading them as one site reported two unrelated skills as co-located.
    """
    if isinstance(node, dict):
        for key, value in node.items():
            path = "%s.%s" % (prefix, key) if prefix else str(key)
            yield path, key, value
            yield from _walk_paths(value, path)
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _walk_paths(value, "%s[%d]" % (prefix, index))


# --- where a skill is mentioned -------------------------------------------------
#
# Each reader says where it looks and what it means. They are written out rather
# than described by a pattern, for the reason the reference validator gives: a
# compact notation that is subtly wrong reports success while finding nothing.


def _ruleset_mentions(ruleset: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """(skill, site, role) from everything the ruleset declares."""
    found: List[Tuple[str, str, str]] = []
    skills = ruleset.get("skills")
    if isinstance(skills, dict) and isinstance(skills.get("stat_bonuses"), dict):
        for skill in skills["stat_bonuses"]:
            if str(skill).startswith("_"):
                continue
            found.append((str(skill), "ruleset.skills.stat_bonuses", NAMES))

    # A system that names the one skill it tests. Read by the engine through
    # `world.ruleset_section(<name>).get("skill")`, and every one of these rolls
    # through `practice_check` or grants xp beside the roll.
    locksmithing = ruleset.get("locksmithing")
    skill = locksmithing.get("skill") if isinstance(locksmithing, dict) else None
    if isinstance(skill, str) and skill.strip():
        found.append((skill.strip(), "ruleset.locksmithing.skill", ROLLS))

    combat = ruleset.get("combat")
    retreat = combat.get("retreat") if isinstance(combat, dict) else None
    skill = retreat.get("skill") if isinstance(retreat, dict) else None
    if isinstance(skill, str) and skill.strip():
        found.append((skill.strip(), "ruleset.combat.retreat.skill", ROLLS))

    crime = ruleset.get("crime")
    if isinstance(crime, dict):
        # Every `skill` inside the crime section, wherever it sits: a witness
        # check rolls and trains, while a custody requirement's `skill` +
        # `minimum` only compares a level. The role comes from the block.
        for block_path, block in _blocks(crime):
            for dotted, key, value in _walk_paths(block):
                if key not in ("skill", "skill_name"):
                    continue
                if not isinstance(value, str) or not value.strip():
                    continue
                site = "ruleset.crime.%s.%s" % (block_path, dotted) if block_path else "ruleset.crime.%s" % dotted
                findings_role = THRESHOLD if "minimum" in block else ROLLS
                found.append((value.strip(), site, findings_role))
    return found


def _block_role(block: Dict[str, Any], relative: str) -> str:
    """What kind of use a `skill` inside this block is.

    Three shapes exist in shipped content and they are not the same thing:

    * `{"skill": ..., "minimum": N}` is a **threshold**, not a roll -- the jail
      escape's concealed-tool requirements read the skill level and compare it.
      Nothing is rolled and nothing is granted.
    * a `check` block (dialogue choice, quest negotiation) rolls through
      `practice_check`, so the attempt trains the skill.
    * a title's `condition` only reads the level.

    A block that carries no `difficulty` is not rolled either, whatever it is:
    `world.py` defaults a missing difficulty, but a *condition* is a comparison
    and reading it as a roll would invent a check the engine never makes.
    """
    if "minimum" in block:
        return THRESHOLD
    if relative.endswith("titles.json"):
        return NAMES
    if "difficulty" not in block:
        return NAMES
    return ROLLS


def _content_mentions(content_root: Path) -> List[Tuple[str, str, str, str]]:
    """(skill, site, role, file) from the content files."""
    found: List[Tuple[str, str, str, str]] = []
    for path in sorted(content_root.rglob("*.json")):
        if "editor" in path.parts:
            continue
        try:
            payload = _load_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        relative = path.relative_to(content_root).as_posix()
        for block_path, block in _blocks(payload):
            where = lambda dotted: "%s:%s.%s" % (relative, block_path, dotted) if block_path else "%s:%s" % (relative, dotted)  # noqa: E731
            for dotted, key, value in _walk_paths(block):
                if key == "skill" and isinstance(value, str) and value.strip():
                    found.append((value.strip(), where(dotted), _block_role(block, relative), relative))
                elif key == "skill_name" and isinstance(value, str) and value.strip():
                    # A room exit's requirement. This rolls through
                    # `practice_check` (`world/world.py:402`) and therefore
                    # TRAINS -- the first version of this tool filed it as a
                    # threshold that grants nothing, which was wrong.
                    found.append((value.strip(), where(dotted), ROLLS, relative))
                elif key == "skills" and isinstance(value, dict) and relative.startswith("player/"):
                    # A background's starting levels, keyed by skill name.
                    for skill in value:
                        found.append((str(skill), where("%s.%s" % (dotted, skill)), NAMES, relative))
    return found


def _blocks(payload: Any, prefix: str = ""):
    """Every object that itself names a skill, with its dotted path."""
    if isinstance(payload, dict):
        if "skill" in payload or "skill_name" in payload or "skills" in payload:
            yield prefix, payload
        for key, value in payload.items():
            child = "%s.%s" % (prefix, key) if prefix else str(key)
            yield from _blocks(value, child)
    elif isinstance(payload, list):
        for index, value in enumerate(payload):
            yield from _blocks(value, "%s[%d]" % (prefix, index))


def _system_mentions() -> List[Tuple[str, str, str, str]]:
    """(skill, site, role, system) for skills the *engine* wires to a system.

    `crafting_manager` rolls `"crafting"` in three places and that string is in
    no content file, so a vocabulary built only from content would report the
    crafting skill as unused while it is being trained on every craft. Declared
    here, once, with the capability that has to be on for the string to be
    reached at all -- this is the hardcoded name, made visible.
    """
    return [("crafting", "engine:crafting_manager", ROLLS, "crafting")]


def _capabilities(package_root: Path) -> Tuple[Set[str], Dict[str, Any]]:
    """What the package says it enables, and its systems switches.

    Needed because a skill the *engine* rolls is only a finding for a set that
    runs that engine system: `crafting_manager` always writes `"crafting"`, and
    for a set with crafting switched off that string is simply never reached.
    Reporting it would be the check inventing a finding.
    """
    capabilities: Set[str] = set()
    manifest = package_root / "content_set.manifest.json"
    if manifest.is_file():
        try:
            payload = _load_json(manifest)
            if isinstance(payload, dict) and isinstance(payload.get("capabilities"), list):
                capabilities = {str(cap) for cap in payload["capabilities"]}
        except (OSError, json.JSONDecodeError):
            capabilities = set()
    ruleset_path = package_root / "rules" / "ruleset.json"
    systems: Dict[str, Any] = {}
    if ruleset_path.is_file():
        try:
            payload = _load_json(ruleset_path)
            if isinstance(payload, dict) and isinstance(payload.get("systems"), dict):
                systems = payload["systems"]
        except (OSError, json.JSONDecodeError):
            systems = {}
    return capabilities, systems


def _system_enabled(name: str, capabilities: Set[str], systems: Dict[str, Any]) -> bool:
    """Whether one engine system is on, by the same rules the engine uses."""
    declared = systems.get(name)
    if isinstance(declared, dict) and "enabled" in declared:
        return bool(declared["enabled"])
    return name in capabilities


def collect(content_root: Path, ruleset_path: Optional[Path],
            ruleset: Dict[str, Any], package_root: Optional[Path] = None) -> Dict[str, SkillUse]:
    """Every skill name this set mentions, and everything known about it."""
    uses: Dict[str, SkillUse] = {}

    def note(name: str, site: str, role: str, declared_by: str = "", file: str = "") -> None:
        if not name:
            return
        use = uses.setdefault(name, SkillUse(name=name))
        use.sites[site] = role
        if declared_by:
            use.declared_by.add(declared_by)
        if file:
            use.files.add(file)

    for skill, site, role in _ruleset_mentions(ruleset):
        declared = site if site.startswith("ruleset.skills") else ""
        note(skill, site, role, declared_by=declared)

    for skill, site, role, file in _content_mentions(content_root):
        # Deliberately no `declared_by` here. A background that grants a skill is
        # *using* the vocabulary, not declaring it: `ruleset.skills.stat_bonuses`
        # is the only place a set says "this skill exists", and treating a
        # background as a declaration would silence the very finding that a
        # background can grant a skill the set never heard of.
        note(skill, site, role, file=file)

    capabilities, systems = _capabilities(package_root) if package_root else (set(), {})
    for skill, site, role, system in _system_mentions():
        if not _system_enabled(system, capabilities, systems):
            continue
        note(skill, site, role)

    for skill, rule in (ruleset.get("skills", {}) or {}).get("stat_bonuses", {}).items():
        if str(skill).startswith("_"):
            continue
        if isinstance(rule, dict) and isinstance(rule.get("stat"), str):
            uses.setdefault(str(skill), SkillUse(name=str(skill))).backing_stat = rule["stat"].strip()
    return uses


# --- the warnings ---------------------------------------------------------------
#
# Six of the seven patterns the audit covers. The seventh -- "two skills that
# always roll together" -- needs more than one shipped instance to be worth a
# heuristic, so it is not guessed at here; `_sites_with_many_skills` reports the
# *system* that gates on more than one skill, which is the same question asked
# where the answer is knowable.


def stat_vocabulary(ruleset: Dict[str, Any], contract_stats: Optional[Dict[str, Any]]) -> Set[str]:
    """Every stat name this set has declared, from all three places it can.

    Deliberately the same span the content validator uses when it checks a
    background's starting stats: the engine's own defaults, whatever
    `ruleset.skills.stat_bonuses` names, the resource pools' driving stats, and
    the `stats` contract. A skill's own rule counts -- `{"stat": "grit"}` claims
    grit as a stat -- so this is not a check that a stat has an engine formula.
    Whether the *engine* can do anything with a name is the validator's question
    and it asks it by naming the file.
    """
    from engine.config import PLAYER_DEFAULT_STATS

    known = {
        str(name) for name, value in PLAYER_DEFAULT_STATS.items()
        if not isinstance(value, dict)
    }
    skills = ruleset.get("skills")
    for rule in (skills.get("stat_bonuses", {}) if isinstance(skills, dict) else {}).values():
        if isinstance(rule, dict) and isinstance(rule.get("stat"), str) and rule["stat"].strip():
            known.add(rule["stat"].strip())
    resources = ruleset.get("resources")
    if isinstance(resources, dict):
        for field in ("max_stat", "regeneration_stat"):
            if isinstance(resources.get(field), str) and resources[field].strip():
                known.add(resources[field].strip())
    for field in ("roles", "short"):
        values = (contract_stats or {}).get(field)
        if isinstance(values, dict):
            known.update(str(stat).strip() for stat in values.values() if str(stat).strip())
    order = (contract_stats or {}).get("order")
    if isinstance(order, list):
        known.update(str(stat).strip() for stat in order if str(stat).strip())
    return {name for name in known if name}


def term_item_classes() -> Dict[str, str]:
    """Item classes whose name is a *genre term* rather than a mechanic.

    `ItemFactory` maps a type name to a class only when the class carries
    behaviour a template cannot express -- a container holds items, a key
    unlocks, a weapon equips. A class that exists to hold a default or a sentence
    is a content decision wearing engine clothing: the set cannot retag its
    items, change the sentence, or use the word for something else.

    Listed rather than inferred, because "does this class add behaviour?" is a
    judgement and a guess would flag half the engine. This is the list of names
    the audit treats as suspicious, so the instances can be discussed rather than
    silently accepted.
    """
    return {
        "Gem": "a cut stone",
        "Junk": "an item with no use",
        "Treasure": "a valuable object",
        "Lockpick": "a lockpicking tool",
    }


# The fields where a class name is a *decision* rather than part of an id.
# `advancement.grants[].match.item_type` branches the XP ledger on "Gem"; an item
# id like `item_coral_gem` merely contains the letters, and flagging those would
# bury the finding that matters under the ones that do not.
_CLASS_DISCRIMINATOR_KEYS = ("item_type", "item_class", "type")


def _class_discriminators(ruleset: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(dotted path, class name) for every branch on an item class name."""
    terms = term_item_classes()
    found: List[Tuple[str, str]] = []
    for dotted, key, value in _walk_paths(ruleset):
        if key not in _CLASS_DISCRIMINATOR_KEYS or not isinstance(value, str):
            continue
        if value.strip() in terms:
            found.append((dotted, value.strip()))
    return found


def _referenced_systems(ruleset: Dict[str, Any]) -> Dict[str, str]:
    """Sections of the ruleset that name a skill, and the skill they name."""
    found: Dict[str, str] = {}
    for section in ("locksmithing", "combat", "crime"):
        block = ruleset.get(section)
        if not isinstance(block, dict):
            continue
        names = sorted({
            value.strip()
            for _dotted, key, value in _walk_paths(block)
            if key in ("skill", "skill_name") and isinstance(value, str) and value.strip()
        })
        if names:
            found[section] = ", ".join(names)
    return found


def audit(content_root: Path, ruleset_path: Optional[Path] = None,
          package_root: Optional[Path] = None) -> Tuple[List[Finding], Dict[str, SkillUse]]:
    """Every finding, plus the map, so a caller can print the inventory too."""
    findings: List[Finding] = []
    ruleset: Dict[str, Any] = {}
    if ruleset_path is not None and ruleset_path.is_file():
        try:
            payload = _load_json(ruleset_path)
            if isinstance(payload, dict):
                ruleset = payload
        except (OSError, json.JSONDecodeError) as error:
            findings.append(Finding("warning", str(ruleset_path), "could not be read: %s" % error))

    contract_stats: Optional[Dict[str, Any]] = None
    contracts = content_root / "contracts" / "world_contracts.json"
    if contracts.is_file():
        try:
            payload = _load_json(contracts)
            if isinstance(payload, dict) and isinstance(payload.get("stats"), dict):
                contract_stats = payload["stats"]
        except (OSError, json.JSONDecodeError):
            contract_stats = None

    uses = collect(content_root, ruleset_path, ruleset, package_root)
    known_stats = stat_vocabulary(ruleset, contract_stats)

    for name in sorted(uses):
        use = uses[name]
        engine_sites = sorted(site for site in use.sites if site.startswith("engine:"))
        from_background = any(file.startswith("player/") for file in use.files)

        # 1/2/3: is the name declared at all.
        if not use.declared:
            if engine_sites:
                findings.append(Finding(
                    "warning", ", ".join(engine_sites),
                    "this set runs the %s system, which rolls skill '%s' -- a name written into "
                    "engine code and declared by no content, so the set cannot rename it and "
                    "nothing checks it" % (
                        engine_sites[0].split(":", 1)[1].replace("_manager", ""), name,
                    ),
                ))
            elif from_background:
                findings.append(Finding(
                    "warning", "player/backgrounds.json",
                    "a background grants skill '%s', which ruleset.skills.stat_bonuses does "
                    "not declare -- it is recorded and no stat backs it" % name,
                ))
            else:
                findings.append(Finding(
                    "warning", use.site_list() or "content",
                    "skill '%s' is named by content and declared nowhere: it rolls at level 0 "
                    "with no stat bonus, and nothing reports a typo of a real skill" % name,
                ))

        # 4: what its life amounts to. Only meaningful once the name exists --
        # saying "nothing rolls it" about a name nothing declares is the same
        # finding twice.
        if use.declared and not use.rolls:
            if engine_sites:
                findings.append(Finding(
                    "warning", ", ".join(sorted(use.declared_by)),
                    "skill '%s' is declared here, but the only roll against it is engine-declared "
                    "(%s) -- the set cannot retune the check, and %s"
                    % (name, ", ".join(engine_sites),
                       "nothing else consults it" if not use.checked else "nothing the set authored does"),
                ))
            else:
                findings.append(Finding(
                    "warning", ", ".join(sorted(use.declared_by)),
                    "skill '%s' is declared and nothing rolls it -- it holds a level and xp that "
                    "no check reads, which is what an attribute already does (%s)"
                    % (name, use.site_list()),
                ))
        if use.declared and use.only_attempted:
            findings.append(Finding(
                "warning", use.site_list(),
                "skill '%s' is rolled but nothing that rolls it grants xp: it can be tested "
                "forever and never improve" % name,
            ))
        if use.declared and use.only_gated:
            findings.append(Finding(
                "warning", use.site_list(),
                "skill '%s' is only ever *gated* on, never rolled: a threshold comparison "
                "reads its level, so the number moves only if something else raises it "
                "(pairing worth a look)" % name,
            ))

        # 5: the stat behind it has to exist, or the bonus is always zero.
        if use.backing_stat and use.backing_stat not in known_stats:
            findings.append(Finding(
                "warning", "ruleset.skills.stat_bonuses.%s" % name,
                "backs skill '%s' with stat '%s', which no stat vocabulary declares (declared: %s)"
                % (name, use.backing_stat, ", ".join(sorted(known_stats))),
            ))

        # 6: a skill that is also a stat.
        if name in known_stats:
            findings.append(Finding(
                "warning", "ruleset.skills.stat_bonuses.%s" % name,
                "skill '%s' is also a stat name -- a check against it reads a value that is "
                "already a stat, and the two will drift" % name,
            ))

    # 7: one action gated by more than one skill. Reported per *action*, not per
    # ruleset section: it is the co-requirement that raises the design question,
    # and a section holding two separate checks is not the same shape.
    for site, skills, detail in _sites_with_many_skills(ruleset):
        findings.append(Finding(
            "warning", site,
            "this action requires more than one skill (%s): %s. Together they are a single "
            "gate, so one of them being the weaker link makes the stronger one pointless -- "
            "worth deciding whether these are one practice, two, or a deliberate pair."
            % (", ".join("'%s'" % skill for skill in sorted(skills)), detail),
        ))

    # 8: a system that declares a skill and never reaches it. `combat.retreat`
    # with no `skill` key is the shape: the section is authored, the block exists,
    # and the one field the engine reads is absent, so retreating is free.
    for section in ("combat", "crime", "locksmithing"):
        block = ruleset.get(section)
        if block is None:
            continue
        if section == "combat" and isinstance(block, dict) and "retreat" not in block:
            continue
        if isinstance(block, dict) and not _referenced_systems(ruleset).get(section):
            findings.append(Finding(
                "warning", "ruleset.%s" % section,
                "this section is declared and names no skill, so whatever it gates is ungated "
                "-- check whether a `skill` key was meant to be here",
            ))

    # 9: the engine branching on a genre term. Five places in the shipped ruleset
    # do it, and nothing cross-checks them against the families the reference
    # rules speak -- this is the "no single id table" gap made visible.
    terms = term_item_classes()
    for dotted, class_name in _class_discriminators(ruleset):
        findings.append(Finding(
            "warning", "ruleset.%s" % dotted,
            "branches on item class '%s' (%s) -- that is the Python class name, not the family "
            "or capability the reference rules speak, so an item of another family cannot "
            "reach this rule" % (class_name, terms[class_name]),
        ))
    # Weaker signal, reported separately: a skill whose name uses a class name as
    # a whole word. Substring matches are not reported -- `lockpicking` contains
    # `Lockpick` and means something different, so flagging it would be noise.
    for name, use in sorted(uses.items()):
        words = {word.strip("_-").lower() for word in re.split(r"[^A-Za-z0-9]+", name)}
        for term in terms:
            if term.lower() in words:
                findings.append(Finding(
                    "warning", use.site_list() or name,
                    "skill '%s' is built on the item class name '%s' (%s); the two are separate "
                    "vocabularies, and a set that renames the class leaves the skill behind"
                    % (name, term, terms[term]),
                ))
                break
    return findings, uses


def _gate_detail(ruleset: Dict[str, Any], site: str) -> str:
    """Where each co-required skill sits, so the finding is actionable."""
    section = site.split(".", 1)[-1]
    block = ruleset.get(section)
    places: List[str] = []
    for dotted, key, value in _walk_paths(block if isinstance(block, dict) else {}):
        if key in ("skill", "skill_name") and isinstance(value, str) and value.strip():
            places.append("%s=%s" % (dotted, value.strip()))
    return ", ".join(places)


def _skill_blocks(block: Any, prefix: str = ""):
    """Objects that name a skill, with their dotted path inside `block`.

    The unit is the **action**, not the containing section: a `minimum` entry in
    a list of them is one requirement of one gate, and two entries in the same
    list are co-requirements of the same action.
    """
    if isinstance(block, dict):
        if "skill" in block or "skill_name" in block:
            yield prefix, block
        for key, value in block.items():
            child = "%s.%s" % (prefix, key) if prefix else str(key)
            yield from _skill_blocks(value, child)
    elif isinstance(block, list):
        for index, value in enumerate(block):
            yield from _skill_blocks(value, "%s[%d]" % (prefix, index))


def _sites_with_many_skills(ruleset: Dict[str, Any]) -> List[Tuple[str, Set[str], str]]:
    """Every action that requires more than one skill at once, with its detail.

    Two shapes reach this, and both are genuinely one gate rather than two
    practices that happen to live in the same file:

    * a list of requirements that is ``all(...)``-ed -- the jail escape needs
      every entry's minimum, so the skills are co-required;
    * one block that names two skills directly.

    The detail is built from the branch that found it rather than re-derived from
    the section, because the two are not the same path: a list of requirements
    sits below the block that names them, and looking only at the block found
    nothing to print.
    """
    found: List[Tuple[str, Set[str], str]] = []
    for section in ("combat", "crime", "locksmithing"):
        block = ruleset.get(section)
        if not isinstance(block, dict):
            continue
        # Requirements that are evaluated together, by list.
        for dotted, _key, value in _walk_paths(block):
            if not isinstance(value, list) or not value:
                continue
            entries = [
                (index, str(entry.get("skill", "")).strip(), entry.get("minimum"))
                for index, entry in enumerate(value)
                if isinstance(entry, dict) and str(entry.get("skill", "")).strip()
            ]
            names = {skill for _index, skill, _minimum in entries}
            if len(names) > 1:
                detail = ", ".join(
                    "needs %s >= %s" % (skill, minimum) for _index, skill, minimum in entries
                )
                found.append(("ruleset.%s.%s" % (section, dotted), names, detail))
        # One block naming two.
        for dotted, entry in _skill_blocks(block):
            names = {
                str(value).strip()
                for _d, key, value in _walk_paths(entry)
                if key in ("skill", "skill_name") and isinstance(value, str) and value.strip()
            }
            if len(names) > 1:
                found.append(("ruleset.%s.%s" % (section, dotted), names,
                              "names %s together" % ", ".join(sorted(names))))
    return found


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("root", nargs="?", default="content_sets/fantasy_frontier/data",
                        help="Path to content-set data root.")
    parser.add_argument("--ruleset", default=None, help="Path to the ruleset (defaults to ../rules/ruleset.json).")
    parser.add_argument("--quiet", action="store_true", help="Only print findings, not the inventory.")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.is_dir():
        print("[ERROR] Data root not found: %s" % root)
        return 2
    ruleset_path = Path(args.ruleset) if args.ruleset else root.parent / "rules" / "ruleset.json"

    findings, uses = audit(root, ruleset_path, package_root=root.parent)

    if not args.quiet:
        print("== Skill inventory: %s" % root)
        for name in sorted(uses):
            use = uses[name]
            print("  %-16s declared=%-5s stat=%-14s %s" % (
                name, use.declared, use.backing_stat or "-", use.site_list() or "-"))
        print()

    for finding in findings:
        print(finding)
    warnings = len(findings)
    print("Skill findings: %d (all warnings; errors: 0)" % warnings)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
