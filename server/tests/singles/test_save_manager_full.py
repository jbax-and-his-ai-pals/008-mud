# tests/singles/test_save_manager_full.py
"""Coverage for engine/world/save_manager.py's remaining branches: save()'s
path-resolution/no-player/exception paths and its no-game/no-content-set
skips, load()'s content-set-metadata-not-a-dict skip, falsy dynamic-region
entries, a Region.from_dict failure during restore, missing player data,
Player.from_dict returning None, falsy region/no-template_id skips during
NPC restore, a missing quest_manager, load()'s outer exception recovery,
and both path-resolvers' exception handling plus the CWD fallback."""

import os
import stat
import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.world.save_manager import SaveManager


def _cleanup(path):
    if os.path.exists(path):
        for _ in range(3):
            try:
                os.chmod(path, stat.S_IWRITE)
                os.remove(path)
                break
            except PermissionError:
                time.sleep(0.1)


class TestSave(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = SaveManager(self.world)
        self.save_file = "save_manager_full_test.json"
        self.save_path = os.path.join("data", "saves", self.save_file)

    def tearDown(self):
        _cleanup(self.save_path)
        super().tearDown()

    def test_unresolvable_path_returns_false(self):
        with patch.object(self.manager, "_resolve_save_path", return_value=None):
            self.assertFalse(self.manager.save(self.save_file))

    def test_no_resolvable_player_returns_false(self):
        with patch.object(self.world, "resolve_reference_player", return_value=None):
            self.assertFalse(self.manager.save(self.save_file))

    def test_exception_during_save_is_caught(self):
        with patch.object(self.player, "to_dict", side_effect=RuntimeError("boom")):
            self.assertFalse(self.manager.save(self.save_file))

    def test_save_without_game_skips_time_and_weather_state(self):
        original_game = self.world.game
        self.world.game = None
        try:
            self.assertTrue(self.manager.save(self.save_file))
        finally:
            self.world.game = original_game
        with open(self.save_path) as f:
            import json
            data = json.load(f)
        self.assertIsNone(data["time_state"])
        self.assertIsNone(data["weather_state"])

    def test_save_without_content_set_skips_metadata(self):
        original_content_set = getattr(self.world, "content_set", None)
        self.world.content_set = None
        try:
            self.assertTrue(self.manager.save(self.save_file))
        finally:
            self.world.content_set = original_content_set
        with open(self.save_path) as f:
            import json
            data = json.load(f)
        self.assertIsNone(data["content_set"])

    def test_falsy_region_entry_is_skipped_when_collecting_items(self):
        self.world.regions["ghost_region_xyz"] = None
        try:
            self.assertTrue(self.manager.save(self.save_file))
        finally:
            del self.world.regions["ghost_region_xyz"]


class TestLoad(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = SaveManager(self.world)
        self.save_file = "save_manager_full_load_test.json"
        self.save_path = os.path.join("data", "saves", self.save_file)

    def tearDown(self):
        _cleanup(self.save_path)
        super().tearDown()

    def test_missing_file_returns_failure_tuple(self):
        result = self.manager.load("totally_bogus_save_xyz.json")
        self.assertEqual(result, (False, None, None))

    def test_content_set_metadata_not_a_dict_is_ignored(self):
        self.assertTrue(self.manager.save(self.save_file))
        import json
        with open(self.save_path) as f:
            data = json.load(f)
        data["content_set"] = "not a dict"
        with open(self.save_path, "w") as f:
            json.dump(data, f)
        success, _, _ = self.manager.load(self.save_file)
        self.assertTrue(success)

    def test_falsy_dynamic_region_entry_is_skipped(self):
        self.assertTrue(self.manager.save(self.save_file))
        import json
        with open(self.save_path) as f:
            data = json.load(f)
        data["dynamic_regions"] = [None]
        with open(self.save_path, "w") as f:
            json.dump(data, f)
        success, _, _ = self.manager.load(self.save_file)
        self.assertTrue(success)

    def test_region_from_dict_failure_is_logged_and_continues(self):
        self.assertTrue(self.manager.save(self.save_file))
        import json
        with open(self.save_path) as f:
            data = json.load(f)
        data["dynamic_regions"] = [{"totally": "malformed"}]
        with open(self.save_path, "w") as f:
            json.dump(data, f)
        with patch("engine.world.save_manager.Region.from_dict", side_effect=RuntimeError("bad region")):
            success, _, _ = self.manager.load(self.save_file)
        self.assertTrue(success)

    def test_missing_player_data_returns_failure_tuple(self):
        self.assertTrue(self.manager.save(self.save_file))
        import json
        with open(self.save_path) as f:
            data = json.load(f)
        del data["player"]
        with open(self.save_path, "w") as f:
            json.dump(data, f)
        result = self.manager.load(self.save_file)
        self.assertEqual(result, (False, None, None))

    def test_player_from_dict_returning_none_triggers_recovery(self):
        self.assertTrue(self.manager.save(self.save_file))
        with patch("engine.world.save_manager.Player.from_dict", return_value=None):
            with patch.object(self.world, "initialize_new_world") as mock_init:
                success, _, _ = self.manager.load(self.save_file)
        self.assertFalse(success)
        mock_init.assert_called_once()

    def test_falsy_region_entry_is_skipped_when_clearing_items(self):
        # A None region isn't something production code actually creates
        # (nothing ever assigns world.regions[id] = None -- entries are only
        # ever popped), but save_manager defends against it anyway; that
        # defense would otherwise crash later inside initialize_npc_schedules
        # (schedules.py has no equivalent guard), so stub it out here to
        # isolate the branch this test actually targets.
        self.assertTrue(self.manager.save(self.save_file))
        self.world.regions["ghost_region_xyz"] = None
        try:
            with patch("engine.world.save_manager.initialize_npc_schedules"):
                success, _, _ = self.manager.load(self.save_file)
        finally:
            self.world.regions.pop("ghost_region_xyz", None)
        self.assertTrue(success)

    def test_npc_state_missing_template_id_is_skipped(self):
        self.assertTrue(self.manager.save(self.save_file))
        import json
        with open(self.save_path) as f:
            data = json.load(f)
        data["npc_states"]["ghost_npc"] = {"name": "No Template"}
        with open(self.save_path, "w") as f:
            json.dump(data, f)
        success, _, _ = self.manager.load(self.save_file)
        self.assertTrue(success)
        self.assertNotIn("ghost_npc", self.world.npcs)

    def test_missing_quest_manager_is_skipped(self):
        self.assertTrue(self.manager.save(self.save_file))
        original_qm = self.world.quest_manager
        self.world.quest_manager = None
        try:
            success, _, _ = self.manager.load(self.save_file)
        finally:
            self.world.quest_manager = original_qm
        self.assertTrue(success)

    def test_exception_during_load_triggers_recovery_and_returns_failure(self):
        self.assertTrue(self.manager.save(self.save_file))
        with patch("engine.world.save_manager.NPCFactory.create_npc_from_template", side_effect=RuntimeError("boom")):
            with patch.object(self.world, "initialize_new_world") as mock_init:
                # Force at least one npc_state entry with a template_id so the
                # patched factory call is actually reached.
                import json
                with open(self.save_path) as f:
                    data = json.load(f)
                data["npc_states"]["forced_npc"] = {"template_id": "goblin"}
                with open(self.save_path, "w") as f:
                    json.dump(data, f)
                success, time_data, weather_data = self.manager.load(self.save_file)
        self.assertFalse(success)
        self.assertIsNone(time_data)
        self.assertIsNone(weather_data)
        mock_init.assert_called_once()


class TestResolvePaths(GameTestBase):
    def setUp(self):
        super().setUp()
        self.manager = SaveManager(self.world)

    def test_resolve_save_path_exception_returns_none(self):
        with patch("engine.world.save_manager.os.makedirs", side_effect=OSError("disk full")):
            self.assertIsNone(self.manager._resolve_save_path("x.json", "data/saves"))

    def test_resolve_load_path_exception_returns_none(self):
        with patch("engine.world.save_manager.os.path.abspath", side_effect=OSError("bad path")):
            self.assertIsNone(self.manager._resolve_load_path("x.json", "data/saves"))

    def test_resolve_load_path_falls_back_to_cwd(self):
        cwd_filename = "save_manager_full_cwd_test.json"
        cwd_path = os.path.abspath(cwd_filename)
        with open(cwd_path, "w") as f:
            f.write("{}")
        try:
            result = self.manager._resolve_load_path(cwd_filename, "totally_bogus_save_dir_xyz")
            self.assertEqual(result, cwd_path)
        finally:
            os.remove(cwd_path)


if __name__ == "__main__":
    unittest.main()
