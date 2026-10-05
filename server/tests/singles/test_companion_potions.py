# tests/singles/test_companion_potions.py
"""A companion with a healing item in its own pack (`initial_inventory`) drinks it when badly hurt.

Below 40% health, not while recovering, one at a time (a few seconds apart), and the line is told like any other
something a companion does. A companion with nothing to drink does nothing.
"""

import unittest

from engine.items.item_factory import ItemFactory
from engine.npcs import companions
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE


class TestACompanionDrinks(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = "varenholt", "barracks"
        self.kessa = next(n for n in self.world.npcs.values() if n.template_id == "captain_kessa")
        self.kessa.current_region_id, self.kessa.current_room_id = "varenholt", "barracks"
        companions.recruit(self.world, self.player, self.kessa)

    def give(self, count):
        potion = ItemFactory.create_item_from_template("item_potion", self.world)
        self.kessa.inventory.add_item(potion, count)

    def potions(self):
        return sum(slot.quantity for slot in self.kessa.inventory.slots if slot.item and slot.item.obj_id == "item_potion")

    def test_a_hurt_companion_drinks_from_her_own_pack(self):
        self.give(2)
        before = self.potions()
        self.kessa.health = 5
        told = companions.drink_potion_if_hurt(self.kessa, self.world, 100.0)
        self.assertIn("drinks", told)
        self.assertIn("recovers", told)
        self.assertGreater(self.kessa.health, 5)
        self.assertEqual(before - 1, self.potions(), "a potion is spent")

    def test_not_while_she_is_healthy(self):
        self.give(1)
        self.assertIsNone(companions.drink_potion_if_hurt(self.kessa, self.world, 100.0))
        self.kessa.health = int(self.kessa.max_health * 0.39)
        self.assertIsNotNone(companions.drink_potion_if_hurt(self.kessa, self.world, 100.0))

    def test_one_at_a_time_a_few_seconds_apart(self):
        self.give(3)
        self.kessa.health = 1
        self.assertIsNotNone(companions.drink_potion_if_hurt(self.kessa, self.world, 100.0))
        self.kessa.health = 1
        self.assertIsNone(companions.drink_potion_if_hurt(self.kessa, self.world, 101.0), "not again at once")
        self.assertIsNotNone(companions.drink_potion_if_hurt(self.kessa, self.world, 120.0))

    def test_with_nothing_to_drink_she_does_nothing(self):
        for slot in list(self.kessa.inventory.slots):
            if slot.item is not None:
                self.kessa.inventory.remove_item(slot.item.obj_id, slot.quantity)
        self.kessa.health = 1
        self.assertIsNone(companions.drink_potion_if_hurt(self.kessa, self.world, 100.0))

    def test_someone_who_is_not_a_companion_never_does(self):
        companions.dismiss(self.world, self.player, self.kessa)
        self.give(1)
        self.kessa.health = 1
        self.assertIsNone(companions.drink_potion_if_hurt(self.kessa, self.world, 100.0))

    def test_the_dispatcher_lets_her_drink_in_the_middle_of_a_fight(self):
        from engine.npcs.ai import dispatcher

        self.give(1)
        before = self.potions()
        self.kessa.health = 2
        self.kessa.in_combat = True
        told = dispatcher.handle_ai(self.kessa, self.world, 500.0, self.player)
        self.assertIsNotNone(told)
        self.assertIn("drinks", told)
        self.assertEqual(before - 1, self.potions())


if __name__ == "__main__":
    unittest.main()
