# tests/singles/test_death_penalty.py
"""`ruleset.death.gold_loss_fraction`: part of the money carried is lost when the character falls."""

import unittest

from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE


def _hero(case, section=None):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                            default_presentation_mode="player")
    case.addCleanup(server.shutdown)
    if section is not None:
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: section if name == "death" else original(name)
    sid = server.create_session(player_id="hero").session_id
    server.execute_command(sid, "char create Aldric")
    player = server.get_player_for_session(sid)
    player.runtime_state.gold = 200
    return server, player


class TestDeathPenalty(unittest.TestCase):
    def test_a_set_that_says_nothing_loses_nothing(self):
        _server, player = _hero(self)
        player.die()
        self.assertEqual(200, player.runtime_state.gold)

    def test_half_is_lost(self):
        _server, player = _hero(self, {"gold_loss_fraction": 0.5})
        player.die()
        self.assertEqual(100, player.runtime_state.gold)

    def test_it_is_paid_once_however_often_death_is_reported(self):
        _server, player = _hero(self, {"gold_loss_fraction": 0.5})
        player.die()
        player.die()
        self.assertEqual(100, player.runtime_state.gold)

    def test_nothing_to_lose_is_not_a_penalty(self):
        _server, player = _hero(self, {"gold_loss_fraction": 0.5})
        player.runtime_state.gold = 1
        player.die()
        self.assertEqual(1, player.runtime_state.gold)

    def test_nonsense_loses_nothing(self):
        for value in (True, "half", -1, 2):
            _server, player = _hero(self, {"gold_loss_fraction": value})
            player.die()
            self.assertEqual(200, player.runtime_state.gold, value)


if __name__ == "__main__":
    unittest.main()
