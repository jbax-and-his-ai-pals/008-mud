"""Faction dispositions: one declaration, and every call site follows.

The engine's attitude matrix has always been the answer, but two dozen call sites
asked the question by comparing a faction *string* to `"hostile"` -- display,
target lists, conversation gating, wander destinations, quest generation,
reputation on a kill. Those tests hold two things: that the refactor changed
nothing for the built-in vocabulary (the derived matrix is the same document), and
that a content set naming its own enemies gets all of that behaviour without
touching a line of engine code.
"""

import json
import re
import shutil
import unittest
import uuid
from pathlib import Path

from engine.config import FACTIONS, FACTION_RELATIONSHIP_MATRIX
from engine.server import content_set as cs
from engine.server.headless_server import HeadlessServer
from engine.world import factions

REPO_ROOT = Path(__file__).resolve().parents[3]
ENGINE_ROOT = REPO_ROOT / "server" / "engine"


class TestTheEngineVocabularyIsUnchanged(unittest.TestCase):
    def test_the_derived_matrix_is_the_engine_matrix(self) -> None:
        """The refactor's safety net: with nothing declared, resolving the
        matrix must produce exactly the numbers the engine shipped."""
        self.assertEqual(FACTION_RELATIONSHIP_MATRIX, factions.matrix(None))

    def test_the_built_in_five_keep_their_meaning(self) -> None:
        self.assertTrue(factions.is_hostile("hostile"))
        self.assertFalse(factions.is_hostile("friendly"))
        self.assertFalse(factions.is_hostile("neutral"))

        self.assertTrue(factions.can_converse("friendly"))
        self.assertTrue(factions.can_converse("neutral"))
        self.assertFalse(factions.can_converse("hostile"), "you cannot chat with an enemy")
        self.assertFalse(factions.can_converse("player"), "nor with the player")
        self.assertFalse(factions.can_converse("player_minion"), "nor with a summoned thing")

        self.assertTrue(factions.same_faction("hostile", "hostile"))
        self.assertFalse(factions.same_faction("hostile", "neutral"))

    def test_a_template_dict_answers_the_same_questions_as_an_actor(self) -> None:
        template = {"name": "goblin", "faction": "hostile"}

        self.assertTrue(factions.is_hostile(template))
        self.assertEqual("hostile", factions.faction_of(template))

    def test_an_unknown_faction_is_a_bystander_rather_than_an_error(self) -> None:
        """The old failure mode, kept as a named behaviour: an undeclared faction
        is nobody's enemy, and still somebody you can talk to. The gate warns
        about it, because the author almost certainly meant one of the two."""
        self.assertFalse(factions.is_hostile("the_cold_ones"))
        self.assertEqual(0, factions.attitude(None, "the_cold_ones", "player"))
        self.assertTrue(factions.can_converse({"faction": "the_cold_ones"}))
        # An actor the engine knows nothing about at all is the exception.
        self.assertFalse(factions.can_converse({"name": "something"}))


class TestNoCallSiteComparesFactionStrings(unittest.TestCase):
    """The tripwire under the refactor.

    A single `npc.faction == "hostile"` reintroduced anywhere in the engine puts
    a content set's own faction names back outside the behaviour it declared, and
    it would do so silently. The module that answers the question is allowed to
    mention the word; nothing else is.
    """

    ALLOWED = {"world/factions.py"}

    def test_engine_code_asks_the_accessor_instead_of_comparing_strings(self) -> None:
        pattern = re.compile(
            r"""faction\s*(?:==|!=)\s*['"](?:hostile|friendly|neutral|player_minion|player)['"]"""
            r"""|['"](?:hostile|friendly|neutral|player_minion)['"]\s*(?:==|!=)\s*\w*\.?faction"""
        )
        offenders = []
        for path in sorted(ENGINE_ROOT.rglob("*.py")):
            relative = path.relative_to(ENGINE_ROOT).as_posix()
            if relative in self.ALLOWED:
                continue
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if pattern.search(line):
                    offenders.append("%s:%d %s" % (relative, number, line.strip()))

        self.assertEqual([], offenders, "ask engine.world.factions instead:\n" + "\n".join(offenders))


class FactionSetBase(unittest.TestCase):
    """A minimal playable set whose only unusual feature is its own faction."""

    def _build(self, *, faction: str, ruleset_extra: dict | None = None) -> Path:
        root = REPO_ROOT / "tmp" / ("faction_set_%s" % uuid.uuid4().hex)
        package = root / "raider_game"
        data = package / "data"
        for directory in ("regions", "items", "npcs"):
            (data / directory).mkdir(parents=True, exist_ok=True)
        (package / "rules").mkdir(parents=True, exist_ok=True)
        (package / "presentation").mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        (data / "npcs" / "raiders.json").write_text(json.dumps({
            "raider": {
                "name": "a raider",
                "description": "A wiry figure in mismatched leathers.",
                "health": 30,
                "level": 1,
                "faction": faction,
                "behavior_type": "aggressive",
                "properties": {"aggression": 1.0, "wander_chance": 0.0, "move_cooldown": 9999},
            }
        }), encoding="utf-8")
        (data / "regions" / "camp.json").write_text(json.dumps({
            "region_id": "camp",
            "name": "Camp",
            "rooms": {
                "gate": {
                    "name": "Gate", "description": "A gate.", "exits": {"north": "yard"},
                },
                "yard": {
                    "name": "Yard", "description": "A yard.", "exits": {"south": "gate"},
                    "initial_npcs": [{"template_id": "raider", "instance_id": "raider_in_yard"}],
                },
            },
        }), encoding="utf-8")

        ruleset = {"ruleset_id": "raider_core", "progression_model": "level_based"}
        if ruleset_extra:
            ruleset.update(ruleset_extra)
        (package / "rules" / "ruleset.json").write_text(json.dumps(ruleset), encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / cs.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
            "id": "raider_game",
            "title": "Raider Game",
            "version": "0.1.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "paths": {
                "content_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "camp", "room_id": "yard"},
            "capabilities": ["inventory", "dialogue", "combat"],
        }), encoding="utf-8")
        return package


class TestADeclaredFactionIsTreatedAsSuch(FactionSetBase):
    def _start(self, package: Path):
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(package),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        session = server.create_session(player_id="faction_test")
        server.execute_command(session.session_id, "char create Raider Tester")
        player = server.get_player_for_session(session.session_id)
        return server, session, player

    def _command(self, server, session, text):
        return "\n".join(
            str(event.get("payload", ""))
            for event in server.execute_command(session.session_id, text)
            if event.get("type") == "text"
        )

    def test_the_raider_is_an_enemy_to_the_player_and_the_engine_agrees(self) -> None:
        package = self._build(
            faction="raiders",
            ruleset_extra={"factions": {"extra": [{"id": "raiders", "disposition": "hostile"}]}},
        )
        server, session, player = self._start(package)
        world = server.world
        raider = world.get_npc("raider_in_yard")

        # The combat matrix the engine uses for targeting.
        from engine.npcs.combat import get_relation_to, is_hostile_to

        self.assertLess(get_relation_to(raider, player), 0)
        self.assertTrue(is_hostile_to(raider, player))

        # Conversation is refused the way an enemy refuses it.
        refused = self._command(server, session, "talk raider")
        self.assertIn("refuses to listen", refused)

        # The room lists it as an enemy rather than as a person.
        listing = self._command(server, session, "look")
        self.assertIn("raider", listing.lower())

        # Killing one pays the reward a hostile pays, not the friendly penalty.
        before = int(player.reputation.get("friendly", 0))
        world._handle_reputation_on_kill({"player": player, "npc": raider})
        self.assertGreater(int(player.reputation.get("friendly", 0)), before)

    def test_the_raider_attacks_the_player_it_considers_an_enemy(self) -> None:
        package = self._build(
            faction="raiders",
            ruleset_extra={"factions": {"extra": [{"id": "raiders", "disposition": "hostile"}]}},
        )
        server, session, player = self._start(package)
        world = server.world
        raider = world.get_npc("raider_in_yard")

        from engine.npcs.ai.combat_logic import scan_for_targets

        message = scan_for_targets(raider, world, player, force_aggression=True)

        self.assertTrue(raider.in_combat or message, "a declared enemy must engage")
        self.assertIn(player, raider.combat_targets)

    def test_the_same_content_without_the_declaration_is_a_bystander(self) -> None:
        """What the set looks like if it forgets to declare its faction: the
        raider is nobody's enemy, and can be chatted with."""
        package = self._build(faction="raiders")
        server, session, player = self._start(package)
        world = server.world
        raider = world.get_npc("raider_in_yard")

        self.assertFalse(factions.is_hostile(raider, world))
        self.assertIn("CONVERSATION", self._command(server, session, "talk raider"))

    def test_an_override_restates_what_an_engine_faction_means(self) -> None:
        package = self._build(
            faction="neutral",
            ruleset_extra={"factions": {"overrides": {"neutral": "hostile"}}},
        )
        server, session, player = self._start(package)
        world = server.world
        raider = world.get_npc("raider_in_yard")

        self.assertTrue(factions.is_hostile(raider, world), "in this world nobody is neutral")
        self.assertFalse(factions.can_converse(raider, world))

    def test_two_declared_hostile_kinds_ignore_each_other(self) -> None:
        """The built-in `hostile` row says 0 about itself -- goblins have never
        fought wolves -- and a set's own hostile kind inherits exactly that."""
        package = self._build(
            faction="raiders",
            ruleset_extra={
                "factions": {
                    "extra": [
                        {"id": "raiders", "disposition": "hostile"},
                        {"id": "beasts", "disposition": "hostile"},
                    ]
                }
            },
        )
        server, _, _ = self._start(package)
        world = server.world

        self.assertEqual(0, factions.attitude(world, "raiders", "beasts"))
        self.assertLess(factions.attitude(world, "raiders", "player"), 0)
        self.assertIn("beasts", factions.factions(world))


class TestTheDeclarationIsValidated(FactionSetBase):
    def _issues(self, section) -> list:
        return factions.issues(factions.RulesetView({"factions": section}))

    def test_a_disposition_must_be_one_of_the_engine_s_dispositions(self) -> None:
        problems = self._issues({"extra": [{"id": "raiders", "disposition": "murderous"}]})

        self.assertTrue(any("murderous" in problem for problem in problems), problems)

    def test_a_faction_without_a_disposition_is_reported(self) -> None:
        problems = self._issues({"extra": [{"id": "raiders"}]})

        self.assertTrue(any("must declare a disposition" in problem for problem in problems), problems)

    def test_an_engine_faction_cannot_be_redeclared_as_an_extra(self) -> None:
        problems = self._issues({"extra": [{"id": "hostile", "disposition": "hostile"}]})

        self.assertTrue(any("engine faction" in problem for problem in problems), problems)

    def test_a_duplicate_declaration_is_reported(self) -> None:
        problems = self._issues({
            "extra": [
                {"id": "raiders", "disposition": "hostile"},
                {"id": "raiders", "disposition": "neutral"},
            ]
        })

        self.assertTrue(any("declares 'raiders' 2 times" in problem for problem in problems), problems)

    def test_an_override_of_an_unknown_faction_is_reported(self) -> None:
        problems = self._issues({"overrides": {"raiders": "hostile"}})

        self.assertTrue(any("factions.extra instead" in problem for problem in problems), problems)

    def test_a_malformed_section_reaches_the_content_gate(self) -> None:
        package = self._build(
            faction="raiders",
            ruleset_extra={"factions": {"extra": [{"id": "raiders", "disposition": "murderous"}]}},
        )

        issues = cs.validate_content_set(package)

        self.assertTrue(
            any(i.severity == "error" and "murderous" in i.message for i in issues),
            [i.message for i in issues],
        )

    def test_an_undeclared_faction_on_an_npc_warns_rather_than_failing(self) -> None:
        """The set still loads -- the NPC is simply a bystander -- but the author
        is told, because the alternative is a guard who never fights."""
        package = self._build(faction="raiders")

        issues = cs.validate_content_set(package)

        warning = [i for i in issues if i.severity == "warning" and "raiders" in i.message]
        self.assertTrue(warning, [i.message for i in issues])
        self.assertFalse([i for i in issues if i.severity == "error"])

    def test_a_declared_faction_produces_no_warning(self) -> None:
        package = self._build(
            faction="raiders",
            ruleset_extra={"factions": {"extra": [{"id": "raiders", "disposition": "hostile"}]}},
        )

        issues = cs.validate_content_set(package)

        self.assertFalse([i for i in issues if "faction" in i.message], [i.message for i in issues])


if __name__ == "__main__":
    unittest.main()
