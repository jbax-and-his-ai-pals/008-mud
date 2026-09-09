"""Regression coverage for a real bug found while scoping player housing:
a dynamic/instance region's door onto a *permanent* room lives only in that
permanent room's `exits` dict, and the permanent room's own (static) region
is always rebuilt fresh from content-set JSON before a save is ever loaded
-- so the runtime-wired door was silently lost on every save/load round
trip, with nothing to ever notice or complain.

This exercises only the pre-existing quest-instance system (no housing code
involved) since it's the cheapest way to prove the general fix works."""

from typing import Any, Dict

from tests.fixtures import GameTestBase
from engine.world.definition_loader import _load_regions


class TestInstanceEntryExitPersistence(GameTestBase):
    def setUp(self):
        super().setUp()
        self.quest_data: Dict[str, Any] = {
            "instance_id": "persistence_test_01",
            "entry_point": {
                "region_id": "town",
                "room_id": "town_square",
                "exit_command": "test_enter_cellar",
            },
            "instance_region": {
                "region_name": "Test Cellar",
                "region_description": "A spooky cellar.",
                "rooms": {
                    "entry_hall": {
                        "name": "Entry Hall",
                        "description": "Dark.",
                        "exits": {"dynamic_exit": "dynamic_exit"},
                    }
                },
            },
            "objective": {"target_template_id": "giant_rat"},
            "layout_generation_config": {"target_count": [1, 1]},
        }

    def test_entry_exit_survives_a_static_region_rebuild_and_reload(self):
        success, msg, _giver_id = self.world.instance_manager.instantiate_quest_region(self.quest_data)
        self.assertTrue(success, f"Instantiation failed: {msg}")

        town_square = self.world.get_region("town").get_room("town_square")
        self.assertIn("test_enter_cellar", town_square.exits)
        instance_region_id = self.quest_data["instance_region_id"]
        self.assertEqual(f"{instance_region_id}:entry_hall", town_square.exits["test_enter_cellar"])

        self.assertTrue(self.world.save_game("persistence_test.json"))

        # Simulate a real process restart: World.__init__ always rebuilds
        # every static region fresh from content-set JSON before a save is
        # ever loaded, discarding any exit wired onto it at runtime. Doing
        # this rebuild directly (rather than constructing a whole new World)
        # is what makes this test fail without the fix and pass with it --
        # every prior instance test kept the same in-memory Room object
        # across the whole test, which could never catch this class of bug.
        _load_regions(self.world, self.world.content_root)
        self.assertNotIn(
            "test_enter_cellar", self.world.get_region("town").get_room("town_square").exits,
            "test setup problem: the static rebuild should have discarded the runtime exit",
        )

        success, _time_state, _weather_state = self.world.load_save_game("persistence_test.json")
        self.assertTrue(success)

        town_square_after_load = self.world.get_region("town").get_room("town_square")
        self.assertIn("test_enter_cellar", town_square_after_load.exits)
        self.assertEqual(
            f"{instance_region_id}:entry_hall",
            town_square_after_load.exits["test_enter_cellar"],
        )
