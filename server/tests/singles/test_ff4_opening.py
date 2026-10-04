# tests/singles/test_ff4_opening.py
"""The FF4 slice opens in Ilmara: a journey through its first hour, pinned to the real set.

The player begins in the crystal chamber and watches the Red Fleet's soldiers do what they were sent to do, takes the
crystal, is carried to the airship, fights two waves of sky creatures (the second a short while after the first is won),
lands at the castle gate and is walked to the king by the chancellor, who takes the crystal and gives the package. Then
Kessa, a night in the castle, and dawn at the gate with her. It is all content: scenes, triggers, conversations and
rooms. These tests are about the shipped story, so they change when the story does (`test_story_fixture.py` lists them).
"""

import re
import unittest
from pathlib import Path

from engine.npcs import companions
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)
HOSTILE_SKY = ("storm_wyvern", "thunderhawk")


def _plain(text):
    return _MARKUP.sub("", text)


class _Journey:
    def __init__(self, case):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "ff4_slice"),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        case.addCleanup(self.server.shutdown)
        self.world = self.server.world
        self.sid = self.server.create_session(player_id="opening").session_id
        self.created = self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.told = []

    def say(self, command):
        events = self.server.execute_command(self.sid, command)
        text = _plain(NL.join(str(e["payload"]) for e in events if e["type"] == "text"))
        self.told.append(text)
        return text

    def wait(self, seconds):
        heard = []
        for _ in range(seconds):
            self.world.clock.advance(1.0)
            events = self.server.tick(self.sid) + self.server._flush_background_batch(self.sid)
            heard += [_plain(str(e["payload"])) for e in events if e["type"] == "text"]
        text = NL.join(heard)
        self.told.append(text)
        return text

    def where(self):
        return "%s:%s" % (self.player.current_region_id, self.player.current_room_id)

    def sky(self):
        return [n for n in self.world.npcs.values() if n.template_id in HOSTILE_SKY and n.is_alive]

    def clear_the_sky(self):
        for _ in range(60):
            alive = self.sky()
            if not alive:
                return
            self.say("attack " + alive[0].name)
            self.wait(3)

    def npc(self, template_id):
        return next((n for n in self.world.npcs.values() if n.template_id == template_id and n.is_alive), None)

    def to_the_crystal_taken(self):
        self.wait(60)
        self.say("take crystal")
        self.wait(40)

    def to_the_king(self):
        self.to_the_crystal_taken()
        self.clear_the_sky()
        self.wait(25)
        self.clear_the_sky()
        self.wait(45)


class TestIlmara(unittest.TestCase):
    def test_the_game_opens_in_the_crystal_chamber_with_what_the_fleet_came_for(self):
        game = _Journey(self)
        self.assertEqual("ilmara:crystal_chamber", game.where())
        self.assertIn("The Water Crystal", "".join(_plain(str(e["payload"])) for e in game.created if e["type"] == "text"))
        told = game.wait(60)
        self.assertIn("Why... why are you here?", told, "the elder notices the player first, afraid")
        self.assertLess(told.index("Why... why are you here?"), told.index("The doors of the crystal chamber burst inward"), "and only then do the doors burst")
        self.assertIn("The doors of the crystal chamber burst inward", told)
        self.assertIn("Red Fleet soldier attacks Ilmaran acolyte", told, "the fight is ordinary combat, told as combat is")
        self.assertNotIn("The elder of Ilmara attacks", told, "the elder takes no part in it")
        self.assertIn("take crystal", told, "the scene ends on what to do")
        self.assertIsNone(game.npc("ilmaran_acolyte"), "the acolytes are gone")
        self.assertIsNotNone(game.npc("elder_of_ilmara"), "the elder is not")
        self.assertEqual(3, len([n for n in game.world.npcs.values() if n.template_id == "red_fleet_raider" and n.current_region_id == "ilmara"]))

    def test_the_captain_starts_with_his_sword_and_armour_on(self):
        game = _Journey(self)
        worn = [item.name for item in game.player.equipment.values() if item is not None]
        self.assertIn("dark blade", worn)
        self.assertIn("dark armor", worn)

    def test_the_player_watches_and_cannot_act_until_it_is_over(self):
        game = _Journey(self)
        self.assertIn("not yours to interrupt", game.say("take crystal"))
        self.assertIsNone(game.player.inventory.get_item("item_ilmaran_crystal"))
        game.wait(60)
        self.assertNotIn("not yours to interrupt", game.say("look"))

    def test_the_elder_speaks_before_and_after_the_crystal_is_taken(self):
        game = _Journey(self)
        game.wait(60)
        self.assertIn("what is left of us", game.say("talk elder"))
        game.say("take crystal")
        game.wait(2)
        game.player.current_region_id, game.player.current_room_id = "ilmara", "crystal_chamber"


class TestTheSky(unittest.TestCase):
    def test_taking_the_crystal_carries_you_to_the_airship_where_the_soldiers_cannot_look_at_each_other(self):
        game = _Journey(self)
        game.wait(60)
        game.say("take crystal")
        told = game.wait(40)
        self.assertEqual("airship:deck", game.where())
        self.assertIn("did not even lift a hand", told)
        self.assertIn("It had to be done", told)
        self.assertEqual(2, len(game.sky()), "and then the first two shapes come out of the cloud")

    def test_the_second_wave_comes_a_short_while_after_the_first_is_won(self):
        game = _Journey(self)
        game.to_the_crystal_taken()
        game.clear_the_sky()
        self.assertEqual([], game.sky(), "the first wave is beaten")
        self.assertFalse(game.player.flags.get("air_second_wave"))
        game.wait(8)
        self.assertEqual([], game.sky(), "a short while is not that short")
        told = game.wait(12)
        self.assertTrue(game.player.flags.get("air_second_wave"))
        self.assertIn("something much larger than a wyvern", told)
        self.assertEqual(["storm_wyvern", "thunderhawk", "thunderhawk"], sorted(n.template_id for n in game.sky()))

    def test_only_the_second_wave_ends_the_flight(self):
        game = _Journey(self)
        game.to_the_crystal_taken()
        game.clear_the_sky()
        game.wait(25)
        self.assertEqual("airship:deck", game.where(), "one wave down is not the end")
        game.clear_the_sky()
        told = game.wait(45)
        self.assertEqual("varenholt:throne_room", game.where())
        self.assertIn("red banners of Varenholt", told)


class TestTheLanding(unittest.TestCase):
    def test_the_chancellor_meets_you_at_the_gate_and_walks_you_to_the_king(self):
        game = _Journey(self)
        game.to_the_crystal_taken()
        game.clear_the_sky()
        game.wait(25)
        game.clear_the_sky()
        told = game.wait(45)
        self.assertIn("CASTLE GATE", told)
        self.assertLess(told.index("CASTLE GATE"), told.index("THRONE ROOM"), "the gate first, then the hall")
        self.assertIn("His Majesty has been waiting", told)
        self.assertIn("The chancellor goes in ahead of you", told)
        self.assertEqual(("varenholt", "throne_room"), (game.npc("chancellor").current_region_id, game.npc("chancellor").current_room_id))

    def test_the_king_takes_the_crystal_and_the_orders_follow(self):
        game = _Journey(self)
        game.to_the_king()
        self.assertIsNotNone(game.player.inventory.get_item("item_ilmaran_crystal"))
        asked = game.say("talk king")
        self.assertIn("The Water Crystal, at last", asked)
        self.assertIsNone(game.player.inventory.get_item("item_ilmaran_crystal"), "the king has it now")
        game.say("reply 1")
        self.assertEqual("varenholt:courtyard", game.where())


class TestTheNightAndTheMorning(unittest.TestCase):
    def test_kessa_sends_you_to_rest_the_night_passes_and_she_rides_with_you(self):
        game = _Journey(self)
        game.to_the_king()
        game.say("talk king")
        game.say("reply 1")
        game.say("go east")
        self.assertEqual("varenholt:barracks", game.where())
        gate_early = game.say("talk kessa")
        self.assertIn("Did you speak to him", gate_early)
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "varenholt", "castle_gate"
        self.assertIn("Not alone, captain", game.say("go south"), "not yet")
        game.player.current_region_id, game.player.current_room_id = "varenholt", "barracks"
        game.say("go north")
        night = game.wait(30)
        self.assertIn("The night passes", night)
        self.assertTrue(game.player.flags.get("rested_at_castle"))
        self.assertEqual(6, game.server.time_manager.hour)
        game.player.current_region_id, game.player.current_room_id = "varenholt", "castle_gate"
        self.assertIn("Are you ready", game.say("talk kessa"))
        game.say("reply 1")
        self.assertEqual(["captain_kessa"], [n.template_id for n in companions.companions_of(game.world, game.player)])
        game.say("go south")
        self.assertEqual("road:castle_road", game.where())
        self.assertIn("Captain Kessa follows you", NL.join(game.told[-1:]))


if __name__ == "__main__":
    unittest.main()
