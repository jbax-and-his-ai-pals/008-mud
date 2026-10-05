# tests/singles/test_teach_companion.py
"""The `teach_companion` effect: one of the player's companions learns an ability and keeps it.

An NPC's abilities come from its template, so a companion that is taught something in play (Ryn, lightning) needs the
lesson written somewhere that is saved with it: `properties.learned_spells`, read back when it is made again.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import apply_effects
from engine.npcs import companions
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE


class TestALesson(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = "varenholt", "barracks"
        self.kessa = next(n for n in self.world.npcs.values() if n.template_id == "captain_kessa")
        self.kessa.current_region_id, self.kessa.current_room_id = "varenholt", "barracks"
        companions.recruit(self.world, self.player, self.kessa)

    def teach(self, npc="captain_kessa", spell="gloom_wave"):
        return apply_effects({"teach_companion": {"npc": npc, "spell": spell}}, {"player": self.player, "world": self.world})

    def test_a_companion_learns_an_ability_and_is_told_so(self):
        self.assertNotIn("cure", self.kessa.usable_spells)
        report = self.teach(spell="cure")
        self.assertFalse(report.failed)
        self.assertIn("cure", self.kessa.usable_spells)
        self.assertTrue([m for m in report.messages if "learns" in m])

    def test_it_is_kept_with_her_in_her_saved_properties_and_returns_when_she_is_made_again(self):
        self.teach(spell="cure")
        saved = self.kessa.to_dict()
        self.assertIn("cure", json.dumps(saved["properties_override"]))
        again = NPCFactory.create_npc_from_template("captain_kessa", self.world, instance_id="kessa_again",
                                                    properties_override={"learned_spells": ["cure"]})
        self.assertIn("cure", again.usable_spells)

    def test_asking_twice_changes_nothing(self):
        self.teach(spell="cure")
        report = self.teach(spell="cure")
        self.assertEqual(1, self.kessa.usable_spells.count("cure"))
        self.assertFalse(report.failed)

    def test_someone_who_is_not_a_companion_cannot_be_taught(self):
        companions.dismiss(self.world, self.player, self.kessa)
        self.assertTrue([f for f in self.teach(spell="cure").failed if "teach_companion" in f])

    def test_an_unknown_ability_is_refused(self):
        self.assertTrue([f for f in self.teach(spell="no_such_spell").failed if "teach_companion" in f])


class TestTheValidator(unittest.TestCase):
    def problems(self, effect):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, package)
        (package / "data" / "scenes").mkdir(exist_ok=True)
        (package / "data" / "scenes" / "lesson.json").write_text(json.dumps({"s": {"beats": [{"text": "x", "effects": effect}]}}), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(package) if i.severity == "error"]

    def test_good_ids_are_accepted_and_missing_ones_are_named(self):
        self.assertEqual([], [m for m in self.problems({"teach_companion": {"npc": "captain_kessa", "spell": "cure"}}) if "teach_companion" in m])
        self.assertTrue([m for m in self.problems({"teach_companion": {"npc": "nobody", "spell": "cure"}}) if "nobody" in m])
        self.assertTrue([m for m in self.problems({"teach_companion": {"npc": "captain_kessa", "spell": "no_such"}}) if "no_such" in m])
        self.assertTrue([m for m in self.problems({"teach_companion": {"npc": "captain_kessa"}}) if "spell" in m])


if __name__ == "__main__":
    unittest.main()
