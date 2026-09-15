# tests/singles/test_combat_xp_allocation.py
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.utils.utils import calculate_xp_gain

class TestCombatXPAllocation(GameTestBase):

    def test_xp_on_kill(self):
        """Verify XP is awarded when an enemy dies in combat."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if not target: return
        self.world.add_npc(target)
        
        # Sync location
        target.current_region_id = self.player.current_region_id
        target.current_room_id = self.player.current_room_id
        
        start_xp = self.player.runtime_state.progression.experience
        
        # Calculate expected XP
        expected_gain = calculate_xp_gain(
            self.player.runtime_state.progression.level, target.level, target.max_health
        )
        
        # Weak Target
        target.health = 1
        
        # Kill
        with patch('random.random', return_value=0.0): # Hit
            self.player.attack(target, self.world)
            
        self.assertFalse(target.is_alive)
        # Combat XP is the floor. The advancement ledger (ROADMAP P4) also pays
        # for meeting a creature kind for the first time, so the total is at
        # least the kill award -- and this asserts the kill award itself landed
        # rather than pinning an exact sum that couples this test to content.
        gained = self.player.runtime_state.progression.experience - start_xp
        self.assertGreaterEqual(
            gained, expected_gain,
            "killing a target must award at least the combat XP for it",
        )

    def test_repeat_kills_award_combat_xp_but_no_further_advancement_xp(self):
        """First-encounter XP is once per kind; the kill award is not."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if not target: return
        self.world.add_npc(target)
        target.current_region_id = self.player.current_region_id
        target.current_room_id = self.player.current_room_id
        target.health = 1

        with patch('random.random', return_value=0.0):
            self.player.attack(target, self.world)
        after_first = self.player.runtime_state.progression.experience

        self.assertTrue(
            any(entry.startswith("creature:") for entry in self.player.advancement_entries),
            "the first encounter was not recorded in the ledger",
        )

        second = NPCFactory.create_npc_from_template("goblin", self.world)
        self.world.add_npc(second)
        second.current_region_id = self.player.current_region_id
        second.current_room_id = self.player.current_room_id
        second.health = 1
        with patch('random.random', return_value=0.0):
            self.player.attack(second, self.world)

        second_gain = self.player.runtime_state.progression.experience - after_first
        expected_gain = calculate_xp_gain(
            self.player.runtime_state.progression.level, second.level, second.max_health
        )
        # The second goblin pays combat XP only -- no repeated encounter bonus.
        self.assertLess(second_gain, expected_gain + 15,
                        "a repeat encounter paid advancement XP again")
