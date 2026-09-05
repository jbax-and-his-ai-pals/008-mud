# tests/singles/test_logger.py
"""Coverage for engine/utils/logger.py: the singleton __new__, each level's
convenience method actually printing when its level is enabled (vs. being
suppressed when below threshold), the unrecognized-level name fallback, and
separator()'s enabled/suppressed branches."""

import io
import unittest
from contextlib import redirect_stdout

from engine.utils.logger import Logger, LogLevel


class TestLoggerSingleton(unittest.TestCase):
    def test_new_returns_the_same_instance_every_time(self):
        first = Logger()
        second = Logger()
        self.assertIs(first, second)

    def tearDown(self):
        Logger.set_level(LogLevel.CRITICAL)


class TestLoggerLevelMethods(unittest.TestCase):
    def tearDown(self):
        Logger.set_level(LogLevel.CRITICAL)

    def test_debug_prints_when_level_permits(self):
        Logger.set_level(LogLevel.DEBUG)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.debug("Src", "debug message")
        self.assertIn("DEBUG", buf.getvalue())
        self.assertIn("debug message", buf.getvalue())

    def test_debug_suppressed_below_threshold(self):
        Logger.set_level(LogLevel.INFO)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.debug("Src", "should not appear")
        self.assertEqual(buf.getvalue(), "")

    def test_info_prints_when_level_permits(self):
        Logger.set_level(LogLevel.INFO)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.info("Src", "info message")
        self.assertIn("INFO", buf.getvalue())

    def test_warning_prints_when_level_permits(self):
        Logger.set_level(LogLevel.WARNING)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.warning("Src", "warn message")
        self.assertIn("WARN", buf.getvalue())

    def test_error_prints_when_level_permits(self):
        Logger.set_level(LogLevel.ERROR)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.error("Src", "error message")
        self.assertIn("ERROR", buf.getvalue())

    def test_critical_prints_when_level_permits(self):
        Logger.set_level(LogLevel.CRITICAL)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.critical("Src", "critical message")
        self.assertIn("CRIT", buf.getvalue())

    def test_unrecognized_level_falls_back_to_log_label(self):
        Logger.set_level(LogLevel.DEBUG)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger._log(99, "Src", "mystery level")
        self.assertIn("[LOG  ]", buf.getvalue())


class TestLoggerSeparator(unittest.TestCase):
    def tearDown(self):
        Logger.set_level(LogLevel.CRITICAL)

    def test_prints_when_level_permits(self):
        Logger.set_level(LogLevel.DEBUG)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.separator()
        self.assertIn("-" * 60, buf.getvalue())

    def test_suppressed_when_below_threshold(self):
        Logger.set_level(LogLevel.CRITICAL)
        buf = io.StringIO()
        with redirect_stdout(buf):
            Logger.separator(level=LogLevel.DEBUG)
        self.assertEqual(buf.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
