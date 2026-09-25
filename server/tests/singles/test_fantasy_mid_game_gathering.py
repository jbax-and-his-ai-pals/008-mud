"""Productive trips past the starter ring: gathering in the mid- and late-game
regions, and what it makes.

Fantasy had sixteen gathering spots, all but two in the level 1-5 ring; the
Frostpeak Mining Lodge had nothing to mine, and iron ingots (24 recipes) and
leather strips (12) could only be bought. Now:

* iron veins in the old caves mine and at the mountain mine exit; two ore
  smelt into an ingot at a forge's anvil, and Hessa the Smith at Frostpeak
  keeps a standing order for ore;
* a wolf pelt (or troll hide) cuts into three leather strips;
* marshlight moss in the swamp brews a mana draught at an alchemy table, and
  with a frostpetal (now gatherable in the mountains) a greater one;
* sunstone outcrops on the Sunscorch road and in Aurelia's Sunstone Fields,
  and sunstone can stand in for rose quartz in a sunfire flask.

Each is played as a player would: walk to the place, gather with the tool it
names (bought from Talia), carry it to the station, craft.
"""

import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class _Gatherer:
    def __init__(self, test: unittest.TestCase):
        self.test = test
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        test.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="gatherer")
        self.run("char create Gatherer")
        self.player = self.server.get_player_for_session(self.session.session_id)
        for _ in range(14):
            self.player.level_up()
        self.player.max_health = self.player.health = 100_000
        for tool in ("item_prospector_pick", "item_foraging_knife"):
            self.give(tool)

    def run(self, command: str) -> str:
        lines = []
        for event in self.server.execute_command(self.session.session_id, command) or []:
            if isinstance(event, dict) and event.get("type") == "text":
                payload = event.get("payload")
                lines.append(str(payload.get("text", "") if isinstance(payload, dict) else payload))
        return "\n".join(lines)

    def give(self, item_id: str, quantity: int = 1) -> None:
        for _ in range(quantity):
            self.player.inventory.add_item(ItemFactory.create_item_from_template(item_id, self.server.world))

    def count(self, item_id: str) -> int:
        return self.player.inventory.count_item(item_id)

    def walk(self, region: str, room: str) -> None:
        path = self.server.world.find_path(self.player.current_region_id, self.player.current_room_id, region, room)
        self.test.assertIsNotNone(path, f"no walking route to {region}:{room}")
        for direction in path:
            self.run(direction)
        self.test.assertEqual((region, room), (self.player.current_region_id, self.player.current_room_id))

    def gather(self, region: str, room: str, node_name: str, times: int) -> None:
        self.walk(region, room)
        self.test.assertIn(node_name, self.run("look"), f"the {node_name} is visible at {region}:{room}")
        for _ in range(times):
            self.test.assertIn("You gather", self.run(f"gather {node_name}"))

    def craft_at(self, region: str, room: str, recipe: str) -> str:
        self.walk(region, room)
        return self.run(f"craft {recipe}")


class TestMidGameGathering(unittest.TestCase):
    def test_mine_and_smelt_iron(self):
        g = _Gatherer(self)
        g.gather("caves", "mine_upper_level", "iron vein", 2)
        g.gather("mountains", "mine_exit", "iron vein", 2)
        self.assertGreaterEqual(g.count("item_iron_ore"), 4)
        before = g.count("item_iron_ingot")
        self.assertIn("Successfully crafted", g.craft_at("frostpeak_outpost", "forge", "smelt_iron_ingot"))
        self.assertIn("Successfully crafted", g.craft_at("town", "blacksmith_interior", "smelt_iron_ingot"))
        self.assertEqual(before + 2, g.count("item_iron_ingot"))

    def test_hessa_buys_ore_at_frostpeak(self):
        g = _Gatherer(self)
        g.gather("caves", "mine_upper_level", "iron vein", 4)
        g.walk("frostpeak_outpost", "forge")
        gold = g.player.runtime_state.gold
        g.run("trade Hessa")
        self.assertIn("iron_ore", g.run("orders"))
        self.assertIn("15", g.run("fulfill iron_ore"))
        self.assertEqual(gold + 15, g.player.runtime_state.gold)
        self.assertEqual(0, g.count("item_iron_ore"))

    def test_cut_a_pelt_into_leather_strips(self):
        g = _Gatherer(self)
        g.give("item_wolf_pelt")
        before = g.count("item_leather_strip")
        self.assertIn("Successfully crafted", g.run("craft cut_leather_strips"))
        self.assertEqual(before + 3, g.count("item_leather_strip"))

    def test_swamp_moss_and_frostpetal_make_mana_draughts(self):
        g = _Gatherer(self)
        g.gather("swamp", "ancient_bog", "marshlight moss", 2)
        g.gather("swamp", "willow_grove", "marshlight moss", 2)
        g.gather("mountains", "frozen_waterfall_base", "frostpetal patch", 1)
        g.give("item_glass_vial", 2)
        self.assertIn("Successfully crafted", g.craft_at("town", "alchemist_interior", "brew_mana_draught"))
        self.assertIn("Successfully crafted", g.run("craft brew_greater_mana_draught"))
        self.assertGreaterEqual(g.count("item_mana_potion_small"), 1)
        self.assertGreaterEqual(g.count("item_mana_potion_medium"), 1)

    def test_sunstone_is_mined_in_the_south_and_fires_a_flask(self):
        g = _Gatherer(self)
        g.gather("sunscorch_road", "windbreak_pass", "sunstone outcrop", 1)
        g.gather("aurelia_outlands", "sunstone_fields", "sunstone outcrop", 1)
        self.assertGreaterEqual(g.count("item_sunstone"), 2)
        g.give("item_glass_vial")
        self.assertIn("Successfully crafted", g.craft_at("town", "alchemist_interior", "distill_sunfire_flask"))
        self.assertGreaterEqual(g.count("item_sunfire_flask"), 1)


if __name__ == "__main__":
    unittest.main()
