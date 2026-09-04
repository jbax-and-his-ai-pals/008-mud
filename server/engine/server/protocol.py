from __future__ import annotations

from typing import Any, Dict, Tuple

PROTOCOL_VERSION = "0.2.0"

SERVER_EVENT_REQUIRED_FIELDS = {"type", "session_id", "payload", "server_time", "protocol_version"}
CLIENT_COMMAND_REQUIRED_FIELDS = {"type", "session_id", "command_text"}


def build_server_event(event_type: str, session_id: str, payload: Any, server_time: float) -> Dict[str, Any]:
    return {
        "type": event_type,
        "session_id": session_id,
        "payload": payload,
        "server_time": server_time,
        "protocol_version": PROTOCOL_VERSION,
    }


def validate_client_command_envelope(envelope: Dict[str, Any]) -> Tuple[bool, str]:
    missing = [field for field in CLIENT_COMMAND_REQUIRED_FIELDS if field not in envelope]
    if missing:
        return False, f"Missing fields: {', '.join(sorted(missing))}"

    if envelope.get("type") != "command":
        return False, "Envelope type must be 'command'"
    if not isinstance(envelope.get("session_id"), str) or not envelope["session_id"]:
        return False, "session_id must be a non-empty string"
    if not isinstance(envelope.get("command_text"), str):
        return False, "command_text must be a string"
    if "client_capabilities" in envelope and not isinstance(envelope.get("client_capabilities"), dict):
        return False, "client_capabilities must be an object/dict when provided"
    return True, ""

