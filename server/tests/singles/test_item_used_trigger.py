# tests/singles/test_item_used_trigger.py
"""The trigger event `item_used`: using an item does what it does, and the place it is used in may add something (a pipe played at
the foot of a hill opens a way)."""

import re
import unittest

from engine.items.consumable import Consumable

from tests.singles.test_encounters import _game, _rooms

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _setup(case, **on):
    server, player = _game(case)
    region_id, here, other = _rooms(server, player)
    room = server.world.get_region(region_id).get_room(here)
    room.exits.pop("north", None)
    room.properties["hidden_exits"] = {"north": other}
    pipe = Consumable(obj_id="item_t_pipe", name="pipe", uses=1, effect_type="effects", reusable=True, weight=0,
                      effects={"message": "You play a low, sweet tune."})
    player.inventory.add_item(pipe)
    trigger = {"on": {"event": "item_used", "item": "item_t_pipe", **on},
               "once": False, "effects": {"reveal_exit": {"room": "%s:%s" % (region_id, here), "direction": "north"}, "message": "Somewhere a way opens."}}
    server.world.trigger_runner.triggers["t_pipe"] = trigger
    return server, player, room, region_id, here, other, next(iter(server.sessions))


def _say(server, sid, text):
    return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in server.execute_command(sid, text) if e.get("type") == "text"))


class TestItemUsed(unittest.TestCase):
    def test_using_the_item_where_the_trigger_names_does_what_the_place_does(self):
        server, player, room, region_id, here, other, sid = _setup(self, region="x", room="y")
        said = _say(server, sid, "use pipe")
        self.assertIn("low, sweet tune", said, "the item still does what it does")
        self.assertNotIn("north", room.exits, "elsewhere the place does nothing")

    def test_in_that_place_the_item_opens_the_way(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        server.world.trigger_runner.triggers["t_pipe"]["on"].update(region=region_id, room=here)
        said = _say(server, sid, "use pipe")
        self.assertIn("low, sweet tune", said)
        self.assertIn("Somewhere a way opens", said)
        self.assertIn("north", room.exits)

    def test_a_trigger_for_any_place_fires_wherever_the_item_is_used(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        _say(server, sid, "use pipe")
        self.assertIn("north", room.exits)

    def test_a_different_item_does_not_fire_it(self):
        server, player, room, region_id, here, other, sid = _setup(self)
        server.world.trigger_runner.triggers["t_pipe"]["on"]["item"] = "item_other"
        _say(server, sid, "use pipe")
        self.assertNotIn("north", room.exits)


if __name__ == "__main__":
    unittest.main()
