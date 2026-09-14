# tests/singles/test_hostile_dialog_no_leftover_placeholders.py
"""NPC.talk() only ever calls .format() on the `default_dialog` fallback;
every other `dialog` key (greeting/threat/flee) is returned verbatim.
hostiles.json used to author `{name}` inside those fields for seven
templates, which would leak a literal unformatted brace to a player the
moment any code path read them. Guards the content fix directly."""

import json
import unittest
from pathlib import Path

CONTENT_ROOT = Path(__file__).resolve().parents[3] / "content_sets" / "fantasy_frontier" / "data" / "npcs"


class TestHostileDialogHasNoLeftoverPlaceholders(unittest.TestCase):
    def test_no_dialog_field_other_than_trade_contains_a_brace(self) -> None:
        payload = json.loads((CONTENT_ROOT / "hostiles.json").read_text(encoding="utf-8"))
        offenders = []
        for template_id, template in payload.items():
            dialog = template.get("dialog")
            if not isinstance(dialog, dict):
                continue
            for key, value in dialog.items():
                if key != "trade" and isinstance(value, str) and "{" in value:
                    offenders.append(f"{template_id}.dialog.{key} = {value!r}")
        self.assertEqual([], offenders)


if __name__ == "__main__":
    unittest.main()
