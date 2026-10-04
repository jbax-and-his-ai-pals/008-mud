# tests/singles/test_skill_detail_command.py
"""`skills <name>` describes one skill, so the client's Skills panel can be clicked."""

import re
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _say(server, sid, command):
    return "\n".join(_MARKUP.sub("", str(e["payload"])) for e in server.execute_command(sid, command) if e["type"] == "text")


class TestSkillDetail(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(STORY_FIXTURE),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="skills").session_id
        self.server.execute_command(self.sid, "char create Tester")
        self.player = self.server.get_player_for_session(self.sid)
        self.player.runtime_state.progression.skills["lockpicking"] = {"level": 3, "xp": 40}

    def test_a_named_skill_is_described(self):
        said = _say(self.server, self.sid, "skills lock")
        self.assertIn("LOCKPICKING", said)
        self.assertIn("Level 3", said)
        self.assertIn("40/", said)

    def test_an_unknown_skill_says_so(self):
        self.assertIn("no skill called 'swimming'", _say(self.server, self.sid, "skills swimming"))

    def test_the_plain_list_still_works(self):
        self.assertIn("Lockpicking", _say(self.server, self.sid, "skills"))


if __name__ == "__main__":
    unittest.main()
