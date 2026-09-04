# tests/singles/test_quests.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory

class TestQuests(GameTestBase):

    def test_quest_lifecycle_kill(self):
        """Verify full lifecycle of a Kill quest (Saga structure)."""
        # 1. Setup Board with Saga Structure
        quest_id = "test_kill_quest"
        objective_data = {
            "type": "kill",
            "target_template_id": "giant_rat",
            "required_quantity": 1,
            "current_quantity": 0
        }
        
        # New Schema
        quest_data = {
            "instance_id": quest_id,
            "title": "Kill Rats",
            "type": "kill",
            "giver_instance_id": "quest_board",
            "current_stage_index": 0,
            "rewards": {"xp": 100},
            "objective": objective_data, # Sync top-level
            "stages": [
                {
                    "stage_index": 0,
                    "description": "Kill the rats.",
                    "turn_in_id": "quest_board",
                    "objective": objective_data
                }
            ]
        }
        
        self.world.quest_board = [quest_data]
        
        # Mock player location for board access
        self.world.quest_manager.config["quest_board_locations"] = ["town:town_square"]
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        
        # 2. Accept
        self.game.process_command("accept quest 1")
        self.assertIn(quest_id, self.player.runtime_state.quests.active)
        
        # 3. Complete Objective
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world)
        if rat:
            self.world.dispatch_event("npc_killed", {"player": self.player, "npc": rat})
            
            # Check state
            self.assertEqual(self.player.runtime_state.quests.active[quest_id]["state"], "ready_to_complete")

    def test_quest_fetch_mechanics(self):
        """Verify Fetch quests remove items from inventory."""
        self.world.npcs = {}

        # 1. Setup Quest manually in log
        quest_id = "test_fetch"
        giver = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="elder_1")
        
        if giver:
            self.world.add_npc(giver)
            giver.current_region_id = self.player.current_region_id
            giver.current_room_id = self.player.current_room_id
            
            objective_data = {"type": "fetch", "item_id": "item_iron_ingot", "required_quantity": 1}

            # Saga Structure
            self.player.runtime_state.quests.active[quest_id] = {
                "instance_id": quest_id,
                "type": "fetch",
                "state": "active",
                "giver_instance_id": "elder_1",
                "current_stage_index": 0,
                "rewards": {"gold": 100},
                "objective": objective_data, # Sync top-level
                "stages": [
                    {
                        "stage_index": 0,
                        "turn_in_id": "elder_1",
                        "objective": objective_data
                    }
                ]
            }
            
            # 2. Give Items
            ingot = ItemFactory.create_item_from_template("item_iron_ingot", self.world)
            if ingot: self.player.inventory.add_item(ingot)
            
            # 3. Turn In
            result = self.game.process_command(f"talk {giver.name} complete")
            
            # 4. Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("Quest Complete", result)
            
            self.assertEqual(self.player.inventory.count_item("item_iron_ingot"), 0)
            self.assertEqual(self.player.runtime_state.gold, 100)

    def test_quest_deliver_mechanics(self):
        """Verify Deliver quests work with 'give' command."""
        # 1. Setup Recipient
        recipient = NPCFactory.create_npc_from_template("tavern_keeper", self.world, instance_id="recipient_1")
        if recipient:
            self.world.add_npc(recipient)
            recipient.current_region_id = self.player.current_region_id
            recipient.current_room_id = self.player.current_room_id

            # 2. Setup Quest
            package_id = "pkg_123"
            objective_data = {
                "type": "deliver",
                "item_instance_id": package_id,
                "recipient_instance_id": "recipient_1",
                "item_to_deliver_name": "Package"
            }

            self.player.runtime_state.quests.active["test_deliver"] = {
                "instance_id": "test_deliver",
                "type": "deliver",
                "state": "active",
                "current_stage_index": 0,
                "giver_instance_id": "sender",
                "rewards": {"xp": 50},
                "objective": objective_data, # Sync top-level so give_handler finds it
                "stages": [
                    {
                        "stage_index": 0,
                        "turn_in_id": "recipient_1",
                        "objective": objective_data
                    }
                ]
            }
            
            # 3. Add Package to Inventory
            package = ItemFactory.create_item_from_template("quest_package_generic", self.world)
            if package:
                package.obj_id = package_id
                package.name = "Package"
                self.player.inventory.add_item(package)
                
            # 4. Deliver
            result = self.game.process_command(f"give Package to {recipient.name}")
            
            # 5. Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("Quest Complete", result)
            
            self.assertIsNone(self.player.inventory.find_item_by_id(package_id))
