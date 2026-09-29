# tests/singles/test_campaign_scenes.py
"""A campaign can pause on a scene and wait for a conversation.

Until now a campaign node was a quest or an ending; any other type was refused by the
validator because the manager did nothing on reaching it. Two more types are acted on:

* `CUTSCENE` applies the node's `effects` (the vocabulary a conversation uses) and moves
  straight on along its `SUCCESS` transition. Narration goes to whoever started or
  advanced the campaign.
* `DIALOGUE` applies its `effects` and waits. The `advance_campaign` effect, written in a
  conversation or a trigger, moves the player's campaign on from it. It refuses to skip
  a quest: it only moves a campaign that is waiting on a DIALOGUE node.
"""

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.campaign.campaign_models import MAX_CHAIN, CampaignDefinition
from engine.dialogue.effects import apply_effects
from tests.fixtures import GameTestBase

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402


def _campaign(**nodes):
    return {"campaign_id": "saga", "name": "Saga", "description": "", "start_node_id": "start", "nodes": nodes}


END = {"type": "END", "outcome": "won"}


def _to(target, trigger="SUCCESS", text=""):
    move = {"trigger": trigger, "target_node_id": target}
    if text:
        move["narrative_text"] = text
    return [move]


class TestScenes(GameTestBase):
    def load(self, **nodes):
        self.manager = self.world.campaign_manager
        self.manager.definitions["saga"] = CampaignDefinition.from_dict(_campaign(**nodes))
        return self.manager

    def state(self):
        return self.player.runtime_state.quests.active_campaigns.get("saga")

    def test_a_cutscene_applies_its_effects_and_moves_on(self):
        manager = self.load(
            start={"description": "", "type": "CUTSCENE", "effects": {"set_flag": "seen_intro", "message": "A bell tolls."},
                   "transitions": _to("wait", text="The day begins.")},
            wait={"description": "", "type": "DIALOGUE", "transitions": _to("end")},
            end=END)
        lines = []
        self.assertTrue(manager.start_campaign("saga", self.player, narration=lines))
        self.assertTrue(self.player.flags.get("seen_intro"))
        self.assertIn("A bell tolls.", "\n".join(lines))
        self.assertIn("The day begins.", "\n".join(lines))
        self.assertEqual("wait", self.state()["current_node"])
        self.assertEqual("wait", self.player.runtime_state.quests.finite_adventure["current_node"])

    def test_cutscenes_chain_and_can_end_the_campaign(self):
        manager = self.load(
            start={"description": "", "type": "CUTSCENE", "effects": {"message": "one"}, "transitions": _to("two")},
            two={"description": "", "type": "CUTSCENE", "effects": {"message": "two"}, "transitions": _to("end")},
            end=END)
        lines = []
        manager.start_campaign("saga", self.player, narration=lines)
        self.assertEqual(["one", "two"], [m for m in lines if m in ("one", "two")])
        self.assertIsNone(self.state())
        self.assertIn("saga", self.player.runtime_state.quests.completed_campaigns)

    def test_a_dialogue_node_waits_until_a_conversation_advances_it(self):
        manager = self.load(
            start={"description": "", "type": "DIALOGUE", "effects": {"set_flag": "met_king"}, "transitions": _to("end", text="Off you go.")},
            end=END)
        manager.start_campaign("saga", self.player)
        self.assertTrue(self.player.flags.get("met_king"))
        self.assertEqual("start", self.state()["current_node"], "it does not move on by itself")
        report = apply_effects({"advance_campaign": "saga", "message": "Go."}, {"player": self.player, "world": self.world})
        self.assertIn("advanced campaign saga", report.applied)
        self.assertIn("Off you go.", report.messages)
        self.assertIsNone(self.state())
        self.assertIn("saga", self.player.runtime_state.quests.completed_campaigns)

    def test_advancing_never_skips_a_quest(self):
        manager = self.load(
            start={"description": "", "quest_template_id": "q", "transitions": _to("end")},
            end=END)
        manager.start_campaign("saga", self.player)
        report = apply_effects({"advance_campaign": "saga"}, {"player": self.player, "world": self.world})
        self.assertTrue(report.failed, "waiting on a quest is not waiting on a conversation")
        self.assertEqual("start", self.state()["current_node"])

    def test_advancing_a_campaign_that_is_not_running_reports_failure(self):
        self.load(start={"description": "", "type": "DIALOGUE", "transitions": _to("end")}, end=END)
        report = apply_effects({"advance_campaign": "saga"}, {"player": self.player, "world": self.world})
        self.assertTrue(any("advance_campaign" in f for f in report.failed), report.failed)

    def test_a_quest_finishing_into_a_cutscene_narrates_it(self):
        manager = self.load(
            start={"description": "", "quest_template_id": "q", "transitions": _to("scene")},
            scene={"description": "", "type": "CUTSCENE", "effects": {"message": "The gate groans open."}, "transitions": _to("end")},
            end=END)
        manager.definitions["saga"].nodes["start"].quest_template_id = None   # not started; only its completion matters here
        self.player.runtime_state.quests.active_campaigns["saga"] = {"current_node": "start", "history": [], "variables": {}}
        text = manager.handle_quest_completion("saga", "start", "SUCCESS", self.player)
        self.assertIn("The gate groans open.", text)
        self.assertIn("saga", self.player.runtime_state.quests.completed_campaigns)

    def test_a_loop_of_cutscenes_stops_instead_of_hanging(self):
        manager = self.load(
            start={"description": "", "type": "CUTSCENE", "effects": {"message": "again"}, "transitions": _to("start")})
        lines = []
        manager.start_campaign("saga", self.player, narration=lines)
        self.assertLessEqual(len([m for m in lines if m == "again"]), MAX_CHAIN + 1)

    def test_the_waiting_state_is_plain_data_a_save_keeps(self):
        manager = self.load(start={"description": "", "type": "DIALOGUE", "transitions": _to("end")}, end=END)
        manager.start_campaign("saga", self.player)
        restored = json.loads(json.dumps(self.player.runtime_state.quests.active_campaigns))
        self.assertEqual("start", restored["saga"]["current_node"])
        self.player.runtime_state.quests.active_campaigns = restored
        self.assertTrue(apply_effects({"advance_campaign": "saga"}, {"player": self.player, "world": self.world}).applied)


class TestValidating(unittest.TestCase):
    """Against a scratch copy of Zelda Slice with a campaign added."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def issues(self, campaign, severity="error", extra=None):
        (self.package / "data" / "campaigns" / "probe.json").write_text(json.dumps(campaign), encoding="utf-8")
        for name, body in (extra or {}).items():
            (self.package / "data" / name).write_text(json.dumps(body), encoding="utf-8")
        _definition, found = validator.load_content_set(self.package)
        return [i.message for i in found if i.severity == severity and i.path.endswith("probe.json")]

    def good(self, **overrides):
        nodes = {
            "start": {"description": "", "type": "CUTSCENE", "effects": {"message": "hi"}, "transitions": _to("wait")},
            "wait": {"description": "", "type": "DIALOGUE", "transitions": _to("end")},
            "end": END,
        }
        nodes.update(overrides)
        return {**_campaign(**nodes), "campaign_id": "probe"}

    def test_scenes_are_accepted(self):
        self.assertEqual([], self.issues(self.good(), extra={"dialogue/probe_advance.json": {
            "id": "probe_advance", "root": "a",
            "nodes": {"a": {"text": "x", "choices": [{"text": "Go on.", "effects": {"advance_campaign": "probe"}}]}}}}))

    def test_a_scene_needs_a_way_out(self):
        errors = self.issues(self.good(start={"description": "", "type": "CUTSCENE", "effects": {"message": "hi"}}))
        self.assertTrue(any("nodes.start is a CUTSCENE node with no transitions" in m for m in errors), errors)

    def test_scene_effects_are_checked_like_a_conversations(self):
        errors = self.issues(self.good(start={"description": "", "type": "CUTSCENE", "transitions": _to("wait"),
                                              "effects": {"no_such_effect": 1, "start_quest": "no_such_quest"}}))
        self.assertTrue(any("no_such_effect" in m for m in errors), errors)
        self.assertTrue(any("no_such_quest" in m for m in errors), errors)

    def test_effects_on_a_quest_or_end_node_are_never_applied(self):
        errors = self.issues(self.good(end={**END, "effects": {"message": "unread"}}))
        self.assertTrue(any("nodes.end.effects is never applied" in m for m in errors), errors)

    def test_a_cutscene_cannot_advance_a_campaign(self):
        errors = self.issues(self.good(start={"description": "", "type": "CUTSCENE", "transitions": _to("wait"),
                                              "effects": {"advance_campaign": "probe"}}))
        self.assertTrue(any("advance_campaign is for a DIALOGUE node" in m for m in errors), errors)

    def test_a_loop_of_cutscenes_is_refused(self):
        errors = self.issues(self.good(
            start={"description": "", "type": "CUTSCENE", "transitions": _to("wait")},
            wait={"description": "", "type": "CUTSCENE", "transitions": _to("start")}))
        self.assertTrue(any("loop of CUTSCENE nodes" in m for m in errors), errors)

    def test_a_conversation_node_nothing_advances_is_a_warning(self):
        warnings = self.issues(self.good(), severity="warning")
        self.assertTrue(any("nothing in this set carries an advance_campaign effect naming 'probe'" in m for m in warnings), warnings)


if __name__ == "__main__":
    unittest.main()
