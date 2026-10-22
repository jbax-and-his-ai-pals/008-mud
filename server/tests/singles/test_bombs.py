# tests/singles/test_bombs.py
"""A bomb: a counted item that works a room-wide ability. It hurts what is in the room, opens a hidden way the room
reacts to it with, and is spent whether or not either happens; a pack holds only so many, and a bag holds more."""

import copy
import json
import re
import unittest

from engine.items.consumable import Consumable
from engine.items.item import Item
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.world import world_snapshot

from engine.npcs.npc_factory import NPCFactory

from tests.fixtures import GameTestBase
from tests.singles.test_encounters import _game, _hostile_template, _rooms

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _setup(case, hidden=False):
    server, player = _game(case)
    SPELL_REGISTRY["t_blast"] = Spell("t_blast", "Blast", "d", effects=[{"type": "damage", "value": 500, "damage_type": "explosive"}],
                                      mana_cost=0, target_type="room", cast_message="The bomb goes off with a crack.")
    case.addCleanup(SPELL_REGISTRY.pop, "t_blast", None)
    region_id, here, other = _rooms(server, player)
    room = server.world.get_region(region_id).get_room(here)
    room.exits.pop("north", None)
    if hidden:
        room.properties["hidden_exits"] = {"north": other}
        room.properties["env_interactions"] = {"explosive": {"type": "reveal_exit", "direction": "north", "message": "The north wall crumbles away."}}
    bomb = Consumable(obj_id="item_t_bomb", name="bomb", uses=1, effect_type="ability", ability="t_blast", carry_limit=8, weight=0)
    player.inventory.add_item(bomb, 3)
    return server, player, room, region_id, here


class TestABomb(unittest.TestCase):
    def _say(self, server, player):
        sid = next(iter(server.sessions)) if hasattr(server, "sessions") else None
        out = server.execute_command(sid, "use bomb")
        return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in out if e.get("type") == "text"))

    def test_it_kills_what_is_in_the_room_and_pays_as_any_kill_does(self):
        server, player, room, region_id, here = _setup(self)
        foe, _status = server.world.spawn_npc(_hostile_template(server), region_id, here, "t_foe")
        before = player.runtime_state.progression.experience + (player.runtime_state.gold or 0)
        said = self._say(server, player)
        self.assertFalse(foe.is_alive)
        self.assertTrue(foe._death_processed, "the kill ran: loot, the trigger and the respawn queue")
        self.assertIn("defeated", said)
        self.assertGreater(player.runtime_state.progression.experience + (player.runtime_state.gold or 0), before, "and it paid")
        self.assertEqual(2, player.inventory.count_item("item_t_bomb"))

    def test_it_opens_a_hidden_way_and_the_way_stays_open(self):
        server, player, room, region_id, here = _setup(self, hidden=True)
        self.assertNotIn("north", room.exits)
        said = self._say(server, player)
        self.assertIn("north", room.exits)
        self.assertIn("crumbles", said)
        self.assertIn("north", room.properties["exits"], "in the room's own exits, which the world snapshot keeps")
        self.assertEqual(2, player.inventory.count_item("item_t_bomb"))
        again = self._say(server, player)
        self.assertNotIn("crumbles", again, "a way already open is nothing to react to")
        self.assertEqual(1, player.inventory.count_item("item_t_bomb"), "but the bomb is spent all the same")

    def test_in_an_empty_room_with_nothing_to_find_it_is_spent_and_nothing_happens(self):
        server, player, room, region_id, here = _setup(self)
        said = self._say(server, player)
        self.assertIn("crack", said)
        self.assertEqual(2, player.inventory.count_item("item_t_bomb"))
        self.assertNotIn("north", room.exits)

    def test_every_bomb_of_a_stack_goes_off_not_only_the_first(self):
        server, player, room, region_id, here = _setup(self)
        for expected in (2, 1, 0):
            self.assertIn("crack", self._say(server, player))
            self.assertEqual(expected, player.inventory.count_item("item_t_bomb"))

    def test_it_does_not_need_to_be_a_known_ability_or_cost_anything(self):
        server, player, room, region_id, here = _setup(self)
        self.assertNotIn("t_blast", player.runtime_state.magic.known_spells)
        self._say(server, player)
        self.assertEqual(player.runtime_state.magic.max_mana, player.runtime_state.magic.mana)

    def test_a_way_a_bomb_opened_is_still_open_after_a_snapshot_and_restore(self):
        server, player, room, region_id, here = _setup(self, hidden=True)
        self._say(server, player)
        snapshot = copy.deepcopy(world_snapshot.capture(server.world))
        json.loads(json.dumps(snapshot))
        room.exits.pop("north")   # the static definition would not have it
        world_snapshot.restore(server.world, snapshot)
        self.assertIn("north", server.world.get_region(region_id).get_room(here).exits)


class TestACarryLimit(unittest.TestCase):
    def test_a_pack_holds_only_so_many_and_says_so(self):
        server, player, *_rest = _setup(self)
        player.inventory.add_item(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, effect_type="ability", ability="t_blast", carry_limit=8, weight=0), 5)
        self.assertEqual(8, player.inventory.count_item("item_t_bomb"))
        ok, said = player.inventory.can_add_item(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, carry_limit=8), 1)
        self.assertFalse(ok)
        self.assertIn("cannot carry more than 8", said)
        ok, said = player.inventory.add_item(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, carry_limit=8), 1)
        self.assertFalse(ok)
        self.assertEqual(8, player.inventory.count_item("item_t_bomb"), "and nothing was added")

    def test_a_bag_held_raises_the_limit_and_putting_it_down_does_not_take_the_bombs_away(self):
        server, player, *_rest = _setup(self)
        player.inventory.add_item(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, carry_limit=8, weight=0), 5)
        bag = Item(obj_id="item_t_bag", name="bomb bag", description="d", weight=0, carry_limits={"item_t_bomb": 12})
        player.inventory.add_item(bag)
        ok, _said = player.inventory.add_item(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, carry_limit=8, weight=0), 4)
        self.assertTrue(ok)
        self.assertEqual(12, player.inventory.count_item("item_t_bomb"))
        self.assertFalse(player.inventory.can_add_item(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, carry_limit=8), 1)[0])
        player.inventory.remove_item("item_t_bag")
        self.assertEqual(8, player.inventory.carry_cap(Consumable(obj_id="item_t_bomb", name="bomb", uses=1, carry_limit=8)))
        self.assertEqual(12, player.inventory.count_item("item_t_bomb"), "what is carried stays carried")

    def test_an_item_without_a_limit_is_unlimited(self):
        server, player, *_rest = _setup(self)
        self.assertIsNone(player.inventory.carry_cap(Item(obj_id="item_t_rock", name="rock", description="d", stackable=True)))


class TestBuyingAtTheLimit(GameTestBase):
    def test_a_purchase_beyond_the_limit_is_refused_and_the_money_kept(self):
        self.world.item_templates["test_bomb"] = {"type": "Consumable", "name": "Bomb", "value": 10, "stackable": True,
                                                  "properties": {"carry_limit": 3, "effect_type": "heal", "effect_value": 1}}
        self.world.npc_templates["bomb_seller"] = {"name": "Seller", "faction": "friendly",
                                                   "properties": {"is_vendor": True, "sells_items": [{"item_id": "test_bomb"}]}}
        vendor = NPCFactory.create_npc_from_template("bomb_seller", self.world)
        self.world.add_npc(vendor)
        vendor.current_region_id, vendor.current_room_id = self.player.current_region_id, self.player.current_room_id
        self.player.trading_with = vendor.obj_id
        self.player.runtime_state.gold = 1000
        for _ in range(3):
            self.assertIn("You buy", self.game.process_command("buy Bomb"))
        gold = self.player.runtime_state.gold
        said = self.game.process_command("buy Bomb")
        self.assertIn("cannot carry more than 3", said)
        self.assertEqual(gold, self.player.runtime_state.gold, "no money was taken")
        self.assertEqual(3, self.player.inventory.count_item("test_bomb"))


if __name__ == "__main__":
    unittest.main()
