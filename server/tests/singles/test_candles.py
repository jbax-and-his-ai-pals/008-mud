# tests/singles/test_candles.py
"""A candle: an item that lights the room you stand in until you leave it, burns what is there and what the room is made of,
and (the blue one) works once in each room, because the light it leaves is what stops a second use."""

import re
import unittest

from engine import conditions
from engine.items.consumable import Consumable
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY

from tests.singles.test_encounters import _game, _hostile_template, _rooms

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
_LIT_ONCE = {"not": {"kind": "status_active", "tag": "candlelight"}}


def _setup(case, dark=False, burnable=False):
    server, player = _game(case)
    SPELL_REGISTRY["t_flame"] = Spell("t_flame", "Flame", "d", effects=[
        {"type": "damage", "value": 5, "damage_type": "fire"},
        {"type": "apply_effect", "on": "caster", "effect_data": {"name": "Candlelight", "tags": ["light", "candlelight"], "base_duration": 3600, "ends_on_move": True}},
    ], mana_cost=0, target_type="room", cast_message="You touch the wick and a small flame stands up.")
    case.addCleanup(SPELL_REGISTRY.pop, "t_flame", None)
    region_id, here, other = _rooms(server, player)
    room = server.world.get_region(region_id).get_room(here)
    room.exits.pop("north", None)
    if dark:
        room.properties["dark"] = True
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"dark_requires_light": True} if name == "world" else original(name)
    if burnable:
        room.properties["hidden_exits"] = {"north": other}
        room.properties["env_interactions"] = {"fire": {"type": "reveal_exit", "direction": "north", "message": "The bush burns away."}}
    candle = Consumable(obj_id="item_t_candle", name="candle", uses=1, effect_type="ability", ability="t_flame", reusable=True,
                        requires=_LIT_ONCE, requires_message="The candle already burns in this room.", weight=0)
    player.inventory.add_item(candle)
    sid = next(iter(server.sessions))
    return server, player, room, region_id, here, other, sid


def _say(server, sid, text):
    return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in server.execute_command(sid, text) if e.get("type") == "text"))


class TestACandle(unittest.TestCase):
    def test_it_lights_the_caster_even_in_a_room_with_nobody_to_burn(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        self.assertFalse(player.has_effect_tag("light"))
        _say(server, sid, "use candle")
        self.assertTrue(player.has_effect_tag("light"))

    def test_it_burns_the_creatures_in_the_room_and_lights_the_caster_not_them(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        foe, _status = server.world.spawn_npc(_hostile_template(server), region_id, here, "t_foe")
        before = foe.health
        _say(server, sid, "use candle")
        self.assertLess(foe.health, before)
        self.assertTrue(player.has_effect_tag("light"))
        self.assertFalse(foe.has_effect_tag("light"), "an effect on the caster does not land on the targets")

    def test_the_light_stays_in_the_room_it_lit(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        _say(server, sid, "use candle")
        server.world._arrive(player, region_id, other, region_id)
        self.assertFalse(player.has_effect_tag("light"), "leaving the room puts it out")
        server.world._arrive(player, region_id, here, region_id)
        self.assertFalse(player.has_effect_tag("light"), "and coming back does not bring it back")

    def test_the_blue_candle_works_once_in_a_room_and_again_in_the_next_visit(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        _say(server, sid, "use candle")
        again = _say(server, sid, "use candle")
        self.assertIn("already burns", again)
        self.assertIsNotNone(player.inventory.get_item("item_t_candle"), "a candle is not used up")
        server.world._arrive(player, region_id, other, region_id)
        server.world._arrive(player, region_id, here, region_id)
        self.assertNotIn("already burns", _say(server, sid, "use candle"))
        self.assertTrue(player.has_effect_tag("light"))

    def test_a_candle_without_the_limit_works_as_often_as_it_is_used(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        player.inventory.get_item("item_t_candle").properties.pop("requires")
        _say(server, sid, "use candle")
        self.assertNotIn("already burns", _say(server, sid, "use candle"))

    def test_it_burns_a_bush_away_and_opens_the_way_beyond(self):
        server, player, room, region_id, here, other, sid = _setup(self, burnable=True)
        self.assertNotIn("north", room.exits)
        said = _say(server, sid, "use candle")
        self.assertIn("north", room.exits)
        self.assertIn("burns away", said)

    def test_it_is_the_difference_between_seeing_a_dark_room_and_not(self):
        server, player, room, region_id, here, other, sid = _setup(self, dark=True)
        self.assertIn("pitch dark", _say(server, sid, "look"))
        _say(server, sid, "use candle")
        self.assertIn("Exits", _say(server, sid, "look"))
        server.world._arrive(player, region_id, other, region_id)
        server.world._arrive(player, region_id, here, region_id)
        self.assertIn("pitch dark", _say(server, sid, "look"))


class TestTwoConditions(unittest.TestCase):
    def test_status_active_is_true_only_while_the_effect_is_on(self):
        server, player = _game(self)
        light = {"kind": "status_active", "tag": "candlelight"}
        self.assertFalse(conditions.evaluate(light, player).satisfied)
        player.apply_effect({"type": "status", "name": "Candlelight", "tags": ["candlelight"], "base_duration": 30}, 0.0)
        self.assertTrue(conditions.evaluate(light, player).satisfied)
        player.active_effects.clear()
        self.assertFalse(conditions.evaluate(light, player).satisfied)

    def test_max_health_at_least_reads_the_most_not_the_current(self):
        server, player = _game(self)
        player.max_health = 10
        player.health = 2
        self.assertTrue(conditions.evaluate({"kind": "max_health_at_least", "value": 10}, player).satisfied)
        self.assertFalse(conditions.evaluate({"kind": "max_health_at_least", "value": 11}, player).satisfied)


if __name__ == "__main__":
    unittest.main()
