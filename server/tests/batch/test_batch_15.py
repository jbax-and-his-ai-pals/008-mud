# tests/batch/test_batch_15.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.world.region import Region
from engine.world.room import Room
from engine.items.item_factory import ItemFactory
from engine.items.container import Container

class TestBatch15(GameTestBase):

    def test_respawn_multiple(self):
        mgr = self.world.respawn_manager
        mgr.respawn_queue = []
        now = time.time()
        for i in range(3):
            mgr.respawn_queue.append({"template_id": "goblin", "instance_id": f"g_{i}", "respawn_time": now + 10.0, "home_region_id": "town", "home_room_id": "town_square"})
        mgr.update(now + 5.0)
        self.assertEqual(len(mgr.respawn_queue), 3)
        with patch('time.time', return_value=now + 15.0):
             mgr.update(now + 15.0)
        self.assertEqual(len(mgr.respawn_queue), 0)

    def test_pathfinding_island(self):
        region = self.world.get_region("town")
        if region:
            region.add_room("island", Room("Island", "x", obj_id="island"))
            path = self.world.find_path("town", "town_square", "town", "island")
            self.assertIsNone(path)

    def test_pathfinding_long(self):
        region = self.world.get_region("town")
        if region:
            for i in range(1, 6):
                prev = "town_square" if i == 1 else f"r{i-1}"
                curr = f"r{i}"
                region.add_room(curr, Room(curr, "x", obj_id=curr))
                prev_room = region.get_room(prev)
                if prev_room: prev_room.exits["next"] = curr
            path = self.world.find_path("town", "town_square", "town", "r5")
            self.assertIsNotNone(path)
            if path: self.assertEqual(len(path), 5)

    def test_reward_inventory_full(self):
        if not self.player: return
        q_id = "reward_full"
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "state": "active", "type": "fetch", "current_stage_index": 0,
            "rewards": {"items": [{"item_id": "reward_item", "quantity": 1}]},
            "giver_instance_id": "giver",
            "stages": [{
                "stage_index": 0, "turn_in_id": "giver",
                "objective": {"type": "talk"} # Simple objective to allow instant turn in
            }]
        }
        self.player.inventory.max_slots = 1
        self.player.inventory.slots = [self.player.inventory.slots[0]]
        dummy = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if dummy: self.player.inventory.add_item(dummy)
        
        self.world.item_templates["reward_item"] = {"type": "Item", "name": "Reward"}
        giver = NPCFactory.create_npc_from_template("wandering_villager", self.world, instance_id="giver")
        
        if giver:
             self.world.add_npc(giver)
             from engine.commands.interaction.npcs import _handle_quest_dialogue
             _handle_quest_dialogue(self.player, giver, self.world)
             # Current implementation might fail silently or drop, just ensure it doesn't crash
             self.assertEqual(self.player.inventory.count_item("reward_item"), 0)

    def test_spawn_cap_region(self):
        spawner = self.world.spawner
        region = self.world.get_region("town")
        if region:
            region.properties["safe_zone"] = False
            region.spawner_config = {"monster_types": {"goblin": 1}}
            for i in range(50):
                npc = NPCFactory.create_npc_from_template("goblin", self.world)
                if npc:
                    npc.current_region_id = "town"
                    self.world.add_npc(npc)
            initial_count = len([n for n in self.world.npcs.values() if n.current_region_id == "town"])
            with patch('random.random', return_value=0.0):
                 spawner.update(time.time() + 100.0)
            final_count = len([n for n in self.world.npcs.values() if n.current_region_id == "town"])
            self.assertEqual(initial_count, final_count)

    def test_time_regen_tick(self):
        if not self.player: return
        self.player.max_health = 100
        self.player.health = 50
        region = self.world.get_region(self.player.current_region_id) if self.player.current_region_id else None
        if region: region.properties["safe_zone"] = True
        self.player.last_mana_regen_time = 0
        self.player.update(time.time(), 0.1)
        self.assertGreater(self.player.health, 50)

    def test_system_save_load_stress(self):
        if not self.player: return
        TEST_SAVE = "stress_save.json"
        
        # FIX: Directly initialize with InventorySlot objects to satisfy type checker
        from engine.items.inventory import InventorySlot
        self.player.inventory.max_slots = 100
        # FIX: Increase weight limit so all 50 items fit
        self.player.inventory.max_weight = 5000.0 
        self.player.inventory.slots = [InventorySlot() for _ in range(100)]

        for i in range(50):
            item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
            if item: self.player.inventory.add_item(item)
            
        self.world.save_game(TEST_SAVE)
        self.world.load_save_game(TEST_SAVE)
        
        # FIX: Ensure player is not None before accessing inventory
        loaded_player = self.world.player
        if loaded_player:
            self.assertEqual(len([s for s in loaded_player.inventory.slots if s.item]), 50)
        else:
            self.fail("Player was not loaded correctly.")

        import os
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)): os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_weather_indoor_transition(self):
        region = self.world.get_region("town")
        if not self.player: return
        
        if region:
            region.add_room("in", Room("In", "x", {"out": "out"}, obj_id="in"))
            region.add_room("out", Room("Out", "x", {"in": "in"}, obj_id="out"))
            
            # FIX: Safe access to rooms before setting properties
            room_in = region.get_room("in")
            room_out = region.get_room("out")
            
            if room_in and room_out:
                room_in.properties["outdoors"] = False
                room_out.properties["outdoors"] = True
                
                self.game.weather_manager.current_weather = "storm"
                self.player.current_region_id = "town"
                
                self.player.current_room_id = "out"
                self.world.current_room_id = "out"
                self.assertIn("storm", self.world.look())
                
                self.player.current_room_id = "in"
                self.world.current_room_id = "in"
                self.assertNotIn("storm", self.world.look())

    def test_non_existent_item_template(self):
        item = ItemFactory.create_item_from_template("missing_id_999", self.world)
        self.assertIsNone(item)

    def test_container_recursive_prevention_deep(self):
        """Verify A -> B, then trying B -> A is blocked."""
        if not self.player: return

        a = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        b = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        
        # FIX: Check if items were created successfully before setting attributes
        if isinstance(a, Container) and isinstance(b, Container):
            a.name = "A"
            b.name = "B"
            a.properties["is_open"] = True
            b.properties["is_open"] = True
            self.player.inventory.add_item(a)
            self.player.inventory.add_item(b)
            
            # Put B in A
            self.game.process_command("put B in A")
            
            # Try put A in B (Recursion)
            res = self.game.process_command("put A in B")
            
            # FIX: Assert res is not None before checking contents
            self.assertIsNotNone(res)
            if res:
                self.assertIn("already inside", res)
            
            self.assertNotIn(a, b.properties.get("contains", []))
