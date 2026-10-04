"""The scripts an author (or an agent) edits and plays content with: `toolkit/content_edit.py` and
`toolkit/play_script.py`. They are small, and they are how a change gets made and looked at, so they are kept honest."""

import json
import shutil
import subprocess
import sys
import unittest
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
STORY_FIXTURE = REPO_ROOT / "server" / "tests" / "sets" / "story_fixture"
PEOPLE = "data/npcs/people.json"


def run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(REPO_ROOT / "toolkit" / script), *args],
                          cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace", timeout=120)


class TestContentEdit(unittest.TestCase):
    def setUp(self) -> None:
        root = REPO_ROOT / "tmp" / ("content_edit_%s" % uuid.uuid4().hex)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))
        self.package = root / "story_fixture"
        shutil.copytree(STORY_FIXTURE, self.package, ignore=shutil.ignore_patterns("editor", "saves", "*.bak"))
        self.people = self.package / PEOPLE

    def test_get_set_and_the_file_changes_only_where_asked(self) -> None:
        before = json.loads(self.people.read_text(encoding="utf-8"))
        npc = next(iter(before))
        self.assertEqual(0, run("content_edit.py", "set", str(self.package), PEOPLE, "%s.description" % npc, '"changed"').returncode)
        after = json.loads(self.people.read_text(encoding="utf-8"))
        self.assertEqual("changed", after[npc]["description"])
        after[npc]["description"] = before[npc]["description"]
        self.assertEqual(before, after, "nothing else moved")
        shown = run("content_edit.py", "get", str(self.package), PEOPLE, "%s.description" % npc)
        self.assertIn("changed", shown.stdout)

    def test_a_set_that_changes_nothing_writes_the_same_bytes(self) -> None:
        raw = self.people.read_bytes()
        npc = next(iter(json.loads(raw)))
        health = json.loads(raw)[npc].get("health", 10)
        run("content_edit.py", "set", str(self.package), PEOPLE, "%s.health" % npc, json.dumps(health))
        self.assertEqual(raw.replace(b"\r\n", b"\n"), self.people.read_bytes().replace(b"\r\n", b"\n"))

    def test_a_whole_number_float_is_written_whole_and_append_and_delete_work(self) -> None:
        npc = next(iter(json.loads(self.people.read_text(encoding="utf-8"))))
        run("content_edit.py", "set", str(self.package), PEOPLE, "%s.properties.probe" % npc, '{"list": [1.0, 2.5]}')
        value = json.loads(self.people.read_text(encoding="utf-8"))[npc]["properties"]["probe"]
        self.assertEqual({"list": [1, 2.5]}, value)
        self.assertIsInstance(value["list"][0], int)
        run("content_edit.py", "append", str(self.package), PEOPLE, "%s.properties.probe.list" % npc, "7")
        run("content_edit.py", "delete", str(self.package), PEOPLE, "%s.properties.probe.list.0" % npc)
        self.assertEqual([2.5, 7], json.loads(self.people.read_text(encoding="utf-8"))[npc]["properties"]["probe"]["list"])

    def test_a_missing_file_is_a_clear_refusal(self) -> None:
        done = run("content_edit.py", "get", str(self.package), "data/npcs/nope.json")
        self.assertEqual(2, done.returncode)


class TestPlayScript(unittest.TestCase):
    def test_it_creates_a_character_and_runs_commands(self) -> None:
        done = run("play_script.py", str(STORY_FIXTURE), "--name", "Tester", "where", "look")
        self.assertEqual(0, done.returncode, done.stderr[-400:])
        self.assertIn("Character created: Tester", done.stdout)
        self.assertIn("-- at ", done.stdout)
        self.assertNotIn("[[", done.stdout, "colour markup is stripped")


class TestQuietLogging(unittest.TestCase):
    def level(self, value) -> int:
        import os

        env = dict(os.environ)
        env.pop("MUD_LOG_LEVEL", None)
        if value is not None:
            env["MUD_LOG_LEVEL"] = value
        done = subprocess.run([sys.executable, "-c", "from engine.utils.logger import Logger; print(Logger._level)"],
                              cwd=str(REPO_ROOT / "server"), env=env, capture_output=True, text=True, timeout=60)
        return int(done.stdout.strip().splitlines()[-1])

    def test_the_environment_sets_the_starting_level(self) -> None:
        self.assertEqual(0, self.level(None), "unset is as chatty as it always was")
        self.assertEqual(2, self.level("warning"))
        self.assertEqual(5, self.level("NONE"))
        self.assertEqual(0, self.level("nonsense"))


if __name__ == "__main__":
    unittest.main()
