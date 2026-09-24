"""The Bandit Rebellion, played to both of its endings.

Elder Thorne starts it (ask about "trouble", then "accept mission"): scout the
forest camp, then deal with the Bandit Lieutenant. A successful negotiation
sends a peace treaty to the Bandit King; a failed one means killing the
Lieutenant and then the King. No test had played it, and the peaceful ending
was unreachable: the "White Flag" quest asked the player to deliver a treaty
that nothing ever gave them (only accepting at the board handed a package
over). The negotiation's roll is fixed each way; everything else is walked
and fought as a player would, with the runner raised to level 7.
"""

import re
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class _Rebel:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        test.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="rebel")
        self.run("char create Rebelhunter")
        self.player = self.server.get_player_for_session(self.session.session_id)
        for _ in range(6):
            self.player.level_up()
        self.player.max_health = self.player.health = 100_000
        self.player.stats["strength"] = 500

    def run(self, command: str) -> str:
        lines = []
        for event in self.server.execute_command(self.session.session_id, command) or []:
            if isinstance(event, dict) and event.get("type") == "text":
                payload = event.get("payload")
                lines.append(str(payload.get("text", "") if isinstance(payload, dict) else payload))
        return "\n".join(lines)

    def walk(self, region: str, room: str) -> None:
        for direction in self.server.world.find_path(self.player.current_region_id, self.player.current_room_id, region, room) or []:
            self.run(direction)
        self.test.assertEqual((region, room), (self.player.current_region_id, self.player.current_room_id))

    def node(self):
        return (self.player.runtime_state.quests.active_campaigns.get("bandit_rebellion") or {}).get("current_node")

    def hand_in(self) -> str:
        hint = re.search(r"Ready to turn in! \((?:\[\[/\]\])?(talk [^\[\)]+)", self.run("journal"))
        self.test.assertIsNotNone(hint, "the journal names the hand-in")
        return self.run(hint.group(1).strip())

    def kill(self, name: str) -> None:
        for _ in range(20):
            target = next((npc for npc in self.server.world.npcs.values() if npc.name == name and npc.is_alive), None)
            if target is None:
                return
            self.walk(target.current_region_id, target.current_room_id)
            self.run(f"attack {target.name}")
            for _tick in range(25):
                self.server.tick(self.session.session_id)
        self.test.fail(f"{name} did not fall")

    def up_to_the_lieutenant(self) -> None:
        self.run("ask elder about trouble")
        self.run("ask elder about accept mission")
        self.test.assertEqual("intro_investigation", self.node())
        self.walk("forest", "clearing")
        self.walk("town", "town_square")
        self.test.assertIn("Quest Complete", self.hand_in())
        self.test.assertEqual("confront_lieutenant", self.node())
        self.walk("forest", "clearing")


class TestBanditRebellion(unittest.TestCase):
    def test_the_peaceful_ending(self):
        rebel = _Rebel(self)
        rebel.up_to_the_lieutenant()
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            self.assertIn("Quest Complete", rebel.run("talk bandit lieutenant negotiate"))
        self.assertEqual("diplomatic_envoy", rebel.node())
        self.assertIn("(You have the package)", rebel.run("journal"), "the treaty is handed over with the quest")
        rebel.walk("town", "town_square")
        rebel.walk("forest", "clearing")
        delivered = rebel.run("give peace treaty to bandit king")
        self.assertIn("Quest Complete", delivered)
        self.assertIn("Peace is restored", delivered)
        self.assertIsNone(rebel.node())

    def test_the_violent_ending(self):
        rebel = _Rebel(self)
        rebel.up_to_the_lieutenant()
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(False, "rolled poorly")):
            self.assertIn("Negotiation FAIL", rebel.run("talk bandit lieutenant negotiate"))
        rebel.kill("Bandit Lieutenant")
        rebel.walk("town", "town_square")
        self.assertIn("Quest Complete", rebel.hand_in())
        self.assertEqual("assault_stronghold", rebel.node())
        rebel.walk("forest", "clearing")
        rebel.kill("Bandit King")
        rebel.walk("town", "town_square")
        self.assertIn("Quest Complete", rebel.hand_in())
        self.assertIsNone(rebel.node())


if __name__ == "__main__":
    unittest.main()
