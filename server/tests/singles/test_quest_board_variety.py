# tests/singles/test_quest_board_variety.py
from tests.fixtures import GameTestBase

class TestQuestBoardVariety(GameTestBase):

    def test_board_refill_uniqueness(self):
        """Verify the board doesn't offer quests the player already has."""
        qm = self.world.quest_manager
        
        # 1. Clear everything
        self.world.quest_board = []
        self.player.quest_log = {}
        
        # 2. Add a specific hostile for the generator
        self.world.npc_templates["target_rat"] = {"name": "Rat", "faction": "hostile", "level": 1}
        
        # 3. Accept a quest
        qm.ensure_initial_quests()
        self.assertGreater(len(self.world.quest_board), 0)
        
        quest = self.world.quest_board[0]
        quest_id = quest["instance_id"]
        
        # Process acceptance
        self.player.quest_log[quest_id] = quest
        self.world.quest_board.pop(0)
        
        # 4. Refill board
        qm.ensure_initial_quests()
        
        # 5. Assert the accepted quest is not back on the board
        board_ids = [q["instance_id"] for q in self.world.quest_board]
        self.assertNotIn(quest_id, board_ids, "Accepted quest should not reappear on the board.")

    def test_variety_logic(self):
        """Verify board attempts to provide different types of quests."""
        qm = self.world.quest_manager
        self.world.quest_board = []
        
        # Ensure sufficient templates
        self.world.npc_templates["target"] = {"name": "Target", "faction": "hostile", "level": 1}
        self.world.item_templates["item_a"] = {"name": "Item A", "type": "Junk", "value": 1}
        
        qm.ensure_initial_quests()
        
        # Check types in stages[0]
        types_on_board = set()
        for q in self.world.quest_board:
            if "stages" in q and q["stages"]:
                types_on_board.add(q["stages"][0]["objective"].get("type"))
                
        self.assertGreaterEqual(len(types_on_board), 2, "Quest board should prioritize variety.")
