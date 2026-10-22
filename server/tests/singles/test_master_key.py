# tests/singles/test_master_key.py
"""An item with `properties.master_key` opens every locked exit and is never spent."""

import unittest

from engine.items.item import Item

from tests.singles.test_encounters import _game, _rooms


def _locked_door(case, consume):
    server, player = _game(case)
    region_id, here, other = _rooms(server, player)
    room = server.world.get_region(region_id).get_room(here)
    room.exits.pop("north", None)
    room.exits["north"] = other
    room.properties["exit_requirements"] = {"north": {"type": "locked", "key_id": "item_t_small", "pick_difficulty": 999, "consume": consume, "failure_message": "Locked."}}
    sid = next(iter(server.sessions))
    return server, player, sid, (region_id, here), (region_id, other)


def _key(obj_id, **props):
    return Item(obj_id=obj_id, name=obj_id.replace("item_t_", "") + " key", description="d", weight=0, stackable=True, **props)


class TestAMasterKey(unittest.TestCase):
    def test_without_either_key_the_door_is_shut(self):
        server, player, sid, here, other = _locked_door(self, True)
        server.execute_command(sid, "go north")
        self.assertEqual(here, (player.current_region_id, player.current_room_id))

    def test_a_master_key_opens_it_and_is_not_spent(self):
        server, player, sid, here, other = _locked_door(self, True)
        player.inventory.add_item(_key("item_t_master", master_key=True))
        server.execute_command(sid, "go north")
        self.assertEqual(other, (player.current_region_id, player.current_room_id))
        self.assertEqual(1, player.inventory.count_item("item_t_master"))

    def test_with_both_the_ordinary_key_is_kept_too(self):
        server, player, sid, here, other = _locked_door(self, True)
        player.inventory.add_item(_key("item_t_master", master_key=True))
        player.inventory.add_item(_key("item_t_small"))
        server.execute_command(sid, "go north")
        self.assertEqual(other, (player.current_region_id, player.current_room_id))
        self.assertEqual(1, player.inventory.count_item("item_t_small"))

    def test_the_ordinary_key_is_still_spent_when_it_is_all_there_is(self):
        server, player, sid, here, other = _locked_door(self, True)
        player.inventory.add_item(_key("item_t_small"))
        server.execute_command(sid, "go north")
        self.assertEqual(0, player.inventory.count_item("item_t_small"))


class TestCarryingSlots(unittest.TestCase):
    def test_a_set_may_say_how_many_things_a_character_carries(self):
        server, player = _game(self)
        self.assertEqual(20, player.inventory.max_slots)
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"inventory_slots": 45} if name == "player_defaults" else original(name)
        from engine.player import Player

        self.assertEqual(45, Player("Wide", server.world).inventory.max_slots)

    def test_a_nonsense_number_is_ignored_by_the_engine_and_refused_by_the_validator(self):
        server, player = _game(self)
        original = server.world.ruleset_section
        from engine.player import Player

        for bad in (0, -3, True, "many"):
            server.world.ruleset_section = lambda name, bad=bad: {"inventory_slots": bad} if name == "player_defaults" else original(name)
            self.assertEqual(20, Player("Narrow", server.world).inventory.max_slots, bad)


if __name__ == "__main__":
    unittest.main()
