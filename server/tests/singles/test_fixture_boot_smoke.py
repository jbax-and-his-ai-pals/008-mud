"""Boot smoke test for the canonical fantasy content set."""
import unittest

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER

class TestFixtureBootSmoke(unittest.TestCase):
    """Verify HeadlessServer boots cleanly from a content-set definition."""

    def test_boots_without_exception(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            # No crash = pass. Boot warnings are acceptable (e.g. mods disabled),
            # but hard errors would have raised during __init__.
            self.assertIsNotNone(server)
        finally:
            server.shutdown()

    def test_no_critical_boot_warnings(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            critical = [
                w for w in server.boot_warnings
                if any(
                    kw in w.lower()
                    for kw in ("error", "corrupt", "invalid json", "failed to load")
                )
            ]
            self.assertEqual(
                [],
                critical,
                msg=f"Unexpected critical boot warnings from fixture:\n"
                + "\n".join(critical),
            )
        finally:
            server.shutdown()

    def test_no_critical_boot_warning_codes(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            codes = {
                str(entry.get("code", "")).strip()
                for entry in getattr(server, "boot_warning_records", [])
            }
            disallowed = {
                "content.spells.dir_missing",
                "content.spells.file_errors",
                "content.items.dir_missing",
                "content.items.file_errors",
                "content.npcs.dir_missing",
                "content.npcs.file_errors",
            }
            present = sorted(c for c in codes if c in disallowed)
            self.assertEqual([], present, msg=f"Unexpected critical warning code(s): {present}")
        finally:
            server.shutdown()

    def test_world_has_regions(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            self.assertGreater(
                len(server.world.regions),
                0,
                msg="Expected at least one region loaded from fixture data.",
            )
        finally:
            server.shutdown()

    def test_session_and_command_round_trip(self) -> None:
        """Minimal command round-trip: create session, create character, 'look'."""
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        try:
            session = server.create_session()
            events = server.execute_command(session.session_id, "char create TestPlayer")
            types = {e.get("type") for e in events}
            self.assertIn("text", types, msg="Expected 'text' event after char create.")

            events = server.execute_command(session.session_id, "look")
            types = {e.get("type") for e in events}
            self.assertIn("text", types, msg="Expected 'text' event after 'look'.")
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
