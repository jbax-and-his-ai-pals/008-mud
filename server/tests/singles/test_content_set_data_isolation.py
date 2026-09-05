import json
import shutil
import unittest
import uuid
from pathlib import Path

from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestContentSetDataIsolation(unittest.TestCase):
    def _case_root(self) -> Path:
        root = REPO_ROOT / "tmp" / f"content_set_isolation_{uuid.uuid4().hex}"
        root.mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        return root

    def _write_alternate_content_set(self, root: Path) -> Path:
        package = root / "alternate_game"
        content_root = package / "data"
        for directory in ("regions", "items", "npcs", "magic", "knowledge"):
            (content_root / directory).mkdir(parents=True, exist_ok=True)

        (content_root / "regions" / "alternate.json").write_text(
            json.dumps(
                {
                    "region_id": "alternate",
                    "name": "Alternate Region",
                    "rooms": {"hub": {"name": "Alternate Hub", "description": "A separate test world.", "exits": {}}},
                }
            ),
            encoding="utf-8",
        )
        (content_root / "items" / "items.json").write_text(
            json.dumps({"alternate_token": {"name": "Alternate Token", "type": "misc", "description": "A token."}}),
            encoding="utf-8",
        )
        (content_root / "items" / "sets.json").write_text(
            json.dumps({"alternate_set": {"items": ["alternate_token"], "bonuses": {}}}),
            encoding="utf-8",
        )
        (content_root / "npcs" / "npcs.json").write_text("{}", encoding="utf-8")
        (content_root / "magic" / "spells.json").write_text("{}", encoding="utf-8")
        (content_root / "knowledge" / "topics.json").write_text(
            json.dumps({"alternate_topic": {"display_name": "Alternate Topic", "keywords": [], "responses": []}}),
            encoding="utf-8",
        )
        (content_root / "collections.json").write_text(
            json.dumps({"alternate_collection": {"name": "Alternate Collection"}}),
            encoding="utf-8",
        )

        (package / "rules").mkdir(parents=True, exist_ok=True)
        (package / "presentation").mkdir(parents=True, exist_ok=True)
        (package / "rules" / "ruleset.json").write_text("{}", encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / "content_set.manifest.json").write_text(
            json.dumps(
                {
                    "id": "alternate_game",
                    "title": "Alternate Game",
                    "version": "0.1.0",
                    "manifest_schema_version": "1",
                    "engine_api_min": "1.0",
                    "engine_api_max": "1.0",
                    "paths": {
                        "content_root": "data",
                        "ruleset": "rules/ruleset.json",
                        "presentation": "presentation/default.json",
                    },
                    "start": {"scenario_id": "alternate_start", "region_id": "alternate", "room_id": "hub"},
                    "capabilities": ["inventory", "dialogue"],
                }
            ),
            encoding="utf-8",
        )
        return package

    def test_selected_content_set_uses_its_own_data_without_mutating_defaults(self) -> None:
        package = self._write_alternate_content_set(self._case_root())
        alternate = HeadlessServer(db_path=":memory:", content_set_path=str(package))
        try:
            self.assertFalse(alternate.world.definition_load_stats["spell_registry"]["enabled"])
            self.assertIsNone(alternate.crafting_manager)
            self.assertIsNone(alternate.world.quest_manager)
            self.assertIsNone(alternate.world.campaign_manager)
            self.assertEqual({"alternate"}, set(alternate.world.regions))
            self.assertIn("alternate_topic", alternate.knowledge_manager.topics)
            self.assertIn("alternate_collection", alternate.collection_manager.collections)
            session = alternate.create_session()
            alternate.execute_command(session.session_id, "char create Alternate")
            magic_events = alternate.execute_command(session.session_id, "spells")
            self.assertIn(
                "does not include the 'magic' system",
                "\n".join(str(event["payload"]) for event in magic_events),
            )
            status_events = alternate.execute_command(session.session_id, "status")
            status_text = "\n".join(str(event["payload"]) for event in status_events)
            self.assertNotIn("Mana:", status_text)
            self.assertNotIn("SPELLS KNOWN", status_text)
            help_events = alternate.execute_command(session.session_id, "help")
            help_text = "\n".join(str(event["payload"]) for event in help_events)
            self.assertNotIn("Magic", help_text)
            self.assertNotIn("Crafting", help_text)
            player = alternate.get_player_for_session(session.session_id)
            self.assertEqual("alternate", player.current_region_id)
            self.assertEqual("hub", player.current_room_id)
            self.assertIn("alternate_set", player.set_manager.sets)
        finally:
            alternate.shutdown()

        default_server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER))
        try:
            self.assertIn("town", default_server.world.regions)
            self.assertNotIn("alternate", default_server.world.regions)
            self.assertNotIn("alternate_campaign", default_server.world.campaign_manager.definitions)
        finally:
            default_server.shutdown()


if __name__ == "__main__":
    unittest.main()
