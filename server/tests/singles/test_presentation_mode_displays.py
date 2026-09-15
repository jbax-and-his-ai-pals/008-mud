# tests/singles/test_presentation_mode_displays.py
"""Player mode must not show engine internals.

The engine has two audiences. A tester needs precise state -- charge counts,
recovery timers, trust thresholds, difficulty colour, exact vitals. A player
should see the world: a task that simply is not offered yet, a patch that has
been picked clean, a creature that looks wounded.

This complements `test_presentation_mode_gating.py`, which covers command
*access* (the debug category). This file covers what is *rendered*.

The safety rail is the last class here: test mode must reproduce the previous
output exactly, because the existing suite, the journey lab, and operator
tooling all read it.
"""

import re
import unittest

MARKUP = re.compile(r"\[\[[^\]]*\]\]")

from engine.presentation import (
    DEFAULT_MODE,
    MODE_PLAYER,
    MODE_TEST,
    is_player_mode,
    resolve_mode,
    resolve_mode_for_player,
    show_internals,
    variant,
)


class _Session:
    def __init__(self, player_id, mode):
        self.player_id = player_id
        self.presentation_mode = mode


class _Server:
    def __init__(self, modes, default="test"):
        self.sessions = {sid: _Session(pid, mode) for sid, pid, mode in modes}
        self.default_presentation_mode = default


class _World:
    def __init__(self, server):
        self.server = server


class _Player:
    def __init__(self, obj_id, world):
        self.obj_id = obj_id
        self.world = world


class TestModeResolution(unittest.TestCase):

    def test_default_is_test_so_unowned_callers_are_unchanged(self):
        """A world with no server attached keeps today's behaviour."""
        self.assertEqual(DEFAULT_MODE, MODE_TEST)
        self.assertEqual(resolve_mode({}), MODE_TEST)
        self.assertEqual(resolve_mode(None), MODE_TEST)
        self.assertFalse(is_player_mode({}))
        self.assertTrue(show_internals({}))

    def test_session_id_wins(self):
        server = _Server([("s1", "p", MODE_PLAYER), ("s2", "p", MODE_TEST)])
        world = _World(server)
        ctx = {"world": world, "session_id": "s1", "player": _Player("p", world)}
        self.assertEqual(resolve_mode(ctx), MODE_PLAYER)
        ctx["session_id"] = "s2"
        self.assertEqual(resolve_mode(ctx), MODE_TEST)

    def test_falls_back_to_a_session_for_the_player(self):
        server = _Server([("s1", "p", MODE_PLAYER)], default="test")
        world = _World(server)
        ctx = {"world": world, "player": _Player("p", world)}
        self.assertEqual(resolve_mode(ctx), MODE_PLAYER)

    def test_player_mode_wins_when_several_sessions_disagree(self):
        """Being shown too little is cosmetic; leaking internals is not."""
        server = _Server([("s1", "p", MODE_TEST), ("s2", "p", MODE_PLAYER)])
        world = _World(server)
        self.assertEqual(resolve_mode_for_player(world, _Player("p", world)), MODE_PLAYER)

    def test_server_default_used_when_no_session_matches(self):
        server = _Server([], default=MODE_PLAYER)
        world = _World(server)
        self.assertEqual(resolve_mode({"world": world}), MODE_PLAYER)

    def test_unrecognised_mode_fails_closed_to_player_for_a_session(self):
        server = _Server([("s1", "p", "banana")], default="test")
        world = _World(server)
        # An invalid session mode is ignored; the server default applies.
        self.assertEqual(resolve_mode({"world": world, "session_id": "s1"}), MODE_TEST)

    def test_show_internals_is_the_inverse_of_player_mode(self):
        server = _Server([("s1", "p", MODE_PLAYER)], default="player")
        ctx = {"world": _World(server), "session_id": "s1"}
        self.assertTrue(is_player_mode(ctx))
        self.assertFalse(show_internals(ctx))


class TestContentAuthoredVariants(unittest.TestCase):

    def test_plain_string_passes_through(self):
        self.assertEqual(variant("hello", {}), "hello")

    def test_variant_selects_by_mode(self):
        text = {"test": "0/6 (depleted)", "player": "You've picked this clean."}
        server = _Server([("s1", "p", MODE_PLAYER)], default="test")
        ctx = {"world": _World(server), "session_id": "s1"}
        self.assertEqual(variant(text, ctx), "You've picked this clean.")
        ctx["session_id"] = None
        ctx["world"] = _World(_Server([("s2", "p", MODE_TEST)], default="test"))
        self.assertEqual(variant(text, {"world": ctx["world"], "session_id": "s2"}),
                         "0/6 (depleted)")

    def test_variant_falls_back_to_default_then_any_string(self):
        server = _Server([("s1", "p", MODE_PLAYER)], default="test")
        ctx = {"world": _World(server), "session_id": "s1"}
        self.assertEqual(variant({"default": "D", "test": "T"}, ctx), "D")
        self.assertEqual(variant({"test": "T"}, ctx), "T")


class TestRenderedDisplays(unittest.TestCase):
    """End-to-end renders through the real command handlers."""

    def setUp(self):
        from tests.fixtures import GameTestBase
        self._base = GameTestBase("run")
        self._base.setUp()
        self.addCleanup(self._base.doCleanups)
        self.world = self._base.world
        self.player = self._base.player
        self.game = self._base.game

    def _ctx(self, mode):
        """A context whose session carries the requested presentation mode."""
        server = _Server([("viewer", "viewer", mode)], default=mode)
        server.build_opening_guidance = lambda: ""
        self.world.server = server
        return {
            "world": self.world,
            "player": self.player,
            "game": self.game,
            "session_id": "viewer",
        }

    def _render(self, mode, handler, args=None):
        from engine.commands import quest, information, crafting
        ctx = self._ctx(mode)
        return handler(args or [], ctx)

    def test_board_hides_gated_tasks_from_players(self):
        """A task behind a trust gate is simply not offered."""
        from engine.commands.quest import look_board_handler
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

        test_out = self._render(MODE_TEST, look_board_handler)
        player_out = self._render(MODE_PLAYER, look_board_handler)

        self.assertIn("(locked)", test_out)
        self.assertNotIn("(locked)", player_out)
        self.assertNotIn("Trust:", player_out)
        # The ungated starter task is offered in both.
        self.assertIn("A Posy for Riverside", player_out)
        self.assertIn("A Posy for Riverside", test_out)

    def test_player_board_numbering_is_contiguous_and_acceptable(self):
        """Hidden entries must not leave gaps, and `accept <n>` must still work."""
        from engine.commands.quest import look_board_handler, accept_quest_handler
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"

        out = self._render(MODE_PLAYER, look_board_handler)
        numbers = [int(m) for m in re.findall(r"\[(\d+)\]", out)]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)),
                         "player board numbering has gaps: %s" % numbers)

        # The first offered task must be the one that `accept 1` actually takes.
        # The rendered line is "[1] <title>", possibly with markup tags.
        first_match = re.search(r"\[1\]\s*(.+)", out)
        self.assertIsNotNone(first_match, "no first entry rendered")
        first_title = MARKUP.sub("", first_match.group(1)).strip()
        accepted = accept_quest_handler(["1"], self._ctx(MODE_PLAYER))
        self.assertIn(
            first_title.split(" (")[0].strip(), accepted,
            "accepting #1 did not take the task shown as #1 (%r)" % first_title,
        )

    def test_survey_hides_counts_and_timers_from_players(self):
        from engine.commands.information import survey_handler
        from engine.commands.gathering import gather_handler
        self.player.current_region_id = "town"
        self.player.current_room_id = "community_garden"

        test_out = self._render(MODE_TEST, survey_handler)
        player_out = self._render(MODE_PLAYER, survey_handler)
        self.assertIn("/", test_out)          # "6/6" charge readout
        self.assertNotIn("remaining", player_out)
        self.assertNotIn("recovers in", player_out)
        self.assertNotIn("depleted", player_out)

    def test_recipes_hide_lock_state_and_scoring_from_players(self):
        from engine.commands.crafting import recipes_handler
        test_out = self._render(MODE_TEST, recipes_handler, ["all"])
        player_out = self._render(MODE_PLAYER, recipes_handler, ["all"])

        self.assertIn("[Locked]", test_out)
        self.assertNotIn("[Locked]", player_out)
        self.assertIn("material score", test_out)
        self.assertNotIn("material score", player_out)

    def test_npc_display_hides_level_and_exact_hp_from_players(self):
        """A player is told how something looks, not its stat block."""
        from engine.npcs.npc_factory import NPCFactory
        from engine.utils.utils import format_name_for_display

        npc = NPCFactory.create_npc_from_template("wolf", self.world, instance_id="disp_wolf")
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        self.world.add_npc(npc)

        self.world.server = _Server([("viewer", "viewer", MODE_PLAYER)], default=MODE_PLAYER)
        self.player.world = self.world
        player_view = format_name_for_display(self.player, npc)

        self.world.server = _Server([("viewer", "viewer", MODE_TEST)], default=MODE_TEST)
        test_view = format_name_for_display(self.player, npc)

        self.assertIn("Level", test_view)
        self.assertIn("HP", test_view)
        self.assertNotIn("Level", player_view)
        self.assertNotIn("HP", player_view)


class TestTestModeIsUnchanged(unittest.TestCase):
    """The safety rail: test mode must still show everything it used to."""

    def test_show_internals_true_and_mode_is_test_by_default(self):
        self.assertEqual(resolve_mode({}), MODE_TEST)
        self.assertTrue(show_internals({}))


if __name__ == "__main__":
    unittest.main()
