# tests/singles/test_world_time_is_continuous.py
"""The world ages with the server, not with the number of people watching it.

The decision (2026-09-19): *if everything is a server, even when single player,
then the world time advances continuously for as long as the server is up.*

That was not true. Both background tick loops read

    if not active_session_ids:
        continue

so a server with nobody connected simulated nothing. In single-player this is not
a subtle scaling property, it is the whole game: close the client and the season
stops. It was invisible in play because the disconnect and the freeze happen
together -- you only see it from outside, which is what these tests do.

The player-specific half is deliberately unchanged. `tick(session_id)` still only
advances the player named by that session, because a disconnected player's
cooldowns and regeneration are that player's, not the world's.
"""
import unittest
import time
from pathlib import Path

from tests.fixtures import FANTASY_FRONTIER, GameTestBase, make_test_server


SERVER_ROOT = Path(__file__).resolve().parents[2]


class TestTickAdvancingNeedsNoSession(GameTestBase):
    """`tick(None)` is the server-with-nobody-connected case."""

    def setUp(self):
        super().setUp()
        self.server = make_test_server()
        self.server.world.game = self.game
        self.addCleanup(self._stop_server)

    def _stop_server(self):
        try:
            self.server.stop()
        except Exception:
            pass

    def _use_explicit_dt(self):
        """Let the dt passed to `tick` be the dt used.

        `deterministic_test_mode` makes `tick` ignore its own `dt` argument and
        substitute `tick_dt`. That is right for tests that want a fixed step and
        wrong for these, whose whole subject is how far the world moves for a
        given span of real time.
        """
        self.server.deterministic_test_mode = False

    def test_tick_accepts_no_session(self):
        """The signature has to allow it before any of the rest can."""
        events = self.server.tick(None)
        self.assertIsInstance(events, list)

    def test_time_advances_with_no_session(self):
        """The claim, in one assertion: a session-less tick moves the clock."""
        before = self.server.time_manager.game_time
        self.server.tick(None, dt=self.server.tick_dt)
        self.assertGreater(
            self.server.time_manager.game_time, before,
            "a tick with nobody connected must still advance world time",
        )

    def test_repeated_ticks_keep_advancing(self):
        """One tick could be an initialisation side effect; ten is a clock."""
        start = self.server.time_manager.game_time
        for _ in range(10):
            self.server.tick(None, dt=self.server.tick_dt)
        self.assertGreater(self.server.time_manager.game_time, start)

    def test_a_long_absence_advances_time_by_that_much(self):
        """The single-player case: an absence is world time, scaled by the game's rate.

        `TimeManager.update` multiplies real dt by `86400 / TIME_REAL_SECONDS_PER_GAME_DAY`
        -- with the shipped 1200 that is 72 game-seconds per real second, so a
        minute of downtime is 72 minutes of world time. Asserted as the exact
        product rather than "more than before", so a change to the rate shows up
        here instead of quietly halving how fast the world ages.
        """
        from engine.config import TIME_REAL_SECONDS_PER_GAME_DAY

        self._use_explicit_dt()
        ratio = 86400 / TIME_REAL_SECONDS_PER_GAME_DAY
        before = self.server.time_manager.game_time
        real_seconds = 60.0
        self.server.tick(None, dt=real_seconds)
        self.assertAlmostEqual(
            self.server.time_manager.game_time, before + real_seconds * ratio, places=4,
            msg="world time should advance by dt * the game-time rate",
        )

    def _ticks_for_game_days(self, days: float) -> float:
        """How much real dt the world needs to age by `days` game days."""
        from engine.config import TIME_REAL_SECONDS_PER_GAME_DAY

        return (days * 86400) / (86400 / TIME_REAL_SECONDS_PER_GAME_DAY)

    def test_a_full_year_passes_with_nobody_connected(self):
        """The point of the decision, at the scale a player would notice.

        Seasons are derived from the month (`(month - 1) * 4 / 12`), so all four
        arrive within one game year. If time only moved while connected, a player
        who plays in short sessions could never reach winter -- which is the season
        the whole preservation half of this chunk exists to give counterplay to.
        """
        from engine.config import TIME_DAYS_PER_MONTH, TIME_MONTHS_PER_YEAR

        self._use_explicit_dt()
        seen = {self.server.time_manager.time_data.get("season")}
        year_days = float(TIME_DAYS_PER_MONTH * TIME_MONTHS_PER_YEAR)
        # Twelve steps, so every month boundary is crossed inside a tick.
        for _ in range(12):
            self.server.tick(None, dt=self._ticks_for_game_days(year_days / 12.0))
            seen.add(self.server.time_manager.time_data.get("season"))
        self.assertEqual(
            {"winter", "spring", "summer", "fall"}, seen,
            "a game year should pass with no client connected",
        )

    def test_the_weather_provider_hears_about_an_unwatched_period_change(self):
        """A time transition must not depend on a session to fire.

        Stepped in six-hour slices rather than one day: a whole game day lands on
        the same time of day it started from, so it crosses the boundaries and
        arrives back where it began without ever reporting a change. That is
        correct behaviour, and it is why this test walks the clock instead of
        jumping it.
        """
        self._use_explicit_dt()
        changes = []
        original = self.server.weather_provider.on_time_period_change

        def spy(*args, **kwargs):
            changes.append(args)
            return original(*args, **kwargs)

        self.server.weather_provider.on_time_period_change = spy
        self.addCleanup(setattr, self.server.weather_provider, "on_time_period_change", original)
        periods = {self.server.time_manager.current_time_period}
        for _ in range(4):
            self.server.tick(None, dt=self._ticks_for_game_days(1.0 / 4.0))
            periods.add(self.server.time_manager.current_time_period)
        self.assertTrue(changes, "the weather provider should hear about a period change")
        self.assertGreater(len(periods), 1, "a day walked in quarters should show several periods")


class TestTheBackgroundBatchDoesNotGrowUnwatched(GameTestBase):
    """With nobody to send to, ambient events must be dropped, not accumulated."""

    def setUp(self):
        super().setUp()
        self.server = make_test_server()
        self.server.world.game = self.game
        self.addCleanup(lambda: self.server.stop() if hasattr(self.server, "stop") else None)

    def test_discard_background_batch_empties_it(self):
        self.server._background_event_batch.append({"type": "text", "payload": "ambient"})
        self.assertNotEqual([], self.server._background_event_batch)
        self.server.discard_background_batch()
        self.assertEqual([], self.server._background_event_batch)

    def test_a_long_unwatched_run_does_not_accumulate_events(self):
        """Unbounded growth here would be a memory leak with a season for a clock."""
        for _ in range(40):
            self.server.tick(None, dt=600.0)
            self.server.discard_background_batch()
        self.assertEqual(
            [], self.server._background_event_batch,
            "an unwatched server must not queue events for a session that may never come",
        )


class TestTheTickLoopsAdvanceWithZeroSessions(unittest.TestCase):
    """Drive the real loop with no sessions and assert it ticks the world.

    The loop is `while True: await asyncio.sleep(...)`, so it is run for exactly
    one iteration by replacing the sleep with something that stops it. That makes
    this a behavioural test of the branch rather than a reading of its source,
    which matters because the bug being guarded was one line of control flow.
    """

    # (module, driver class, attribute path to the HeadlessServer, sessions attr)
    LOOPS = {
        "ws": ("poc_ws_server", "JsonWebSocketMudServer", ("core", "server"), "_ws_sessions"),
        "tcp": ("poc_server", "JsonLineMudServer", ("server",), "_session_writers"),
    }

    def _one_iteration(self, key: str):
        import asyncio
        import importlib

        module_name, class_name, server_path, sessions_attr = self.LOOPS[key]
        module = importlib.import_module(module_name)
        driver = getattr(module, class_name)(
            "127.0.0.1", 0, "world_time_test_save.json",
            asset_db_path=":memory:", content_set_path=str(FANTASY_FRONTIER),
        )
        server = driver
        for attribute in server_path:
            server = getattr(server, attribute)

        ticks = []
        original_tick = server.tick

        def spy(session_id=None, dt=None):
            ticks.append((session_id, dt))
            return original_tick(session_id, dt)

        server.tick = spy
        # No sessions at all: the exact condition the old `continue` keyed on.
        setattr(driver, sessions_attr, {})

        calls = {"n": 0}

        async def one_shot(_seconds):
            calls["n"] += 1
            if calls["n"] > 1:
                raise asyncio.CancelledError()

        real_sleep = asyncio.sleep
        asyncio.sleep = one_shot
        try:
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(driver._run_background_ticks())
        finally:
            asyncio.sleep = real_sleep
            server.tick = original_tick
            try:
                server.stop()
            except Exception:
                pass

        return ticks

    def test_the_websocket_loop_ticks_the_world_with_no_clients(self):
        ticks = self._one_iteration("ws")
        self.assertTrue(ticks, "a server with no clients must still advance the world")

    def test_the_tcp_loop_ticks_the_world_with_no_clients(self):
        ticks = self._one_iteration("tcp")
        self.assertTrue(ticks, "a server with no clients must still advance the world")

    def test_the_tick_is_made_without_a_session(self):
        """`tick(None)` is what makes this the zero-client case."""
        ticks = self._one_iteration("ws")
        self.assertEqual(
            None, ticks[-1][0],
            "with no clients the world should be advanced with no session",
        )

    def test_both_loops_drop_unaddressed_ambient_events(self):
        """They are twins; a fix in one and not the other is a transport bug."""
        for name, path in (("tcp", SERVER_ROOT / "poc_server.py"),
                           ("ws", SERVER_ROOT / "poc_ws_server.py")):
            with self.subTest(loop=name):
                self.assertIn("discard_background_batch()", path.read_text(encoding="utf-8"))

    def test_the_tick_signature_allows_a_missing_session(self):
        lifecycle = (SERVER_ROOT / "engine" / "server" / "headless" / "lifecycle.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("def tick(self, session_id: Optional[str] = None", lifecycle)


if __name__ == "__main__":
    unittest.main()
