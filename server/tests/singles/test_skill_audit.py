# tests/singles/test_skill_audit.py
"""Skills are named in four places and declared in none of them.

A skill is a named number that `SkillSystem` rolls against a difficulty, and
that mechanism is already general -- nine systems call it and it knows no content.
What was missing is a declaration, so nothing could check a skill name against
anything. The audit reads what exists and says what the names are used for.

Every finding is a warning, deliberately: a skill nothing rolls is not an error,
it is a design question, and the seven warnings exist so the instances can be
looked at before the pattern is decided.
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import skill_audit  # noqa: E402

CONTENT_SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage")


class TestTheShippedSets(unittest.TestCase):
    def _audit(self, name: str):
        root = REPO_ROOT / "content_sets" / name / "data"
        return skill_audit.audit(root, root.parent / "rules" / "ruleset.json", package_root=root.parent)

    def test_every_set_audits_without_errors(self):
        for name in CONTENT_SETS:
            findings, _uses = self._audit(name)
            self.assertTrue(
                all(finding.severity == "warning" for finding in findings),
                "%s produced a non-warning: %s" % (name, [str(f) for f in findings]),
            )

    def test_the_known_first_specimen_is_reported(self):
        """`diplomacy` is rolled by a quest negotiation and declared nowhere."""
        findings, uses = self._audit("fantasy_frontier")
        messages = [finding.message for finding in findings]
        self.assertFalse(uses["diplomacy"].declared)
        self.assertTrue(any("'diplomacy'" in message and "declared nowhere" in message for message in messages),
                        messages)

    def test_the_engine_supplied_name_is_reported_for_a_set_that_runs_it(self):
        """Orbital enables crafting, so the hardcoded `"crafting"` is reachable."""
        findings, _uses = self._audit("orbital_salvage")
        messages = " ".join(finding.message for finding in findings)
        self.assertIn("crafting", messages)
        self.assertIn("engine code", messages)

    def test_the_engine_supplied_name_is_not_reported_for_a_set_that_does_not(self):
        """Modern capsule has crafting off, so that string is never reached."""
        findings, _uses = self._audit("modern_capsule")
        self.assertEqual([], [str(finding) for finding in findings])

    def test_two_skills_gating_one_action_are_reported_with_their_places(self):
        findings, uses = self._audit("fantasy_frontier")
        gate = [f for f in findings if "more than one skill" in f.message]
        self.assertEqual(1, len(gate), [str(f) for f in findings])
        self.assertIn("custody.concealed_tool_requirements", gate[0].path)
        self.assertIn("needs stealth >= 20", gate[0].message)
        self.assertIn("needs lockpicking >= 20", gate[0].message)
        # And the gate is only ever compared, not rolled: it is a hard
        # requirement that nothing in that system trains.
        threshold_sites = [
            site for site, role in uses["lockpicking"].sites.items() if role == skill_audit.THRESHOLD
        ]
        self.assertTrue(threshold_sites, dict(uses["lockpicking"].sites))

    def test_every_declared_fantasy_skill_is_accounted_for(self):
        _findings, uses = self._audit("fantasy_frontier")
        for skill in ("crafting", "lockpicking", "mercantile", "stealth"):
            self.assertTrue(uses[skill].declared, skill)
            self.assertTrue(uses[skill].checked, "%s has no check site" % skill)
            self.assertTrue(uses[skill].trains, "%s has no trainer" % skill)


class TestItDoesNotInventFindings(unittest.TestCase):
    """A check that reports working content is a check people learn to ignore."""

    def _package(self, *, ruleset: dict, files: dict) -> Path:
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        package = root / "content_set"
        (package / "rules").mkdir(parents=True)
        (package / "data" / "contracts").mkdir(parents=True)
        (package / "content_set.manifest.json").write_text(json.dumps({
            "id": "skill_probe", "title": "Skill Probe", "version": "0.1.0",
            "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
            "paths": {"content_root": "data", "ruleset": "rules/ruleset.json",
                      "presentation": "presentation/default.json"},
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": [],
        }), encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
        for relative, payload in files.items():
            target = package / "data" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(payload), encoding="utf-8")
        return package

    def _findings(self, package: Path):
        root = package / "data"
        findings, uses = skill_audit.audit(root, package / "rules" / "ruleset.json", package_root=package)
        return findings, uses

    def test_a_declared_skill_that_is_rolled_and_trained_is_quiet(self):
        package = self._package(
            ruleset={
                "skills": {"stat_bonuses": {"lockpicking": {"stat": "dexterity"}}},
                "locksmithing": {"skill": "lockpicking"},
            },
            files={"items/keys.json": {}},
        )
        findings, uses = self._findings(package)
        self.assertEqual([], [f.message for f in findings])
        self.assertTrue(uses["lockpicking"].trains)

    def test_a_title_condition_is_not_a_roll(self):
        """`skill_at_least` reads a level; reading it as a roll invents a check."""
        package = self._package(
            ruleset={"skills": {"stat_bonuses": {"crafting": {"stat": "intelligence"}}}},
            files={"titles.json": {"wright": {"name": "Wright",
                                              "condition": {"kind": "skill_at_least", "skill": "crafting", "value": 3}}}},
        )
        findings, uses = self._findings(package)
        self.assertEqual("named", uses["crafting"].sites["titles.json:wright.condition.skill"])
        self.assertTrue(any("nothing rolls it" in finding.message for finding in findings), findings)

    def test_a_threshold_is_not_a_roll(self):
        """`{"skill": ..., "minimum": N}` compares a level; it rolls nothing."""
        package = self._package(
            ruleset={
                "skills": {"stat_bonuses": {"stealth": {"stat": "agility"}}},
                "crime": {"custody": {"concealed_tool_requirements": [
                    {"skill": "stealth", "minimum": 20},
                ]}},
            },
            files={"items/keys.json": {}},
        )
        _findings, uses = self._findings(package)
        site = "ruleset.crime.custody.concealed_tool_requirements[0].skill"
        self.assertEqual("threshold", uses["stealth"].sites[site])

    def test_a_room_exit_rolls_and_trains(self):
        """The regression Track E caught.

        A room exit's requirement calls `SkillSystem.practice_check`
        (`world/world.py:402`), which awards xp. The first version of this tool
        filed it as a threshold that grants nothing, so any set shipping a skill
        exit would have been told a working skill was untrainable.
        """
        package = self._package(
            ruleset={"skills": {"stat_bonuses": {"climbing": {"stat": "strength"}}}},
            files={"regions/cliff.json": {
                "region_id": "cliff",
                "rooms": {"ledge": {"name": "Ledge", "exits": {},
                                    "properties": {"exit_requirements": {
                                        "up": {"type": "skill", "skill_name": "climbing",
                                               "difficulty": 12}}}}},
            }},
        )
        _findings, uses = self._findings(package)
        site = "regions/cliff.json:rooms.ledge.properties.exit_requirements.up.skill_name"
        self.assertEqual("rolls", uses["climbing"].sites[site])
        self.assertTrue(uses["climbing"].trains, "a room exit grants xp")
        self.assertFalse(
            uses["climbing"].only_attempted,
            "a trained skill must not be reported as untrainable",
        )

    def test_two_sections_naming_one_skill_are_not_one_site(self):
        """`locksmithing.skill` and `combat.retreat.skill` are different practices."""
        package = self._package(
            ruleset={
                "skills": {"stat_bonuses": {
                    "lockpicking": {"stat": "dexterity"},
                    "stealth": {"stat": "agility"},
                }},
                "locksmithing": {"skill": "lockpicking"},
                "combat": {"retreat": {"skill": "stealth"}},
            },
            files={"items/keys.json": {}},
        )
        findings, _uses = self._findings(package)
        self.assertEqual([], [f.message for f in findings], "two unrelated sections were read as co-located")

    def test_an_authoring_note_is_not_a_skill(self):
        package = self._package(
            ruleset={"skills": {"stat_bonuses": {
                "_comment": "why these", "lockpicking": {"stat": "dexterity"},
            }}},
            files={},
        )
        _findings, uses = self._findings(package)
        self.assertNotIn("_comment", uses)


class TestTheOtherFiveWarnings(unittest.TestCase):
    def _uses_from(self, ruleset: dict, files: dict) -> tuple:
        helper = TestItDoesNotInventFindings()
        package = helper._package(ruleset=ruleset, files=files)
        return helper._findings(package)

    def test_a_skill_backed_by_a_stat_no_contract_declares(self):
        """A skill's own rule *claims* its stat, so this is not a check that the
        stat has an engine formula -- the content validator asks that question by
        naming the file, and asking it twice would be two lists that drift."""
        findings, _uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {"endurance": {"stat": "grit"}}}},
            files={},
        )
        self.assertFalse(any("no stat vocabulary" in finding.message for finding in findings), findings)
        self.assertTrue(any("nothing rolls it" in finding.message for finding in findings), findings)

    def test_the_vocabulary_spans_all_three_places_a_stat_can_be_declared(self):
        contract = {"schema_version": 1, "stats": {"roles": {"health": "vigour"}}}
        ruleset = {
            "skills": {"stat_bonuses": {"endurance": {"stat": "grit"}}},
            "resources": {"max_stat": "focus"},
        }
        known = skill_audit.stat_vocabulary(ruleset, contract["stats"])
        for name in ("strength", "grit", "focus", "vigour"):
            self.assertIn(name, known)

    def test_a_stat_declared_by_the_contract_is_accepted(self):
        findings, _uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {"endurance": {"stat": "grit"}}}},
            files={"contracts/world_contracts.json": {
                "schema_version": 1, "stats": {"roles": {"health": "grit"}},
            }},
        )
        self.assertEqual([], [f for f in findings if "'grit'" in f.message], findings)

    def test_a_skill_that_is_also_a_stat_name(self):
        findings, _uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {"agility": {"stat": "agility"}}}},
            files={},
        )
        self.assertTrue(any("also a stat name" in finding.message for finding in findings), findings)

    def test_every_roll_the_engine_makes_also_trains(self):
        """No shipped check rolls a skill without granting xp, and none should.

        This test used to assert the opposite for a room exit, on the assumption
        that a requirement only reads the level. It calls `practice_check`
        (`world/world.py:402`). So `only_attempted` is now a genuine finding
        rather than an expected one, and the case that exercises it is a
        threshold -- which rolls nothing at all.
        """
        findings, uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {"climbing": {"stat": "strength"}}}},
            files={"regions/cliff.json": {
                "region_id": "cliff",
                "rooms": {"ledge": {"name": "Ledge", "exits": {},
                                    "properties": {"exit_requirements": {
                                        "up": {"type": "skill", "skill_name": "climbing", "difficulty": 12}}}}},
            }},
        )
        self.assertFalse(any("never improve" in finding.message for finding in findings), findings)
        self.assertTrue(uses["climbing"].trains)

    def test_a_declared_skill_no_content_rolls_is_a_warning_not_an_error(self):
        """The case worth naming: it behaves like an attribute, not a practice.

        A skill with a level, a stat and no check is not broken -- it is a
        passive number occupying the skill slot. That is a design question, so it
        is reported and the build stays green.
        """
        findings, uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {"awareness": {"stat": "wisdom"}}}},
            files={},
        )
        self.assertTrue(any("nothing rolls it" in finding.message for finding in findings), findings)
        self.assertTrue(all(finding.severity == "warning" for finding in findings), findings)
        self.assertTrue(uses["awareness"].declared)

    def test_a_background_granting_a_skill_the_vocabulary_never_hears_of(self):
        findings, _uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {}}},
            files={"player/backgrounds.json": {
                "probe": {"name": "Probe", "stats": {"strength": 10}, "skills": {"fishing": 1}},
            }},
        )
        self.assertTrue(any("a background grants skill 'fishing'" in finding.message for finding in findings),
                        findings)

    def test_a_typo_of_a_real_skill_is_reported_as_undeclared(self):
        """The whole point: `lockpikcing` currently rolls at level 0, silently."""
        findings, uses = self._uses_from(
            ruleset={"skills": {"stat_bonuses": {"lockpicking": {"stat": "dexterity"}}}},
            files={"regions/vault.json": {
                "region_id": "vault",
                "rooms": {"door": {"name": "Door", "exits": {},
                                   "properties": {"exit_requirements": {
                                       "in": {"type": "skill", "skill_name": "lockpikcing", "difficulty": 12}}}}},
            }},
        )
        self.assertFalse(uses["lockpikcing"].declared)
        self.assertTrue(any("'lockpikcing'" in finding.message and "declared nowhere" in finding.message for finding in findings),
                        findings)


class TestThePairingsWorthTalkingAbout(unittest.TestCase):
    """The findings that are judgement calls, reported so they can be discussed.

    Each of these is a real instance in shipped content. None is a bug; all are
    the kind of thing that is invisible until somebody looks.
    """

    def _findings(self, ruleset: dict, files: dict | None = None):
        helper = TestItDoesNotInventFindings()
        package = helper._package(ruleset=ruleset, files=files or {})
        return helper._findings(package)

    def test_one_action_requiring_two_skills_reports_both_thresholds(self):
        findings, _uses = self._findings({
            "skills": {"stat_bonuses": {
                "stealth": {"stat": "agility"}, "lockpicking": {"stat": "dexterity"},
            }},
            "locksmithing": {"skill": "lockpicking"},
            "crime": {"custody": {"concealed_tool_requirements": [
                {"skill": "stealth", "minimum": 20},
                {"skill": "lockpicking", "minimum": 20},
            ]}},
        })
        gate = [f for f in findings if "more than one skill" in f.message]
        self.assertEqual(1, len(gate), findings)
        self.assertIn("needs stealth >= 20", gate[0].message)
        self.assertIn("needs lockpicking >= 20", gate[0].message)

    def test_two_separate_checks_in_one_section_are_not_one_gate(self):
        findings, _uses = self._findings({
            "skills": {"stat_bonuses": {
                "lockpicking": {"stat": "dexterity"}, "stealth": {"stat": "agility"},
            }},
            "locksmithing": {"skill": "lockpicking"},
            "combat": {"retreat": {"skill": "stealth"}},
        })
        self.assertEqual([], [f for f in findings if "more than one skill" in f.message], findings)

    def test_a_threshold_only_skill_is_reported_as_gated_never_rolled(self):
        """A name that moves only if something else raises it."""
        findings, uses = self._findings({
            "skills": {"stat_bonuses": {"security": {"stat": "dexterity"}}},
            "crime": {"custody": {"concealed_tool_requirements": [
                {"skill": "security", "minimum": 20},
            ]}},
        })
        self.assertTrue(uses["security"].only_gated)
        self.assertTrue(any("only ever *gated* on" in f.message for f in findings), findings)
        # And the gate itself is reported as ungated-in-the-other-direction: the
        # skill is a hard requirement that nothing trains.
        self.assertTrue(any("nothing rolls it" in f.message for f in findings), findings)

    def test_a_skill_the_set_only_rolls_through_the_engine_says_so(self):
        """Orbital's case: a real roll the set cannot move, so the finding points
        at the hardcoded name rather than pretending nothing checks it."""
        helper = TestItDoesNotInventFindings()
        package = helper._package(
            ruleset={"skills": {"stat_bonuses": {"crafting": {"stat": "intelligence"}}}},
            files={},
        )
        (package / "content_set.manifest.json").write_text(json.dumps({
            "id": "skill_probe", "title": "Skill Probe", "version": "0.1.0",
            "manifest_schema_version": "1", "engine_api_min": "1.0", "engine_api_max": "1.0",
            "paths": {"content_root": "data", "ruleset": "rules/ruleset.json",
                      "presentation": "presentation/default.json"},
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["crafting"],
        }), encoding="utf-8")
        root = package / "data"
        findings, uses = skill_audit.audit(root, package / "rules" / "ruleset.json", package_root=package)
        messages = [finding.message for finding in findings]
        self.assertIn("engine:crafting_manager", " ".join(uses["crafting"].sites))
        self.assertTrue(
            any("the only roll against it is engine-declared" in message for message in messages),
            messages,
        )

    def test_branching_on_an_item_class_name_is_reported(self):
        findings, _uses = self._findings({
            "advancement": {"grants": [
                {"id": "item_gem", "match": {"kind": "item", "item_type": "Gem"}, "xp": 15},
            ]},
        })
        self.assertTrue(
            any("branches on item class 'Gem'" in f.message for f in findings), findings
        )

    def test_an_item_id_that_merely_contains_a_class_name_is_not_reported(self):
        """`item_coral_gem` is an id, not a branch; flagging it buries the real ones."""
        findings, _uses = self._findings({
            "loot": {"ambient_pools": [{"entries": [
                {"item_id": "item_coral_gem", "weight": 1},
                {"item_id": "item_lockpick_shiv", "weight": 1},
            ]}]},
        })
        self.assertEqual([], [f for f in findings if "item class" in f.message], findings)

    def test_a_skill_that_contains_a_class_name_as_a_substring_is_not_reported(self):
        """`lockpicking` contains `Lockpick` and means something else."""
        findings, _uses = self._findings({
            "skills": {"stat_bonuses": {"lockpicking": {"stat": "dexterity"}}},
            "locksmithing": {"skill": "lockpicking"},
        })
        self.assertEqual([], [f for f in findings if "item class name" in f.message], findings)

    def test_a_documents_section_with_no_skill_key_is_reported(self):
        """The shape `combat.retreat` had: authored, reached, ungated."""
        findings, _uses = self._findings({
            "skills": {"stat_bonuses": {"stealth": {"stat": "agility"}}},
            "combat": {"retreat": {"base_difficulty": 10}},
        })
        self.assertTrue(any("names no skill" in f.message for f in findings), findings)


if __name__ == "__main__":
    unittest.main()
