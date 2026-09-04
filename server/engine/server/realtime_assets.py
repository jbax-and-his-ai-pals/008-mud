from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import time
from typing import Any, Callable

_ALLOWED_SVG_COLORS = {
    "black",
    "white",
    "#000",
    "#fff",
    "#000000",
    "#ffffff",
    "none",
    "transparent",
}

_SVG_COLOR_ATTR_PATTERN = re.compile(r"(fill|stroke)\s*=\s*(['\"])\s*([^'\"]+?)\s*\2", re.IGNORECASE)
_SVG_STYLE_PATTERN = re.compile(r"style\s*=\s*(['\"])\s*([^'\"]+?)\s*\1", re.IGNORECASE)


class RealtimeAssetService:
    def __init__(
        self,
        event_builder: Callable[[str, str, Any], dict[str, Any]],
        asset_db_path: str = ":memory:",
        max_svg_bytes: int = 16 * 1024,
        lock_lease_seconds: float = 30.0,
    ) -> None:
        self._event = event_builder
        self.max_svg_bytes = max_svg_bytes
        self.lock_lease_seconds = lock_lease_seconds
        self._assets: dict[str, dict[str, Any]] = {}
        self._asset_locks: dict[str, dict[str, Any]] = {}
        self._asset_db = sqlite3.connect(asset_db_path, check_same_thread=False)
        self._init_asset_db()
        self._load_assets_from_db()

    def close(self) -> None:
        self._asset_db.close()

    def build_svg_test_payload(self) -> dict[str, Any]:
        raw_svg = (
            "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'>"
            "<rect width='32' height='32' fill='white'/>"
            "<rect x='2' y='2' width='28' height='28' fill='black'/>"
            "<circle cx='16' cy='16' r='8' fill='white'/>"
            "<rect x='15' y='7' width='2' height='18' fill='black'/>"
            "</svg>"
        )
        svg = self.sanitize_svg(raw_svg)
        payload = self._payload_from_svg("test_glyph_001", 1, svg, "A circular emblem with a vertical slit through the center.")
        self._set_asset(payload)
        return payload

    def handle_asset_update(self, session_id: str, envelope: dict[str, Any]) -> list[dict[str, Any]]:
        self._expire_stale_locks()
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            return [self._event("error", session_id, "asset_update payload must be an object")]
        asset_id = str(payload.get("asset_id", "")).strip()
        if not asset_id:
            return [self._event("error", session_id, "asset_update missing asset_id")]
        if asset_id not in self._assets:
            return [self._event("error", session_id, f"unknown asset_id '{asset_id}'")]
        lock = self._asset_locks.get(asset_id)
        if lock and lock.get("owner_session_id") != session_id:
            return [self._event("asset_update_rejected", session_id, {"asset_id": asset_id, "reason": "locked", "owner_session_id": lock.get("owner_session_id")})]
        current = self._assets[asset_id]
        current_revision = int(current.get("revision", 0))
        base_revision = int(payload.get("base_revision", -1))
        if base_revision != current_revision:
            return [self._event("asset_update_rejected", session_id, {"asset_id": asset_id, "expected_revision": current_revision, "provided_base_revision": base_revision})]
        try:
            svg = self.sanitize_svg(str(payload.get("svg", "")))
        except ValueError as exc:
            return [self._event("error", session_id, f"invalid svg: {exc}")]
        updated = self._payload_from_svg(asset_id, current_revision + 1, svg, str(payload.get("alt_text", current.get("alt_text", "Decorative image"))))
        self._set_asset(updated)
        return [self._event("asset_update_accepted", session_id, {"asset_id": asset_id, "revision": updated["revision"]}), self._event("asset", session_id, updated)]

    def handle_lock_acquire(self, session_id: str, envelope: dict[str, Any]) -> list[dict[str, Any]]:
        self._expire_stale_locks()
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            return [self._event("error", session_id, "lock_acquire payload must be an object")]
        asset_id = str(payload.get("asset_id", "")).strip()
        if not asset_id:
            return [self._event("error", session_id, "lock_acquire missing asset_id")]
        if asset_id not in self._assets:
            return [self._event("error", session_id, f"unknown asset_id '{asset_id}'")]
        lock = self._asset_locks.get(asset_id)
        if lock and lock.get("owner_session_id") != session_id:
            return [self._event("lock_denied", session_id, {"asset_id": asset_id, "owner_session_id": lock.get("owner_session_id")})]
        expires_at = time.time() + self.lock_lease_seconds
        self._asset_locks[asset_id] = {"owner_session_id": session_id, "expires_at": expires_at}
        return [self._event("lock_acquired", session_id, {"asset_id": asset_id, "expires_at": expires_at}), self._event("lock_state_delta", session_id, {"asset_id": asset_id, "owner_session_id": session_id, "expires_at": expires_at, "state": "acquired"})]

    def handle_lock_release(self, session_id: str, envelope: dict[str, Any]) -> list[dict[str, Any]]:
        self._expire_stale_locks()
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            return [self._event("error", session_id, "lock_release payload must be an object")]
        asset_id = str(payload.get("asset_id", "")).strip()
        if not asset_id:
            return [self._event("error", session_id, "lock_release missing asset_id")]
        lock = self._asset_locks.get(asset_id)
        if not lock:
            return [self._event("lock_released", session_id, {"asset_id": asset_id, "released": False})]
        if lock.get("owner_session_id") != session_id:
            return [self._event("lock_denied", session_id, {"asset_id": asset_id, "reason": "not_owner"})]
        self._asset_locks.pop(asset_id, None)
        return [self._event("lock_released", session_id, {"asset_id": asset_id, "released": True}), self._event("lock_state_delta", session_id, {"asset_id": asset_id, "owner_session_id": None, "expires_at": 0.0, "state": "released"})]

    def handle_lock_renew(self, session_id: str, envelope: dict[str, Any]) -> list[dict[str, Any]]:
        self._expire_stale_locks()
        payload = envelope.get("payload", {})
        if not isinstance(payload, dict):
            return [self._event("error", session_id, "lock_renew payload must be an object")]
        asset_id = str(payload.get("asset_id", "")).strip()
        if not asset_id:
            return [self._event("error", session_id, "lock_renew missing asset_id")]
        lock = self._asset_locks.get(asset_id)
        if not lock:
            return [self._event("lock_denied", session_id, {"asset_id": asset_id, "reason": "no_lock"})]
        if lock.get("owner_session_id") != session_id:
            return [self._event("lock_denied", session_id, {"asset_id": asset_id, "reason": "not_owner"})]
        expires_at = time.time() + self.lock_lease_seconds
        lock["expires_at"] = expires_at
        return [self._event("lock_renewed", session_id, {"asset_id": asset_id, "expires_at": expires_at}), self._event("lock_state_delta", session_id, {"asset_id": asset_id, "owner_session_id": session_id, "expires_at": expires_at, "state": "renewed"})]

    def build_lock_state_payload(self) -> dict[str, Any]:
        self._expire_stale_locks()
        return {
            "locks_ephemeral": True,
            "active_locks": [
                {"asset_id": aid, "owner_session_id": str(l.get("owner_session_id", "")), "expires_at": float(l.get("expires_at", 0.0))}
                for aid, l in self._asset_locks.items()
            ],
        }

    def release_locks_for_session(self, session_id: str) -> list[dict[str, Any]]:
        self._expire_stale_locks()
        owner = str(session_id).strip()
        if owner == "":
            return []
        released: list[dict[str, Any]] = []
        for asset_id, lock in list(self._asset_locks.items()):
            if str(lock.get("owner_session_id", "")) != owner:
                continue
            self._asset_locks.pop(asset_id, None)
            released.append(
                {
                    "asset_id": str(asset_id),
                    "owner_session_id": None,
                    "expires_at": 0.0,
                    "state": "released_disconnect",
                }
            )
        return released

    def sanitize_svg(self, svg: str) -> str:
        if not isinstance(svg, str):
            raise ValueError("SVG must be a string")
        if len(svg.encode("utf-8")) > self.max_svg_bytes:
            raise ValueError("SVG exceeds max byte size")
        lowered = svg.lower()
        if "<svg" not in lowered:
            raise ValueError("SVG root tag missing")
        for pattern in [r"<\s*script", r"on\w+\s*=", r"<\s*foreignobject", r"javascript:"]:
            if re.search(pattern, lowered):
                raise ValueError("SVG contains blocked content")
        self._validate_1bit_palette(svg)
        return svg

    def _validate_1bit_palette(self, svg: str) -> None:
        violations: list[str] = []
        for match in _SVG_COLOR_ATTR_PATTERN.finditer(svg):
            color = match.group(3).strip().lower()
            if color not in _ALLOWED_SVG_COLORS:
                violations.append(f"{match.group(1).lower()}={color}")
        for style_match in _SVG_STYLE_PATTERN.finditer(svg):
            style_text = style_match.group(2)
            for part in style_text.split(";"):
                if ":" not in part:
                    continue
                key, raw_value = part.split(":", 1)
                css_key = key.strip().lower()
                if css_key not in {"fill", "stroke"}:
                    continue
                css_value = raw_value.strip().lower()
                if css_value not in _ALLOWED_SVG_COLORS:
                    violations.append(f"{css_key}={css_value}")
        if violations:
            raise ValueError("SVG contains non-1-bit colors: " + ", ".join(sorted(set(violations))))

    def _payload_from_svg(self, asset_id: str, revision: int, svg: str, alt_text: str) -> dict[str, Any]:
        return {
            "asset_type": "svg_1bit",
            "asset_id": asset_id,
            "revision": revision,
            "checksum_sha256": hashlib.sha256(svg.encode("utf-8")).hexdigest(),
            "byte_length": len(svg.encode("utf-8")),
            "svg": svg,
            "alt_text": alt_text,
        }

    def _expire_stale_locks(self) -> None:
        now = time.time()
        for aid in [k for k, v in self._asset_locks.items() if float(v.get("expires_at", 0.0)) <= now]:
            self._asset_locks.pop(aid, None)

    def _init_asset_db(self) -> None:
        self._asset_db.execute("CREATE TABLE IF NOT EXISTS assets (asset_id TEXT PRIMARY KEY, payload_json TEXT NOT NULL)")
        self._asset_db.commit()

    def _load_assets_from_db(self) -> None:
        for asset_id, payload_json in self._asset_db.execute("SELECT asset_id, payload_json FROM assets").fetchall():
            try:
                payload = json.loads(payload_json)
            except json.JSONDecodeError:
                continue
            if isinstance(payload, dict):
                self._assets[str(asset_id)] = payload

    def _set_asset(self, payload: dict[str, Any]) -> None:
        aid = str(payload["asset_id"])
        self._assets[aid] = payload
        self._asset_db.execute("INSERT OR REPLACE INTO assets(asset_id, payload_json) VALUES(?, ?)", (aid, json.dumps(payload)))
        self._asset_db.commit()
