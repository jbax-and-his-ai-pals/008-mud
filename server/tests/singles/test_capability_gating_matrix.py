"""Regression coverage for content-set capability gating.

Fantasy Frontier declares every optional system (combat, magic, crafting,
quests, economy, a level-based progression model). Modern Capsule declares
none of them -- only `inventory` and `dialogue`. Every command decorated with
`content_capability=`/`ruleset_system=` in engine/commands/*.py is supposed
to be refused in Modern Capsule and reach real handling in Fantasy Frontier.

docs/roadmap/content-engine-roadmap.md calls this out directly: capability
gating is "a tested boundary, not a claim that all runtime behavior is
capability-driven." Before this file, that boundary was spot-checked for 3
of the 8 gated systems (combat, quests, progression) by
test_content_set_runtime.py. This file exercises all of them, command by
command, so a new gated command -- or a regression in an existing one --
shows up here instead of only in manual playtesting.
"""

import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPO_ROOT / "content_sets" / "modern_capsule"

# (invocation text, system name expected in the block message). Mirrors every
# content_capability=/ruleset_system= declaration in engine/commands/*.py as
# of this writing. Args are chosen to reach each handler's first safe
# no-op/error branch so the gate (which runs before the handler) is the only
# thing under test -- a new gated command needs an entry here to be covered.
GATED_COMMANDS = [
    ("attack nobody", "combat"),
    ("combat", "combat"),
    ("recipes", "crafting"),
    ("craft anything", "crafting"),
    ("salvage anything", "crafting"),
    ("cast", "magic"),
    ("spells", "magic"),
    ("look board", "quests"),
    ("accept quest 1", "quests"),
    ("journal", "quests"),
    ("skills", "progression"),
    ("rules", "economy"),
    ("bet 10", "economy"),
    ("hit", "economy"),
    ("stand", "economy"),
    ("guess fire water earth", "economy"),
    ("trade nobody", "economy"),
    ("list", "economy"),
    ("buy anything", "economy"),
    ("sell anything", "economy"),
    ("stoptrade", "economy"),
    ("repair anything", "economy"),
    ("repaircost anything", "economy"),
]

# Commands gated on `inventory`, which both reference content sets enable.
# Kept separate because there is no shipped content set to exercise the
# "blocked" side of this gate -- see test_inventory_gate_blocks_via_synthetic_contract.
INVENTORY_GATED_COMMANDS = ["inventory", "invmode", "equip", "unequip"]


def _boot(content_set_path: Path) -> HeadlessServer:
    return HeadlessServer(
        db_path=":memory:",
        content_set_path=str(content_set_path),
        deterministic_test_mode=True,
    )


class TestCapabilityGatingMatrix(unittest.TestCase):
    def setUp(self) -> None:
        self.modern = _boot(MODERN_CAPSULE)
        self.addCleanup(self.modern.shutdown)
        modern_session = self.modern.create_session(player_id="gating_modern_player")
        self.modern.execute_command(modern_session.session_id, "char create Gating")
        self.modern_session_id = modern_session.session_id

        self.fantasy = _boot(FANTASY_FRONTIER)
        self.addCleanup(self.fantasy.shutdown)
        fantasy_session = self.fantasy.create_session(player_id="gating_fantasy_player")
        self.fantasy.execute_command(fantasy_session.session_id, "char create Gating")
        self.fantasy_session_id = fantasy_session.session_id

    @staticmethod
    def _events_text(server: HeadlessServer, session_id: str, command_text: str) -> str:
        events = server.execute_command(session_id, command_text)
        return "\n".join(str(event["payload"]) for event in events)

    def test_every_gated_command_is_blocked_when_its_system_is_disabled(self) -> None:
        for command_text, system in GATED_COMMANDS:
            with self.subTest(command=command_text, system=system):
                output = self._events_text(self.modern, self.modern_session_id, command_text)
                self.assertIn(f"does not include the '{system}' system", output)

    def test_every_gated_command_reaches_real_handling_when_its_system_is_enabled(self) -> None:
        for command_text, system in GATED_COMMANDS:
            with self.subTest(command=command_text, system=system):
                output = self._events_text(self.fantasy, self.fantasy_session_id, command_text)
                self.assertNotIn("does not include the", output)

    def test_inventory_commands_are_not_blocked_in_either_content_set(self) -> None:
        # Both shipped content sets declare `inventory`, so this is a sanity
        # check that the gate itself isn't over-triggering, not a test of the
        # "disabled" branch (see the synthetic-contract test below for that).
        for command_text in INVENTORY_GATED_COMMANDS:
            with self.subTest(command=command_text, content_set="modern"):
                output = self._events_text(self.modern, self.modern_session_id, command_text)
                self.assertNotIn("does not include the", output)
            with self.subTest(command=command_text, content_set="fantasy"):
                output = self._events_text(self.fantasy, self.fantasy_session_id, command_text)
                self.assertNotIn("does not include the", output)

    def test_disabled_system_categories_are_hidden_from_help_and_gone_from_command_help(self) -> None:
        modern_help = self._events_text(self.modern, self.modern_session_id, "help")
        for keyword in ("Combat", "Magic", "Crafting"):
            self.assertNotIn(keyword, modern_help)

        for command_text in ("attack", "cast", "craft", "skills", "trade", "accept quest"):
            with self.subTest(command=command_text):
                help_output = self._events_text(self.modern, self.modern_session_id, f"help {command_text}")
                self.assertIn("not available in this game", help_output)

    def test_enabled_system_categories_surface_in_help(self) -> None:
        fantasy_help = self._events_text(self.fantasy, self.fantasy_session_id, "help")
        for keyword in ("Combat", "Magic", "Crafting"):
            self.assertIn(keyword, fantasy_help)


class TestSyntheticCapabilityGating(unittest.TestCase):
    """Exercise the one gated system (`inventory`) neither shipped content
    set disables, using the same synthetic-GameContract technique as
    test_content_set_runtime.test_mixed_contracts_compose_only_their_declared_player_aspects.
    """

    def test_inventory_gate_blocks_via_synthetic_contract(self) -> None:
        from dataclasses import replace
        from unittest.mock import patch

        from engine.server.content_set import GameContract, load_content_set

        modern_definition, issues = load_content_set(MODERN_CAPSULE)
        self.assertIsNotNone(modern_definition, issues)
        assert modern_definition is not None

        no_inventory_contract = GameContract(
            progression_model="none",
            systems=tuple(sorted({
                "inventory": False, "dialogue": True, "combat": False, "magic": False,
                "crafting": False, "quests": False, "progression": False, "economy": False,
            }.items())),
            status_fields=("name", "health"),
            ui_sections=("log", "nearby", "status"),
        )
        no_inventory_definition = replace(
            modern_definition,
            content_set_id="no_inventory",
            capabilities=("dialogue",),
            game_contract=no_inventory_contract,
        )
        with patch("engine.server.headless_server.load_content_set", return_value=(no_inventory_definition, [])):
            server = _boot(MODERN_CAPSULE)
        try:
            session = server.create_session(player_id="no_inventory_player")
            server.execute_command(session.session_id, "char create NoBags")
            for command_text in INVENTORY_GATED_COMMANDS:
                with self.subTest(command=command_text):
                    events = server.execute_command(session.session_id, command_text)
                    output = "\n".join(str(event["payload"]) for event in events)
                    self.assertIn("does not include the 'inventory' system", output)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
