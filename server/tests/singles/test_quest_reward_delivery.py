# tests/singles/test_quest_reward_delivery.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestQuestRewardDelivery(GameTestBase):

    def test_rewards_applied(self):
        """Verify XP and Gold are added upon quest completion."""
        # 1. Setup Quest
        q_id = "reward_test"
        quest_data = {
            "instance_id": q_id,
            "title": "Rich Quest",
            "type": "kill", # Dummy type
            "state": "ready_to_complete", # Skip directly to turn-in
            "rewards": { "xp": 500, "gold": 100 },
            "giver_instance_id": "giver_npc"
        }
        self.player.runtime_state.quests.active[q_id] = quest_data
        
        # 2. Setup Giver
        giver = NPCFactory.create_npc_from_template("villager", self.world, instance_id="giver_npc")
        if not giver: return
        self.world.add_npc(giver)
        
        # Colocate
        giver.current_region_id = self.player.current_region_id
        giver.current_room_id = self.player.current_room_id
        
        # Snapshot stats
        start_xp = self.player.runtime_state.progression.experience
        start_gold = self.player.runtime_state.gold
        
        # 3. Act: Turn In
        self.game.process_command(f"talk {giver.name} complete")
        
        # 4. Assert
        self.assertEqual(self.player.runtime_state.gold, start_gold + 100)
        self.assertEqual(self.player.runtime_state.progression.experience, start_xp + 500)
        self.assertIn(q_id, self.player.runtime_state.quests.completed)
