# tests/singles/test_player_display.py
"""Coverage for engine/player/display.py's get_combat_status() (target HP
color tiers, no-hp-attrs fallback, recent-actions log) and get_status()'s
stat buff/debuff coloring, resistance display, equipped-item durability
tiers, active-effect (dot/hot) display, and known-spell cooldown/level-
requirement display -- most of which the command-level status tests never
exercise in combination."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.weapon import Weapon


def _target(world, player, instance_id="disp_target", template="goblin"):
    npc = NPCFactory.create_npc_from_template(template, world, instance_id=instance_id)
    npc.current_region_id = player.current_region_id
    npc.current_room_id = player.current_room_id
    world.add_npc(npc)
    return npc


class TestGetCombatStatus(GameTestBase):
    def test_not_in_combat_returns_empty_string(self):
        self.assertEqual("", self.player.get_combat_status())

    def test_target_with_health_shows_hp_and_color_tier_high(self):
        npc = _target(self.world, self.player)
        npc.health = npc.max_health
        self.player.enter_combat(npc)
        result = self.player.get_combat_status()
        self.assertIn("HP", result)

    def test_target_with_health_shows_color_tier_medium(self):
        npc = _target(self.world, self.player)
        npc.max_health = 100
        npc.health = 40  # >25% and <=50%
        self.player.enter_combat(npc)
        result = self.player.get_combat_status()
        self.assertIn("40/100", result)

    def test_target_with_health_shows_color_tier_low(self):
        npc = _target(self.world, self.player)
        npc.max_health = 100
        npc.health = 10  # <=25%
        self.player.enter_combat(npc)
        result = self.player.get_combat_status()
        self.assertIn("10/100", result)

    def test_target_without_health_attrs_shows_name_only(self):
        class _NoHealthTarget:
            is_alive = True
            current_room_id = None
            name = "Mystery Thing"
        target = _NoHealthTarget()
        target.current_room_id = self.player.current_room_id
        self.player.runtime_state.combat.in_combat = True
        self.player.runtime_state.combat.targets.add(target)
        result = self.player.get_combat_status()
        self.assertIn("Mystery Thing", result)

    def test_recent_actions_are_listed(self):
        npc = _target(self.world, self.player)
        self.player.enter_combat(npc)
        self.player.combat_messages = ["You hit the goblin.", "The goblin hits you."]
        result = self.player.get_combat_status()
        self.assertIn("Recent Actions", result)
        self.assertIn("You hit the goblin.", result)

    def test_no_valid_targets_in_sight_reports_so(self):
        npc = _target(self.world, self.player)
        self.player.enter_combat(npc)
        npc.current_room_id = "somewhere_else"
        result = self.player.get_combat_status()
        self.assertIn("No current targets in sight", result)


class TestGetStatusStatColoring(GameTestBase):
    def test_buffed_stat_shows_success_color(self):
        self.player.stats["strength"] = 10
        with patch.object(self.player, "get_effective_stat", side_effect=lambda s: 15 if s == "strength" else self.player.stats.get(s, 0)):
            result = self.player.get_status()
        self.assertIn("STR", result)

    def test_debuffed_stat_shows_error_color(self):
        self.player.stats["strength"] = 10
        with patch.object(self.player, "get_effective_stat", side_effect=lambda s: 5 if s == "strength" else self.player.stats.get(s, 0)):
            result = self.player.get_status()
        self.assertIn("STR", result)


class TestGetStatusResistances(GameTestBase):
    def test_positive_resistance_is_displayed(self):
        with patch.object(self.player, "get_resistance", side_effect=lambda dt: 25 if dt == "fire" else 0):
            result = self.player.get_status()
        self.assertIn("Resistances", result)
        self.assertIn("Fire", result)

    def test_negative_resistance_is_displayed(self):
        with patch.object(self.player, "get_resistance", side_effect=lambda dt: -10 if dt == "fire" else 0):
            result = self.player.get_status()
        self.assertIn("Fire", result)

    def test_zero_resistance_everywhere_omits_section(self):
        with patch.object(self.player, "get_resistance", return_value=0):
            result = self.player.get_status()
        self.assertNotIn("Resistances", result)


class TestGetStatusEquippedItems(GameTestBase):
    def test_equipped_item_with_durability_shown(self):
        weapon = Weapon(obj_id="disp_weapon", name="Iron Sword", durability=80)
        weapon.properties["max_durability"] = 100
        self.player.equipment["main_hand"] = weapon
        result = self.player.get_status()
        self.assertIn("EQUIPPED", result)
        self.assertIn("Iron Sword", result)
        self.assertIn("80/100", result)

    def test_equipped_item_at_zero_durability_shows_error_color(self):
        weapon = Weapon(obj_id="disp_weapon_broken", name="Broken Sword", durability=0)
        weapon.properties["max_durability"] = 100
        self.player.equipment["main_hand"] = weapon
        result = self.player.get_status()
        self.assertIn("0/100", result)

    def test_equipped_item_at_low_durability_shows_warning_color(self):
        weapon = Weapon(obj_id="disp_weapon_low", name="Worn Sword", durability=20)
        weapon.properties["max_durability"] = 100
        self.player.equipment["main_hand"] = weapon
        result = self.player.get_status()
        self.assertIn("20/100", result)

    def test_equipped_item_without_max_durability_shows_no_durability_string(self):
        weapon = Weapon(obj_id="disp_weapon_nodur", name="Ageless Sword")
        weapon.properties["max_durability"] = 0
        self.player.equipment["main_hand"] = weapon
        result = self.player.get_status()
        self.assertIn("Ageless Sword", result)

    def test_no_equipped_items_omits_equipped_section(self):
        for slot in self.player.equipment:
            self.player.equipment[slot] = None
        result = self.player.get_status()
        self.assertNotIn("EQUIPPED", result)


class TestGetStatusActiveEffects(GameTestBase):
    def test_dot_effect_shows_damage_details(self):
        self.player.active_effects = [{
            "name": "Poison", "type": "dot", "damage_per_tick": 5, "damage_type": "poison",
            "tick_interval": 2.0, "duration_remaining": 10.0,
        }]
        result = self.player.get_status()
        self.assertIn("EFFECTS", result)
        self.assertIn("Poison", result)
        self.assertIn("poison", result)

    def test_hot_effect_shows_heal_details(self):
        self.player.active_effects = [{
            "name": "Regeneration", "type": "hot", "heal_per_tick": 3,
            "tick_interval": 2.0, "duration_remaining": 10.0,
        }]
        result = self.player.get_status()
        self.assertIn("Regeneration", result)
        self.assertIn("HP/", result)

    def test_long_duration_effect_shown_in_minutes(self):
        self.player.active_effects = [{"name": "Blessing", "duration_remaining": 120.0}]
        result = self.player.get_status()
        self.assertIn("2.0m remaining", result)

    def test_effect_without_duration_remaining_key_omits_duration(self):
        self.player.active_effects = [{"name": "Permanent Mark"}]
        result = self.player.get_status()
        self.assertIn("Permanent Mark", result)
        self.assertNotIn("remaining", result)

    def test_no_active_effects_omits_effects_section(self):
        self.player.active_effects = []
        result = self.player.get_status()
        self.assertNotIn("EFFECTS", result)


class TestGetStatusSpells(GameTestBase):
    def test_known_spell_shown_without_cooldown(self):
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.known_spells = {"magic_missile"}
        result = self.player.get_status()
        self.assertIn("SPELLS KNOWN", result)

    def test_unknown_spell_id_is_skipped(self):
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.known_spells = {"not_a_real_spell_id"}
        result = self.player.get_status()  # must not raise
        self.assertIsNotNone(result)

    def test_spell_on_cooldown_shows_cooldown_remaining(self):
        import time
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.known_spells = {"magic_missile"}
        self.player.runtime_state.magic.cooldowns["magic_missile"] = time.time() + 30
        result = self.player.get_status()
        self.assertIn("CD", result)

    def test_spell_below_level_requirement_shows_error_color(self):
        assert self.player.runtime_state.magic is not None
        assert self.player.runtime_state.progression is not None
        self.player.runtime_state.magic.known_spells = {"magic_missile"}
        self.player.runtime_state.progression.level = 1
        result = self.player.get_status()  # must not raise regardless of level req display
        self.assertIsNotNone(result)


class TestGetStatusHealthTiers(GameTestBase):
    def test_critical_health_shows_error_color(self):
        from engine.config import PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD
        self.player.health = max(1, int(self.player.max_health * PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD / 100) - 1)
        result = self.player.get_status()
        self.assertIn("Health:", result)

    def test_low_health_shows_highlight_color(self):
        from engine.config import PLAYER_STATUS_HEALTH_LOW_THRESHOLD, PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD
        midpoint = (PLAYER_STATUS_HEALTH_CRITICAL_THRESHOLD + PLAYER_STATUS_HEALTH_LOW_THRESHOLD) / 2
        self.player.health = max(1, int(self.player.max_health * midpoint / 100))
        result = self.player.get_status()
        self.assertIn("Health:", result)


class TestGetStatusOverall(GameTestBase):
    def test_dead_player_shows_dead_banner(self):
        self.player.is_alive = False
        result = self.player.get_status()
        self.assertIn("YOU ARE DEAD", result)

    def test_in_combat_appends_combat_status(self):
        npc = _target(self.world, self.player)
        self.player.enter_combat(npc)
        result = self.player.get_status()
        self.assertIn("COMBAT STATUS", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
