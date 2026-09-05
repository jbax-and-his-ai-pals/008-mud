import unittest
import shutil
import uuid
from pathlib import Path

from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestHeadlessEntitlementPolicyWiring(unittest.TestCase):
    def setUp(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        self._tmp_content_root = repo_root / "server" / "tests" / "_tmp" / f"headless_topics_{uuid.uuid4().hex}"
        shutil.copytree(FANTASY_FRONTIER, self._tmp_content_root)
        self.addCleanup(lambda: shutil.rmtree(self._tmp_content_root, ignore_errors=True))

    def test_default_session_grants_apply_on_session_create(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            entitlement_policy={"default_session_grants": ["pack.sample_world"]},
        )
        try:
            session = server.create_session(player_id="entitlement_policy_player")
            self.assertIn("pack.sample_world", session.entitlements)
        finally:
            server.shutdown()

    def test_gate_definitions_loaded_from_constructor_policy(self) -> None:
        policy = {"gates": {"operator.world.debug": {"requires": ["operator.world.debug"]}}}
        server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, entitlement_policy=policy)
        try:
            self.assertIn("operator.world.debug", server.entitlement_guard.gates)
        finally:
            server.shutdown()

    def test_optional_topics_are_not_required_for_content_set_boot(self) -> None:
        server = HeadlessServer(db_path=":memory:", content_set_path=str(self._tmp_content_root))
        try:
            codes = [entry.get("code") for entry in server.boot_warning_records]
            self.assertNotIn("content.topics.missing", codes)
        finally:
            server.shutdown()

    def test_boot_warning_policy_can_fail_server_start(self) -> None:
        shutil.rmtree(self._tmp_content_root / "data" / "magic")
        with self.assertRaises(RuntimeError):
            HeadlessServer(
                db_path=":memory:",
                content_set_path=str(self._tmp_content_root),
                boot_warning_fail_codes=["content.spells.dir_missing"],
            )


if __name__ == "__main__":
    unittest.main()
