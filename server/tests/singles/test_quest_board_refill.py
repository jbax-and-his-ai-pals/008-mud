# tests/singles/test_quest_board_refill.py
from tests.fixtures import GameTestBase

class TestQuestBoardRefill(GameTestBase):

    def test_replenish_logic(self):
        """Verify board refills up to max after a quest is taken."""
        qm = self.world.quest_manager
        
        # 1. Force Empty Board
        self.world.quest_board = []
        
        # 2. Fill Board
        qm.ensure_initial_quests()
        initial_count = len(self.world.quest_board)
        self.assertGreater(initial_count, 0)
        
        # 3. Remove one (simulate accepting)
        taken_quest = self.world.quest_board.pop(0)
        
        # 4. Replenish
        # Pass the ID of the completed quest (or None if just accepting/refilling)
        qm.replenish_board(None)
        
        # 5. Assert Refilled
        new_count = len(self.world.quest_board)
        self.assertEqual(new_count, initial_count, "Board should refill to cap.")
        if self.world.quest_board:
            self.assertNotEqual(self.world.quest_board[-1]["instance_id"], taken_quest["instance_id"], "New quest should be different.")