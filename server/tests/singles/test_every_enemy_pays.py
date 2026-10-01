# tests/singles/test_every_enemy_pays.py
"""In ff4_slice every enemy drops some gil, and tougher ones drop more.

The world of the game it adapts pays for every kill, so no hostile template is allowed to leave its
purse to chance, and the purse must not shrink as monsters get tougher.
"""

import json
import unittest
from pathlib import Path

from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
HOSTILES = REPO_ROOT / "content_sets" / "ff4_slice" / "data" / "npcs" / "hostiles.json"


def _hostiles():
    data = json.loads(HOSTILES.read_text(encoding="utf-8"))
    return {k: v for k, v in data.items() if not k.startswith("_") and v.get("friendly") is False}


class TestEveryEnemyPays(unittest.TestCase):
    def test_every_hostile_always_drops_at_least_a_coin(self):
        for name, template in _hostiles().items():
            gold = template["loot_table"]["gold_value"]
            self.assertEqual(1, gold["chance"], f"{name} must always pay")
            self.assertGreaterEqual(gold["quantity"][0], 1, f"{name} pays at least 1")

    def test_the_purse_never_shrinks_as_enemies_get_tougher(self):
        ordered = sorted(_hostiles().items(), key=lambda item: item[1]["max_health"])
        for (weaker, a), (tougher, b) in zip(ordered, ordered[1:]):
            lo_a, hi_a = a["loot_table"]["gold_value"]["quantity"]
            lo_b, hi_b = b["loot_table"]["gold_value"]["quantity"]
            self.assertLessEqual(lo_a, lo_b, f"{tougher} pays less at the bottom than {weaker}")
            self.assertLessEqual(hi_a, hi_b, f"{tougher} pays less at the top than {weaker}")

    def test_killing_one_puts_gil_in_the_purse(self):
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "ff4_slice"),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="loot").session_id
        server.execute_command(sid, "char create Cecil")
        player = server.get_player_for_session(sid)
        player.current_region_id, player.current_room_id = "road", "castle_road"
        goblin = next(n for n in server.world.npcs.values() if n.template_id == "goblin_scout")
        goblin.health = 1
        before = player.runtime_state.gold
        for _ in range(40):
            server.tick(sid)
        server.execute_command(sid, "attack goblin")
        self.assertGreaterEqual(player.runtime_state.gold - before, 3)


if __name__ == "__main__":
    unittest.main()
