# tests/singles/test_tcp_abrupt_disconnect.py
"""A client that resets the connection does not put a traceback in the server's log.

A port check (the launcher's, or any monitor's) connects and hangs up at once; on Windows the
hang-up arrives as a reset while the server is still sending its greeting or closing the
stream. The handler let that surface as "Unhandled exception in client_connected_cb". The
session is still cleaned up; nothing else about a dropped connection changes.
"""

import asyncio
import socket
import struct
import unittest

from poc_server import JsonLineMudServer as _JsonLineMudServer
from tests.fixtures import FANTASY_FRONTIER


class JsonLineMudServer(_JsonLineMudServer):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, content_set_path=FANTASY_FRONTIER, **kwargs)


class TestAbruptDisconnect(unittest.IsolatedAsyncioTestCase):
    async def test_a_reset_connection_is_not_an_unhandled_error(self) -> None:
        app = JsonLineMudServer("127.0.0.1", 0, "test_save.json")
        problems = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: problems.append(context))
        server = await asyncio.start_server(app._handle_client, "127.0.0.1", 0)
        host, port = server.sockets[0].getsockname()[:2]
        for _ in range(5):
            raw = socket.create_connection((host, port), timeout=2)
            raw.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))   # close with a reset
            raw.close()
        await asyncio.sleep(1.0)
        server.close()
        await server.wait_closed()
        # asyncio itself may log a reset on the accept side (WinError 64); the handler must not.
        ours = [p for p in problems if "client_connected_cb" in str(p.get("message"))]
        self.assertEqual([], [str(p.get("exception")) for p in ours])
        self.assertEqual({}, app._session_writers, "and every session was cleaned up")


if __name__ == "__main__":
    unittest.main()
