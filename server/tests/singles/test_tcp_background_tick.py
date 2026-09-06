import asyncio
import unittest
from pathlib import Path
from unittest.mock import Mock

from poc_server import JsonLineMudServer


FANTASY_FRONTIER = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier"


class TestTcpBackgroundTick(unittest.IsolatedAsyncioTestCase):
    async def test_idle_connected_session_drives_background_tick(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(FANTASY_FRONTIER),
        )
        app.server.tick_dt = 0.01
        session = app.server.create_session()
        app.server.mark_session_connected(session.session_id)
        app._session_writers[session.session_id] = object()  # No output events in this probe.
        tick = Mock(return_value=[])
        app.server.tick = tick

        task = asyncio.create_task(app._run_background_ticks())
        try:
            await asyncio.sleep(0.04)
        finally:
            task.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await task
            app._session_writers.clear()
            app.shutdown()

        self.assertGreaterEqual(tick.call_count, 1)
        self.assertEqual(session.session_id, tick.call_args.args[0])


if __name__ == "__main__":
    unittest.main()