# tests/singles/test_realtime_assets_full.py
"""Coverage for engine/server/realtime_assets.py's message handlers
(handle_asset_update, handle_lock_acquire/release/renew), the guard/error
branches in each, sanitize_svg's remaining validation paths, the style-attr
parsing edge cases in _validate_1bit_palette, lock expiry, and asset
persistence (_load_assets_from_db) -- none of which the existing lock/SVG
tests exercise directly."""

import json
import unittest
from unittest.mock import patch

from engine.server.realtime_assets import RealtimeAssetService


def _event_builder(event_type: str, session_id: str, payload):
    return {"type": event_type, "session_id": session_id, "payload": payload}


class RealtimeAssetsTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.service = RealtimeAssetService(_event_builder)

    def tearDown(self) -> None:
        self.service.close()

    def _event_types(self, events):
        return [e["type"] for e in events]


class TestHandleAssetUpdate(RealtimeAssetsTestBase):
    def test_non_dict_payload_reports_error(self):
        events = self.service.handle_asset_update("s1", {"payload": "not_a_dict"})
        self.assertEqual(["error"], self._event_types(events))
        self.assertIn("must be an object", events[0]["payload"])

    def test_missing_asset_id_reports_error(self):
        events = self.service.handle_asset_update("s1", {"payload": {}})
        self.assertEqual(["error"], self._event_types(events))
        self.assertIn("missing asset_id", events[0]["payload"])

    def test_unknown_asset_id_reports_error(self):
        events = self.service.handle_asset_update("s1", {"payload": {"asset_id": "ghost"}})
        self.assertEqual(["error"], self._event_types(events))
        self.assertIn("unknown asset_id", events[0]["payload"])

    def test_locked_by_other_session_is_rejected(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        events = self.service.handle_asset_update(
            "intruder", {"payload": {"asset_id": "test_glyph_001", "base_revision": 1, "svg": "<svg></svg>"}},
        )
        self.assertEqual(["asset_update_rejected"], self._event_types(events))
        self.assertEqual("locked", events[0]["payload"]["reason"])

    def test_stale_base_revision_is_rejected(self):
        self.service.build_svg_test_payload()
        events = self.service.handle_asset_update(
            "s1", {"payload": {"asset_id": "test_glyph_001", "base_revision": 999, "svg": "<svg></svg>"}},
        )
        self.assertEqual(["asset_update_rejected"], self._event_types(events))
        self.assertEqual(1, events[0]["payload"]["expected_revision"])

    def test_invalid_svg_reports_error(self):
        self.service.build_svg_test_payload()
        events = self.service.handle_asset_update(
            "s1", {"payload": {"asset_id": "test_glyph_001", "base_revision": 1, "svg": "not an svg at all"}},
        )
        self.assertEqual(["error"], self._event_types(events))
        self.assertIn("invalid svg", events[0]["payload"])

    def test_successful_update_bumps_revision_and_uses_provided_alt_text(self):
        self.service.build_svg_test_payload()
        new_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='2' height='2'><rect width='2' height='2' fill='black'/></svg>"
        events = self.service.handle_asset_update(
            "s1",
            {"payload": {"asset_id": "test_glyph_001", "base_revision": 1, "svg": new_svg, "alt_text": "New alt"}},
        )
        self.assertEqual(["asset_update_accepted", "asset"], self._event_types(events))
        self.assertEqual(2, events[0]["payload"]["revision"])
        self.assertEqual("New alt", events[1]["payload"]["alt_text"])

    def test_successful_update_without_alt_text_falls_back_to_existing(self):
        self.service.build_svg_test_payload()
        new_svg = "<svg xmlns='http://www.w3.org/2000/svg' width='2' height='2'><rect width='2' height='2' fill='black'/></svg>"
        events = self.service.handle_asset_update(
            "s1", {"payload": {"asset_id": "test_glyph_001", "base_revision": 1, "svg": new_svg}},
        )
        self.assertIn("emblem", events[1]["payload"]["alt_text"])


class TestHandleLockAcquire(RealtimeAssetsTestBase):
    def test_non_dict_payload_reports_error(self):
        events = self.service.handle_lock_acquire("s1", {"payload": "nope"})
        self.assertEqual(["error"], self._event_types(events))

    def test_missing_asset_id_reports_error(self):
        events = self.service.handle_lock_acquire("s1", {"payload": {}})
        self.assertEqual(["error"], self._event_types(events))

    def test_unknown_asset_id_reports_error(self):
        events = self.service.handle_lock_acquire("s1", {"payload": {"asset_id": "ghost"}})
        self.assertEqual(["error"], self._event_types(events))

    def test_locked_by_other_session_is_denied(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        events = self.service.handle_lock_acquire("intruder", {"payload": {"asset_id": "test_glyph_001"}})
        self.assertEqual(["lock_denied"], self._event_types(events))

    def test_reacquiring_own_lock_succeeds(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        events = self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        self.assertEqual(["lock_acquired", "lock_state_delta"], self._event_types(events))


class TestHandleLockRelease(RealtimeAssetsTestBase):
    def test_non_dict_payload_reports_error(self):
        events = self.service.handle_lock_release("s1", {"payload": "nope"})
        self.assertEqual(["error"], self._event_types(events))

    def test_missing_asset_id_reports_error(self):
        events = self.service.handle_lock_release("s1", {"payload": {}})
        self.assertEqual(["error"], self._event_types(events))

    def test_release_without_existing_lock_reports_not_released(self):
        events = self.service.handle_lock_release("s1", {"payload": {"asset_id": "never_locked"}})
        self.assertEqual(["lock_released"], self._event_types(events))
        self.assertFalse(events[0]["payload"]["released"])

    def test_release_by_non_owner_is_denied(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        events = self.service.handle_lock_release("intruder", {"payload": {"asset_id": "test_glyph_001"}})
        self.assertEqual(["lock_denied"], self._event_types(events))
        self.assertEqual("not_owner", events[0]["payload"]["reason"])

    def test_release_by_owner_succeeds(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        events = self.service.handle_lock_release("owner", {"payload": {"asset_id": "test_glyph_001"}})
        self.assertEqual(["lock_released", "lock_state_delta"], self._event_types(events))
        self.assertTrue(events[0]["payload"]["released"])


class TestHandleLockRenew(RealtimeAssetsTestBase):
    def test_non_dict_payload_reports_error(self):
        events = self.service.handle_lock_renew("s1", {"payload": "nope"})
        self.assertEqual(["error"], self._event_types(events))

    def test_missing_asset_id_reports_error(self):
        events = self.service.handle_lock_renew("s1", {"payload": {}})
        self.assertEqual(["error"], self._event_types(events))

    def test_renew_without_existing_lock_is_denied(self):
        events = self.service.handle_lock_renew("s1", {"payload": {"asset_id": "never_locked"}})
        self.assertEqual(["lock_denied"], self._event_types(events))
        self.assertEqual("no_lock", events[0]["payload"]["reason"])

    def test_renew_by_non_owner_is_denied(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        events = self.service.handle_lock_renew("intruder", {"payload": {"asset_id": "test_glyph_001"}})
        self.assertEqual(["lock_denied"], self._event_types(events))
        self.assertEqual("not_owner", events[0]["payload"]["reason"])

    def test_renew_by_owner_succeeds_and_extends_expiry(self):
        self.service.build_svg_test_payload()
        acquired = self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        original_expiry = acquired[0]["payload"]["expires_at"]
        # Advance time a little, but stay well inside the lease window so
        # _expire_stale_locks() doesn't prune the lock before renew runs.
        with patch("engine.server.realtime_assets.time.time", return_value=original_expiry - 1):
            events = self.service.handle_lock_renew("owner", {"payload": {"asset_id": "test_glyph_001"}})
        self.assertEqual(["lock_renewed", "lock_state_delta"], self._event_types(events))
        self.assertGreater(events[0]["payload"]["expires_at"], original_expiry)


class TestReleaseLocksForSession(RealtimeAssetsTestBase):
    def test_blank_session_id_returns_empty(self):
        self.assertEqual([], self.service.release_locks_for_session("   "))

    def test_only_releases_locks_owned_by_that_session(self):
        self.service.build_svg_test_payload()
        self.service._assets["other_asset"] = {"asset_id": "other_asset", "revision": 1}
        self.service.handle_lock_acquire("s1", {"payload": {"asset_id": "test_glyph_001"}})
        self.service.handle_lock_acquire("s2", {"payload": {"asset_id": "other_asset"}})
        released = self.service.release_locks_for_session("s1")
        self.assertEqual(["test_glyph_001"], [r["asset_id"] for r in released])
        state = self.service.build_lock_state_payload()
        self.assertEqual(1, len(state["active_locks"]))
        self.assertEqual("other_asset", state["active_locks"][0]["asset_id"])


class TestExpireStaleLocks(RealtimeAssetsTestBase):
    def test_expired_locks_are_pruned_on_next_operation(self):
        self.service.build_svg_test_payload()
        self.service.handle_lock_acquire("owner", {"payload": {"asset_id": "test_glyph_001"}})
        with patch("engine.server.realtime_assets.time.time", return_value=1e15):
            state = self.service.build_lock_state_payload()
        self.assertEqual([], state["active_locks"])


class TestSanitizeSvgEdgeCases(RealtimeAssetsTestBase):
    def test_non_string_raises(self):
        with self.assertRaisesRegex(ValueError, "must be a string"):
            self.service.sanitize_svg(12345)

    def test_oversized_svg_raises(self):
        self.service.max_svg_bytes = 10
        with self.assertRaisesRegex(ValueError, "exceeds max byte size"):
            self.service.sanitize_svg("<svg>" + "x" * 100 + "</svg>")

    def test_missing_svg_root_tag_raises(self):
        with self.assertRaisesRegex(ValueError, "root tag missing"):
            self.service.sanitize_svg("<rect fill='white'/>")

    def test_on_event_handler_attribute_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "blocked content"):
            self.service.sanitize_svg("<svg onclick='doEvil()'><rect fill='white'/></svg>")

    def test_foreignobject_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "blocked content"):
            self.service.sanitize_svg("<svg><foreignObject></foreignObject></svg>")

    def test_javascript_uri_is_blocked(self):
        with self.assertRaisesRegex(ValueError, "blocked content"):
            self.service.sanitize_svg("<svg><a href='javascript:doEvil()'></a></svg>")


class TestValidate1BitPaletteStyleParsing(RealtimeAssetsTestBase):
    def test_style_entry_without_colon_is_skipped(self):
        svg = "<svg><rect style='not-a-declaration' fill='white'/></svg>"
        self.assertEqual(svg, self.service.sanitize_svg(svg))

    def test_style_entry_with_unrelated_property_is_skipped(self):
        svg = "<svg><rect style='opacity: 0.5' fill='white'/></svg>"
        self.assertEqual(svg, self.service.sanitize_svg(svg))

    def test_style_fill_with_allowed_color_passes(self):
        svg = "<svg><rect style='fill: #000000' /></svg>"
        self.assertEqual(svg, self.service.sanitize_svg(svg))


class TestAssetPersistence(unittest.TestCase):
    def test_loads_existing_assets_from_db_on_startup(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            service1 = RealtimeAssetService(_event_builder, asset_db_path=path)
            payload = service1.build_svg_test_payload()
            service1.close()

            service2 = RealtimeAssetService(_event_builder, asset_db_path=path)
            try:
                self.assertIn("test_glyph_001", service2._assets)
                self.assertEqual(payload["checksum_sha256"], service2._assets["test_glyph_001"]["checksum_sha256"])
            finally:
                service2.close()
        finally:
            os.remove(path)

    def test_malformed_json_row_is_skipped(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            service1 = RealtimeAssetService(_event_builder, asset_db_path=path)
            service1._asset_db.execute(
                "INSERT INTO assets(asset_id, payload_json) VALUES(?, ?)", ("broken_asset", "{not valid json"),
            )
            service1._asset_db.commit()
            service1.close()

            service2 = RealtimeAssetService(_event_builder, asset_db_path=path)
            try:
                self.assertNotIn("broken_asset", service2._assets)
            finally:
                service2.close()
        finally:
            os.remove(path)

    def test_non_dict_json_row_is_skipped(self):
        import tempfile, os
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            service1 = RealtimeAssetService(_event_builder, asset_db_path=path)
            service1._asset_db.execute(
                "INSERT INTO assets(asset_id, payload_json) VALUES(?, ?)",
                ("list_asset", json.dumps(["not", "a", "dict"])),
            )
            service1._asset_db.commit()
            service1.close()

            service2 = RealtimeAssetService(_event_builder, asset_db_path=path)
            try:
                self.assertNotIn("list_asset", service2._assets)
            finally:
                service2.close()
        finally:
            os.remove(path)


if __name__ == "__main__":
    unittest.main()
