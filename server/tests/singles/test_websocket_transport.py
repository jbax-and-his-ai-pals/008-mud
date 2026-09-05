# tests/singles/test_websocket_transport.py
"""Coverage for engine/server/transport/websocket_transport.py: codec
property, negotiate_codec's already-negotiated short-circuit, decode's
non-dict-msgpack rejection and the no-msgpack byte fallback, encode's
no-msgpack fallback, send_events, and the module-level msgpack-unavailable
import guard."""

import asyncio
import importlib
import sys
import unittest
from unittest.mock import patch, MagicMock

import engine.server.transport.websocket_transport as ws_transport_module
from engine.server.transport.websocket_transport import WebSocketTransport


class TestWebSocketTransport(unittest.TestCase):
    def test_codec_property_returns_current_codec(self):
        transport = WebSocketTransport(websocket=None, codec="json")
        self.assertEqual(transport.codec, "json")

    def test_negotiate_codec_is_a_noop_once_already_negotiated(self):
        transport = WebSocketTransport(websocket=None)
        transport.negotiate_codec(b"\x00binary")
        self.assertEqual(transport.codec, "msgpack")
        # A second call, even with a str, must not re-negotiate.
        transport.negotiate_codec("some text")
        self.assertEqual(transport.codec, "msgpack")

    def test_decode_msgpack_non_dict_raises_value_error(self):
        transport = WebSocketTransport(websocket=None, codec="msgpack")
        packed = ws_transport_module._msgpack.packb([1, 2, 3], use_bin_type=True)
        with self.assertRaises(ValueError):
            transport.decode(packed)

    def test_decode_bytes_falls_back_to_utf8_json_when_msgpack_unavailable(self):
        transport = WebSocketTransport(websocket=None, codec="json")
        with patch.object(ws_transport_module, "MSGPACK_AVAILABLE", False):
            result = transport.decode(b'{"type": "hello"}')
        self.assertEqual(result, {"type": "hello"})

    def test_encode_falls_back_to_json_when_msgpack_unavailable(self):
        transport = WebSocketTransport(websocket=None, codec="msgpack")
        with patch.object(ws_transport_module, "MSGPACK_AVAILABLE", False):
            encoded = transport.encode({"type": "hello"})
        self.assertIsInstance(encoded, str)
        self.assertIn("hello", encoded)

    def test_send_events_sends_each_event_in_order(self):
        mock_ws = MagicMock()
        mock_ws.send = unittest.mock.AsyncMock()
        transport = WebSocketTransport(websocket=mock_ws, codec="json")
        events = [{"type": "a"}, {"type": "b"}]

        asyncio.run(transport.send_events(events))

        self.assertEqual(mock_ws.send.await_count, 2)


class TestMsgpackAvailabilityImportGuard(unittest.TestCase):
    def test_msgpack_unavailable_skips_module_level_import(self):
        import engine.server.transport.base as base_module
        try:
            with patch.dict(sys.modules, {"msgpack": None}):
                importlib.reload(base_module)
                importlib.reload(ws_transport_module)
                self.assertFalse(ws_transport_module.MSGPACK_AVAILABLE)
        finally:
            # Restore real msgpack availability now that the fake ImportError
            # is no longer in effect, so later tests see the real module.
            importlib.reload(base_module)
            importlib.reload(ws_transport_module)


if __name__ == "__main__":
    unittest.main()
