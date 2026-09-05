# tests/singles/test_player_core_full.py
"""Coverage for engine/player/core.py: __init__'s missing-world guard,
get_effective_stat's set-bonus loop-back past a non-stat_mod bonus,
apply_class_template's no-world guard and each optional-field skip
(no "name", no "stats", magic disabled, an inventory ref missing item_id,
magic disabled at the spells step, and spells already present), update()'s
dead-player guard and each environment-check skip (no location, no room,
no region for the safe-zone check), update_quest/get_quest_progress
(including the no-magic-quests-aspect guard), and restore_mana's dead/no-
magic guard."""

import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.player.core import Player


class TestInit(unittest.TestCase):
    def test_missing_world_is_rejected(self):
        with self.assertRaises(TypeError):
            Player(name="Test")


class TestGetEffectiveStat(GameTestBase):
    def test_loops_past_non_stat_mod_bonus(self):
        with patch.object(
            self.player.set_manager, "get_active_bonuses",
            return_value=[{"type": "something_else"}, {"type": "stat_mod", "modifiers": {"strength": 5}}],
        ):
            result = self.player.get_effective_stat("strength")
        base = self.player.stats.get("strength", 0)
        self.assertEqual(result, base + 5)


class TestApplyClassTemplate(GameTestBase):
    def test_no_world_is_a_noop(self):
        original_world = self.player.world
        self.player.world = None
        try:
            self.player.apply_class_template({"name": "Warrior"})
        finally:
            self.player.world = original_world
        self.assertNotEqual(self.player.runtime_state.progression.player_class, "Warrior")

    def test_class_data_without_name_skips_class_name_update(self):
        original_class = self.player.runtime_state.progression.player_class
        self.player.apply_class_template({})
        self.assertEqual(self.player.runtime_state.progression.player_class, original_class)

    def test_class_data_without_stats_skips_stat_update(self):
        original_max_health = self.player.max_health
        self.player.apply_class_template({"name": "Bard"})
        self.assertEqual(self.player.max_health, original_max_health)

    def test_magic_disabled_skips_mana_recalculation_within_stats(self):
        original_magic = self.player.runtime_state.magic
        self.player.runtime_state.magic = None
        try:
            self.player.apply_class_template({"stats": {"intelligence": 20}})
        finally:
            self.player.runtime_state.magic = original_magic

    def test_inventory_ref_missing_item_id_is_skipped(self):
        self.player.apply_class_template({"inventory": [{"quantity": 1}, {"item_id": "item_iron_sword"}]})
        self.assertIsNotNone(self.player.inventory.find_item_by_name("Iron Sword") or self.player.inventory.find_item_by_name("sword"))

    def test_magic_disabled_skips_spell_assignment(self):
        original_magic = self.player.runtime_state.magic
        self.player.runtime_state.magic = None
        try:
            self.player.apply_class_template({"spells": ["magic_missile"]})
        finally:
            self.player.runtime_state.magic = original_magic

    def test_explicit_spells_are_kept_without_fallback(self):
        self.player.apply_class_template({"spells": ["magic_missile"]})
        self.assertEqual(self.player.runtime_state.magic.known_spells, {"magic_missile"})


class TestUpdate(GameTestBase):
    def test_dead_player_returns_no_messages(self):
        self.player.is_alive = False
        self.assertEqual(self.player.update(0.0, 1.0), [])

    def test_no_location_skips_environment_logic(self):
        self.player.current_region_id = None
        self.player.current_room_id = None
        result = self.player.update(0.0, 1.0)  # must not raise
        self.assertIsInstance(result, list)

    def test_missing_room_skips_hazard_check(self):
        self.player.current_region_id = "totally_bogus_region_xyz"
        self.player.current_room_id = "totally_bogus_room_xyz"
        result = self.player.update(0.0, 1.0)  # must not raise
        self.assertIsInstance(result, list)

    def test_no_current_region_skips_safe_zone_regen(self):
        self.player.current_region_id = None
        result = self.player.update(0.0, 1.0)
        self.assertIsInstance(result, list)


class TestQuestHelpers(GameTestBase):
    def test_update_quest_sets_active_entry(self):
        self.player.update_quest("q1", {"stage": 1})
        self.assertEqual(self.player.runtime_state.quests.active["q1"], {"stage": 1})

    def test_update_quest_with_no_quests_aspect_is_a_noop(self):
        original_quests = self.player.runtime_state.quests
        self.player.runtime_state.quests = None
        try:
            self.player.update_quest("q1", {"stage": 1})  # must not raise
        finally:
            self.player.runtime_state.quests = original_quests

    def test_get_quest_progress_returns_none_without_quests_aspect(self):
        original_quests = self.player.runtime_state.quests
        self.player.runtime_state.quests = None
        try:
            self.assertIsNone(self.player.get_quest_progress("q1"))
        finally:
            self.player.runtime_state.quests = original_quests

    def test_get_quest_progress_returns_stored_value(self):
        self.player.update_quest("q1", {"stage": 2})
        self.assertEqual(self.player.get_quest_progress("q1"), {"stage": 2})


class TestRestoreMana(GameTestBase):
    def test_dead_player_restores_nothing(self):
        self.player.is_alive = False
        self.assertEqual(self.player.restore_mana(10), 0)

    def test_magic_disabled_restores_nothing(self):
        original_magic = self.player.runtime_state.magic
        self.player.runtime_state.magic = None
        try:
            self.assertEqual(self.player.restore_mana(10), 0)
        finally:
            self.player.runtime_state.magic = original_magic


if __name__ == "__main__":
    unittest.main()
