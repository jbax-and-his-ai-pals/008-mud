# tests/singles/test_quest_text_pace_config.py
"""How fast quest text is revealed is chosen, in order, by the server's operator, then the content set, then the engine.

(A player's own switch and speed are the client's, and are checked in `client/tests`.)
"""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer
from engine.server.server_config import resolve_server_settings
from engine.utils import pacing

REPO_ROOT = Path(__file__).resolve().parents[3]
FF4 = REPO_ROOT / "content_sets" / "ff4_slice"


class TestWhichPaceWins(unittest.TestCase):
    def test_operator_then_content_set_then_engine(self):
        self.assertEqual("solemn", pacing.effective_quest_text_pace("solemn", "brisk"))
        self.assertEqual("brisk", pacing.effective_quest_text_pace(None, "brisk"))
        self.assertEqual(pacing.DEFAULT_QUEST_TEXT_PACE, pacing.effective_quest_text_pace(None, None))
        self.assertEqual(35, pacing.effective_quest_text_pace(35, "brisk"))

    def test_instant_is_a_choice_not_an_absence(self):
        self.assertEqual("instant", pacing.effective_quest_text_pace("instant", "brisk"))
        self.assertEqual("instant", pacing.effective_quest_text_pace(None, "instant"))

    def test_nonsense_is_not_said(self):
        self.assertEqual("brisk", pacing.effective_quest_text_pace("warp", "brisk"))
        self.assertEqual(pacing.DEFAULT_QUEST_TEXT_PACE, pacing.effective_quest_text_pace(True, 9999))


class _Set:
    """A copy of ff4_slice whose presentation file says `presentation_pace` (or nothing)."""

    def __init__(self, case, presentation_pace=None):
        tmp = Path(tempfile.mkdtemp())
        case.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.package = tmp / "ff4_slice"
        shutil.copytree(FF4, self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        if presentation_pace is not None:
            path = self.package / "presentation" / "default.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["quest_text_pace"] = presentation_pace
            path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def server(self, case, operator=None):
        server = HeadlessServer(db_path=":memory:", content_set_path=str(self.package), deterministic_test_mode=True,
                                default_presentation_mode="player", quest_text_pace=operator)
        case.addCleanup(server.shutdown)
        return server


def _paced_speed(server, text="[Quest Accepted] The Fog Drake"):
    sid = server.create_session(player_id="hero").session_id
    marked = server._paced_text(sid, text)
    found = re.search(r"\[\[PACE:(\d+)\]\]", marked)
    return int(found.group(1)) if found else None


class TestTheServerAppliesIt(unittest.TestCase):
    def test_a_set_that_says_nothing_gets_the_engine_default(self):
        self.assertEqual(pacing.TEXT_PACES["slow"], _paced_speed(_Set(self).server(self)))

    def test_the_content_set_can_ask_for_its_own(self):
        self.assertEqual(pacing.TEXT_PACES["solemn"], _paced_speed(_Set(self, "solemn").server(self)))
        self.assertEqual(55, _paced_speed(_Set(self, 55).server(self)))

    def test_the_content_set_can_ask_for_none(self):
        self.assertIsNone(_paced_speed(_Set(self, "instant").server(self)))

    def test_the_operator_overrides_the_set(self):
        self.assertEqual(pacing.TEXT_PACES["brisk"], _paced_speed(_Set(self, "solemn").server(self, operator="brisk")))
        self.assertIsNone(_paced_speed(_Set(self, "solemn").server(self, operator="instant")))

    def test_authored_paces_are_not_the_operators_to_take_away(self):
        server = _Set(self).server(self, operator="instant")
        sid = server.create_session(player_id="hero").session_id
        authored = pacing.paced("The king speaks.", "slow")
        self.assertEqual(authored, server._paced_text(sid, authored))


class TestTheOperatorsSetting(unittest.TestCase):
    def settings(self, session):
        return resolve_server_settings("ws", {"session": session}, None, None, None, None, None)

    def test_the_server_config_names_it(self):
        self.assertEqual("brisk", self.settings({"quest_text_pace": "brisk"}).session_quest_text_pace)
        self.assertIsNone(self.settings({}).session_quest_text_pace)


class TestTheValidator(unittest.TestCase):
    def errors_with(self, pace):
        from engine.server import content_set as validator

        package = _Set(self, pace).package
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_a_name_a_speed_and_instant_pass(self):
        for good in ("slow", "solemn", "instant", 20, 200):
            self.assertEqual([], self.errors_with(good), good)

    def test_nonsense_is_refused_with_what_would_work(self):
        for bad in ("glacial", 1, 5000, True, ["slow"]):
            errors = self.errors_with(bad)
            self.assertTrue(any("quest_text_pace" in m and "is not a pace" in m for m in errors), (bad, errors))


if __name__ == "__main__":
    unittest.main()
