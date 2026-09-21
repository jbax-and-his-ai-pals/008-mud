"""`behavior_type`: the engine's closed vocabulary of NPC routines.

The list in `config_npc.NPC_BEHAVIOR_TYPES` had no reader at all -- nothing in the
engine consulted it -- and it was wrong: `healer`, which three shipped templates
use, was missing, so the one place an author could have looked would have told
them their working NPC was invalid. An unknown value is not a loud failure
either: the NPC simply stands there for the rest of the world's life.

So the vocabulary is read in two places now, and these tests hold both: the
dispatcher's routine table is exactly the declared list minus `stationary` (which
has no routine by definition), and the content gate warns about a value outside
the list.
"""

import json
import shutil
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from engine.config import NPC_BEHAVIOR_TYPES, NPC_RUNTIME_BEHAVIORS
from engine.npcs.ai import dispatcher
from engine.server import content_set as cs
from tests.fixtures import FANTASY_FRONTIER

REPO_ROOT = Path(__file__).resolve().parents[3]


class FakeWorld:
    """As much world as `handle_ai` touches when nothing is happening."""

    def has_capability(self, name):
        return False

    def get_region(self, region_id):
        return None


class FakeNPC:
    behavior_type = "stationary"
    properties: dict = {}
    is_trading = False
    is_alive = True
    in_combat = False
    in_combat_targets = ()
    move_cooldown = 0
    last_moved = 0
    current_region_id = "room"
    current_room_id = "room"
    health = 10
    max_health = 10
    mana = 10
    max_mana = 10
    usable_spells = ()
    owner_id = None

    def has_effect(self, name):
        return False


class TestTheVocabularyAndItsRoutinesAgree(unittest.TestCase):
    def test_every_declared_behaviour_has_a_routine_except_standing_still(self) -> None:
        declared = set(NPC_BEHAVIOR_TYPES)
        dispatched = set(dispatcher.IDLE_ROUTINES)

        self.assertEqual(
            {"stationary"}, declared - dispatched,
            "a behaviour with no routine means an NPC that silently does nothing",
        )
        self.assertEqual(set(), dispatched - declared, "a routine for an undeclared behaviour")

    def test_the_engines_own_runtime_states_are_not_authorable_routines(self) -> None:
        for behaviour in NPC_RUNTIME_BEHAVIORS:
            self.assertNotIn(behaviour, NPC_BEHAVIOR_TYPES)
            self.assertNotIn(behaviour, dispatcher.IDLE_ROUTINES)

    def test_a_healer_walks(self) -> None:
        """`healer` is not a movement routine of its own: it heals on its turn
        *and* wanders, because a healer that cannot reach anybody is scenery."""
        walked = []

        def recorder(npc, world, player):
            walked.append(npc.behavior_type)
            return None

        with patch.object(dispatcher, "perform_wander", recorder):
            dispatcher.IDLE_ROUTINES["healer"](FakeNPC(), FakeWorld(), None, 1.0)

        self.assertEqual(["stationary"], walked)

    def test_each_declared_behaviour_reaches_its_routine(self) -> None:
        """The table is the vocabulary's consumer, so prove it dispatches."""
        calls = {}

        def recorder(name):
            def routine(npc, world, player, now):
                calls.setdefault(name, 0)
                calls[name] += 1
                return None

            return routine

        for behaviour in NPC_BEHAVIOR_TYPES:
            if behaviour == "stationary":
                continue
            npc = FakeNPC()
            npc.behavior_type = behaviour
            with patch.object(dispatcher, "IDLE_ROUTINES",
                              {behaviour: recorder(behaviour)}):
                dispatcher.handle_ai(npc, FakeWorld(), 100.0, None)
            self.assertEqual(1, calls.get(behaviour, 0), "%s never reached a routine" % behaviour)

    def test_standing_still_runs_nothing_at_all(self) -> None:
        calls = []

        def recorder(npc, world, player, now):
            calls.append(npc.behavior_type)
            return None

        table = {name: recorder for name in NPC_BEHAVIOR_TYPES if name != "stationary"}
        npc = FakeNPC()
        with patch.object(dispatcher, "IDLE_ROUTINES", table):
            result = dispatcher.handle_ai(npc, FakeWorld(), 100.0, None)

        self.assertEqual([], calls)
        self.assertIsNone(result)


class TestAnUnknownBehaviourIsReported(unittest.TestCase):
    def _package(self) -> Path:
        root = REPO_ROOT / "tmp" / ("behavior_set_%s" % uuid.uuid4().hex)
        package = root / "wander_game"
        data = package / "data"
        for directory in ("regions", "items", "npcs"):
            (data / directory).mkdir(parents=True, exist_ok=True)
        (package / "rules").mkdir(parents=True, exist_ok=True)
        (package / "presentation").mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        (data / "npcs" / "folk.json").write_text(json.dumps({
            "wanderer": {
                "name": "a wanderer",
                "description": "Somebody going somewhere.",
                "health": 20,
                "level": 1,
                "faction": "friendly",
                "behavior_type": "wanders",
            }
        }), encoding="utf-8")
        (data / "regions" / "town.json").write_text(json.dumps({
            "region_id": "town",
            "name": "Town",
            "rooms": {
                "square": {
                    "name": "Square", "description": "A square.",
                    "initial_npcs": [{"template_id": "wanderer", "instance_id": "wanderer_one"}],
                }
            },
        }), encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(
            json.dumps({"ruleset_id": "wander_core"}), encoding="utf-8"
        )
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / cs.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
            "id": "wander_game",
            "title": "Wander Game",
            "version": "0.1.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "paths": {
                "content_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory", "dialogue"],
        }), encoding="utf-8")
        return package

    def test_a_misspelled_behaviour_is_a_warning_that_says_what_happens(self) -> None:
        issues = cs.validate_content_set(self._package())

        warnings = [i for i in issues if i.severity == "warning" and "behavior_type" in i.message]
        self.assertTrue(warnings, [i.message for i in issues])
        self.assertIn("stand still and do nothing", warnings[0].message)
        self.assertFalse([i for i in issues if i.severity == "error"])

    def test_every_declared_behaviour_passes_the_gate_in_the_shipped_sets(self) -> None:
        """`fantasy_frontier` uses healer, minion, patrol, scheduled, wanderer and
        aggressive; none of them may warn."""
        issues = cs.validate_content_set(Path(FANTASY_FRONTIER))

        self.assertEqual(
            [], [i.message for i in issues if "behavior_type" in i.message],
        )


if __name__ == "__main__":
    unittest.main()
