from __future__ import annotations

from typing import Any, Dict, List, Literal, Protocol, Union

# Supported codec identifiers.
CodecName = Literal["json", "msgpack"]

# Detect msgpack availability once at import time.
try:
    import msgpack as _msgpack  # type: ignore[import]
    MSGPACK_AVAILABLE: bool = True
except ImportError:
    _msgpack = None  # type: ignore[assignment]
    MSGPACK_AVAILABLE = False


class ServerTransport(Protocol):
    """
    Abstract transport interface.

    Implementations are responsible for:
    - Encoding events to the wire format (JSON text or MessagePack binary).
    - Sending encoded events over the underlying connection.
    - Exposing the active codec name so callers can log or branch on it.
    """

    @property
    def codec(self) -> CodecName:
        """The active codec for this transport session."""
        ...

    def negotiate_codec(self, raw: Union[str, bytes]) -> None:
        """
        Inspect an incoming raw message and lock in the codec for this session.
        Must be called exactly once, on the first incoming message.
        - bytes  → msgpack  (if MSGPACK_AVAILABLE, else falls back to json)
        - str    → json
        """
        ...

    def decode(self, raw: Union[str, bytes]) -> Dict[str, Any]:
        """Decode a raw incoming message into an envelope dict."""
        ...

    async def send_event(self, event: Dict[str, Any]) -> None:
        """Encode and send a single server event."""
        ...

    async def send_events(self, events: List[Dict[str, Any]]) -> None:
        """Encode and send multiple server events in order."""
        ...

