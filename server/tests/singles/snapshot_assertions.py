import json
import os
import re
from pathlib import Path
from typing import Any

_HEX_SUFFIX_RE = re.compile(r"_[0-9a-f]{8}$")
_UUID_RE = re.compile(r"^[0-9a-f]{32}$")

# Repo root (this file lives at <root>/server/tests/singles/). Absolute paths
# baked into payloads (e.g. content-set manifest_path/data_root) are specific
# to wherever the repo happens to be checked out, so they must be relativized
# before snapshot comparison or every clone/move breaks every snapshot test.
_REPO_ROOT = str(Path(__file__).resolve().parents[3])


def _normalize_path_prefix(value: str) -> str:
    if _REPO_ROOT and value.startswith(_REPO_ROOT):
        rest = value[len(_REPO_ROOT):].replace("\\", "/")
        return "<REPO_ROOT>" + rest
    return value


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
        return _normalize_path_prefix(value)
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
