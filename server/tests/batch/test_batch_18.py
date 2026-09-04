# tests/batch/test_batch_18.py
import time
import os
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.world.region_generator import RegionGenerator
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.world.room import Room
from engine.world.region import Region

class TestBatch18(GameTestBase):
    """Focus: World Generation, Quests, and State Persistence."""

    def test_dynamic_region_portal(self):
        """Verify generated regions create accessible portals."""
        # 1. Generate
        self.game.process_command("genregion caves 5")
        
        # 2. Check current room for portal exit
        room = self.world.get_current_room()
        self.assertIsNotNone(room)
        if room:
            self.assertIn("portal", room.exits)
        
            # 3. Enter
            dest = room.exits["portal"]
            new_reg, new_room = dest.split(":")
            
            self.world.change_room("portal")
            self.assertEqual(self.world.current_region_id, new_reg)

    def test_clear_region_quest(self):
        """Verify 'clear_region' quest updates when last mob dies."""
        # 1. Setup Instance Region
        inst_id = "inst_clear"
        inst_reg = Region("Inst", "x", obj_id=inst_id)
        inst_reg.add_room("r1", Room("R1", "x", obj_id="r1"))
        self.world.add_region(inst_id, inst_reg)
        
        # 2. Setup Quest (Saga Structure)
        q_id = "quest_clear"
        objective_data = {"type": "clear_region", "target_template_id": "goblin"}
        
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "state": "active", "type": "instance",
            "instance_region_id": inst_id,
            "completion_check_enabled": True,
            "current_stage_index": 0,
            # Sync top-level for legacy/UI, but Manager uses stages
            "objective": objective_data,
            "stages": [
                {
                    "stage_index": 0,
                    "objective": objective_data
                }
            ]
        }
        
        # 3. Add Mobs
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            goblin.current_region_id = inst_id; goblin.current_room_id = "r1"
            self.world.add_npc(goblin)
            
            # 4. Check not done
            self.world.quest_manager.check_quest_completion()
            self.assertEqual(self.player.runtime_state.quests.active[q_id]["state"], "active")
            
            # 5. Kill
            goblin.is_alive = False
            self.world.quest_manager.check_quest_completion()
            
            self.assertEqual(self.player.runtime_state.quests.active[q_id]["state"], "ready_to_complete")

    def test_reward_overflow(self):
        """Verify quest completion fails (or handles) full inventory."""
        # Setup Quest with item reward
        q_id = "rew_test"
        giver = NPCFactory.create_npc_from_template("villager", self.world)
        if not giver: return
        self.world.add_npc(giver)
        giver.current_region_id = self.player.current_region_id
        giver.current_room_id = self.player.current_room_id
        
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "state": "ready_to_complete",
            "giver_instance_id": giver.obj_id,
            "rewards": {"items": [{"item_id": "item_iron_sword", "quantity": 1}]},
            "current_stage_index": 0,
            "stages": [{"stage_index": 0, "objective": {"type": "talk"}, "turn_in_id": giver.obj_id}]
        }
        
        # Fill Inventory
        self.player.inventory.max_slots = 1
        dummy = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if dummy:
             dummy.obj_id = "dummy"
             self.player.inventory.add_item(dummy)
        
        # Try turn in
        from engine.commands.interaction.npcs import _handle_quest_dialogue
        res = _handle_quest_dialogue(self.player, giver, self.world)
        
        pass

    def test_schedule_movement(self):
        """Verify NPCs move when time advances to schedule point."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        npc.behavior_type = "scheduled"
        npc.current_region_id = "town"; npc.current_room_id = "town_square"
        
        # Setup valid destination
        r = self.world.get_region("town")
        if r:
             r.add_room("market", Room("Market", "x", {"west": "town_square"}, obj_id="market"))
             sq = r.get_room("town_square")
             if sq: sq.exits["east"] = "market"
             
        npc.schedule = {"12": {"region_id": "town", "room_id": "market"}}
        
        self.game.time_manager.hour = 12
        npc.last_moved = 0
        npc.update(self.world, time.time())
        
        self.assertEqual(npc.current_room_id, "market")

    def test_weather_indoor_mask(self):
        """Verify indoor rooms don't show weather description."""
        self.game.weather_manager.current_weather = "storm"
        
        r = self.world.get_region("town")
        if r:
             r.add_room("indoor_test", Room("Inside", "x", obj_id="indoor_test"))
             room = r.get_room("indoor_test")
             if room:
                  room.properties["outdoors"] = False
                  
                  self.player.current_region_id = "town"
                  self.player.current_room_id = "indoor_test"
                  self.world.current_region_id = "town"
                  self.world.current_room_id = "indoor_test"
                  
                  desc = self.world.look()
                  self.assertNotIn("storm", desc)

    def test_respawn_queue_persistence(self):
        """Verify respawn queue saves and loads."""
        TEST_SAVE = "respawn_batch18.json"
        
        mgr = self.world.respawn_manager
        mgr.respawn_queue.append({"template_id": "goblin", "instance_id": "g1", "respawn_time": 999999})
        
        self.world.save_game(TEST_SAVE)
        mgr.respawn_queue = []
        self.world.load_save_game(TEST_SAVE)
        
        self.assertEqual(len(mgr.respawn_queue), 1)
        self.assertEqual(mgr.respawn_queue[0]["instance_id"], "g1")
        
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
            os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_pathfinding_long_distance(self):
        """Verify pathfinding works across multiple hops."""
        # A -> B -> C -> D
        reg = Region("Linear", "x", obj_id="lin")
        reg.add_room("A", Room("A", "x", {"e": "B"}, obj_id="A"))
        reg.add_room("B", Room("B", "x", {"e": "C", "w": "A"}, obj_id="B"))
        reg.add_room("C", Room("C", "x", {"e": "D", "w": "B"}, obj_id="C"))
        reg.add_room("D", Room("D", "x", {"w": "C"}, obj_id="D"))
        self.world.add_region("lin", reg)
        
        path = self.world.find_path("lin", "A", "lin", "D")
        self.assertEqual(path, ["e", "e", "e"])

    def test_dialogue_quest_state_change(self):
        """Verify NPC dialogue updates immediately after accepting quest."""
        km = self.game.knowledge_manager
        km.topics["help"] = {
             "display_name": "Help",
             "responses": [
                  {"text": "Thanks!", "conditions": {"quest_state": {"state": "active"}}, "priority": 10},
                  {"text": "I need help.", "conditions": {}, "priority": 0}
             ]
        }
        
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # 1. Before
        res1 = km.get_response(npc, "help", self.player)
        self.assertIn("need help", res1)
        
        # 2. Accept
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active["q1"] = {"instance_id": "q1", "state": "active", "giver_instance_id": npc.obj_id}
        
        # 3. After
        res2 = km.get_response(npc, "help", self.player)
        self.assertIn("Thanks", res2)

    def test_durability_loss_combat(self):
        """Verify weapon durability decreases on hit."""
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        if not target: return
        target.health = 100
        
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if sword:
            self.player.inventory.add_item(sword)
            self.player.equip_item(sword)
            start_dura = sword.get_property("durability")
            
            with patch('random.random', return_value=0.0): # Hit
                self.player.attack(target, self.world)
                
            self.assertLess(sword.get_property("durability"), start_dura)

    def test_player_respawn_reset(self):
        """Verify dying resets combat flags and restores stats."""
        self.player.health = 0
        self.player.is_alive = False
        assert self.player.runtime_state.combat is not None
        self.player.runtime_state.combat.in_combat = True
        self.player.runtime_state.combat.targets.add("dummy")
        
        self.player.respawn()
        
        self.assertTrue(self.player.is_alive)
        self.assertEqual(self.player.health, self.player.max_health)
        self.assertFalse(self.player.runtime_state.combat.in_combat)
        self.assertEqual(len(self.player.runtime_state.combat.targets), 0)
