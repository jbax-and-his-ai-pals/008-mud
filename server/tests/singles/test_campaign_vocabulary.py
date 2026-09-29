"""The campaign vocabulary constants are what the engine actually does.

`CAMPAIGN_TRIGGERS` must be exactly the resolutions a quest completion can
report: a trigger outside them never fires, and a resolution missing from them
is one the validator would refuse authors to route. `CAMPAIGN_NODE_TYPES` must be
exactly the types `_trigger_node` acts on.
"""
import inspect
import re
import unittest
from pathlib import Path

from engine.campaign.campaign_manager import CampaignManager
from engine.campaign.campaign_models import CAMPAIGN_NODE_TYPES, CAMPAIGN_TRIGGERS

ENGINE = Path(__file__).resolve().parents[2] / "engine"


class TestCampaignVocabulary(unittest.TestCase):
    def test_triggers_are_the_resolutions_the_engine_reports(self):
        reported: set[str] = set()
        for path in ENGINE.rglob("*.py"):
            if path.parent.name == "campaign":
                continue
            source = path.read_text(encoding="utf-8", errors="replace")
            reported.update(re.findall(r'resolution\s*=\s*"([A-Z_]+)"', source))
            reported.update(re.findall(r'resolution\s*=\s*"([A-Z_]+)"\s+if', source))
            reported.update(re.findall(r'else\s+"([A-Z_]+_SUCCESS)"', source))
            reported.update(re.findall(r'resolution: str = "([A-Z_]+)"', source))
        self.assertEqual(set(CAMPAIGN_TRIGGERS), reported)

    def test_node_types_are_the_ones_trigger_node_acts_on(self):
        source = inspect.getsource(CampaignManager._trigger_node)
        acted_on = set(re.findall(r'node_type == "([A-Z_]+)"', source))
        for group in re.findall(r'node_type in \(([^)]*)\)', source):
            acted_on.update(re.findall(r'"([A-Z_]+)"', group))
        self.assertEqual(set(CAMPAIGN_NODE_TYPES), acted_on)


if __name__ == "__main__":
    unittest.main()
