# tests/singles/test_elite_encounters.py
"""Coverage for the generalized elite system (engine/npcs/elite.py):
any hostile template spawned via the ambient Spawner has a
content-configured chance to be promoted to an elite instance --
boosted stats, guaranteed/scaled loot, and a randomized flavor name --
instead of needing a dedicated template per species (superseding the
earlier dire_wolf_alpha/troll_elder hand-authored templates, now
folded into this generic system and removed from content)."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.elite import roll_elite_overrides
from engine.npcs.npc_factory import NPCFactory
from engine.world.spawner import Spawner


class TestRollEliteOverrides(GameTestBase):
    def setUp(self):
        super().setUp()
        self.template = self.world.npc_templates["dire_wolf"]

    def test_returns_none_when_chance_is_zero(self):
        with patch.object(self.world, "ruleset_section", return_value={"chance": 0.0}):
            self.assertIsNone(roll_elite_overrides(self.template, self.world))

    def test_returns_none_when_roll_misses(self):
        config = {"chance": 0.05}
        with patch.object(self.world, "ruleset_section", return_value=config), \
             patch("engine.npcs.elite.random.random", return_value=0.5):
            self.assertIsNone(roll_elite_overrides(self.template, self.world))

    def test_returns_boosted_overrides_when_roll_hits(self):
        config = {
            "chance": 1.0,
            "stat_multiplier": 2.0,
            "loot_guaranteed_chance": 1.0,
            "loot_quantity_multiplier": 2.0,
            "name_pattern": "{prefix} {name}",
            "prefixes": ["Dread"],
        }
        with patch.object(self.world, "ruleset_section", return_value=config), \
             patch("engine.npcs.elite.random.random", return_value=0.0):
            overrides = roll_elite_overrides(self.template, self.world)

        self.assertIsNotNone(overrides)
        for key, value in self.template["stats"].items():
            self.assertEqual(value * 2, overrides["stats"][key])
        self.assertEqual(self.template["attack_power"] * 2, overrides["attack_power"])
        self.assertEqual(self.template["defense"] * 2, overrides["defense"])
        self.assertEqual("Dread dire wolf", overrides["name"])
        self.assertTrue(overrides["properties_override"]["is_elite"])

        for item_id, entry in self.template["loot_table"].items():
            self.assertEqual(1.0, overrides["loot_table"][item_id]["chance"])
            self.assertEqual(
                [q * 2 for q in entry["quantity"]],
                overrides["loot_table"][item_id]["quantity"],
            )

    def test_original_template_dict_is_never_mutated(self):
        original_stats = dict(self.template["stats"])
        original_loot = {k: dict(v) for k, v in self.template["loot_table"].items()}
        config = {"chance": 1.0, "stat_multiplier": 3.0, "loot_quantity_multiplier": 3.0}
        with patch.object(self.world, "ruleset_section", return_value=config), \
             patch("engine.npcs.elite.random.random", return_value=0.0):
            roll_elite_overrides(self.template, self.world)
        self.assertEqual(original_stats, self.template["stats"])
        self.assertEqual(original_loot, self.template["loot_table"])

    def test_no_elites_section_defaults_to_never_elite(self):
        with patch.object(self.world, "ruleset_section", return_value={}):
            self.assertIsNone(roll_elite_overrides(self.template, self.world))


class TestSpawnerAppliesEliteOverrides(GameTestBase):
    def test_spawned_monster_carries_elite_overrides_when_roll_hits(self):
        region = self.world.get_region("mountains")
        region.spawner_config = {"monster_types": {"dire_wolf": 1}, "level_range": [5, 5]}
        spawner = Spawner(self.world)

        self.player.current_region_id = "mountains"
        self.player.current_room_id = next(iter(region.rooms))

        elite_overrides = {
            "name": "Dread dire wolf",
            "stats": {"strength": 999},
            "attack_power": 999,
            "defense": 999,
            "loot_table": {},
            "properties_override": {"is_elite": True},
        }
        with patch("engine.world.spawner.roll_elite_overrides", return_value=elite_overrides), \
             patch("engine.world.spawner.random.choice", side_effect=lambda seq: seq[0]):
            spawner._spawn_monsters_in_region(region)

        spawned = [n for n in self.world.npcs.values() if n.template_id == "dire_wolf" and n.name == "Dread dire wolf"]
        self.assertEqual(1, len(spawned))
        self.assertTrue(spawned[0].properties.get("is_elite"))
        # attack_power = overrides["attack_power"] + boosted strength // 3
        # (engine/npcs/npc_factory.py) -- assert it's at least the override
        # floor rather than an exact figure coupled to that formula.
        self.assertGreaterEqual(spawned[0].attack_power, 999)

    def test_non_elite_roll_spawns_a_plain_instance(self):
        region = self.world.get_region("mountains")
        region.spawner_config = {"monster_types": {"dire_wolf": 1}, "level_range": [5, 5]}
        spawner = Spawner(self.world)

        self.player.current_region_id = "mountains"
        self.player.current_room_id = next(iter(region.rooms))

        with patch("engine.world.spawner.roll_elite_overrides", return_value=None), \
             patch("engine.world.spawner.random.choice", side_effect=lambda seq: seq[0]):
            spawner._spawn_monsters_in_region(region)

        spawned = [n for n in self.world.npcs.values() if n.template_id == "dire_wolf"]
        self.assertEqual(1, len(spawned))
        self.assertFalse(spawned[0].properties.get("is_elite", False))
