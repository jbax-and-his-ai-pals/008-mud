# tests/singles/test_elite_encounters.py
"""Coverage for the two new elite hostile templates: boosted variants of
dire_wolf and troll with guaranteed bonus loot, placed rarely in the
mountains' existing weighted Spawner pool (engine/world/spawner.py) --
no engine changes were needed, this is pure content on an existing
mechanism."""

from tests.fixtures import GameTestBase


class TestEliteTemplatesAreBoosted(GameTestBase):
    def test_dire_wolf_alpha_is_stronger_than_the_base_dire_wolf(self):
        base = self.world.npc_templates["dire_wolf"]
        elite = self.world.npc_templates["dire_wolf_alpha"]
        self.assertGreater(elite["health"], base["health"])
        self.assertGreater(elite["attack_power"], base["attack_power"])
        self.assertGreater(elite["level"], base["level"])
        self.assertTrue(elite["properties"]["is_elite"])

    def test_troll_elder_is_stronger_than_the_base_troll(self):
        base = self.world.npc_templates["troll"]
        elite = self.world.npc_templates["troll_elder"]
        self.assertGreater(elite["health"], base["health"])
        self.assertGreater(elite["attack_power"], base["attack_power"])
        self.assertGreater(elite["level"], base["level"])
        self.assertTrue(elite["properties"]["is_elite"])

    def test_elites_guarantee_their_signature_material(self):
        alpha_loot = self.world.npc_templates["dire_wolf_alpha"]["loot_table"]
        self.assertEqual(1.0, alpha_loot["item_wolf_pelt"]["chance"])
        self.assertEqual(1.0, alpha_loot["item_wolf_fang"]["chance"])

        elder_loot = self.world.npc_templates["troll_elder"]["loot_table"]
        self.assertEqual(1.0, elder_loot["item_troll_hide"]["chance"])


class TestEliteSpawnerPlacement(GameTestBase):
    def test_mountains_spawner_includes_troll_and_both_elites_at_low_weight(self):
        region = self.world.get_region("mountains")
        weights = region.spawner_config["monster_types"]
        self.assertIn("troll", weights)
        self.assertIn("dire_wolf_alpha", weights)
        self.assertIn("troll_elder", weights)
        # Elites should be rarer than the common roster, not equally likely.
        self.assertLess(weights["dire_wolf_alpha"], weights["dire_wolf"])
        self.assertLess(weights["troll_elder"], weights["orc_grunt"])

    def test_spawner_weight_entries_resolve_to_real_templates(self):
        region = self.world.get_region("mountains")
        for template_id in region.spawner_config["monster_types"]:
            self.assertIn(template_id, self.world.npc_templates, f"{template_id} has no template")
