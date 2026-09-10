# tests/singles/test_crime_manager.py
"""Coverage for engine/core/crime_manager.py in isolation: the witness
roll, fine-vs-jail decision, and jailing/release/forfeit mechanics --
independent of the `steal` command or content that drives them."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc import NPC
from engine.items.lockpick import Lockpick
from engine.items.item import Item
from engine.player.core import Player


class TestAttemptWitness(GameTestBase):
    def setUp(self):
        super().setUp()
        # town_square (the default spawn room) is packed with authored
        # NPCs; move to a room with none so "no witness present" tests
        # mean what they say.
        self.player.current_region_id = "town"
        self.player.current_room_id = "west_lane"

    def _place_npc(self, level=1, is_guard=False):
        npc = NPC(name="Bystander", level=level)
        npc.faction = "friendly"
        if is_guard:
            npc.properties["is_guard"] = True
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        self.world.add_npc(npc)
        return npc

    def test_no_npcs_present_means_no_witness(self):
        witness = self.world.crime_manager.attempt_witness(self.player)
        self.assertIsNone(witness)

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_successful_stealth_check_avoids_witness(self, mock_check):
        mock_check.return_value = (True, "", 10)
        self._place_npc()
        witness = self.world.crime_manager.attempt_witness(self.player)
        self.assertIsNone(witness)

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_failed_stealth_check_returns_the_witness(self, mock_check):
        mock_check.return_value = (False, "", -10)
        npc = self._place_npc()
        witness = self.world.crime_manager.attempt_witness(self.player)
        self.assertIs(witness, npc)

    @patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin")
    def test_hostile_npcs_are_never_witnesses(self, mock_check):
        mock_check.return_value = (False, "", -10)
        hostile = self._place_npc()
        hostile.faction = "hostile"
        witness = self.world.crime_manager.attempt_witness(self.player)
        self.assertIsNone(witness)

    def test_guard_perception_beats_an_ordinary_bystander(self):
        bystander = self._place_npc(level=1, is_guard=False)
        guard = self._place_npc(level=1, is_guard=True)
        difficulties = {
            npc: self.world.crime_manager._npc_perception_difficulty(npc)
            for npc in (bystander, guard)
        }
        self.assertGreater(difficulties[guard], difficulties[bystander])


class TestResolveCrime(GameTestBase):
    def test_small_theft_with_good_reputation_is_a_fine(self):
        self.player.runtime_state.gold = 1000
        start_gold = self.player.runtime_state.gold
        msg = self.world.crime_manager.resolve_crime(self.player, theft_value=10)
        self.assertIn("fine", msg)
        self.assertLess(self.player.runtime_state.gold, start_gold)
        self.assertIsNone(self.player.jailed_until)

    def test_unaffordable_fine_escalates_to_jail(self):
        self.player.runtime_state.gold = 0
        msg = self.world.crime_manager.resolve_crime(self.player, theft_value=10)
        self.assertIn("cell", msg)
        self.assertIsNotNone(self.player.jailed_until)

    def test_high_value_theft_goes_straight_to_jail(self):
        self.player.runtime_state.gold = 100000
        from engine.config import CRIME_JAIL_VALUE_THRESHOLD
        msg = self.world.crime_manager.resolve_crime(self.player, theft_value=CRIME_JAIL_VALUE_THRESHOLD)
        self.assertIn("cell", msg)
        self.assertIsNotNone(self.player.jailed_until)

    def test_notoriety_accumulates_and_is_isolated_from_combat_reputation(self):
        self.player.runtime_state.gold = 1000
        self.world.crime_manager.resolve_crime(self.player, theft_value=10)
        self.assertLess(self.player.get_reputation("town_guard"), 0)
        self.assertEqual(0, self.player.get_reputation("friendly"))

    def test_repeat_offenses_eventually_escalate_to_jail(self):
        from engine.config import CRIME_JAIL_CUMULATIVE_THRESHOLD
        self.player.runtime_state.gold = 1000000
        msg = ""
        for _ in range(50):
            msg = self.world.crime_manager.resolve_crime(self.player, theft_value=1)
            if self.player.jailed_until is not None:
                break
        self.assertIsNotNone(self.player.jailed_until)
        self.assertGreaterEqual(self.player.total_theft_value, 1)


class TestJailingAndRelease(GameTestBase):
    def test_send_to_jail_confiscates_the_full_backpack(self):
        self.player.inventory.add_item(Item(name="Trinket", value=5))
        self.assertGreater(len([s for s in self.player.inventory.slots if s.item]), 0)

        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)

        self.assertEqual(0, len([s for s in self.player.inventory.slots if s.item]))
        self.assertIsNotNone(self.player.confiscated_inventory)
        self.assertTrue(any(s.item and s.item.name == "Trinket" for s in self.player.confiscated_inventory.slots))

    def test_send_to_jail_teleports_to_the_authored_cell(self):
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)
        room = self.world.get_current_room(self.player)
        self.assertTrue(room.properties.get("is_jail_cell"))

    def test_release_restores_confiscated_items_and_clears_jail_state(self):
        self.player.inventory.add_item(Item(name="Trinket", value=5))
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)

        msg = self.world.crime_manager.release_from_jail(self.player)

        self.assertIn("returns your belongings", msg)
        self.assertIsNone(self.player.jailed_until)
        self.assertIsNone(self.player.confiscated_inventory)
        self.assertTrue(any(s.item and s.item.name == "Trinket" for s in self.player.inventory.slots))

    def test_forfeit_clears_state_without_restoring_items(self):
        self.player.inventory.add_item(Item(name="Trinket", value=5))
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)

        self.world.crime_manager.forfeit_confiscated_items(self.player)

        self.assertIsNone(self.player.jailed_until)
        self.assertIsNone(self.player.confiscated_inventory)
        self.assertFalse(any(s.item and s.item.name == "Trinket" for s in self.player.inventory.slots))

    def test_no_concealed_pick_bottleneck_means_no_pick_granted(self):
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)
        self.assertFalse(any(isinstance(s.item, Lockpick) for s in self.player.inventory.slots))

    def test_bottleneck_crossed_with_no_pick_carried_grants_a_shiv(self):
        self.player.add_skill("stealth", 25)
        self.player.add_skill("lockpicking", 25)

        msg = self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)

        self.assertIn("keep a spare pick", msg)
        self.assertTrue(any(isinstance(s.item, Lockpick) for s in self.player.inventory.slots))
        self.assertTrue(self.player.discovered_concealed_pick_trick)

    def test_bottleneck_crossed_with_a_carried_pick_exempts_it_instead_of_granting_a_new_one(self):
        self.player.add_skill("stealth", 25)
        self.player.add_skill("lockpicking", 25)
        carried = Lockpick(obj_id="my_pick", name="My Pick", durability=9)
        self.player.inventory.add_item(carried)

        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)

        kept = [s.item for s in self.player.inventory.slots if isinstance(s.item, Lockpick)]
        self.assertEqual(1, len(kept))
        self.assertIs(kept[0], carried)

    def test_flavor_beat_only_shows_once(self):
        self.player.add_skill("stealth", 25)
        self.player.add_skill("lockpicking", 25)

        first_msg = self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)
        self.world.crime_manager.release_from_jail(self.player)
        second_msg = self.world.crime_manager.send_to_jail(self.player, sentence_seconds=60)

        self.assertIn("keep a spare pick", first_msg)
        self.assertNotIn("keep a spare pick", second_msg)


class TestJailStatePersistence(GameTestBase):
    def test_jail_state_survives_a_save_load_round_trip(self):
        from engine.items.item_factory import ItemFactory
        coin = ItemFactory.create_item_from_template("item_gold_coin", self.world)
        self.player.inventory.add_item(coin)
        self.world.crime_manager.send_to_jail(self.player, sentence_seconds=123.0)
        self.player.total_theft_value = 42
        self.player.discovered_concealed_pick_trick = True

        data = self.player.to_dict(self.world)
        restored = Player.from_dict(data, self.world)

        self.assertIsNotNone(restored)
        self.assertAlmostEqual(self.player.jailed_until, restored.jailed_until)
        self.assertEqual(42, restored.total_theft_value)
        self.assertTrue(restored.discovered_concealed_pick_trick)
        self.assertIsNotNone(restored.confiscated_inventory)
        self.assertTrue(any(
            s.item and s.item.obj_id == "item_gold_coin" for s in restored.confiscated_inventory.slots
        ))

    def test_no_jail_state_round_trips_as_none(self):
        data = self.player.to_dict(self.world)
        restored = Player.from_dict(data, self.world)
        self.assertIsNone(restored.jailed_until)
        self.assertIsNone(restored.confiscated_inventory)
