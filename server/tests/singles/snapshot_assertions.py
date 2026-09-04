import json
import os
import re
from pathlib import Path
from typing import Any

_HEX_SUFFIX_RE = re.compile(r"_[0-9a-f]{8}$")
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")


def _normalize(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value.keys()):
            if key in {"server_time", "session_id", "expires_at"}:
                continue
            out[key] = _normalize(value[key])
        return out
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, str):
        if _UUID_RE.match(value):
            return "<uuid>"
        if _HEX_SUFFIX_RE.search(value):
            return _HEX_SUFFIX_RE.sub("_<id>", value)
    return value


def assert_snapshot(testcase: Any, snapshot_path: str, payload: Any) -> None:
    normalized = _normalize(payload)
    path = Path(snapshot_path)

    if os.environ.get("MUD_UPDATE_SNAPSHOTS", "") == "1":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(normalized, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    testcase.assertTrue(path.exists(), f"Missing snapshot fixture: {path}")
    expected = json.loads(path.read_text(encoding="utf-8"))
    testcase.assertEqual(expected, normalized)
