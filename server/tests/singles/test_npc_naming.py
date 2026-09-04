# tests/singles/test_npc_naming.py
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory

class TestNPCNaming(GameTestBase):

    def test_procedural_wandering_names(self):
        """Verify that wandering NPCs receive randomized names."""
        # The factory uses VILLAGER_FIRST_NAMES lists for these templates
        template_id = "wandering_villager"
        
        # Create a batch to ensure we see variety (mitigates RNG collisions)
        names = set()
        for _ in range(10):
            npc = NPCFactory.create_npc_from_template(template_id, self.world)
            if npc:
                self.assertTrue(npc.name.endswith("the Villager"))
                names.add(npc.name)
        
        # Verify we got at least 2 unique names
        self.assertGreater(len(names), 1, "Names should be randomized and not identical every time.")

    def test_static_naming(self):
        """Verify that unique NPCs (like the Elder) keep their specific names."""
        elder = NPCFactory.create_npc_from_template("village_elder", self.world)
        self.assertIsNotNone(elder)
        if elder:
            self.assertEqual(elder.name, "Elder Thorne")