# tests/singles/test_theft_and_jail.py
"""End-to-end coverage for the `steal`, `wait`/`rest`, and `search`
commands, and the jail-cell escape hooks in
World.attempt_pick_lock_direction -- driven through process_command like a
real player session, not by calling CrimeManager directly (that's
test_crime_manager.py's job)."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.lockpick import Lockpick


def _find_npc(world, template_id):
    return next(npc for npc in world.npcs.values() if npc.template_id == template_id)


class TestStealFromVendor(GameTestBase):
    def setUp(self):
        super().setUp()
        grenda = _find_npc(self.world, "blacksmith")
        self.player.current_region_id = grenda.current_region_id
        self.player.current_room_id = grenda.current_room_id

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_undetected_theft_gives_the_item_with_no_consequence(self, mock_check):
        mock_check.return_value = (True, "", 10)
        result = self.game.process_command("steal crude bronze lockpick from Grenda")
        self.assertIn("unnoticed", result)
        self.assertEqual(1, self.player.inventory.count_item("item_lockpick_crude_bronze"))
        self.assertIsNone(self.player.jailed_until)

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_witnessed_small_theft_is_fined_and_keeps_the_item(self, mock_check):
        mock_check.return_value = (False, "", -10)
        self.player.runtime_state.gold = 1000
        result = self.game.process_command("steal crude bronze lockpick from Grenda")
        self.assertIn("red-handed", result)
        self.assertIn("fine", result)
        self.assertEqual(1, self.player.inventory.count_item("item_lockpick_crude_bronze"))
        self.assertLess(self.player.runtime_state.gold, 1000)

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_witnessed_theft_with_no_gold_is_jailed_and_loses_everything(self, mock_check):
        mock_check.return_value = (False, "", -10)
        self.player.runtime_state.gold = 0
        self.player.inventory.add_item(Lockpick(name="Spare Pick"))

        result = self.game.process_command("steal crude bronze lockpick from Grenda")

        self.assertIn("confiscated", result)
        self.assertIsNotNone(self.player.jailed_until)
        room = self.world.get_current_room(self.player)
        self.assertTrue(room.properties.get("is_jail_cell"))
        # Everything, including the stolen pick, went into confiscation.
        self.assertEqual(0, len([s for s in self.player.inventory.slots if s.item]))

    def test_nonexistent_item_reports_nothing_to_steal(self):
        result = self.game.process_command("steal a whole anvil from Grenda")
        self.assertIn("nothing like that", result)


class TestStealFromHome(GameTestBase):
    def setUp(self):
        super().setUp()
        self.mira = _find_npc(self.world, "weaver_mira")
        self.player.current_region_id = "town"
        self.player.current_room_id = "small_house_1_interior"

    def test_burglary_is_safe_when_the_owner_is_out(self):
        self.mira.current_room_id = "town_square"  # at "work", not home
        result = self.game.process_command("steal trinket from old trunk")
        # Whatever the lazily-generated loot happens to be, an absent
        # owner means no witness roll can occur at all.
        self.assertNotIn("red-handed", result)
        self.assertIsNone(self.player.jailed_until)

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_burglary_is_risky_when_the_owner_is_home(self, mock_check):
        mock_check.return_value = (False, "", -10)
        self.mira.current_room_id = "small_house_1_interior"
        self.player.runtime_state.gold = 1000

        # Force known contents so the item name is deterministic.
        from engine.items.item_factory import ItemFactory
        trunk = self.world.get_items_in_room("town", "small_house_1_interior")[0]
        trunk.properties["loot_generated"] = True
        coin = ItemFactory.create_item_from_template("item_gold_coin", self.world)
        trunk.properties["contains"] = [coin]

        result = self.game.process_command("steal gold coin from old trunk")

        self.assertIn("red-handed", result)
        self.assertIs(self.mira, _find_npc(self.world, "weaver_mira"))


class TestJailWaitAndSearch(GameTestBase):
    def test_wait_reports_time_remaining_before_release(self):
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=600)
        result = self.game.process_command("wait")
        self.assertIn("wait in your cell", result)
        self.assertIsNotNone(self.player.jailed_until)

    def test_wait_releases_once_the_sentence_has_elapsed(self):
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=-1)
        result = self.game.process_command("rest")
        self.assertIn("returns your belongings", result)
        self.assertIsNone(self.player.jailed_until)

    def test_wait_outside_jail_is_just_flavor(self):
        result = self.game.process_command("wait")
        self.assertEqual("Time passes.", result)

    def test_search_outside_a_cell_finds_nothing_to_search(self):
        result = self.game.process_command("search")
        self.assertIn("nothing to search", result)

    @patch("engine.commands.jail.random.random", return_value=0.0)
    def test_search_in_a_cell_can_find_gold(self, mock_random):
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=600)
        start_gold = self.player.runtime_state.gold
        result = self.game.process_command("search")
        self.assertIn("find", result)
        self.assertGreater(self.player.runtime_state.gold, start_gold)


class TestJailEscape(GameTestBase):
    def setUp(self):
        super().setUp()
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=600)

    @patch("engine.world.world.SkillSystem.attempt_check_with_margin")
    def test_successful_escape_forfeits_confiscated_items(self, mock_check):
        mock_check.return_value = (True, "", 10)
        self.player.inventory.add_item(Lockpick(name="Shiv"))

        result = self.game.process_command("pick up")

        self.assertIn("confiscated stays with them", result)
        self.assertIsNone(self.player.jailed_until)
        self.assertIsNone(self.player.confiscated_inventory)

    @patch("engine.world.world.SkillSystem.attempt_check_with_margin")
    def test_minor_escape_failure_is_a_safe_retry(self, mock_check):
        mock_check.return_value = (False, "", -5)
        self.player.inventory.add_item(Lockpick(name="Shiv"))
        original_release = self.player.jailed_until

        result = self.game.process_command("pick up")

        self.assertIn("fail to pick the lock", result)
        self.assertNotIn("sentence just got longer", result)
        self.assertEqual(original_release, self.player.jailed_until)

    @patch("engine.world.world.SkillSystem.attempt_check_with_margin")
    def test_major_escape_failure_extends_the_sentence(self, mock_check):
        mock_check.return_value = (False, "", -50)
        self.player.inventory.add_item(Lockpick(name="Shiv"))
        original_release = self.player.jailed_until

        result = self.game.process_command("pick up")

        self.assertIn("sentence just got longer", result)
        self.assertGreater(self.player.jailed_until, original_release)

    def test_no_lockpick_means_no_escape_attempt_possible(self):
        result = self.game.process_command("pick up")
        self.assertIn("need a lockpick", result)
        self.assertIsNotNone(self.player.jailed_until)


class TestConcealedPickGrant(GameTestBase):
    def test_pick_is_granted_and_usable_for_escape_when_bottleneck_crossed(self):
        self.player.add_skill("stealth", 25)
        self.player.add_skill("lockpicking", 25)
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=600)

        self.assertTrue(any(isinstance(s.item, Lockpick) for s in self.player.inventory.slots))

        with patch("engine.world.world.SkillSystem.attempt_check_with_margin", return_value=(True, "", 10)):
            result = self.game.process_command("pick up")
        self.assertIn("unlock the way up", result)
