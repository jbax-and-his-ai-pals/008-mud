# tests/singles/test_dialogue_narration.py
"""A dialogue node marked `narration: true` is told plainly, not said by the NPC.

`Ryn speaks: "(She does not stir.)"` read like a line of speech; a narration node reads as what the player sees.
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
GRAPH = {"id": "still_one", "root": "greeting", "nodes": {
    "greeting": {"text": "(She does not stir.)", "narration": True, "end": True},
    "spoken": {"text": "Leave me be.", "end": True},
}}


def package(narration=True):
    tmp = Path(tempfile.mkdtemp())
    pkg = tmp / "story_fixture"
    shutil.copytree(STORY_FIXTURE, pkg)
    graph = json.loads(json.dumps(GRAPH))
    graph["nodes"]["greeting"]["narration"] = narration
    (pkg / "data" / "dialogue" / "still_one.json").write_text(json.dumps(graph), encoding="utf-8")
    path = pkg / "data" / "npcs" / "people.json"
    people = json.loads(path.read_text(encoding="utf-8"))
    people["quartermaster"]["properties"]["dialogue"] = "still_one"
    path.write_text(json.dumps(people), encoding="utf-8")
    return tmp, pkg


class TestNarration(unittest.TestCase):
    def talk(self, narration):
        tmp, pkg = package(narration)
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        server = HeadlessServer(db_path=":memory:", content_set_path=str(pkg), deterministic_test_mode=True, default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Aldric")
        player = server.get_player_for_session(sid)
        player.current_region_id, player.current_room_id = "varenholt", "stores"
        events = server.execute_command(sid, "talk quartermaster")
        return _MARKUP.sub("", chr(10).join(str(e["payload"]) for e in events if e["type"] == "text"))

    def test_a_narration_node_is_told_plainly(self):
        said = self.talk(True)
        self.assertIn("(She does not stir.)", said)
        self.assertNotIn("speaks", said)
        self.assertNotIn('"(She', said, "and is not put in quotation marks")

    def test_an_ordinary_node_is_still_the_npcs_speech(self):
        said = self.talk(False)
        self.assertIn('speaks: "(She does not stir.)"', said)


class TestTheValidator(unittest.TestCase):
    def test_narration_must_be_true_or_false(self):
        tmp, pkg = package()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        path = pkg / "data" / "dialogue" / "still_one.json"
        graph = json.loads(path.read_text(encoding="utf-8"))
        graph["nodes"]["greeting"]["narration"] = "yes"
        path.write_text(json.dumps(graph), encoding="utf-8")
        errors = [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]
        self.assertTrue([m for m in errors if "narration must be true or false" in m], errors)


if __name__ == "__main__":
    unittest.main()
