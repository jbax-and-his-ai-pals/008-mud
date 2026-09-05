# tests/singles/test_debug_world_commands.py
"""Coverage for GM/debug world commands (engine/commands/debug/world.py):
settime, setweather, teleport, whereis, census, genregion, close portal."""

from unittest.mock import patch

from tests.fixtures import GameTestBase


class TestSetTimeCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertEqual("Usage: settime <val>", self.game.process_command("settime"))

    def test_named_period_sets_hour(self):
        result = self.game.process_command("settime dusk")
        self.assertIn("18:00", result)
        self.assertEqual(18, self.game.time_manager.hour)

    def test_numeric_hour_and_minute(self):
        result = self.game.process_command("settime 7 30")
        self.assertIn("07:30", result)
        self.assertEqual(7, self.game.time_manager.hour)
        self.assertEqual(30, self.game.time_manager.minute)

    def test_invalid_format_is_reported(self):
        result = self.game.process_command("settime not_a_time")
        self.assertEqual("Invalid format.", result)

    def test_resets_scheduled_npc_paths(self):
        from engine.npcs.npc_factory import NPCFactory

        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="sched_npc")
        self.world.add_npc(npc)
        npc.behavior_type = "scheduled"
        npc.schedule_destination = ("town", "market_square")
        npc.current_path = ["north"]

        self.game.process_command("settime day")
        self.assertIsNone(npc.schedule_destination)
        self.assertEqual([], npc.current_path)


class TestSetWeatherCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertEqual("Usage: setweather <type> [intensity]", self.game.process_command("setweather"))

    def test_invalid_type_is_reported(self):
        self.assertEqual("Invalid type.", self.game.process_command("setweather not_a_real_type"))

    def test_valid_type_updates_weather(self):
        valid_type = next(iter(self.game.weather_manager.weather_chances["summer"].keys()))
        result = self.game.process_command(f"setweather {valid_type}")
        self.assertIn("Weather set", result)
        self.assertEqual(valid_type, self.game.weather_manager.current_weather)

    def test_intensity_argument_is_applied(self):
        valid_type = next(iter(self.game.weather_manager.weather_chances["summer"].keys()))
        self.game.process_command(f"setweather {valid_type} heavy")
        self.assertEqual("heavy", self.game.weather_manager.current_intensity)


class TestTeleportCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertEqual("Usage: tp <target>", self.game.process_command("tp"))

    def test_no_player_reports_not_found(self):
        from engine.commands.debug.world import teleport_handler
        result = teleport_handler(["town", "market_square"], {"world": self.world, "player": None})
        self.assertEqual("Player not found.", result)

    def test_region_room_teleport_without_quest_manager_skips_quest_check(self):
        with patch.object(self.world, "quest_manager", None):
            result = self.game.process_command("tp town market_square")
        self.assertIn("Teleported to town:market_square", result)

    def test_npc_teleport_without_quest_manager_skips_quest_check(self):
        from engine.npcs.npc_factory import NPCFactory

        npc = NPCFactory.create_npc_from_template(
            "village_elder", self.world, instance_id="tp_target_noqm", name="Noqm Target Npc"
        )
        npc.current_region_id = "town"
        npc.current_room_id = "market_square"
        self.world.add_npc(npc)

        with patch.object(self.world, "quest_manager", None):
            result = self.game.process_command("tp Noqm Target Npc")
        self.assertIn("Teleported to Noqm Target Npc", result)

    def test_teleport_to_region_and_room(self):
        result = self.game.process_command("tp town market_square")
        self.assertIn("Teleported to town:market_square", result)
        self.assertEqual("town", self.player.current_region_id)
        self.assertEqual("market_square", self.player.current_room_id)

    def test_teleport_to_npc_by_name(self):
        from engine.npcs.npc_factory import NPCFactory

        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="tp_target", name="Unique Target Npc")
        npc.current_region_id = "town"
        npc.current_room_id = "market_square"
        self.world.add_npc(npc)

        result = self.game.process_command("tp Unique Target Npc")
        self.assertIn("Teleported to Unique Target Npc", result)
        self.assertEqual("market_square", self.player.current_room_id)

    def test_unknown_target_is_reported(self):
        result = self.game.process_command("tp nowhere_at_all")
        self.assertIn("Could not find location or NPC", result)

    def test_ambiguous_npc_name_is_reported(self):
        from engine.npcs.npc_factory import NPCFactory

        for i in range(2):
            npc = NPCFactory.create_npc_from_template(
                "village_elder", self.world, instance_id=f"dup_{i}", name="Duplicate Name Npc"
            )
            npc.current_region_id = "town"
            npc.current_room_id = "market_square"
            self.world.add_npc(npc)

        result = self.game.process_command("tp Duplicate Name Npc")
        self.assertIn("Ambiguous", result)

    def test_npc_without_location_is_reported(self):
        from engine.npcs.npc_factory import NPCFactory

        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="lost_npc", name="Lost Unique Npc")
        npc.current_region_id = None
        self.world.add_npc(npc)

        result = self.game.process_command("tp Lost Unique Npc")
        self.assertEqual("NPC location unknown.", result)


class TestWhereisCommand(GameTestBase):
    def test_no_args_shows_usage(self):
        self.assertEqual("Usage: whereis <name>", self.game.process_command("whereis"))

    def test_not_found_is_reported(self):
        self.assertEqual("Not found.", self.game.process_command("whereis nobody_at_all"))

    def test_found_reports_location(self):
        from engine.npcs.npc_factory import NPCFactory

        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="find_me", name="Findable Npc")
        npc.current_region_id = "town"
        npc.current_room_id = "market_square"
        self.world.add_npc(npc)

        result = self.game.process_command("whereis Findable Npc")
        self.assertIn("town:market_square", result)


class TestCensusCommand(GameTestBase):
    def test_reports_counts_by_region(self):
        result = self.game.process_command("census")
        self.assertIn("World Census", result)
        self.assertIn("town", result)

    def test_dead_npcs_are_excluded_from_counts(self):
        from engine.npcs.npc_factory import NPCFactory

        before = self.game.process_command("census")
        npc = NPCFactory.create_npc_from_template("giant_rat", self.world, instance_id="dead_census_rat")
        npc.current_region_id = "town"
        npc.is_alive = False
        self.world.add_npc(npc)

        after = self.game.process_command("census")
        self.assertEqual(before, after)


class TestGenregionAndClosePortal(GameTestBase):
    def test_genregion_no_args_shows_usage(self):
        self.assertEqual("Usage: genregion <theme> [rooms]", self.game.process_command("genregion"))

    def test_genregion_without_player_location_reports_must_be_in_world(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.game.process_command("genregion caves")
        self.assertEqual("Must be in world.", result)

    def test_genregion_generation_failure_is_reported(self):
        with patch(
            "engine.commands.debug.world.RegionGenerator.generate_region", return_value=None,
        ):
            result = self.game.process_command("genregion caves")
        self.assertEqual("Generation failed.", result)

    def test_genregion_with_unresolvable_current_room_skips_local_portal_link(self):
        self.player.current_room_id = "not_a_real_room_in_town"
        result = self.game.process_command("genregion caves 5")
        self.assertIn("Generated", result)

    def test_genregion_with_missing_entry_room_skips_far_side_portal_link(self):
        from engine.world.region import Region
        from engine.world.room import Room

        fake_region = Region("Generated", "A place.", obj_id="dynamic_no_entry_room")
        fake_region.add_room("some_other_room", Room("Other", "x", obj_id="some_other_room"))
        with patch(
            "engine.commands.debug.world.RegionGenerator.generate_region",
            return_value=(fake_region, "not_a_real_entry_id"),
        ):
            result = self.game.process_command("genregion caves 5")
        self.assertIn("Generated", result)

    def test_close_portal_without_player_location_reports_must_be_in_world(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.game.process_command("close portal")
        self.assertEqual("Must be in world.", result)

    def test_close_portal_on_a_non_dynamic_region_is_rejected(self):
        room = self.world.get_region(self.player.current_region_id).get_room(self.player.current_room_id)
        room.exits["portal"] = "town:market_square"
        result = self.game.process_command("close portal")
        self.assertEqual("Not a dynamic region.", result)

    def test_genregion_creates_portal_and_close_portal_removes_it(self):
        result = self.game.process_command("genregion caves 5")
        self.assertIn("Generated", result)

        room = self.world.get_region(self.player.current_region_id).get_room(self.player.current_room_id)
        self.assertIn("portal", room.exits)
        dynamic_region_id = room.exits["portal"].split(":")[0]
        self.assertTrue(dynamic_region_id.startswith("dynamic_"))
        self.assertIn(dynamic_region_id, self.world.regions)

        close_result = self.game.process_command("close portal")
        self.assertIn("Region destroyed", close_result)
        self.assertNotIn("portal", room.exits)
        self.assertNotIn(dynamic_region_id, self.world.regions)

    def test_close_portal_without_a_portal_is_reported(self):
        result = self.game.process_command("close portal")
        self.assertEqual("No portal here.", result)
