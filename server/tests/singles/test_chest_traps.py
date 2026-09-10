# tests/singles/test_chest_traps.py
"""Coverage for chest traps: Container.trigger_trap()'s effect resolution,
the hidden-from-examine property mechanism, the `disarm` command, and every
access path that can set a trap off (picking, a bad disarm, the Knock
spell, and the locksmith's safe defuse)."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.container import Container
from engine.items.lockpick import Lockpick
from engine.items.item_factory import ItemFactory
from engine.magic.effects import apply_spell_effect
from engine.magic.spell import Spell


class TestTriggerTrap(GameTestBase):
    def _trapped_box(self, kind="damage", difficulty=20):
        box = Container(name="Box", locked=True)
        box.update_property("trapped", True)
        box.update_property("trap_kind", kind)
        box.update_property("trap_difficulty", difficulty)
        return box

    def test_no_trap_is_a_safe_no_op(self):
        box = Container(name="Box", locked=True)
        self.assertIsNone(box.trigger_trap(self.player))

    def test_damage_trap_hurts_and_is_spent(self):
        box = self._trapped_box(kind="damage", difficulty=20)
        start_health = self.player.health
        msg = box.trigger_trap(self.player)
        self.assertIsNotNone(msg)
        self.assertIn("snaps", msg)
        self.assertLess(self.player.health, start_health)
        self.assertFalse(box.properties["trapped"])
        # Spent -- triggering again does nothing.
        self.assertIsNone(box.trigger_trap(self.player))

    def test_poison_trap_applies_dot_and_is_spent(self):
        box = self._trapped_box(kind="poison", difficulty=20)
        msg = box.trigger_trap(self.player)
        self.assertIsNotNone(msg)
        self.assertIn("poison", msg.lower() + "needle venom")
        self.assertTrue(self.player.has_effect("Trap Venom"))
        self.assertFalse(box.properties["trapped"])

    def test_defensive_no_crash_for_user_missing_combat_hooks(self):
        box = self._trapped_box(kind="damage")

        class _BareUser:
            is_alive = True

        # Must not raise even though _BareUser has neither take_damage nor
        # apply_effect -- mirrors Lockpick.apply_wear's own defensive guard.
        result = box.trigger_trap(_BareUser())
        self.assertIsNone(result)
        self.assertFalse(box.properties["trapped"])

    def test_dead_user_triggers_nothing_but_still_spends_the_trap(self):
        box = self._trapped_box(kind="damage")

        class _DeadUser:
            is_alive = False

        self.assertIsNone(box.trigger_trap(_DeadUser()))
        self.assertFalse(box.properties["trapped"])


class TestTrapHiddenFromExamine(GameTestBase):
    def test_trap_properties_do_not_leak_on_examine(self):
        box = Container(name="Box", locked=True)
        box.update_property("trapped", True)
        box.update_property("trap_kind", "poison")
        box.update_property("trap_difficulty", 30)
        text = box.examine()
        self.assertNotIn("Trapped", text)
        self.assertNotIn("Trap Kind", text)
        self.assertNotIn("Trap Difficulty", text)

    def test_other_properties_still_show(self):
        # Regression: the hidden-properties mechanism must not swallow
        # unrelated properties like lock_difficulty or lockpick durability.
        box = Container(name="Box", locked=True)
        box.update_property("lock_difficulty", 42)
        self.assertIn("Lock Difficulty: 42", box.examine())

        pick = Lockpick(name="Pick", durability=7, max_durability=10)
        self.assertIn("Durability: 7", pick.examine())


class TestLockpickTriggersTrap(GameTestBase):
    def _trapped_box(self, difficulty=999, trap_difficulty=20):
        box = Container(name="Box", locked=True)
        box.update_property("lock_difficulty", difficulty)
        box.update_property("trapped", True)
        box.update_property("trap_kind", "damage")
        box.update_property("trap_difficulty", trap_difficulty)
        return box

    def test_picking_a_trapped_lock_triggers_it_even_on_failure(self):
        box = self._trapped_box(difficulty=999)
        pick = Lockpick(name="Pick", durability=10)
        self.player.inventory.add_item(pick)
        start_health = self.player.health

        msg = pick.use(self.player, box)

        self.assertIn("snaps as you disturb", msg)
        self.assertLess(self.player.health, start_health)
        self.assertFalse(box.properties["trapped"])
        self.assertTrue(box.properties["locked"])  # the pick itself still failed

    @patch("engine.items.lockpick.SkillSystem.attempt_check_with_margin")
    def test_picking_a_trapped_lock_triggers_it_even_on_success(self, mock_check):
        mock_check.return_value = (True, "", 10)
        box = self._trapped_box(trap_difficulty=20)
        pick = Lockpick(name="Pick", durability=10)
        self.player.inventory.add_item(pick)
        start_health = self.player.health

        msg = pick.use(self.player, box)

        self.assertIn("snaps as you disturb", msg)
        self.assertIn("skillfully pick", msg)
        self.assertLess(self.player.health, start_health)
        self.assertFalse(box.properties["locked"])

    def test_undisarmed_but_untrapped_box_picks_normally(self):
        box = Container(name="Box", locked=True)
        box.update_property("lock_difficulty", 1)
        pick = Lockpick(name="Pick", durability=10)
        self.player.inventory.add_item(pick)
        msg = pick.use(self.player, box)
        self.assertNotIn("snaps as you disturb", msg)

    def test_trap_killing_the_user_skips_the_pick_roll(self):
        box = self._trapped_box(trap_difficulty=999999)
        pick = Lockpick(name="Pick", durability=10)
        self.player.inventory.add_item(pick)
        self.player.health = 1

        msg = pick.use(self.player, box)

        self.assertIn("snaps as you disturb", msg)
        self.assertFalse(self.player.is_alive)
        # No pick outcome text should follow a killing trap.
        self.assertNotIn("fumble", msg)
        self.assertNotIn("skillfully", msg)


class TestDisarmCommand(GameTestBase):
    def _place_trapped_box(self, difficulty=20):
        box = Container(name="Strongbox", locked=True)
        box.update_property("trapped", True)
        box.update_property("trap_kind", "damage")
        box.update_property("trap_difficulty", difficulty)
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        self.world.add_item_to_room(rid, room_id, box)
        return box

    def test_nothing_to_disarm_on_an_untrapped_box(self):
        box = Container(name="Strongbox", locked=True)
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        self.world.add_item_to_room(rid, room_id, box)
        result = self.game.process_command("disarm Strongbox")
        self.assertIn("nothing to disarm", result)
        self.assertNotIn(box.properties.get("trapped"), [True])

    def test_no_lockpick_is_reported(self):
        self._place_trapped_box()
        result = self.game.process_command("disarm Strongbox")
        self.assertIn("need a lockpick", result)

    @patch("engine.commands.interaction.traps.SkillSystem.attempt_check_with_margin")
    def test_successful_disarm_defuses_with_no_damage(self, mock_check):
        mock_check.return_value = (True, "", 10)
        box = self._place_trapped_box()
        self.player.inventory.add_item(Lockpick(name="Pick", durability=10))
        start_health = self.player.health

        result = self.game.process_command("disarm Strongbox")

        self.assertIn("disarm the trap", result)
        self.assertFalse(box.properties["trapped"])
        self.assertEqual(start_health, self.player.health)

    @patch("engine.commands.interaction.traps.SkillSystem.attempt_check_with_margin")
    def test_minor_failure_is_safe_and_retryable(self, mock_check):
        mock_check.return_value = (False, "", -5)
        box = self._place_trapped_box()
        pick = Lockpick(name="Pick", durability=10)
        self.player.inventory.add_item(pick)
        start_health = self.player.health

        result = self.game.process_command("disarm Strongbox")

        self.assertIn("fumble", result)
        self.assertTrue(box.properties["trapped"])
        self.assertEqual(start_health, self.player.health)
        self.assertLess(pick.durability, pick.max_durability)

    @patch("engine.commands.interaction.traps.SkillSystem.attempt_check_with_margin")
    def test_major_failure_triggers_the_trap(self, mock_check):
        mock_check.return_value = (False, "", -50)
        box = self._place_trapped_box()
        self.player.inventory.add_item(Lockpick(name="Pick", durability=10))
        start_health = self.player.health

        result = self.game.process_command("disarm Strongbox")

        self.assertIn("hand slips", result)
        self.assertFalse(box.properties["trapped"])
        self.assertLess(self.player.health, start_health)


class TestLocksmithDefusesTrap(GameTestBase):
    def _grenda(self):
        for npc in self.world.npcs.values():
            if npc.properties.get("can_unlock_chests"):
                return npc
        self.fail("No locksmith-capable NPC found in fantasy_frontier content.")

    def test_unlock_command_safely_defuses_a_trap(self):
        grenda = self._grenda()
        self.player.current_region_id = grenda.current_region_id
        self.player.current_room_id = grenda.current_room_id

        box = Container(name="Strongbox", locked=True, value=10)
        box.update_property("lock_difficulty", 20)
        box.update_property("trapped", True)
        box.update_property("trap_kind", "damage")
        box.update_property("trap_difficulty", 20)
        self.player.inventory.add_item(box)
        self.player.runtime_state.gold = 1000
        start_health = self.player.health

        result = self.game.process_command("unlock Strongbox")

        self.assertFalse(box.properties["locked"])
        self.assertFalse(box.properties["trapped"])
        self.assertEqual(start_health, self.player.health)
        self.assertIn("disarms a hidden trap", result)


class TestKnockSpellTriggersTrap(GameTestBase):
    def test_knock_triggers_trap_on_a_trapped_container(self):
        box = Container(name="Strongbox", locked=True)
        box.update_property("trapped", True)
        box.update_property("trap_kind", "damage")
        box.update_property("trap_difficulty", 20)
        knock = Spell("knock", "Knock", "desc", effects=[{"type": "unlock"}], target_type="item")
        start_health = self.player.health

        _, msg = apply_spell_effect(self.player, box, knock, viewer=None)

        self.assertFalse(box.properties["locked"])
        self.assertFalse(box.properties["trapped"])
        self.assertLess(self.player.health, start_health)
        self.assertIn("snaps as you disturb", msg)
