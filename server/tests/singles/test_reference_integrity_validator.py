"""Coverage for toolkit/reference_integrity_validator.py.

Note: three branches are left untested as unreachable:
- validate_catalogs()'s `if not isinstance(rooms, dict): continue` inside
  the region-references loop -- that loop only ever iterates
  `region_payloads`, which is populated earlier gated on
  `isinstance(rooms, dict)` already being true for that exact payload, so
  re-fetching `payload.get("rooms", {})` here is guaranteed to still be a
  dict.
- main()'s `else: print(f"[WARN] ...")` arm -- every RefIssue that
  validate_catalogs() can produce is constructed with severity="error";
  the module defines no "warn"-severity issue anywhere, so the else
  branch can never fire.
- the module's `if __name__ == "__main__": main()` guard, which only runs
  when the file is invoked directly as a script (consistent with this
  codebase's established precedent for such guards)."""

import io
import json
import shutil
import sys
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import reference_integrity_validator as riv


class TestReferenceIntegrityValidator(unittest.TestCase):
    def test_live_data_has_no_reference_errors(self) -> None:
        catalogs = riv.load_catalogs(REPO_ROOT / "server" / "data")
        issues = riv.validate_catalogs(catalogs)
        errors = [i for i in issues if i.severity == "error"]
        self.assertEqual([], errors)


def _issue_paths(issues: list) -> set:
    return {i.path for i in issues}


class TestCollectTemplates(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"ref_integrity_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def test_non_dict_template_file_is_skipped(self) -> None:
        root = self._case_root()
        items_dir = root / "items"
        items_dir.mkdir()
        (items_dir / "list.json").write_text(json.dumps(["not", "a", "dict"]), encoding="utf-8")
        self.assertEqual(set(), riv._collect_templates(items_dir))

    def test_blank_template_key_is_skipped(self) -> None:
        root = self._case_root()
        items_dir = root / "items"
        items_dir.mkdir()
        (items_dir / "mixed.json").write_text(
            json.dumps({"   ": {"name": "blank key"}, "item_real": {"name": "real"}}), encoding="utf-8",
        )
        self.assertEqual({"item_real"}, riv._collect_templates(items_dir))


class TestValidateCatalogsRegionReferences(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"ref_integrity_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _base_catalogs(self, root: Path, **overrides) -> dict:
        (root / "campaigns").mkdir(parents=True, exist_ok=True)
        base = {
            "root": root,
            "item_ids": set(),
            "npc_template_ids": set(),
            "quest_ids": set(),
            "quests_payload": {},
            "campaign_files": root / "campaigns",
            "region_files": [],
        }
        base.update(overrides)
        return base

    def _write_region(self, root: Path, name: str, payload: dict) -> Path:
        regions = root / "regions"
        regions.mkdir(parents=True, exist_ok=True)
        path = regions / f"{name}.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_malformed_region_file_reports_parse_error(self) -> None:
        root = self._case_root()
        regions = root / "regions"
        regions.mkdir(parents=True)
        bad = regions / "broken.json"
        bad.write_text("{not valid", encoding="utf-8")
        catalogs = self._base_catalogs(root, region_files=[bad])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual(1, len(issues))
        self.assertEqual("error", issues[0].severity)

    def test_unknown_exit_target_is_reported(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town",
            "rooms": {"square": {"exits": {"north": "town:nowhere"}}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertIn("regions/town:square.exits.north", _issue_paths(issues))

    def test_bare_room_exit_resolves_within_same_region(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town",
            "rooms": {"square": {"exits": {"north": "gate"}}, "gate": {}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)

    def test_unknown_room_item_id_is_reported(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town",
            "rooms": {"square": {"items": [{"item_id": "item_ghost"}, "not-a-dict"]}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertIn("regions/town:square.items[0]", _issue_paths(issues))

    def test_known_room_item_id_is_not_reported(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town",
            "rooms": {"square": {"items": [{"item_id": "item_sword"}]}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf], item_ids={"item_sword"})
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)

    def test_unknown_initial_npc_template_id_is_reported(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town",
            "rooms": {"square": {"initial_npcs": [{"template_id": "npc_ghost"}, "not-a-dict"]}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertIn("regions/town:square.initial_npcs[0]", _issue_paths(issues))

    def test_region_without_region_id_or_non_dict_rooms_is_ignored(self) -> None:
        root = self._case_root()
        rf1 = self._write_region(root, "noid", {"rooms": {"a": {}}})
        rf2 = self._write_region(root, "badrooms", {"region_id": "b", "rooms": "not-a-dict"})
        rf3 = self._write_region(root, "notdict", ["not", "a", "dict"])
        catalogs = self._base_catalogs(root, region_files=[rf1, rf2, rf3])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)

    def test_non_dict_room_entry_is_skipped(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {"region_id": "town", "rooms": {"square": "not-a-dict"}})
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)

    def test_non_dict_exits_is_skipped(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town", "rooms": {"square": {"exits": "not-a-dict"}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)

    def test_non_list_items_is_skipped(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town", "rooms": {"square": {"items": "not-a-list"}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)

    def test_non_list_initial_npcs_is_skipped(self) -> None:
        root = self._case_root()
        rf = self._write_region(root, "town", {
            "region_id": "town", "rooms": {"square": {"initial_npcs": "not-a-list"}},
        })
        catalogs = self._base_catalogs(root, region_files=[rf])
        issues = riv.validate_catalogs(catalogs)
        self.assertEqual([], issues)


class TestValidateCatalogsQuestReferences(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"ref_integrity_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _base_catalogs(self, root: Path, quests_payload: dict, **overrides) -> dict:
        (root / "campaigns").mkdir(parents=True, exist_ok=True)
        base = {
            "root": root,
            "item_ids": set(),
            "npc_template_ids": set(),
            "quest_ids": set(),
            "quests_payload": quests_payload,
            "campaign_files": root / "campaigns",
            "region_files": [],
        }
        base.update(overrides)
        return base

    def test_unknown_reward_item_id_is_reported(self) -> None:
        root = self._case_root()
        quests = {"q1": {"rewards": {"items": [{"item_id": "item_ghost"}, "not-a-dict"]}}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertIn("quests/q1.rewards.items[0]", _issue_paths(issues))

    def test_non_dict_quest_and_non_dict_rewards_are_ignored(self) -> None:
        root = self._case_root()
        quests = {"q1": "not-a-dict", "q2": {"rewards": "not-a-dict"}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertEqual([], issues)

    def test_unknown_turn_in_id_is_reported(self) -> None:
        root = self._case_root()
        quests = {"q1": {"stages": ["not-a-dict", {"turn_in_id": "npc_ghost"}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertIn("quests/q1.stages[1].turn_in_id", _issue_paths(issues))

    def test_unknown_spawn_on_entry_template_id_is_reported(self) -> None:
        root = self._case_root()
        quests = {"q1": {"stages": [{"spawn_on_entry": {"template_id": "npc_ghost"}}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertIn("quests/q1.stages[0].spawn_on_entry.template_id", _issue_paths(issues))

    def test_spawn_on_entry_unknown_region_and_room_are_reported(self) -> None:
        root = self._case_root()
        quests_unknown_region = {"q1": {"stages": [{"spawn_on_entry": {"region_id": "nowhere"}}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests_unknown_region))
        self.assertIn("quests/q1.stages[0].spawn_on_entry.region_id", _issue_paths(issues))

        rf = root / "regions" / "town.json"
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text(json.dumps({"region_id": "town", "rooms": {"square": {}}}), encoding="utf-8")
        quests_unknown_room = {"q1": {"stages": [{"spawn_on_entry": {"region_id": "town", "room_id": "nowhere"}}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests_unknown_room, region_files=[rf]))
        self.assertIn("quests/q1.stages[0].spawn_on_entry.room_id", _issue_paths(issues))

    def test_objective_unknown_item_and_npc_fields_are_reported(self) -> None:
        root = self._case_root()
        quests = {
            "q1": {
                "stages": [{
                    "objective": {
                        "item_id": "item_ghost",
                        "item_template_id": "item_ghost2",
                        "target_template_id": "npc_ghost",
                        "target_npc_id": "npc_ghost2",
                        "recipient_id": "npc_ghost3",
                    }
                }]
            }
        }
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        paths = _issue_paths(issues)
        self.assertIn("quests/q1.stages[0].objective.item_id", paths)
        self.assertIn("quests/q1.stages[0].objective.item_template_id", paths)
        self.assertIn("quests/q1.stages[0].objective.target_template_id", paths)
        self.assertIn("quests/q1.stages[0].objective.target_npc_id", paths)
        self.assertIn("quests/q1.stages[0].objective.recipient_id", paths)

    def test_objective_unknown_target_region_and_room_are_reported(self) -> None:
        root = self._case_root()
        quests_unknown_region = {"q1": {"stages": [{"objective": {"target_region": "nowhere"}}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests_unknown_region))
        self.assertIn("quests/q1.stages[0].objective.target_region", _issue_paths(issues))

        rf = root / "regions" / "town.json"
        rf.parent.mkdir(parents=True, exist_ok=True)
        rf.write_text(json.dumps({"region_id": "town", "rooms": {"square": {}}}), encoding="utf-8")
        quests_unknown_room = {"q1": {"stages": [{"objective": {"target_region": "town", "target_room_id": "nowhere"}}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests_unknown_room, region_files=[rf]))
        self.assertIn("quests/q1.stages[0].objective.target_room_id", _issue_paths(issues))

    def test_non_list_reward_items_is_ignored(self) -> None:
        root = self._case_root()
        quests = {"q1": {"rewards": {"items": "not-a-list"}}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertEqual([], issues)

    def test_non_dict_spawn_on_entry_is_ignored(self) -> None:
        root = self._case_root()
        quests = {"q1": {"stages": [{"spawn_on_entry": "not-a-dict"}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertEqual([], issues)

    def test_non_dict_objective_is_ignored(self) -> None:
        root = self._case_root()
        quests = {"q1": {"stages": [{"objective": "not-a-dict"}]}}
        issues = riv.validate_catalogs(self._base_catalogs(root, quests))
        self.assertEqual([], issues)

    def test_non_dict_quests_payload_is_ignored(self) -> None:
        root = self._case_root()
        issues = riv.validate_catalogs(self._base_catalogs(root, quests_payload=["not", "a", "dict"]))
        self.assertEqual([], issues)


class TestValidateCatalogsCampaignReferences(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"ref_integrity_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _base_catalogs(self, root: Path, **overrides) -> dict:
        base = {
            "root": root,
            "item_ids": set(),
            "npc_template_ids": set(),
            "quest_ids": set(),
            "quests_payload": {},
            "campaign_files": root / "campaigns",
            "region_files": [],
        }
        base.update(overrides)
        return base

    def _write_campaign(self, root: Path, name: str, payload) -> None:
        campaigns = root / "campaigns"
        campaigns.mkdir(parents=True, exist_ok=True)
        (campaigns / f"{name}.json").write_text(json.dumps(payload), encoding="utf-8")

    def test_malformed_campaign_file_reports_parse_error(self) -> None:
        root = self._case_root()
        campaigns = root / "campaigns"
        campaigns.mkdir(parents=True)
        (campaigns / "broken.json").write_text("{not valid", encoding="utf-8")
        issues = riv.validate_catalogs(self._base_catalogs(root))
        self.assertEqual(1, len(issues))
        self.assertEqual("error", issues[0].severity)

    def test_non_dict_campaign_is_ignored(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", ["not", "a", "dict"])
        issues = riv.validate_catalogs(self._base_catalogs(root))
        self.assertEqual([], issues)

    def test_unknown_start_node_id_is_reported(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", {"start_node_id": "missing", "nodes": {"a": {}}})
        issues = riv.validate_catalogs(self._base_catalogs(root))
        self.assertTrue(any("start_node_id" in i.path for i in issues))

    def test_unknown_quest_template_id_on_node_is_reported(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", {"nodes": {"a": {"quest_template_id": "missing_quest"}}})
        issues = riv.validate_catalogs(self._base_catalogs(root))
        self.assertTrue(any("quest_template_id" in i.path for i in issues))

    def test_known_quest_template_id_is_not_reported(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", {"nodes": {"a": {"quest_template_id": "q1"}}})
        issues = riv.validate_catalogs(self._base_catalogs(root, quest_ids={"q1"}))
        self.assertEqual([], issues)

    def test_unknown_transition_target_node_id_is_reported(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", {
            "nodes": {
                "a": {"transitions": [{"target_node_id": "missing"}, "not-a-dict"]},
            }
        })
        issues = riv.validate_catalogs(self._base_catalogs(root))
        self.assertTrue(any("transitions[0].target_node_id" in i.path for i in issues))

    def test_non_dict_nodes_is_ignored(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", {"start_node_id": "a", "nodes": "not-a-dict"})
        issues = riv.validate_catalogs(self._base_catalogs(root))
        # start_node_id is still checked against the (empty) node_ids set...
        self.assertTrue(any("start_node_id" in i.path for i in issues))

    def test_non_dict_node_and_non_list_transitions_are_ignored(self) -> None:
        root = self._case_root()
        self._write_campaign(root, "c1", {
            "nodes": {"a": "not-a-dict", "b": {"transitions": "not-a-list"}},
        })
        issues = riv.validate_catalogs(self._base_catalogs(root))
        self.assertEqual([], issues)


class TestReferenceIntegrityValidatorMain(unittest.TestCase):
    def _case_root(self) -> Path:
        root = Path("tmp") / f"ref_integrity_main_test_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _run_main(self, argv: list) -> int:
        with patch.object(sys, "argv", argv), redirect_stdout(io.StringIO()):
            with self.assertRaises(SystemExit) as cm:
                riv.main()
        return cm.exception.code

    def test_missing_root_exits_two(self) -> None:
        code = self._run_main(["reference_integrity_validator.py", str(self._case_root() / "missing")])
        self.assertEqual(2, code)

    def test_clean_data_root_exits_zero(self) -> None:
        root = self._case_root()
        (root / "items").mkdir(parents=True)
        (root / "npcs").mkdir(parents=True)
        (root / "regions").mkdir(parents=True)
        (root / "campaigns").mkdir(parents=True)
        (root / "quests").mkdir(parents=True)
        (root / "quests" / "quests.json").write_text("{}", encoding="utf-8")

        code = self._run_main(["reference_integrity_validator.py", str(root)])
        self.assertEqual(0, code)

    def test_data_root_with_issues_exits_one(self) -> None:
        root = self._case_root()
        (root / "items").mkdir(parents=True)
        (root / "npcs").mkdir(parents=True)
        (root / "regions").mkdir(parents=True)
        (root / "campaigns").mkdir(parents=True)
        (root / "quests").mkdir(parents=True)
        (root / "quests" / "quests.json").write_text("{}", encoding="utf-8")
        (root / "regions" / "town.json").write_text(
            json.dumps({"region_id": "town", "rooms": {"square": {"exits": {"north": "nowhere"}}}}),
            encoding="utf-8",
        )

        code = self._run_main(["reference_integrity_validator.py", str(root)])
        self.assertEqual(1, code)


if __name__ == "__main__":
    unittest.main()
