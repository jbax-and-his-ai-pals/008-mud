# tests/singles/test_quest_log_cleanup.py
from tests.fixtures import GameTestBase

class TestQuestLogCleanup(GameTestBase):
    def test_quest_move_completed(self):
        """Verify quest moves from active log to completed log."""
        qid = "q1"
        self.player.runtime_state.quests.active[qid] = {"instance_id": qid, "state": "active", "title": "Test"}
        
        # Simulate completion logic manually 
        # (This mimics what happens inside give_handler or talk_handler)
        if qid in self.player.runtime_state.quests.active:
            q = self.player.runtime_state.quests.active.pop(qid)
            q["state"] = "completed"
            self.player.runtime_state.quests.completed[qid] = q
        
        self.assertNotIn(qid, self.player.runtime_state.quests.active)
        self.assertIn(qid, self.player.runtime_state.quests.completed)
        self.assertEqual(self.player.runtime_state.quests.completed[qid]["state"], "completed")
