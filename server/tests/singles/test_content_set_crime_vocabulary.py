# tests/singles/test_content_set_crime_vocabulary.py
"""Proves the engine's crime/custody/lockpicking/combat-retreat code paths
carry no hardcoded fantasy vocabulary: `content_sets/night_shift` is a
small, real content set that renames every configurable slot the crime
system exposes (a "security_office" reputation key instead of
"town_guard", an "is_holding_room" property instead of "is_jail_cell",
an "item_shim_card" emergency tool instead of "item_lockpick_shiv", and
"awareness"/"security"/"evasion" skills instead of "stealth"/
"lockpicking"). If a future change reintroduces a hardcoded fantasy
literal into engine/core/crime_manager.py, engine/world/world.py,
engine/commands/jail.py, engine/commands/interaction/traps.py, or
engine/items/lockpick.py, the equivalent behavior here silently stops
working and one of these assertions fails."""

import unittest
from pathlib import Path
from unittest.mock import patch

from engine.server.headless_server import HeadlessServer

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
NIGHT_SHIFT = REPOSITORY_ROOT / "content_sets" / "night_shift"


class NightShiftTestCase(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(NIGHT_SHIFT),
            deterministic_test_mode=True,
        )
        session = self.server.create_session()
        self.session_id = session.session_id
        self.cmd("char create Robin")
        self.player = self.server.get_player_for_session(self.session_id)

    def tearDown(self):
        self.server.shutdown()

    def cmd(self, command_text: str) -> str:
        events = self.server.execute_command(self.session_id, command_text)
        return "\n".join(str(e.get("payload")) for e in events if e.get("type") == "text")

    def _steal_and_get_caught(self):
        self.cmd("north")  # loading_dock -> supply_room
        with patch("engine.core.skill_system.SkillSystem.attempt_check_with_margin", return_value=(False, "", -20)):
            return self.cmd("steal multitool from dana")


class TestTheftWitnessAndCustodyVocabulary(NightShiftTestCase):
    def test_witness_uses_the_configured_authority_property_and_skill(self):
        result = self._steal_and_get_caught()
        self.assertIn("Priya catches you red-handed", result)

    def test_consequences_use_the_configured_reputation_key(self):
        self._steal_and_get_caught()
        self.assertLess(self.player.get_reputation("security_office"), 0)
        # The real notoriety key must be isolated from the unrelated
        # "friendly"/"hostile" combat-faction reputation, exactly like
        # fantasy_frontier's "town_guard" key.
        self.assertEqual(0, self.player.get_reputation("friendly"))

    def test_custody_moves_the_player_to_the_configured_room_property(self):
        self._steal_and_get_caught()
        self.assertEqual("depot", self.player.current_region_id)
        self.assertEqual("holding_room", self.player.current_room_id)
        self.assertIsNotNone(self.player.confiscated_inventory)
        self.assertEqual([], [s.item for s in self.player.inventory.slots if s.item])

    def test_currency_name_is_respected_in_custody_messages(self):
        self.player.add_skill("awareness", 25)
        self.player.add_skill("security", 25)
        self._steal_and_get_caught()
        with patch("random.random", return_value=0.0):
            result = self.cmd("search")
        self.assertIn("credits", result)


class TestEscapeVocabulary(NightShiftTestCase):
    def test_below_the_configured_skill_floor_grants_no_escape_tool(self):
        self._steal_and_get_caught()
        self.assertEqual([], [s.item for s in self.player.inventory.slots if s.item])

    def test_meeting_the_configured_skill_floor_grants_the_configured_emergency_item(self):
        self.player.add_skill("awareness", 25)
        self.player.add_skill("security", 25)
        self._steal_and_get_caught()
        names = [s.item.name for s in self.player.inventory.slots if s.item]
        self.assertIn("makeshift shim card", names)

    def test_escape_uses_the_configured_locksmithing_skill_and_forfeits_belongings(self):
        self.player.add_skill("awareness", 25)
        self.player.add_skill("security", 25)
        self._steal_and_get_caught()
        with patch("engine.core.skill_system.SkillSystem.attempt_check_with_margin", return_value=(True, "", 10)):
            result = self.cmd("pick north")
        self.assertIn("Click!", result)
        self.assertIsNone(self.player.confiscated_inventory)


class TestCombatRetreatVocabulary(NightShiftTestCase):
    def _enter_combat_with_the_dog(self):
        self.player.current_region_id = "depot"
        self.player.current_room_id = "back_alley"
        dog = next(n for n in self.server.world.npcs.values() if n.template_id == "stray_dog")
        self.player.enter_combat(dog)
        return dog

    def test_failed_retreat_check_blocks_the_move(self):
        self._enter_combat_with_the_dog()
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(False, "")):
            result = self.cmd("west")
        self.assertIn("can't break away", result)
        self.assertEqual("back_alley", self.player.current_room_id)

    def test_successful_retreat_check_allows_the_move(self):
        self._enter_combat_with_the_dog()
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "")):
            result = self.cmd("west")
        self.assertIn("LOADING DOCK", result)
        self.assertEqual("loading_dock", self.player.current_room_id)


if __name__ == "__main__":
    unittest.main()
