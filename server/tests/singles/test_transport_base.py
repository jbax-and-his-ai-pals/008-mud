# tests/singles/test_transport_base.py
"""Coverage for engine/server/transport/base.py's msgpack-unavailable
fallback (lines 12-14). The rest of the module is a typing.Protocol whose
`...` method bodies are never executed -- implementations (WebSocket/TCP
transports) provide the real bodies and are covered by their own tests."""

import importlib
import sys
import unittest
from unittest.mock import patch


class TestMsgpackAvailabilityFallback(unittest.TestCase):
    def test_msgpack_import_error_sets_unavailable(self):
        import engine.server.transport.base as base_module
        try:
            with patch.dict(sys.modules, {"msgpack": None}):
                importlib.reload(base_module)
                self.assertFalse(base_module.MSGPACK_AVAILABLE)
                self.assertIsNone(base_module._msgpack)
        finally:
            # Restore real msgpack availability now that the fake ImportError
            # is no longer in effect, so later tests see the real module.
            importlib.reload(base_module)


if __name__ == "__main__":
    unittest.main()
