# tests/singles/test_permanent_reactions.py
"""An element can change a room for good, not only for a while.

`env_interactions` (a spell's damage type doing something to the room) always reverted
after `duration`, so a bombed wall closed again and a wall that should *stay* open could
not be written. `permanent: true` applies the change and schedules no revert. It is
world state, not the player's (Decision 11): the room's properties are what changed, and
the world snapshot already keeps a room's property changes, so it survives a restart.
"""

import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.server import content_set
from engine.world import world_snapshot
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


class _Walls(GameTestBase):
    def setUp(self):
        super().setUp()
        self.room = self.world.get_current_room(self.player)
        self.direction = sorted(self.room.exits)[0]
        self.room.properties["exit_requirements"] = {
            self.direction: {"type": "locked", "key_id": None, "pick_difficulty": 999}}

    def react(self, **more):
        self.room.properties["env_interactions"] = {
            "fire": {"type": "clear_exit_req", "direction": self.direction, "message": "The wall bursts inward.", **more}}
        return self.room.apply_elemental_interaction("fire")

    def shut(self):
        return self.direction in self.room.properties.get("exit_requirements", {})


class TestTheVocabulary(unittest.TestCase):
    def test_both_reactions_read_permanent(self):
        self.assertIn("permanent", content_set.ENV_INTERACTION_KEYS["clear_exit_req"])
        self.assertIn("permanent", content_set.ENV_INTERACTION_KEYS["suppress_hazard"])


class TestAPermanentWall(_Walls):
    def test_a_temporary_reaction_still_reverts(self):
        self.assertIn("bursts", self.react(duration=5))
        self.assertFalse(self.shut())
        self.room.update(6)
        self.assertTrue(self.shut(), "unchanged behaviour")

    def test_a_permanent_reaction_opens_the_wall_and_says_so(self):
        self.assertIn("bursts", self.react(permanent=True))
        self.assertFalse(self.shut())

    def test_it_schedules_no_revert(self):
        self.react(permanent=True)
        self.assertEqual([], self.room.active_env_effects)

    def test_it_stays_open_however_long_it_is_left(self):
        self.react(permanent=True)
        for _ in range(20):
            self.room.update(10 ** 6)
        self.assertFalse(self.shut())

    def test_a_second_blast_does_nothing_more(self):
        self.react(permanent=True)
        self.assertIsNone(self.room.apply_elemental_interaction("fire"))

    def test_it_is_still_open_after_a_snapshot_and_restore(self):
        self.react(permanent=True)
        snapshot = copy.deepcopy(world_snapshot.capture(self.world))
        json.loads(json.dumps(snapshot))
        # The static definition puts the requirement back; the snapshot's memory of the
        # room's changed properties must take it away again.
        self.room.properties["exit_requirements"] = {self.direction: {"type": "locked", "key_id": None}}
        world_snapshot.restore(self.world, snapshot)
        restored = self.world.get_current_room(self.player)
        self.assertNotIn(self.direction, restored.properties.get("exit_requirements", {}))


class TestAPermanentQuenching(GameTestBase):
    def test_a_permanent_suppression_never_returns(self):
        room = self.world.get_current_room(self.player)
        room.properties["hazards"] = [{"type": "poison_gas", "damage": 8}]
        room.properties["env_interactions"] = {"ice": {"type": "suppress_hazard", "permanent": True}}
        self.assertIsNotNone(room.apply_elemental_interaction("ice"))
        self.assertEqual([], room.properties["hazards"])
        self.assertEqual([], room.active_env_effects)
        room.update(10 ** 6)
        self.assertEqual([], room.properties["hazards"])

    def test_a_permanent_suppression_of_a_single_hazard_type_never_returns(self):
        room = self.world.get_current_room(self.player)
        room.properties.pop("hazards", None)
        room.properties["hazard_type"] = "poison_gas"
        room.properties["env_interactions"] = {"ice": {"type": "suppress_hazard", "permanent": True}}
        room.apply_elemental_interaction("ice")
        room.update(10 ** 6)
        self.assertIsNone(room.properties.get("hazard_type"))


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice, changing the bomb chamber's reaction."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))
        self.region_file = self.package / "data" / "regions" / "drowned_vault.json"

    def _errors(self, **more):
        payload = json.loads(self.region_file.read_text(encoding="utf-8"))
        reaction = payload["rooms"]["bomb_chamber"]["properties"]["env_interactions"]["explosive"]
        reaction.pop("duration", None)
        reaction.update(more)
        self.region_file.write_text(json.dumps(payload), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error" and "bomb_chamber" in i.message]

    def test_a_permanent_reaction_is_accepted(self):
        self.assertEqual([], self._errors(permanent=True))

    def test_permanent_must_be_true_or_false(self):
        errors = self._errors(permanent="yes")
        self.assertTrue(any("permanent" in m for m in errors), errors)

    def test_permanent_with_a_duration_is_a_contradiction_and_is_refused(self):
        errors = self._errors(permanent=True, duration=120)
        self.assertTrue(any("permanent" in m and "duration" in m for m in errors), errors)

    def test_permanent_false_with_a_duration_is_fine(self):
        self.assertEqual([], self._errors(permanent=False, duration=120))


if __name__ == "__main__":
    unittest.main()
