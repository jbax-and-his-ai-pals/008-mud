# tests/singles/test_quest_retroactive_fetch.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory

class TestQuestRetroactiveFetch(GameTestBase):

    def test_fetch_quest_precollected_items(self):
        """Verify fetch quest updates immediately if player already has items."""
        # 1. Setup: Player gathers items BEFORE accepting quest
        self.world.item_templates["herb"] = {"type": "Item", "name": "Healing Herb", "stackable": True}
        herb = ItemFactory.create_item_from_template("herb", self.world)
        if herb:
            self.player.inventory.add_item(herb, 5)

        # 2. Define Quest
        quest_id = "herb_gather"
        quest_data = {
            "instance_id": quest_id,
            "type": "fetch",
            "title": "Herbalist",
            "objective": {
                "item_id": "herb",
                "required_quantity": 5,
                "current_quantity": 0
            },
            "giver_instance_id": "quest_board"
        }
        self.world.quest_board.append(quest_data)
        
        # 3. Accept Quest
        # We manually process acceptance to bypass 'accept quest 1' parsing for precision,
        # or just use the command if board is set up right.
        # Let's use internal logic to simulate immediate state check.
        
        self.player.runtime_state.quests.active[quest_id] = quest_data
        quest_data["state"] = "active"
        
        # 4. Trigger Update Check
        # Usually happens on item pickup, but here we just picked them up.
        # We need to manually check quest status or simulate the pickup event again?
        # The game engine usually checks on 'get'. 
        # However, many games check on accept.
        # Let's see if our logic handles "already have it".
        # Current QuestManager doesn't auto-scan inventory on accept.
        # BUT, the 'talk' command (turnin) checks inventory dynamically.
        
        # Create Giver
        giver = NPCFactory.create_npc_from_template("villager", self.world)
        if giver:
            giver.obj_id = "giver_npc"
            quest_data["giver_instance_id"] = "giver_npc"
            self.world.add_npc(giver)
            
            # 5. Attempt Turn In
            # The logic in `_handle_quest_dialogue` checks inventory count at the moment of talking.
            # So it should be ready to complete immediately.
            
            from engine.commands.interaction.npcs import _handle_quest_dialogue
            msg = _handle_quest_dialogue(self.player, giver, self.world)
            
            # 6. Assert
            self.assertIn("Quest Complete", msg, "Should be able to complete immediately if items are held.")
            self.assertEqual(self.player.inventory.count_item("herb"), 0, "Items should be consumed.")
