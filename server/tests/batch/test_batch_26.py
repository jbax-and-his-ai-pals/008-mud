# tests/batch/test_batch_26.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestBatch26(GameTestBase):
    """Focus: Quests & NPC AI Logic."""

    def test_quest_kill_counter_increment(self):
        """Verify killing target increments quest counter."""
        q_id = "kill_q"
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "kill", "state": "active", "current_stage_index": 0,
            "stages": [{
                "stage_index": 0,
                "objective": {"type": "kill", "target_template_id": "goblin", "required_quantity": 5, "current_quantity": 0}
            }]
        }
        
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        if goblin:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": goblin})
            
        self.assertEqual(self.player.runtime_state.quests.active[q_id]["stages"][0]["objective"]["current_quantity"], 1)

    def test_quest_fetch_removal(self):
        """Verify items are removed on fetch turn-in."""
        q_id = "fetch_q"
        self.world.item_templates["rock"] = {"type": "Item", "name": "Rock"}
        
        giver = NPCFactory.create_npc_from_template("villager", self.world)
        if not giver: return
        self.world.add_npc(giver)
        giver.current_region_id = self.player.current_region_id
        giver.current_room_id = self.player.current_room_id
        
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "fetch", "state": "active", "current_stage_index": 0,
            "giver_instance_id": giver.obj_id,
            "stages": [{
                "stage_index": 0, "turn_in_id": giver.obj_id,
                "objective": {"type": "fetch", "item_id": "item_rock", "required_quantity": 1}
            }]
        }
        
        rock = ItemFactory.create_item_from_template("item_rock", self.world)
        if rock: self.player.inventory.add_item(rock)
        
        self.game.process_command(f"talk {giver.name} complete")
        
        self.assertEqual(self.player.inventory.count_item("item_rock"), 0)

    def test_npc_schedule_updates(self):
        """Verify setting time updates NPC scheduled task."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        
        npc.behavior_type = "scheduled"
        npc.schedule = {"8": {"activity": "working"}, "18": {"activity": "sleeping"}}
        
        # 8 AM
        self.game.time_manager.hour = 8
        from engine.npcs.ai.movement import perform_schedule
        perform_schedule(npc, self.world, self.player)
        self.assertEqual(npc.ai_state.get("current_activity"), "working")
        
        # 6 PM
        self.game.time_manager.hour = 18
        perform_schedule(npc, self.world, self.player)
        self.assertEqual(npc.ai_state.get("current_activity"), "sleeping")

    def test_npc_patrol_pathing(self):
        """Verify patrol logic sets next waypoint."""
        npc = NPCFactory.create_npc_from_template("guard", self.world)
        if not npc: npc = NPCFactory.create_npc_from_template("town_guard", self.world)
        
        if npc:
             npc.patrol_points = ["A", "B"]
             npc.current_room_id = "A"
             npc.patrol_index = 0
             
             # At A, target is A -> Should cycle to B
             from engine.npcs.ai.movement import perform_patrol
             perform_patrol(npc, self.world, self.player)
             
             self.assertEqual(npc.patrol_index, 1)

    def test_dialogue_condition_quest_active(self):
        """Verify dialogue conditional on active quest."""
        km = self.game.knowledge_manager
        km.topics["test"] = {
            "responses": [
                {"text": "Quest Active!", "conditions": {"quest_state": {"state": "active", "id_pattern": "q1"}}}
            ]
        }
        
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        
        # No quest
        res1 = km.get_response(npc, "test", self.player)
        self.assertNotIn("Active!", res1)
        
        # With Quest
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active["q1"] = {"state": "active"}
        res2 = km.get_response(npc, "test", self.player)
        self.assertIn("Active!", res2)

    def test_dialogue_condition_quest_complete(self):
        """Verify dialogue conditional on completed quest."""
        km = self.game.knowledge_manager
        km.topics["test"] = {
            "responses": [
                {"text": "Done!", "conditions": {"quest_state": {"state": "completed", "id_pattern": "q1"}}}
            ]
        }
        
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.completed["q1"] = {"state": "completed"}
        res = km.get_response(npc, "test", self.player)
        self.assertIn("Done!", res)

    def test_minion_despawn_timer(self):
        """Verify minion despawns after duration."""
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        if minion:
             minion.properties["creation_time"] = 100
             minion.properties["summon_duration"] = 10
             minion.properties["is_summoned"] = True
             minion.properties["owner_id"] = self.player.obj_id
             
             self.world.add_npc(minion)
             
             # Current time 120 > 110
             from engine.npcs.ai.dispatcher import handle_ai
             handle_ai(minion, self.world, 120, self.player)
             
             self.assertFalse(minion.is_alive)

    def test_quest_board_generation(self):
        """Verify board isn't empty after initialization."""
        self.world.quest_board = []
        self.world.quest_manager.ensure_initial_quests()
        self.assertGreater(len(self.world.quest_board), 0)

    def test_collection_turnin_logic(self):
        """Verify turning in collection item adds to progress."""
        self.game.collection_manager.collections["col1"] = {"items": ["i1"], "rewards": {}}
        self.world.item_templates["i1"] = {"type": "Junk", "name": "I1", "properties": {"collection_id": "col1"}}
        
        collector = NPCFactory.create_npc_from_template("curator", self.world)
        if not collector: return
        collector.properties["is_collector"] = True
        
        item = ItemFactory.create_item_from_template("i1", self.world)
        if item: self.player.inventory.add_item(item)
        
        self.game.collection_manager.turn_in_items(self.player, collector)
        
        self.assertIn("i1", self.player.collections_progress.get("col1", []))

    def test_knowledge_manager_highlighting(self):
        """Verify text is highlighted with command tags."""
        self.game.knowledge_manager.topics["test"] = {"keywords": ["keyword"]}
        
        text = "This text has a keyword."
        res = self.game.knowledge_manager.parse_and_highlight(text, self.player)
        
        self.assertIn("[[CMD:ask keyword]]", res)
