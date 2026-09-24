"""WORLD_DESIGN section 9 item 8: a player "can earn a title by pursuing what
interests them, and it means something".

A title that asks only for a level is conferred on anyone who plays long
enough, whatever they did. Four fantasy titles were that, under names and
descriptions promising a deed: Collector (Curator Vane "asking what you have
found lately") at level 4, Frostpeak Hand (the Mining Lodge can count on you)
and Friend of Riverside (people "would speak for you") at level 5, and
Wayfarer ("out past the walls more than once") at level 3. Each now names the
deed; this keeps every title that way.
"""

import json
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TITLES = REPO_ROOT / "content_sets" / "fantasy_frontier" / "data" / "titles.json"


class TestFantasyTitlesAreEarned(unittest.TestCase):
    def test_no_title_rests_on_level_alone(self):
        titles = json.loads(TITLES.read_text(encoding="utf-8"))
        level_only = []
        for title_id, title in titles.items():
            if title_id.startswith("_") or not isinstance(title, dict):
                continue
            # titles.py combines `condition` and `requirements` as one `all`.
            requirements = title.get("requirements", [])
            conditions = ([title["condition"]] if title.get("condition") else []) + (requirements if isinstance(requirements, list) else [])
            if not any(isinstance(c, dict) and c.get("kind") != "level_at_least" for c in conditions):
                level_only.append(title_id)
        self.assertEqual([], level_only)


if __name__ == "__main__":
    unittest.main()
