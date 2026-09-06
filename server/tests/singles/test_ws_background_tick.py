import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock

from poc_ws_server import JsonWebSocketMudServer


FANTASY_FRONTIER = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class _RecordingTransport:
    def __init__(self) -> None:
        self.events = []

    async def send_event(self, event) -> None:
        self.events.append(event)


class TestWebSocketBackgroundTick(unittest.IsolatedAsyncioTestCase):
    async def test_idle_connected_session_drives_background_tick(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(FANTASY_FRONTIER),
        )
        app.core.server.tick_dt = 0.01
        session = app.core.server.create_session()
        app.core.server.mark_session_connected(session.session_id)
        app._ws_sessions[session.session_id] = _RecordingTransport()
        tick = Mock(return_value=[])
        app.core.server.tick = tick

        task = asyncio.create_task(app._run_background_ticks())
        try:
            await asyncio.sleep(0.04)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            app._ws_sessions.clear()
            app.shutdown()

        self.assertGreaterEqual(tick.call_count, 1)
        self.assertEqual(session.session_id, tick.call_args.args[0])


if __name__ == "__main__":
    unittest.main()