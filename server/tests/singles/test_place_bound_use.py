# tests/singles/test_place_bound_use.py
"""A spell or an item that works only somewhere (`requires`), a spell that runs a conversation's effects, and a warp to the place
the player's own region names."""

import re
import unittest

from engine import conditions
from engine.items.consumable import Consumable
from engine.magic.spell import Spell
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _game(case):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    player = server.get_player_for_session(sid)
    return server, player


def _rooms(world, player):
    """Two rooms of the player's own region: where they stand, and another."""
    region = world.get_region(player.current_region_id)
    other = next(room_id for room_id in region.rooms if room_id != player.current_room_id)
    return region, player.current_room_id, other


class TestTheConditions(unittest.TestCase):
    def test_in_room_is_true_only_in_that_room(self):
        server, player = _game(self)
        _region, here, other = _rooms(server.world, player)
        self.assertTrue(conditions.evaluate({"kind": "in_room", "region_id": player.current_region_id, "room_id": here}, player).satisfied)
        self.assertFalse(conditions.evaluate({"kind": "in_room", "region_id": player.current_region_id, "room_id": other}, player).satisfied)

    def test_room_is_reads_the_rooms_own_atmosphere(self):
        server, player = _game(self)
        region, here, _other = _rooms(server.world, player)
        room = region.get_room(here)
        room.properties["outdoors"] = False
        room.properties["dark"] = False
        self.assertFalse(conditions.evaluate({"kind": "room_is", "property": "dark"}, player).satisfied)
        room.properties["dark"] = True
        self.assertTrue(conditions.evaluate({"kind": "room_is", "property": "dark"}, player).satisfied)
        self.assertFalse(conditions.evaluate({"not": {"kind": "room_is", "property": "dark"}}, player).satisfied)


class TestASpellThatWorksOnlySomewhere(unittest.TestCase):
    def _cast(self, server, player, spell):
        player.runtime_state.magic.known_spells.append(spell.spell_id) if isinstance(player.runtime_state.magic.known_spells, list) \
            else player.runtime_state.magic.known_spells.add(spell.spell_id)
        player.runtime_state.magic.mana = player.runtime_state.magic.max_mana = 50
        return player.cast_spell(spell, player, float(server.world.clock.now()) + 1000, server.world)

    def test_a_spell_will_not_work_where_its_requirement_fails_and_costs_nothing(self):
        server, player = _game(self)
        spell = Spell("t_gate", "Gate", "d", effects=[{"type": "effects", "effects": {"message": "It works."}}], mana_cost=5,
                      target_type="self", requires={"kind": "room_is", "property": "dark"}, requires_message="Only in the dark.")
        result = self._cast(server, player, spell)
        self.assertFalse(result["success"])
        self.assertIn("Only in the dark.", result["message"])
        self.assertEqual(50, player.runtime_state.magic.mana)

    def test_a_spell_works_where_it_is_met_and_runs_the_effects_it_carries(self):
        server, player = _game(self)
        region, here, _other = _rooms(server.world, player)
        region.get_room(here).properties["dark"] = True
        spell = Spell("t_gate2", "Gate", "d", effects=[{"type": "effects", "effects": {"set_flag": "gate_spell_cast"}}], mana_cost=5,
                      target_type="self", requires={"kind": "room_is", "property": "dark"})
        result = self._cast(server, player, spell)
        self.assertTrue(result["success"], result)
        self.assertIs(True, player.flags.get("gate_spell_cast"))

    def test_a_warp_to_the_place_the_region_names_takes_the_player_there(self):
        server, player = _game(self)
        region, _here, other = _rooms(server.world, player)
        region.properties["entrance"] = other
        spell = Spell("t_out", "Out", "d", effects=[{"type": "effects", "effects": {"teleport": {"to": "entrance"}}}],
                      mana_cost=1, target_type="self")
        result = self._cast(server, player, spell)
        self.assertTrue(result["success"], result)
        self.assertEqual(other, player.current_room_id)

    def test_with_no_place_named_the_warp_does_nothing(self):
        server, player = _game(self)
        region, here, _other = _rooms(server.world, player)
        region.properties.pop("entrance", None)
        spell = Spell("t_out2", "Out", "d", effects=[{"type": "effects", "effects": {"teleport": {"to": "entrance"}}}],
                      mana_cost=1, target_type="self")
        self._cast(server, player, spell)
        self.assertEqual(here, player.current_room_id)


class TestAnItemThatWorksOnlySomewhere(unittest.TestCase):
    def _item(self, requires):
        return Consumable(obj_id="item_charm", name="charm", uses=1, effect_type="effects",
                          effects={"set_flag": "charm_used"}, requires=requires, requires_message="Not here.")

    def test_it_is_kept_and_says_why_where_it_does_not_work(self):
        _server, player = _game(self)
        item = self._item({"kind": "in_room", "region_id": "nowhere", "room_id": "nowhere"})
        message = item.use(player)
        self.assertEqual("Not here.", message)
        self.assertEqual(1, item.get_property("uses"))
        self.assertIsNone(player.flags.get("charm_used"))

    def test_it_works_and_is_used_up_where_it_does(self):
        server, player = _game(self)
        _region, here, _other = _rooms(server.world, player)
        item = self._item({"kind": "in_room", "region_id": player.current_region_id, "room_id": here})
        item.use(player)
        self.assertIs(True, player.flags.get("charm_used"))


class TestTheValidator(unittest.TestCase):
    def test_a_bad_requirement_or_effect_block_is_refused(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from engine.server.content_set import load_content_set

        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        shutil.copytree(STORY_FIXTURE, root / "set")
        magic_dir = root / "set" / "data" / "magic"
        bad = {
            "bad_gate": {"name": "Bad", "description": "d", "mana_cost": 1, "cooldown": 1, "target_type": "self", "level_required": 1,
                         "requires": {"kind": "not_a_kind"}, "effects": [{"type": "effects", "effects": {"set_flag": 5}}]},
        }
        (magic_dir / "zz_bad.json").write_text(json.dumps(bad), encoding="utf-8")
        _definition, issues = load_content_set(root / "set")
        text = "\n".join(issue.message for issue in issues if issue.severity == "error")
        self.assertIn("not_a_kind", text)
        self.assertIn("set_flag", text)


if __name__ == "__main__":
    unittest.main()
