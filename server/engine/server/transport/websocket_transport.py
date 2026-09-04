from __future__ import annotations

import json
from typing import Any, Dict, List, Union

from engine.server.transport.base import MSGPACK_AVAILABLE, CodecName

if MSGPACK_AVAILABLE:
    import msgpack as _msgpack  # type: ignore[import]


class WebSocketTransport:
    """
    Codec-aware WebSocket transport.

    Codec is selected once per session by calling negotiate_codec() on the first
    incoming raw message.  Until then, the transport uses JSON (safe default for
    the bootstrap hello/lock_state events sent before the client speaks).

    Codec selection rules:
      - incoming bytes  → msgpack  (if MSGPACK_AVAILABLE, else json)
      - incoming str    → json

    Wire encoding:
      - json   → text frame   (str)
      - msgpack → binary frame (bytes)

    This means the server mirrors whatever codec the client initiates, giving
    zero-config fallback: a client that only speaks JSON never gets binary frames.
    """

    def __init__(self, websocket: Any, codec: CodecName = "json") -> None:
        self.websocket = websocket
        self._codec: CodecName = codec
        self._negotiated: bool = False

    @property
    def codec(self) -> CodecName:
        return self._codec

    def negotiate_codec(self, raw: Union[str, bytes]) -> None:
        """Lock the codec for this session from the first incoming raw message."""
        if self._negotiated:
            return
        self._negotiated = True
        if isinstance(raw, (bytes, bytearray)) and MSGPACK_AVAILABLE:
            self._codec = "msgpack"
        else:
            self._codec = "json"

    def decode(self, raw: Union[str, bytes]) -> Dict[str, Any]:
        """Decode a raw incoming frame into an envelope dict."""
        if isinstance(raw, (bytes, bytearray)):
            if MSGPACK_AVAILABLE:
                result = _msgpack.unpackb(raw, raw=False)
                if not isinstance(result, dict):
                    raise ValueError("msgpack decoded value is not a dict")
                return result
            # Fallback: treat bytes as UTF-8 encoded JSON.
            raw = raw.decode("utf-8", errors="replace")
        return json.loads(raw)

    def encode(self, event: Dict[str, Any]) -> Union[str, bytes]:
        """Encode an event dict to the wire format for this session's codec."""
        if self._codec == "msgpack" and MSGPACK_AVAILABLE:
            return _msgpack.packb(event, use_bin_type=True)
        return json.dumps(event)

    async def send_event(self, event: Dict[str, Any]) -> None:
        await self.websocket.send(self.encode(event))

    async def send_events(self, events: List[Dict[str, Any]]) -> None:
        for event in events:
            await self.send_event(event)

