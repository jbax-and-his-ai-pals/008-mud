# tests/singles/test_magic_utility.py
from typing import cast, Any
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container
from engine.magic.spell import Spell
from engine.magic.effects import apply_spell_effect

class TestMagicUtility(GameTestBase):

    def setUp(self):
        super().setUp()
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", "value": 1, 
            "properties": { "locked": True, "is_open": False, "capacity": 10 }
        }

    def test_spell_unlock_logic(self):
        """Verify that an unlock-type spell opens a locked container."""
        item_box = ItemFactory.create_item_from_template("box", self.world)
        if isinstance(item_box, Container) and self.player:
            box = cast(Container, item_box)
            
            # Create a mock "Knock" spell
            spell = Spell(
                spell_id="knock", name="Knock", description="Unlocks",
                effects=[{"type": "unlock"}], target_type="item"
            )
            
            # Act
            # FIX: Ensure player exists and cast box to SpellTargetType (Any)
            val, msg = apply_spell_effect(self.player, cast(Any, box), spell, self.player)
            
            # Assert
            self.assertEqual(val, 1, "Should return success value 1.")
            self.assertFalse(box.properties["locked"], "Box should be unlocked.")
            self.assertIn("forces the lock", msg)

    def test_spell_lock_logic(self):
        """Verify that a lock-type spell seals a container."""
        item_box = ItemFactory.create_item_from_template("box", self.world)
        if isinstance(item_box, Container) and self.player:
            box = cast(Container, item_box)
            box.properties["locked"] = False
            box.properties["is_open"] = True
            
            spell = Spell(
                spell_id="lock", name="Lock", description="Locks",
                effects=[{"type": "lock"}], target_type="item"
            )
            
            # FIX: cast to Any
            apply_spell_effect(self.player, cast(Any, box), spell, self.player)
            
            self.assertTrue(box.properties["locked"], "Box should now be locked.")
            self.assertFalse(box.properties["is_open"], "Locking should force the box closed.")
