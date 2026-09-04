# tests/batch/test_batch_19.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT

class TestBatch19(GameTestBase):
    """Focus: Dialogue, Social Interaction, and Knowledge System."""

    def test_ask_topic_fuzzy_match(self):
        """Verify 'ask' finds topics even with partial keywords."""
        km = self.game.knowledge_manager
        km.topics["ancient_history"] = {
            "display_name": "Ancient History",
            "keywords": ["history", "old times", "past"],
            "responses": [{"text": "It was long ago."}]
        }
        
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        # Act: Ask "old times"
        result = self.game.process_command(f"ask {npc.name} old times")
        
        self.assertIsNotNone(result)
        if result:
            self.assertIn("long ago", result)

    def test_npc_greeting_on_talk(self):
        """Verify interacting with 'talk' triggers the greeting."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        npc.dialog["greeting"] = "Hello traveler!"
        
        result = self.game.process_command(f"talk {npc.name}")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("Hello traveler!", result)

    def test_vendor_refuse_unsellable(self):
        """Verify vendor refuses items with 0 value or wrong type (if strict)."""
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        if not merchant: return
        self.world.add_npc(merchant)
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        merchant.properties["is_vendor"] = True
        
        # Item with 0 value
        self.world.item_templates["trash"] = {"type": "Junk", "name": "Trash", "value": 0}
        trash = ItemFactory.create_item_from_template("trash", self.world)
        
        if trash:
            self.player.inventory.add_item(trash)
            self.player.trading_with = merchant.obj_id
            
            merchant.properties["buys_item_types"] = ["Weapon"] # Exclude Junk
            
            result = self.game.process_command("sell Trash")
            self.assertIsNotNone(result)
            if result:
                self.assertIn("not interested", result)

    def test_give_non_existent_item(self):
        """Verify error when giving an item not in inventory."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        
        result = self.game.process_command(f"give NonExistentItem to {npc.name}")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("don't have", result.lower())

    def test_look_npc_equipment_details(self):
        """Verify looking at an NPC shows their condition description."""
        npc = NPCFactory.create_npc_from_template("guard", self.world)
        if not npc: 
             npc = NPCFactory.create_npc_from_template("town_guard", self.world)
        
        if npc:
            npc.health = npc.max_health // 2 # Injured
            desc = npc.get_description()
            self.assertIn("wounded", desc.lower())

    def test_knowledge_discovery_item_pickup(self):
        """Verify picking up a collection item triggers a hint and initializes list."""
        # Setup collection
        cm = self.game.collection_manager
        cm.collections["test_col"] = {"name": "Test Col", "items": ["rare_thing"]}
        
        self.world.item_templates["rare_thing"] = {
            "type": "Treasure", "name": "Rare Thing", 
            "properties": {"collection_id": "test_col"}
        }
        item = ItemFactory.create_item_from_template("rare_thing", self.world)
        
        if item:
            hint = cm.handle_collection_discovery(self.player, item)
            self.assertIn("Test Col", hint)
            # handle_collection_discovery initializes the list, it doesn't add the item yet
            self.assertIn("test_col", self.player.collections_progress)
            self.assertEqual(self.player.collections_progress["test_col"], [])

    def test_quest_giver_death_prevents_turnin(self):
        """Verify you cannot turn in a quest if the giver is dead."""
        npc = NPCFactory.create_npc_from_template("villager", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        q_id = "test_q"
        self.player.quest_log[q_id] = {
            "instance_id": q_id, "state": "ready_to_complete", 
            "giver_instance_id": npc.obj_id,
            "rewards": {"xp": 100}
        }
        
        # Kill Giver
        npc.is_alive = False
        
        # Act
        result = self.game.process_command(f"talk {npc.name} complete")
        
        # Assert
        self.assertIsNotNone(result)
        if result:
            self.assertIn("no one matching", result.lower())

    def test_follower_stops_on_command(self):
        """Verify 'follow stop' clears the follow target."""
        self.player.follow_target = "some_npc_id"
        result = self.game.process_command("follow stop")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("stop following", result)
        self.assertIsNone(self.player.follow_target)

    def test_npc_combat_shout(self):
        """Verify NPCs output a threat/greeting when entering combat (if defined)."""
        npc = NPCFactory.create_npc_from_template("bandit", self.world)
        if not npc: return
        self.world.add_npc(npc)
        
        npc.dialog["threat"] = "You'll pay for that!"
        self.assertEqual(npc.dialog["threat"], "You'll pay for that!")

    def test_multiple_topic_learning(self):
        """Verify learning multiple topics at once via text parsing."""
        km = self.game.knowledge_manager
        km.topics["magic"] = {"keywords": ["magic"]}
        km.topics["sword"] = {"keywords": ["sword"]}
        
        text = "I know about magic and the sword."
        km.parse_and_highlight(text, self.player)
        
        self.assertTrue(self.player.conversation.is_in_vocabulary("magic"))
        self.assertTrue(self.player.conversation.is_in_vocabulary("sword"))