import unittest

from engine.server.realtime_assets import RealtimeAssetService


class TestRealtimeAssetLocks(unittest.TestCase):
    def _event(self, event_type: str, session_id: str, payload):
        return {"type": event_type, "session_id": session_id, "payload": payload}

    def test_release_locks_for_session(self) -> None:
        service = RealtimeAssetService(self._event, asset_db_path=":memory:")
        try:
            service.build_svg_test_payload()
            acquired = service.handle_lock_acquire("session_a", {"payload": {"asset_id": "test_glyph_001"}})
            self.assertTrue(any(evt["type"] == "lock_acquired" for evt in acquired))

            deltas = service.release_locks_for_session("session_a")
            self.assertEqual(1, len(deltas))
            self.assertEqual("test_glyph_001", deltas[0]["asset_id"])
            self.assertEqual("released_disconnect", deltas[0]["state"])

            state = service.build_lock_state_payload()
            self.assertEqual([], state["active_locks"])
        finally:
            service.close()


if __name__ == "__main__":
    unittest.main()
