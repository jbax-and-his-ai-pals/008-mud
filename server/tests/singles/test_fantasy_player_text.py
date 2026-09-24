"""WORLD_DESIGN §9 item 5: a new player "never sees `?`, `(locked)`, a reset
timer, or a debug command."

Each background creates a character in player presentation and plays the
opening minutes -- the background list it chose from, the square, the board,
help, its kit, its first steps -- and everything it is shown is scanned for
engine vocabulary: template ids, unfilled `{placeholders}`, `(locked)`, reset
or respawn timers, runs of question marks, and admin/debug commands. The
background list itself used to show its starting kit as template ids
(`item_padded_tunic, item_crude_club, ...`) on the very screen a new player
reads to choose.
"""

import re
import unittest
from pathlib import Path

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"

FORBIDDEN = {
    "template id": r"\b(item|npc|quest|node|scroll|recipe)_[a-z0-9_]+\b",
    "unfilled placeholder": r"\{[a-z_]+\}",
    "(locked)": r"\(locked\)",
    "reset timer": r"\bresets? in\b|\brespawns? in\b|\brecovers? in\b",
    "question marks": r"\?\?|\s\?(\s|$)",
    "debug command": r"\b(debug|sethealth|setlevel|teleport|genregion|godmode|givexp)\b",
}
OPENING = [
    "backgrounds", "look", "help", "inventory", "equipment", "quests", "board", "look board",
    "recipes", "skills", "status", "background", "discoveries", "weather", "time",
    "east", "look", "east", "look", "west", "west", "west", "look",
]


class TestNewPlayerText(unittest.TestCase):
    def test_the_opening_shows_no_engine_vocabulary_for_any_background(self):
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        backgrounds = [background.background_id for background in server.background_manager.available()]
        self.assertGreaterEqual(len(backgrounds), 2)
        found = []
        for index, background in enumerate(backgrounds):
            session = server.create_session(player_id=f"text_{background}")
            for command in [f"char create Reader{index} as {background}"] + OPENING:
                for line in self._text(server.execute_command(session.session_id, command)).splitlines():
                    for label, pattern in FORBIDDEN.items():
                        if re.search(pattern, line, re.IGNORECASE):
                            found.append(f"{background} / {command!r} shows {label}: {line.strip()[:160]}")
        self.assertEqual([], found)

    def test_the_background_list_names_the_kit(self):
        server = HeadlessServer(db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True)
        self.addCleanup(server.shutdown)
        listing = server.background_manager.listing()
        self.assertIn("Starts with: padded tunic, crude club, small healing potion x2", listing)
        self.assertNotRegex(listing, r"\bitem_[a-z_]+")

    @staticmethod
    def _text(events) -> str:
        lines = []
        for event in events or []:
            if isinstance(event, dict) and event.get("type") == "text":
                payload = event.get("payload")
                lines.append(str(payload.get("text", "") if isinstance(payload, dict) else payload))
        return "\n".join(lines)


if __name__ == "__main__":
    unittest.main()
