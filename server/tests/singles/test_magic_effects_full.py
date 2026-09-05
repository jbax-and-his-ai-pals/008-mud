# tests/singles/test_magic_effects_full.py
"""Coverage for engine/magic/effects.py's apply_spell_effect: the Room
environmental-interaction loop and its no-reaction dissipate message, the
unlock/lock branch's non-Container skip and non-unlock/lock effect
loop-back, the damage branch's no-take_damage skip and format-exception
fallback, apply_dot's no-apply_effect skip / tags-copy / failed-apply
skip, heal's no-heal skip and format-exception fallback, cleanse's no-
remove_effects_by_tag skip and nothing-to-cleanse message, remove_curse's
cursed-item/no-equipment-skip/no-cursed-equipment-found branches, life_
tap's no-take_damage skip and zero-damage message, apply_effect's no-
apply_effect skip / empty-effect_data continue / duration-inference
branches / failed-apply skip, and summon's non-Player-caster / missing-
template-or-world / factory-failure skips -- plus a multi-effect spell to
exercise each branch's loop-back to the next effect."""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.effects import apply_spell_effect
from engine.items.item import Item
from engine.items.container import Container
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room


def _spell(effects, spell_id="test_spell", target_type="enemy"):
    return Spell(spell_id=spell_id, name="Test Spell", description="A test spell.",
                 effects=effects, target_type=target_type)


class _BareTarget:
    """A target with no combat/effect methods at all -- unlike Item, which
    inherits take_damage/apply_effect/heal from GameObject, this genuinely
    lacks them, so hasattr(target, ...) checks in apply_spell_effect
    correctly evaluate False."""
    name = "Bare Target"


class TestRoomEnvironmentalInteraction(GameTestBase):
    def test_no_reaction_dissipates_with_no_effect_message(self):
        room = Room("Test Room", "A plain room.", obj_id="effects_test_room")
        spell = _spell([{"type": "damage", "value": 10, "damage_type": "fire"}])
        value, msg = apply_spell_effect(self.player, room, spell, self.player)
        self.assertEqual(value, 0)
        self.assertIn("dissipates", msg)

    def test_multiple_effect_defs_without_damage_type_are_skipped(self):
        room = Room("Test Room", "A plain room.", obj_id="effects_test_room2")
        spell = _spell([{"type": "damage", "value": 10}, {"type": "heal", "value": 5}])
        value, msg = apply_spell_effect(self.player, room, spell, self.player)
        self.assertEqual(value, 0)
        self.assertIn("dissipates", msg)

    def test_reaction_produces_a_message(self):
        room = Room("Icy Room", "A frosty room.", obj_id="effects_test_room3")
        room.properties["env_interactions"] = {"fire": {"type": "clear_exit_req", "direction": "north", "message": "The ice melts."}}
        room.properties["exit_requirements"] = {"north": "locked"}
        spell = _spell([{"type": "damage", "value": 10, "damage_type": "fire"}])
        value, msg = apply_spell_effect(self.player, room, spell, self.player)
        self.assertEqual(value, 1)
        self.assertIn("melts", msg)


class TestUnlockLock(GameTestBase):
    def test_non_container_target_falls_through_to_main_loop(self):
        item = Item(name="Plain Item")
        spell = _spell([{"type": "unlock", "value": 0}])
        value, msg = apply_spell_effect(self.player, item, spell, self.player)
        # Falls through to the main damage/heal/etc loop; "unlock" isn't a
        # recognized eff_type there, so nothing happens and no effect fires.
        self.assertEqual(value, 0)

    def test_non_unlock_lock_effect_in_container_spell_is_skipped(self):
        container = Container(name="Chest", locked=True)
        spell = _spell([{"type": "damage", "value": 5}, {"type": "unlock"}])
        value, msg = apply_spell_effect(self.player, container, spell, self.player)
        self.assertEqual(value, 1)
        self.assertFalse(container.properties["locked"])


class TestDamageBranch(GameTestBase):
    def test_target_without_take_damage_is_skipped(self):
        spell = _spell([{"type": "damage", "value": 10}])
        value, msg = apply_spell_effect(self.player, _BareTarget(), spell, self.player)
        self.assertEqual(value, 0)
        self.assertIn("no effect", msg)

    def test_format_exception_falls_back_to_generic_hit_message(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_fmt")
        spell = Spell(
            spell_id="broken_msg_spell", name="Broken", description="x",
            effects=[{"type": "damage", "value": 5}],
            hit_message="{missing_placeholder} points!",
        )
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertIn("hits", msg)
        self.assertIn("damage", msg)


class TestApplyDot(GameTestBase):
    def test_target_without_apply_effect_is_skipped(self):
        spell = _spell([{"type": "apply_dot", "value": 0}])
        value, msg = apply_spell_effect(self.player, _BareTarget(), spell, self.player)
        self.assertEqual(value, 0)

    def test_dot_with_tags_copies_them_into_payload(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_dot")
        spell = _spell([{
            "type": "apply_dot", "value": 0, "dot_name": "Poison",
            "effect_data": {"tags": ["poison"]},
        }])
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertEqual(value, 1)
        applied = goblin.active_effects[-1]
        self.assertEqual(applied.get("tags"), ["poison"])

    def test_failed_apply_effect_produces_no_message(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_dot_fail")
        spell = _spell([{"type": "apply_dot", "value": 0}])
        with patch.object(goblin, "apply_effect", return_value=(False, "")):
            value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertEqual(value, 0)


class TestHeal(GameTestBase):
    def test_target_without_heal_is_skipped(self):
        spell = _spell([{"type": "heal", "value": 10}], target_type="self")
        value, msg = apply_spell_effect(self.player, _BareTarget(), spell, self.player)
        self.assertEqual(value, 0)
        self.assertNotIn("heals", msg)

    def test_format_exception_falls_back_to_generic_heal_message(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_heal_fmt")
        goblin.health = 1
        spell = Spell(
            spell_id="broken_heal_spell", name="Broken Heal", description="x",
            effects=[{"type": "heal", "value": 10}], target_type="enemy",
            heal_message="{missing_placeholder}",
        )
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertIn("heals", msg)


class TestCleanse(GameTestBase):
    def test_target_without_remove_effects_by_tag_is_skipped(self):
        spell = _spell([{"type": "cleanse"}])
        value, msg = apply_spell_effect(self.player, _BareTarget(), spell, self.player)
        self.assertEqual(value, 0)
        self.assertNotIn("cleansed", msg)
        self.assertNotIn("nothing to cleanse", msg)

    def test_nothing_to_cleanse_produces_a_message(self):
        spell = _spell([{"type": "cleanse"}], target_type="self")
        value, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertEqual(value, 0)
        self.assertIn("nothing to cleanse", msg)

    def test_cleansing_active_afflictions_counts_and_messages(self):
        self.player.active_effects.append({"name": "Poison", "tags": ["poison"]})
        spell = _spell([{"type": "cleanse"}], target_type="self")
        value, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertEqual(value, 1)
        self.assertIn("cleansed", msg)


class TestRemoveCurse(GameTestBase):
    def test_cursed_item_target_is_uncursed(self):
        item = Item(name="Cursed Ring")
        item.update_property("cursed", True)
        spell = _spell([{"type": "remove_curse"}])
        value, msg = apply_spell_effect(self.player, item, spell, self.player)
        self.assertEqual(value, 1)
        self.assertFalse(item.get_property("cursed"))
        self.assertIn("lifted", msg)

    def test_non_item_non_equipment_target_is_skipped(self):
        class _PlainTarget:
            name = "Nothing"
        spell = _spell([{"type": "remove_curse"}])
        value, msg = apply_spell_effect(self.player, _PlainTarget(), spell, self.player)
        self.assertEqual(value, 0)

    def test_equipment_with_no_cursed_items_reports_nothing_found(self):
        spell = _spell([{"type": "remove_curse"}], target_type="self")
        value, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertEqual(value, 0)
        self.assertIn("not wearing any cursed items", msg)

    def test_equipment_with_cursed_items_are_uncursed(self):
        from engine.items.weapon import Weapon
        weapon = Weapon(name="Cursed Sword", damage=5)
        self.player.inventory.add_item(weapon)
        self.player.equip_item(weapon, slot_name="main_hand")
        weapon.update_property("cursed", True)
        spell = _spell([{"type": "remove_curse"}], target_type="self")
        value, msg = apply_spell_effect(self.player, self.player, spell, self.player)
        self.assertEqual(value, 1)
        self.assertIn("removed", msg)
        self.assertFalse(weapon.get_property("cursed"))


class TestLifeTap(GameTestBase):
    def test_target_without_take_damage_is_skipped(self):
        spell = _spell([{"type": "life_tap", "value": 10}])
        value, msg = apply_spell_effect(self.player, _BareTarget(), spell, self.player)
        self.assertEqual(value, 0)

    def test_zero_damage_reports_failed_drain(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_tap")
        spell = _spell([{"type": "life_tap", "value": 1}])
        with patch.object(goblin, "take_damage", return_value=0):
            value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertIn("fails to drain", msg)


class TestApplyEffectGeneric(GameTestBase):
    def test_target_without_apply_effect_is_skipped(self):
        spell = _spell([{"type": "apply_effect", "effect_data": {"name": "Blessed"}}])
        value, msg = apply_spell_effect(self.player, _BareTarget(), spell, self.player)
        self.assertEqual(value, 0)

    def test_empty_effect_data_is_skipped_via_continue(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_empty_eff")
        spell = _spell([{"type": "apply_effect"}, {"type": "damage", "value": 5}])
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        # The empty apply_effect entry contributes nothing; the damage entry does.
        self.assertGreater(value, 0)

    def test_existing_base_duration_is_kept_as_is(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_dur1")
        spell = _spell([{"type": "apply_effect", "effect_data": {"name": "Blessed", "base_duration": 5.0}}])
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertEqual(value, 1)
        self.assertEqual(goblin.active_effects[-1]["base_duration"], 5.0)

    def test_dot_duration_is_used_when_base_duration_missing(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_dur2")
        spell = _spell([{"type": "apply_effect", "effect_data": {"name": "Blessed"}, "dot_duration": 7.0}])
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertEqual(goblin.active_effects[-1]["base_duration"], 7.0)

    def test_top_level_base_duration_used_when_no_dot_duration(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_dur3")
        spell = _spell([{"type": "apply_effect", "effect_data": {"name": "Blessed"}, "base_duration": 3.0}])
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertEqual(goblin.active_effects[-1]["base_duration"], 3.0)

    def test_neither_duration_key_leaves_effect_without_duration(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_dur4")
        spell = _spell([{"type": "apply_effect", "effect_data": {"name": "Blessed"}}])
        value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertNotIn("base_duration", goblin.active_effects[-1])

    def test_failed_apply_effect_produces_no_message(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_goblin_apply_fail")
        spell = _spell([{"type": "apply_effect", "effect_data": {"name": "Blessed"}}])
        with patch.object(goblin, "apply_effect", return_value=(False, "")):
            value, msg = apply_spell_effect(self.player, goblin, spell, self.player)
        self.assertEqual(value, 0)


class TestSummon(GameTestBase):
    def test_non_player_caster_is_skipped(self):
        caster_npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_summoner_npc")
        target = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_summon_target")
        spell = _spell([{"type": "summon", "summon_template_id": "skeleton_minion"}])
        value, msg = apply_spell_effect(caster_npc, target, spell, None)
        self.assertEqual(value, 0)

    def test_missing_template_id_is_skipped(self):
        target = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_summon_target2")
        spell = _spell([{"type": "summon"}])
        value, msg = apply_spell_effect(self.player, target, spell, self.player)
        self.assertEqual(value, 0)

    def test_factory_failure_is_skipped(self):
        target = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_summon_target3")
        spell = _spell([{"type": "summon", "summon_template_id": "totally_bogus_template_xyz"}])
        value, msg = apply_spell_effect(self.player, target, spell, self.player)
        self.assertEqual(value, 0)

    def test_successful_summon_registers_and_messages(self):
        target = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="effects_summon_target4")
        spell = _spell([{"type": "summon", "summon_template_id": "skeleton_minion", "summon_duration": 60}])
        value, msg = apply_spell_effect(self.player, target, spell, self.player)
        self.assertEqual(value, 1)
        self.assertIn("appears to serve you", msg)
        self.assertIn(spell.spell_id, self.player.runtime_state.magic.summons)


if __name__ == "__main__":
    unittest.main()
