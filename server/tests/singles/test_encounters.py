# tests/singles/test_encounters.py
"""Encounter zones (`data/encounters/*.json`): somewhere walking is dangerous."""

import json
import random
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server.content_set import load_content_set
from engine.server.headless_server import HeadlessServer
from engine.world.encounters import count_range, monster_entries

from tests.fixtures import STORY_FIXTURE


def _game(case):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    player = server.get_player_for_session(sid)
    for npc in list(server.world.npcs.values()):   # an empty region: nothing already there to stop a zone
        server.world.remove_npcs(npc.obj_id)
    return server, player


def _hostile_template(server):
    for template_id, template in server.world.npc_templates.items():
        if template.get("faction") == "hostile" and template.get("attack_power") is not None:
            return template_id
    raise AssertionError("no hostile template in the fixture")


def _rooms(server, player):
    """Two rooms of a region that is not a safe place, with the player standing in the first."""
    for region_id, region in server.world.regions.items():
        open_rooms = [room_id for room_id in region.rooms if not server.world.is_location_safe(region_id, room_id)]
        if len(open_rooms) >= 2:
            player.current_region_id, player.current_room_id = region_id, open_rooms[0]
            return region_id, open_rooms[0], open_rooms[1]
    raise AssertionError("the fixture has no region that is not a safe place")


class TestTheDefinition(unittest.TestCase):
    def test_monsters_read_as_ids_with_weights(self):
        self.assertEqual([("a", 1.0), ("b", 3.0)], monster_entries({"monsters": ["a", {"npc": "b", "weight": 3}]}))

    def test_count_reads_a_number_or_a_range(self):
        self.assertEqual((1, 1), count_range({}))
        self.assertEqual((2, 2), count_range({"count": 2}))
        self.assertEqual((1, 3), count_range({"count": [1, 3]}))


class TestAZone(unittest.TestCase):
    def _zone(self, server, player, **extra):
        region_id, here, other = _rooms(server, player)
        server.world.encounters.add("probe", {"region": region_id, "monsters": [_hostile_template(server)], "chance": 1, **extra})
        return region_id, here, other

    def _walk_into(self, server, player, region_id, room_id):
        return server.world._arrive(player, region_id, room_id, player.current_region_id)

    def test_arriving_in_a_zone_with_chance_one_brings_a_creature(self):
        server, player = _game(self)
        region_id, _here, other = self._zone(server, player)
        text = self._walk_into(server, player, region_id, other)
        came = [n for n in server.world.npcs.values() if n.properties.get("encounter") == "probe" and n.is_alive]
        self.assertEqual(1, len(came))
        self.assertEqual(other, came[0].current_room_id)
        self.assertIn("appears", text)

    def test_chance_zero_brings_nothing(self):
        server, player = _game(self)
        region_id, _here, other = self._zone(server, player, chance=0)
        self._walk_into(server, player, region_id, other)
        self.assertFalse([n for n in server.world.npcs.values() if n.properties.get("encounter")])

    def test_a_safe_room_is_never_a_zone(self):
        server, player = _game(self)
        region_id, _here, other = self._zone(server, player)
        server.world.get_region(region_id).get_room(other).properties["safe_zone"] = True
        self._walk_into(server, player, region_id, other)
        self.assertFalse([n for n in server.world.npcs.values() if n.properties.get("encounter")])

    def test_only_the_named_rooms_are_covered(self):
        server, player = _game(self)
        region_id, here, other = _rooms(server, player)
        server.world.encounters.add("probe", {"region": region_id, "rooms": [here], "monsters": [_hostile_template(server)], "chance": 1})
        self.assertEqual(["probe"], server.world.encounters.zones_for(region_id, here))
        self.assertEqual([], server.world.encounters.zones_for(region_id, other))

    def test_it_is_gone_when_the_player_walks_on_and_does_not_come_back_when_killed(self):
        server, player = _game(self)
        region_id, here, other = self._zone(server, player)
        self._walk_into(server, player, region_id, other)
        came = [n for n in server.world.npcs.values() if n.properties.get("encounter")][0]
        self._walk_into(server, player, region_id, here)
        self.assertNotIn(came.obj_id, server.world.npcs, "it was only passing through")
        server.world.encounters.zones["probe"]["chance"] = 1
        self._walk_into(server, player, region_id, other)
        second = [n for n in server.world.npcs.values() if n.properties.get("encounter") and n.is_alive][0]
        second.take_damage(10 ** 6, "physical")
        self.assertFalse(second.is_alive)
        self.assertEqual(-1, second.properties["respawn_cooldown"], "and a killed one does not return")

    def test_a_repel_keeps_weaker_creatures_away(self):
        server, player = _game(self)
        region_id, _here, other = self._zone(server, player)
        player.apply_effect({"type": "status", "name": "Repel", "tags": ["repel"], "base_duration": 60}, 0.0)
        for template_id in list(server.world.npc_templates):
            server.world.npc_templates[template_id]["attack_power"] = 0
        self._walk_into(server, player, region_id, other)
        self.assertFalse([n for n in server.world.npcs.values() if n.properties.get("encounter")], "everything is weaker than the hero")

    def test_a_cooldown_spaces_encounters_out(self):
        server, player = _game(self)
        region_id, here, other = self._zone(server, player, cooldown=60)
        self._walk_into(server, player, region_id, other)
        self.assertTrue([n for n in server.world.npcs.values() if n.properties.get("encounter")])
        self._walk_into(server, player, region_id, here)
        self._walk_into(server, player, region_id, other)
        living = [n for n in server.world.npcs.values() if n.properties.get("encounter") and n.is_alive]
        self.assertEqual(0, len(living), "the second arrival is inside the cooldown")


class TestTheValidator(unittest.TestCase):
    def _errors(self, zones):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        shutil.copytree(STORY_FIXTURE, root / "set")
        directory = root / "set" / "data" / "encounters"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "probe.json").write_text(json.dumps(zones), encoding="utf-8")
        _definition, issues = load_content_set(root / "set")
        return "\n".join(issue.message for issue in issues if issue.severity == "error")

    def test_a_good_zone_is_accepted(self):
        server_templates = None
        probe_server, _player = _game(self)
        template = _hostile_template(probe_server)
        region = next(iter(probe_server.world.regions))
        self.assertEqual("", self._errors({"z": {"region": region, "monsters": [template], "chance": 0.2}}))

    def test_each_mistake_is_named(self):
        text = self._errors({
            "no_region": {"monsters": ["x"], "chance": 0.1},
            "bad_region": {"region": "nowhere_land", "monsters": ["x"], "chance": 0.1},
            "no_monsters": {"region": "ashmere", "monsters": [], "chance": 0.1},
            "no_chance": {"region": "ashmere", "monsters": ["captain_kessa"]},
            "bad_chance": {"region": "ashmere", "monsters": ["captain_kessa"], "chance": 2},
            "unknown_key": {"region": "ashmere", "monsters": ["captain_kessa"], "chance": 0.1, "speed": 3},
            "bad_message": {"region": "ashmere", "monsters": ["captain_kessa"], "chance": 0.1, "message": "{creature}"},
        })
        for expected in ("no_region", "bad_region", "no_monsters", "no_chance", "bad_chance", "unknown_key", "bad_message"):
            self.assertIn(expected, text)


if __name__ == "__main__":
    unittest.main()
