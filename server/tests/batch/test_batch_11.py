# tests/batch/test_batch_11.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestBatch11(GameTestBase):

    def test_schedule_time_transition(self):
        """Verify NPC moves when schedule time triggers."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc:
             npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        
        self.assertIsNotNone(npc)
        if npc:
            self.world.add_npc(npc)
            npc.behavior_type = "scheduled"
            npc.current_room_id = "home"
            
            # Schedule: 8:00 -> Work
            npc.schedule = {"8": {"region_id": "town", "room_id": "work", "activity": "working"}}
            
            # Set time to 8:00
            self.game.time_manager.hour = 8
            npc.last_moved = 0
            
            # Ensure rooms exist
            region = self.world.get_region("town")
            if region:
                from engine.world.room import Room
                region.add_room("home", Room("Home", "x", {"east": "work"}, obj_id="home"))
                region.add_room("work", Room("Work", "x", {"west": "home"}, obj_id="work"))
                
                npc.current_region_id = "town"
                npc.current_room_id = "home"
                
                # Update
                npc.update(self.world, time.time())
                
                # Assert
                self.assertEqual(npc.current_room_id, "work")

    def test_dialogue_quest_prereq(self):
        """Verify topics are hidden/shown based on quest state."""
        km = self.game.knowledge_manager
        km.topics["secret"] = {
            "display_name": "Secret",
            "responses": [
                {"text": "Secret Info", "conditions": {"quest_state": {"state": "completed", "id_pattern": "q1"}}, "priority": 10},
                {"text": "Go away", "conditions": {}, "priority": 0}
            ]
        }
        
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc and self.player:
            # 1. Pre-Quest
            resp1 = km.get_response(npc, "secret", self.player)
            self.assertIn("Go away", resp1)
            
            # 2. Complete Quest
            assert self.player.runtime_state.quests is not None
            self.player.runtime_state.quests.completed["q1"] = {"state": "completed"}
            
            # 3. Post-Quest
            resp2 = km.get_response(npc, "secret", self.player)
            self.assertIn("Secret Info", resp2)

    def test_default_dialogue_fallback(self):
        """Verify NPC falls back to default dialog if no topic match."""
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc:
            npc.default_dialog = "I have nothing to say."
            resp = npc.talk("unknown_topic_123")
            self.assertIn("nothing to say", resp)

    def test_faction_hostility_matrix(self):
        """Verify faction relationships (Hostile vs Player)."""
        from engine.npcs.combat import get_relation_to
        
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        villager = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        
        if goblin and villager and self.player:
            # Goblin vs Player -> -100
            self.assertEqual(get_relation_to(goblin, self.player), -100)
            
            # Villager vs Player -> 100 (Friendly)
            self.assertEqual(get_relation_to(villager, self.player), 100)
            
            # Goblin vs Villager -> -100 (Hostile vs Friendly)
            self.assertEqual(get_relation_to(goblin, villager), -100)

    def test_npc_drops_gold(self):
        """Verify NPCs drop gold on death."""
        if not self.player: return

        npc = NPCFactory.create_npc_from_template("bandit", self.world)
        if npc:
            npc.loot_table = {"gold_value": {"chance": 1.0, "quantity": [10, 10]}}
            npc.current_region_id = "town"
            npc.current_room_id = "town_square"
            
            self.player.runtime_state.gold = 0
            
            # Ensure NPC dies
            npc.health = 1
            
            with patch('random.random', return_value=0.0): # Hit chance
                with patch('random.randint', return_value=10): # Gold amount (also used for damage, so it ensures kill)
                     self.player.attack(npc, self.world)
                 
            self.assertEqual(self.player.runtime_state.gold, 10)

    def test_npc_drops_loot_table(self):
        """Verify correct items drop from loot table."""
        npc = NPCFactory.create_npc_from_template("goblin", self.world)
        self.world.item_templates["drop_item"] = {"type": "Item", "name": "Drop"}
        
        if npc:
            npc.loot_table = {"drop_item": {"chance": 1.0, "quantity": [1, 1]}}
            npc.current_region_id = "town"
            npc.current_room_id = "town_square"
            # Isolate this test to the manual loot_table: with random.random()
            # patched to always "hit", the content-authored ambient loot pools
            # would otherwise also trigger for this goblin's tags.
            self.world.content_set.ruleset["loot"] = {"ambient_pools": []}

            with patch('random.random', return_value=0.0):
                dropped = npc.die(self.world)

            self.assertEqual(len(dropped), 1)
            self.assertEqual(dropped[0].name, "Drop")

    def test_merchant_buy_sell_loop_profit(self):
        """Verify player cannot profit by buying and immediately selling items."""
        if not self.player: return

        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: return
        
        self.world.add_npc(merchant)
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        
        self.world.item_templates["widget"] = {"type": "Item", "name": "Widget", "value": 100}
        
        # Setup properties
        merchant.properties["is_vendor"] = True
        merchant.properties["sells_items"] = [{"item_id": "widget", "price_multiplier": 2.0}] # Buy for 200
        merchant.properties["buys_item_types"] = ["Item"]
        
        # 1. Buy
        self.player.runtime_state.gold = 1000
        self.player.trading_with = merchant.obj_id
        self.game.process_command("buy Widget")
        
        # Cost: 100 * 2.0 = 200
        self.assertEqual(self.player.runtime_state.gold, 800)
        
        # 2. Sell
        # Sell Price: 100 * 0.4 (default) = 40
        self.game.process_command("sell Widget")
        
        self.assertEqual(self.player.runtime_state.gold, 840)
        
        # Net loss: 160 gold. Correct.

    def test_quest_board_generation(self):
        """Verify board populates with quests."""
        self.world.quest_board = []
        self.world.quest_manager.ensure_initial_quests()
        self.assertGreater(len(self.world.quest_board), 0)

    def test_quest_turnin_xp(self):
        """Verify XP is awarded on quest turn-in."""
        if not self.player: return

        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if npc:
            self.world.add_npc(npc)
            q_id = "xp_quest"
            self.player.quest_log[q_id] = {
                "instance_id": q_id, "state": "ready_to_complete", 
                "rewards": {"xp": 500}, "giver_instance_id": npc.obj_id
            }
            
            start_xp = self.player.runtime_state.progression.experience
            
            # Act
            self.game.process_command(f"talk {npc.name} complete")
            
            # Assert
            self.assertEqual(self.player.runtime_state.progression.experience, start_xp + 500)

    def test_guide_npc_behavior(self):
        """Verify NPC guidance command initiates auto-travel."""
        if not self.player: return

        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if npc:
            self.world.add_npc(npc)
            # Mock a quest linking them
            self.player.quest_log["q1"] = {
                "instance_id": "q1", "type": "instance", "giver_instance_id": npc.obj_id,
                "entry_point": {"region_id": "town", "room_id": "destination"}
            }
            
            # Setup path
            region = self.world.get_region("town")
            if region:
                from engine.world.room import Room
                region.add_room("destination", Room("Dest", "x", obj_id="destination"))
                # Link
                ts = region.get_room("town_square")
                if ts: ts.exits["north"] = "destination"
                
                self.player.current_region_id = "town"
                self.player.current_room_id = "town_square"
                
                # Act
                res = self.game.process_command(f"guide {npc.name}")
                
                # Assert
                self.assertTrue(self.game.is_auto_traveling)
