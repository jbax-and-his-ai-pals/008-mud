# tests/singles/test_money_cost_and_target_effects.py
"""An ability that costs money each cast (`gold_cost`: an arrow costs a rupee), and an `effects` block that runs for the one the
ability lands on (`for_target`: a hand that carries the player off), not for the caster."""

import unittest

from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.npcs import combat as npc_combat

from tests.singles.test_encounters import _game, _hostile_template, _rooms


def _foe(server, player):
    region_id, here, other = _rooms(server, player)
    foe, _status = server.world.spawn_npc(_hostile_template(server), region_id, here, "t_foe")
    foe.health = foe.max_health = 500
    return foe, region_id, here, other


class TestAMoneyCost(unittest.TestCase):
    def _arrow(self, case):
        SPELL_REGISTRY["t_arrow"] = Spell("t_arrow", "Arrow", "d", effects=[{"type": "damage", "value": 20, "damage_type": "physical"}],
                                          mana_cost=0, cooldown=0, target_type="enemy", gold_cost=2, cast_message="You loose an arrow.")
        case.addCleanup(SPELL_REGISTRY.pop, "t_arrow", None)

    def test_it_is_refused_without_the_money_and_costs_nothing_then(self):
        server, player = _game(self)
        self._arrow(self)
        foe, *_rest = _foe(server, player)
        player.runtime_state.magic.known_spells.add("t_arrow")
        player.runtime_state.gold = 1
        result = player.cast_spell(SPELL_REGISTRY["t_arrow"], foe, 100.0, server.world)
        self.assertFalse(result["success"])
        self.assertIn("Not enough", result["message"])
        self.assertEqual(1, player.runtime_state.gold)
        self.assertEqual(500, foe.health)

    def test_it_is_paid_on_every_cast(self):
        server, player = _game(self)
        self._arrow(self)
        foe, *_rest = _foe(server, player)
        player.runtime_state.magic.known_spells.add("t_arrow")
        player.runtime_state.gold = 5
        self.assertTrue(player.cast_spell(SPELL_REGISTRY["t_arrow"], foe, 100.0, server.world)["success"])
        self.assertEqual(3, player.runtime_state.gold)
        self.assertLess(foe.health, 500)
        self.assertTrue(player.cast_spell(SPELL_REGISTRY["t_arrow"], foe, 200.0, server.world)["success"])
        self.assertEqual(1, player.runtime_state.gold)

    def test_the_cost_is_told_where_costs_are_told(self):
        from engine.contracts.equipment import ability_cost_text

        server, player = _game(self)
        self._arrow(self)
        self.assertIn("2", ability_cost_text(server.world, SPELL_REGISTRY["t_arrow"]))


class TestAnEffectForTheTarget(unittest.TestCase):
    def test_a_creatures_block_runs_for_the_player_it_lands_on(self):
        server, player = _game(self)
        foe, region_id, here, other = _foe(server, player)
        SPELL_REGISTRY["t_grab"] = Spell("t_grab", "Grab", "d", effects=[
            {"type": "effects", "for_target": True, "effects": {"teleport": {"region": region_id, "room": other}}}],
            mana_cost=0, cooldown=0, target_type="enemy", cast_message="{caster_name} reaches for you.")
        self.addCleanup(SPELL_REGISTRY.pop, "t_grab", None)
        npc_combat.cast_spell(foe, SPELL_REGISTRY["t_grab"], player, 100.0)
        self.assertEqual((region_id, other), (player.current_region_id, player.current_room_id), "the player was carried off")
        self.assertEqual((region_id, here), (foe.current_region_id, foe.current_room_id), "and the creature stayed")

    def test_without_the_flag_the_block_runs_for_the_caster(self):
        server, player = _game(self)
        foe, region_id, here, other = _foe(server, player)
        SPELL_REGISTRY["t_self"] = Spell("t_self", "Self", "d", effects=[
            {"type": "effects", "effects": {"teleport": {"region": region_id, "room": other}}}],
            mana_cost=0, cooldown=0, target_type="enemy", cast_message="{caster_name} gestures.")
        self.addCleanup(SPELL_REGISTRY.pop, "t_self", None)
        npc_combat.cast_spell(foe, SPELL_REGISTRY["t_self"], player, 100.0)
        self.assertEqual((region_id, here), (player.current_region_id, player.current_room_id), "the player stayed where they were")


if __name__ == "__main__":
    unittest.main()
