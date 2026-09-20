# tests/singles/test_transport_entry_points_are_importable.py
"""Both server entry points can start in a pinned environment.

`launch_content_set.py --transport ws` selects `poc_ws_server.py`, which imports
`websockets` and raises without it. That package was in **no** requirements file
and **no** lock, so the WebSocket entry point could not start on a fresh
checkout, and nothing reported it — because the module that should have tested it
(`test_poc_ws_server.py`) was a 0-byte file.

This replaces that empty module with the thing it was named for. It is small on
purpose: the contract is "this entry point imports", and a heavier test would be
a test of `websockets` rather than of this repository's dependency list.
"""
import importlib
import importlib.util
import sys
import unittest
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[2]


def _importable(module_name: str):
    if str(SERVER_ROOT) not in sys.path:
        sys.path.insert(0, str(SERVER_ROOT))
    return importlib.import_module(module_name)


class TestTheDeclaredDependenciesArePresent(unittest.TestCase):
    def test_websockets_is_declared_in_both_dependency_files(self):
        """A dependency the entry point needs must be declared, not assumed.

        `msgpack` set this precedent: it is listed with a comment saying it is
        there so a transport test exercises the codec instead of being silently
        skipped. `websockets` was simply missed.
        """
        runtime = (SERVER_ROOT / "requirements.txt").read_text(encoding="utf-8")
        lock = (SERVER_ROOT / "requirements.lock").read_text(encoding="utf-8")
        self.assertIn("websockets", runtime, "requirements.txt must declare websockets")
        self.assertIn("websockets", lock, "requirements.lock must pin websockets")

    def test_the_package_is_actually_installed_here(self):
        self.assertIsNotNone(
            importlib.util.find_spec("websockets"),
            "install from server/requirements.txt to run this suite",
        )


class TestBothEntryPointsImport(unittest.TestCase):
    def test_the_websocket_server_imports(self):
        module = _importable("poc_ws_server")
        self.assertTrue(hasattr(module, "main") or hasattr(module, "WebSocketMudServer"),
                        "the module should expose its entry point")

    def test_the_tcp_server_imports(self):
        module = _importable("poc_server")
        self.assertTrue(hasattr(module, "main") or hasattr(module, "MudServer"),
                        "the module should expose its entry point")

    def test_the_transport_package_imports(self):
        module = _importable("engine.server.transport.websocket_transport")
        self.assertTrue(hasattr(module, "WebSocketTransport"))


if __name__ == "__main__":
    unittest.main()
