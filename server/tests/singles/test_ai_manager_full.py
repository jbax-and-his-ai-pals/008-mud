# tests/singles/test_ai_manager_full.py
"""Coverage for engine/ai/ai_manager.py's update2()/_worker_generate_text()
logic that test_ai_manager_validation.py's existing tests never actually
reach: update2() returns early whenever llm_interface.pipe is falsy (always
true by default, since model loading is disabled), so its queue-processing,
staleness-discard, error-text, and thread-spawn branches need pipe forced
truthy to exercise. Also covers _worker_generate_text() directly and the
remaining guard branches in _create_context_stamp/_gather_context_for_llm.

Note: _gather_context_for_llm's `if not all([player, room, region]): return
"Context Error..."` is left untested as unreachable -- the preceding `if
not player or not room or not region: return "Error."` is the exact same
condition spelled differently, so it always returns first."""

import queue
from unittest.mock import MagicMock, patch

from tests.fixtures import GameTestBase


class TestWorkerGenerateText(GameTestBase):
    def test_puts_result_package_on_queue(self):
        ai_mgr = self.game.ai_manager
        ai_mgr.llm_interface = MagicMock()
        ai_mgr.llm_interface.generate.return_value = "Generated text."
        ai_mgr._worker_generate_text("ambient_flavor_text", {"context_string": "ctx"}, {"stamp": 1})
        result = ai_mgr.result_queue.get_nowait()
        self.assertEqual("Generated text.", result["text"])
        self.assertEqual({"stamp": 1}, result["context_stamp"])
        self.assertEqual("ctx", result["full_context"])

    def test_no_llm_interface_is_a_no_op(self):
        ai_mgr = self.game.ai_manager
        ai_mgr.llm_interface = None
        ai_mgr._worker_generate_text("ambient_flavor_text", {}, {})  # must not raise
        self.assertTrue(ai_mgr.result_queue.empty())


class TestUpdate2QueueProcessing(GameTestBase):
    def setUp(self):
        super().setUp()
        self.ai_mgr = self.game.ai_manager
        self.ai_mgr.llm_interface = MagicMock()
        self.ai_mgr.llm_interface.pipe = MagicMock()  # bypass the early guard

    def test_no_pipe_returns_none_immediately(self):
        self.ai_mgr.llm_interface.pipe = None
        self.assertIsNone(self.ai_mgr.update2())

    def test_no_llm_interface_returns_none_immediately(self):
        self.ai_mgr.llm_interface = None
        self.assertIsNone(self.ai_mgr.update2())

    def test_empty_queue_falls_through_to_timer_check(self):
        result = self.ai_mgr.update2()  # must not raise
        self.assertIsNone(result)

    def test_matching_context_returns_formatted_text(self):
        stamp = self.ai_mgr._create_context_stamp()
        self.ai_mgr.result_queue.put({
            "text": "A gentle breeze stirs the leaves.", "context_stamp": stamp, "duration": 0.5,
        })
        result = self.ai_mgr.update2()
        self.assertIn("A gentle breeze stirs the leaves.", result)

    def test_matching_context_with_error_text_returns_none(self):
        stamp = self.ai_mgr._create_context_stamp()
        self.ai_mgr.result_queue.put({
            "text": "Error: something broke", "context_stamp": stamp, "duration": 0.5,
        })
        result = self.ai_mgr.update2()
        self.assertIsNone(result)

    def test_stale_context_discards_and_returns_none(self):
        stamp = self.ai_mgr._create_context_stamp()
        self.ai_mgr.result_queue.put({
            "text": "Stale text.", "context_stamp": stamp, "duration": 0.5,
        })
        self.player.current_room_id = "a_totally_different_room"
        result = self.ai_mgr.update2()
        self.assertIsNone(result)

    def test_generated_text_quotes_are_stripped(self):
        stamp = self.ai_mgr._create_context_stamp()
        self.ai_mgr.result_queue.put({
            "text": '"Quoted text."', "context_stamp": stamp, "duration": 0.5,
        })
        result = self.ai_mgr.update2()
        self.assertNotIn('"', result)
        self.assertIn("Quoted text.", result)


class TestUpdate2ThreadSpawning(GameTestBase):
    def setUp(self):
        super().setUp()
        self.ai_mgr = self.game.ai_manager
        self.ai_mgr.llm_interface = MagicMock()
        self.ai_mgr.llm_interface.pipe = MagicMock()
        self.ai_mgr.interval = 0.0  # always past the interval

    def test_spawns_generation_thread_when_interval_elapsed_and_idle(self):
        self.ai_mgr.last_ambient_event_time = 0.0
        self.ai_mgr.generation_thread = None
        with patch("engine.ai.ai_manager.threading.Thread") as MockThread:
            mock_thread_instance = MockThread.return_value
            self.ai_mgr.update2()
        MockThread.assert_called_once()
        mock_thread_instance.start.assert_called_once()
        self.assertIs(mock_thread_instance, self.ai_mgr.generation_thread)

    def test_does_not_spawn_when_thread_already_running(self):
        running_thread = MagicMock()
        running_thread.is_alive.return_value = True
        self.ai_mgr.generation_thread = running_thread
        self.ai_mgr.last_ambient_event_time = 0.0
        with patch("engine.ai.ai_manager.threading.Thread") as MockThread:
            self.ai_mgr.update2()
        MockThread.assert_not_called()

    def test_does_not_spawn_before_interval_elapses(self):
        import time
        self.ai_mgr.interval = 10_000.0
        self.ai_mgr.last_ambient_event_time = time.time()
        self.ai_mgr.generation_thread = None
        with patch("engine.ai.ai_manager.threading.Thread") as MockThread:
            self.ai_mgr.update2()
        MockThread.assert_not_called()


class TestCreateContextStampGuard(GameTestBase):
    def test_no_resolvable_player_returns_empty_dict(self):
        ai_mgr = self.game.ai_manager
        with patch.object(self.world, "resolve_reference_player", return_value=None):
            self.assertEqual({}, ai_mgr._create_context_stamp())


class TestGatherContextForLlmGuards(GameTestBase):
    def test_no_resolvable_player_returns_error_string(self):
        ai_mgr = self.game.ai_manager
        with patch.object(self.world, "resolve_reference_player", return_value=None):
            self.assertEqual("Error.", ai_mgr._gather_context_for_llm())

    def test_indoors_location_omits_weather(self):
        ai_mgr = self.game.ai_manager
        with patch.object(self.world, "is_location_outdoors", return_value=False):
            context = ai_mgr._gather_context_for_llm()
        self.assertIn("Indoors", context)
        self.assertIn("(Indoors)", context)

    def test_low_health_reports_critically_injured(self):
        ai_mgr = self.game.ai_manager
        self.player.health = int(self.player.max_health * 0.1)
        context = ai_mgr._gather_context_for_llm()
        self.assertIn("Critically Injured", context)

    def test_moderate_health_reports_injured(self):
        ai_mgr = self.game.ai_manager
        self.player.health = int(self.player.max_health * 0.5)
        context = ai_mgr._gather_context_for_llm()
        self.assertIn("Player Status: Injured", context)

    def test_full_health_reports_healthy(self):
        ai_mgr = self.game.ai_manager
        self.player.health = self.player.max_health
        context = ai_mgr._gather_context_for_llm()
        self.assertIn("Healthy", context)

    def test_in_combat_is_reported(self):
        ai_mgr = self.game.ai_manager
        self.player.runtime_state.combat.in_combat = True
        context = ai_mgr._gather_context_for_llm()
        self.assertIn("Player is in combat.", context)

    def test_no_npcs_present_reports_none(self):
        ai_mgr = self.game.ai_manager
        with patch.object(self.world, "get_current_room_npcs", return_value=[]):
            context = ai_mgr._gather_context_for_llm()
        self.assertIn("NPCs Present: None", context)


if __name__ == "__main__":
    import unittest
    unittest.main()
