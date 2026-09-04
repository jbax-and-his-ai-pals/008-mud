# tests/batch/test_batch_8.py
import time
import os
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.items.container import Container
from engine.items.lockpick import Lockpick
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.core.skill_system import SkillSystem
from engine.utils.utils import calculate_xp_gain
from engine.config import MIN_XP_GAIN

class TestBatch8(GameTestBase):

    def test_npc_retreat_low_mana(self):
        """Verify mage NPCs attempt to retreat when mana is critical."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Setup Mage
        mage = NPCFactory.create_npc_from_template("wandering_mage", self.world)
        self.assertIsNotNone(mage, "Failed to create mage.")

        if mage:
            mage.current_region_id = "town"
            mage.current_room_id = "town_square"
            mage.max_mana = 100
            mage.mana = 5 # Critical mana (< 20%)
            mage.behavior_type = "aggressive" # Enable combat logic
            
            # CRITICAL FIX: Ensure RNG doesn't skip the spell block where retreat logic lives
            mage.spell_cast_chance = 1.0 
            mage.last_combat_action = 0 # Ensure cooldown doesn't block

            self.world.add_npc(mage)
            
            # 2. Enter Combat
            mage.enter_combat(self.player)
            
            # 3. Run AI Logic (Should trigger start_retreat)
            region = self.world.get_region("town")
            if region:
                region.update_property("safe_zone", False)
                
                # Create the actual safe room and link it so find_path succeeds
                from engine.world.room import Room
                safe_room = Room("Safe House", "Safe", {"out": "town_square"}, obj_id="safe_house")
                region.add_room("safe_house", safe_room)
                
                ts = region.get_room("town_square")
                if ts: ts.exits["safe"] = "safe_house"

                # Mock finding the safe room
                with patch.object(self.world, 'find_nearest_safe_room', return_value=("town", "safe_house")):
                    from engine.npcs.ai.dispatcher import handle_ai
                    handle_ai(mage, self.world, time.time(), self.player)
            
            # 4. Assert Behavior Change
            self.assertEqual(mage.behavior_type, "retreating_for_mana")

    def test_schedule_resumption(self):
        """Verify NPC returns to schedule after interruption."""
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        self.assertIsNotNone(npc, "Failed to create NPC")
        
        if npc:
            npc.current_region_id = "town"
            npc.current_room_id = "town_square"
            self.world.add_npc(npc)
            
            # 1. Set Schedule
            npc.behavior_type = "scheduled"
            npc.schedule = {
                "12": {"region_id": "town", "room_id": "market", "activity": "shopping"}
            }
            self.game.time_manager.hour = 12
            
            # 2. Interrupt (Move manually away from destination)
            npc.current_room_id = "town_square" # Dest is Market
            npc.ai_state["current_activity"] = "idle" # Reset activity state
            
            # CRITICAL FIX: Reset movement cooldown so AI acts immediately
            npc.last_moved = 0 
            
            # 3. Run AI
            from engine.npcs.ai.dispatcher import handle_ai
            handle_ai(npc, self.world, time.time(), self.player)
            
            # 4. Assert Logic Resumed (Activity updated)
            self.assertEqual(npc.ai_state.get("current_activity"), "shopping")

    def test_spell_target_validation(self):
        """Verify offensive spells cannot target self/friendlies."""
        if not self.player: return

        # 1. Setup Offensive Spell
        blast = Spell(
            "test_blast", "Blast", "x",
            effects=[{"type": "damage", "value": 1}],
            target_type="enemy",
        )
        register_spell(blast)
        self.player.runtime_state.magic.known_spells.add("test_blast")
        
        # 2. Cast on Self (Should Fail)
        res_self = self.game.process_command("cast Blast on self")
        self.assertIsNotNone(res_self)
        if res_self:
            self.assertIn("only cast", res_self.lower())
            
        # 3. Cast on Friendly (Should Fail)
        villager = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if villager:
            villager.name = "Bob"
            self.world.add_npc(villager)
            # Sync location
            villager.current_region_id = self.player.current_region_id
            villager.current_room_id = self.player.current_room_id
            
            res_friend = self.game.process_command("cast Blast on Bob")
            self.assertIsNotNone(res_friend)
            if res_friend:
                self.assertIn("only cast", res_friend.lower())

    def test_inventory_swap_equip(self):
        """Verify equipping a weapon swaps it with the currently equipped one."""
        if not self.player: return

        sword1 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        sword2 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        
        self.assertIsNotNone(sword1)
        self.assertIsNotNone(sword2)
        
        if sword1 and sword2:
            sword1.name = "Sword A"; sword1.obj_id="s1"
            sword2.name = "Sword B"; sword2.obj_id="s2"

            self.player.inventory.add_item(sword1)
            self.player.inventory.add_item(sword2)
            
            # 1. Equip A
            self.player.equip_item(sword1, "main_hand")
            self.assertEqual(self.player.equipment["main_hand"], sword1)
            self.assertEqual(self.player.inventory.count_item("s1"), 0)
            
            # 2. Equip B (Should swap)
            self.game.process_command("equip Sword B")
            
            self.assertEqual(self.player.equipment["main_hand"], sword2)
            self.assertEqual(self.player.inventory.count_item("s1"), 1) # A returned
            self.assertEqual(self.player.inventory.count_item("s2"), 0) # B removed

    def test_drop_quest_item(self):
        """Verify dropping a quest item updates the quest logic indirectly."""
        if not self.player: return

        # 1. Setup Quest with valid stages structure
        q_id = "fetch_rock"
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "fetch", "state": "active",
            "current_stage_index": 0,
            "stages": [{
                "stage_index": 0,
                "objective": {"type": "fetch", "item_id": "rock", "required_quantity": 1}
            }]
        }
        
        # 2. Get Item
        self.world.item_templates["rock"] = {"type": "Item", "name": "Quest Rock"}
        rock = ItemFactory.create_item_from_template("rock", self.world)
        if rock:
            self.player.inventory.add_item(rock)
            
            # 3. Verify Player has it
            self.assertEqual(self.player.inventory.count_item("rock"), 1)
            
            # 4. Drop it
            self.game.process_command("drop Quest Rock")
            self.assertEqual(self.player.inventory.count_item("rock"), 0)
            
            # 5. Check Quest Turn-in Logic (Simulate talking to giver)
            from engine.commands.interaction.npcs import _handle_quest_dialogue
            giver = NPCFactory.create_npc_from_template("wandering_villager", self.world)
            if giver:
                # Mock the quest giver ID
                self.player.runtime_state.quests.active[q_id]["giver_instance_id"] = giver.obj_id
                self.player.runtime_state.quests.active[q_id]["stages"][0]["turn_in_id"] = giver.obj_id
                self.player.runtime_state.quests.active[q_id]["state"] = "ready_to_complete" # Force ready state to test fallback
                
                # Act: Attempt complete
                # It should revert or fail because item is missing
                msg = _handle_quest_dialogue(self.player, giver, self.world)
                
                self.assertIn("still need", msg) # Should detect missing item

    def test_time_passing_events(self):
        """Verify updating game time triggers respawn manager."""
        mgr = self.world.respawn_manager
        
        # FIX: Ensure template exists and is valid
        self.world.npc_templates["goblin_test"] = {
            "name": "Goblin", "description": "A test goblin.", "faction": "hostile", "health": 10
        }

        # 1. Queue a respawn
        future = time.time() + 50.0
        mgr.respawn_queue.append({
            "template_id": "goblin_test", "instance_id": "g1",
            "name": "Goblin", "home_region_id": "town", "home_room_id": "town_square",
            "respawn_time": future
        })
        
        # 2. Update time to BEFORE spawn
        mgr.update(future - 10.0)
        self.assertEqual(len(mgr.respawn_queue), 1)
        
        # 3. Update time to AFTER spawn
        mgr.update(future + 10.0)
        self.assertEqual(len(mgr.respawn_queue), 0)
        self.assertIn("g1", self.world.npcs)
