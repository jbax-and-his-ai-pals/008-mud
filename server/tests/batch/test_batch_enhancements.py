# tests/batch/test_batch_enhancements.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.world.room import Room
from engine.config import REP_THRESHOLD_HATED, REP_THRESHOLD_FRIENDLY
from engine.core.skill_system import SkillSystem

class TestBatchEnhancements(GameTestBase):

    def test_set_bonuses_application(self):
        """Verify equipping a full set grants stats."""
        # Inject Set Data Mock
        self.player.set_manager.sets = {
            "test_set": {
                "items": ["helm", "chest"],
                "bonuses": {
                    "2": {"type": "stat_mod", "modifiers": {"strength": 10}}
                }
            }
        }
        
        # Create Dummy Items
        self.world.item_templates["helm"] = {"type": "Armor", "name": "Helm", "properties": {"equip_slot": ["head"], "defense": 1}}
        self.world.item_templates["chest"] = {"type": "Armor", "name": "Chest", "properties": {"equip_slot": ["body"], "defense": 1}}
        
        helm = ItemFactory.create_item_from_template("helm", self.world)
        chest = ItemFactory.create_item_from_template("chest", self.world)
        
        if helm and chest:
            self.player.inventory.add_item(helm)
            self.player.inventory.add_item(chest)
            
            base_str = self.player.stats["strength"]
            
            # Equip 1
            self.player.equip_item(helm)
            self.assertEqual(self.player.get_effective_stat("strength"), base_str)
            
            # Equip 2 (Set Bonus Active)
            self.player.equip_item(chest)
            self.assertEqual(self.player.get_effective_stat("strength"), base_str + 10)

    def test_reputation_impact(self):
        """Verify killing friendly lowers rep and changes relation."""
        villager = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if not villager: return
        villager.faction = "friendly"
        self.world.add_npc(villager)
        
        self.player.reputation["friendly"] = 0
        
        # Kill
        self.world.dispatch_event("npc_killed", {"player": self.player, "npc": villager})
        
        # Verify Rep Drop
        new_rep = self.player.get_reputation("friendly")
        self.assertLess(new_rep, 0)
        
        # Force rep lower to check relation calculation
        self.player.reputation["friendly"] = -200
        
        from engine.npcs.combat import get_relation_to
        # Base friendly->player is 100. Mod is -200. Result -100.
        rel = get_relation_to(villager, self.player)
        self.assertEqual(rel, -100)

    def test_skill_gated_exit(self):
        """Verify movement blocked by lack of skill."""
        region = self.world.get_region("town")
        if region:
            # Create a destination room so we can verify movement actually happened
            region.add_room("high_ledge", Room("High Ledge", "You are up high.", obj_id="high_ledge"))

            room = region.get_room("town_square")
            if room:
                room.exits["climb_up"] = "high_ledge"
                room.properties["exit_requirements"] = {
                    "climb_up": {"type": "skill", "skill_name": "climbing", "difficulty": 50}
                }
                
                # Case 1: No skill (Failure)
                self.player.skills = {}
                
                # Force failure RNG (Roll 1 + 0 < 50)
                with patch('random.randint', return_value=1):
                    res = self.world.change_room("climb_up")
                    self.assertIn("fail to traverse", res)
                    self.assertEqual(self.player.current_room_id, "town_square")
                
                # Case 2: High skill (Success)
                # Patch randomness for success (Roll 100 + 50 > 50)
                with patch('random.randint', return_value=100):
                    self.player.add_skill("climbing", 50)
                    res2 = self.world.change_room("climb_up")
                    
                    # Verify we see the new room title (implies success)
                    self.assertIn("HIGH LEDGE", res2)
                    self.assertEqual(self.player.current_room_id, "high_ledge")

    def test_pick_door_direction(self):
        """Verify picking a directional lock."""
        region = self.world.get_region("town")
        if region:
            room = region.get_room("town_square")
            if room:
                room.exits["north"] = "locked_room"
                room.properties["exit_requirements"] = {
                    "north": {"type": "locked", "pick_difficulty": 10}
                }
                
                # 1. No pick
                res = self.game.process_command("pick north")
                if res: self.assertIn("need a lockpick", res)
                
                # 2. With pick
                self.world.item_templates["pick"] = {"type": "Lockpick", "name": "pick"}
                pick = ItemFactory.create_item_from_template("pick", self.world)
                if pick: self.player.inventory.add_item(pick)
                
                # Force skill check success
                with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
                    res2 = self.game.process_command("pick north")
                    if res2: self.assertIn("unlock the way", res2)
                    
                # Verify lock requirement removed
                reqs = room.properties.get("exit_requirements", {})
                self.assertNotIn("north", reqs)