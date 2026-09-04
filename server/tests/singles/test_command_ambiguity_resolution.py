# tests/singles/test_command_ambiguity_resolution.py
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory

class TestCommandAmbiguityResolution(GameTestBase):

    def test_prefer_exact_match(self):
        """Verify parser picks the exact name match over a partial match."""
        # 1. Create 'Potion' (Generic) and 'Mana Potion' (Specific)
        # We inject a generic template for the test
        self.world.item_templates["generic_potion"] = {"type": "Item", "name": "potion", "value": 1}
        self.world.item_templates["mana_potion"] = {"type": "Item", "name": "mana potion", "value": 10}
        
        p1 = ItemFactory.create_item_from_template("generic_potion", self.world)
        p2 = ItemFactory.create_item_from_template("mana_potion", self.world)
        
        if p1 and p2:
            self.player.inventory.add_item(p1)
            self.player.inventory.add_item(p2)
            
            # 2. Drop "potion"
            # If logic is fuzzy, it might pick "mana potion" because it contains "potion"
            # But we expect it to prefer the exact string match.
            result = self.game.process_command("drop potion")
            
            # 3. Verify
            self.assertEqual(self.player.inventory.count_item(p1.obj_id), 0, "Should drop the exact 'potion'.")
            self.assertEqual(self.player.inventory.count_item(p2.obj_id), 1, "Should keep the 'mana potion'.")

    def test_sequential_ambiguity(self):
        """Verify parser handles 'sword' when 'iron sword' and 'steel sword' exist."""
        self.world.item_templates["i_sword"] = {"type": "Weapon", "name": "iron sword"}
        self.world.item_templates["s_sword"] = {"type": "Weapon", "name": "steel sword"}
        
        s1 = ItemFactory.create_item_from_template("i_sword", self.world)
        s2 = ItemFactory.create_item_from_template("s_sword", self.world)
        
        if s1 and s2:
            self.player.inventory.add_item(s1)
            self.player.inventory.add_item(s2)
            
            # Act: "drop sword"
            # Since neither is an exact match for "sword", it should pick one based on sort order or first found.
            result = self.game.process_command("drop sword")
            
            # Assert: One of them should be gone.
            count_total = self.player.inventory.count_item(s1.obj_id) + self.player.inventory.count_item(s2.obj_id)
            self.assertEqual(count_total, 1, "One sword should be dropped.")