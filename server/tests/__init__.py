"""Test-package bootstrap configuration.

The Pygame ``GameManager`` is still used by a portion of the legacy unit
suite.  Use SDL's in-memory backends by default so running a large test suite
does not open a window per test.  A developer can opt into real SDL surfaces
when debugging a visual test with ``MUD_TEST_HEADLESS=0``.
"""

import os


if os.environ.get("MUD_TEST_HEADLESS", "1").strip().lower() not in {"0", "false", "no"}:
    # These must be in place before any test imports pygame through the engine.
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")


# Loading a content set validates every file in it and a test does it once per test: a set that has not
# changed on disk is answered from memory for the length of the run (engine.server.content_set.enable_load_cache).
from engine.server import content_set as _content_set  # noqa: E402

_content_set.enable_load_cache()
