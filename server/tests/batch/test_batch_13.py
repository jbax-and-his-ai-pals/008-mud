# tests/batch/test_batch_13.py
import unittest
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.items.item import Item

class TestBatch13(GameTestBase):

    def test_quest_recipient_dead(self):
        """Verify delivery fails gracefully if the recipient is dead."""
        if not self.player: return

        # 1. Setup Quest (Saga Style)
        q_id = "deliver_dead"
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "deliver", "state": "active", "current_stage_index": 0,
            "stages": [{
                "stage_index": 0, "turn_in_id": "dead_guy",
                "objective": {
                    "type": "deliver",
                    "item_instance_id": "pkg_dead", 
                    "recipient_instance_id": "dead_guy",
                    "recipient_name": "Dead Guy"
                }
            }]
        }
        
        # 2. Setup Item
        self.world.item_templates["package"] = {"type": "Item", "name": "Package"}
        pkg = ItemFactory.create_item_from_template("package", self.world)
        if pkg:
            pkg.obj_id = "pkg_dead"
            self.player.inventory.add_item(pkg)

        # 3. Setup Dead NPC
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc:
            npc.obj_id = "dead_guy"
            npc.name = "Dead Guy"
            npc.is_alive = False
            self.world.add_npc(npc)
            npc.current_region_id = self.player.current_region_id
            npc.current_room_id = self.player.current_room_id
            
            result = self.game.process_command("give Package to Dead Guy")
            self.assertIsNotNone(result)
            if result:
                self.assertTrue("don't see" in result.lower() or "dead" in result.lower())
                
    def test_quest_fetch_equipped(self):
        """Verify items currently equipped do not count towards fetch quest completion."""
        if not self.player: return
        
        q_id = "fetch_sword"
        giver = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if giver:
            giver.current_region_id = self.player.current_region_id
            giver.current_room_id = self.player.current_room_id
            self.world.add_npc(giver)
            
            assert self.player.runtime_state.quests is not None
            self.player.runtime_state.quests.active[q_id] = {
                "instance_id": q_id, "type": "fetch", "state": "active", "current_stage_index": 0,
                "giver_instance_id": giver.obj_id,
                "stages": [{
                    "stage_index": 0, "turn_in_id": giver.obj_id,
                    "objective": {"type": "fetch", "item_id": "item_iron_sword", "required_quantity": 1}
                }]
            }
            
            sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
            if sword:
                self.player.inventory.add_item(sword)
                self.player.equip_item(sword, "main_hand")
                
                from engine.commands.interaction.npcs import _handle_quest_dialogue
                msg = _handle_quest_dialogue(self.player, giver, self.world)
                
                self.assertIn("still need", msg)
                
    def test_quest_fetch_stack_split(self):
        """Verify turning in a quest consumes only the required amount from a stack."""
        if not self.player: return

        giver = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if giver:
            self.world.add_npc(giver)
            
            self.world.item_templates["token"] = {"type": "Item", "name": "Token", "stackable": True}
            
            q_id = "fetch_tokens"
            assert self.player.runtime_state.quests is not None
            self.player.runtime_state.quests.active[q_id] = {
                "instance_id": q_id, "type": "fetch", "state": "active",
                "giver_instance_id": giver.obj_id, "current_stage_index": 0,
                "rewards": {"xp": 100},
                "stages": [{
                    "stage_index": 0, "turn_in_id": giver.obj_id,
                    "objective": {"type": "fetch", "item_id": "token", "required_quantity": 5}
                }]
            }
            
            token = ItemFactory.create_item_from_template("token", self.world)
            if token:
                self.player.inventory.add_item(token, 10)
                
                from engine.commands.interaction.npcs import _handle_quest_dialogue
                msg = _handle_quest_dialogue(self.player, giver, self.world)
                
                self.assertIn("Complete", msg)
                self.assertEqual(self.player.inventory.count_item("token"), 5)

    def test_quest_instance_entry_link(self):
        """Verify creating an instance quest links the start room correctly."""
        q_data = {
            "instance_id": "test_inst",
            "meta_instance_data": {
                "instance_region": {
                    "region_name": "Inst", "region_description": "x", "rooms": {"start": {"name": "S", "exits": {"out": "dynamic_exit"}}}
                },
                "entry_point": {
                    "region_id": "town", "room_id": "town_square", "exit_command": "enter_portal"
                },
                "layout_generation_config": {"target_count": [0,0]}
            },
            "objective": {"target_template_id": "goblin"} 
        }
        
        # Need to flatten the meta_data for instantiate call as per new logic in QuestManager?
        # Actually, instantiate_quest_region expects keys at top level. 
        # The manager handles the unpacking. In unit test we manually unpack or pass structured data.
        # Let's pass the unpacked structure as instantiate_quest_region expects it.
        flat_data = q_data.copy()
        flat_data.update(q_data["meta_instance_data"])
        
        success, msg, gid = self.world.instantiate_quest_region(flat_data)
        self.assertTrue(success, f"Instantiation failed: {msg}")
        
        region = self.world.get_region("town")
        if region:
            sq = region.get_room("town_square")
            if sq:
                self.assertIn("enter_portal", sq.exits)
                
                assert self.player.runtime_state.quests is not None
                self.player.runtime_state.quests.completed["test_inst"] = flat_data
                self.world.cleanup_quest_region("test_inst")
                self.assertNotIn("enter_portal", sq.exits)

    def test_quest_multi_kill_update(self):
        if not self.player: return
        
        def make_q(qid):
            return {
                "instance_id": qid, "type": "kill", "state": "active", "current_stage_index": 0,
                "stages": [{"stage_index": 0, "objective": {"type": "kill", "target_template_id": "goblin", "required_quantity": 5, "current_quantity": 0}}]
            }
        
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active["q1"] = make_q("q1")
        self.player.runtime_state.quests.active["q2"] = make_q("q2")
        
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": goblin})
            self.assertEqual(self.player.runtime_state.quests.active["q1"]["stages"][0]["objective"]["current_quantity"], 1)
            self.assertEqual(self.player.runtime_state.quests.active["q2"]["stages"][0]["objective"]["current_quantity"], 1)
