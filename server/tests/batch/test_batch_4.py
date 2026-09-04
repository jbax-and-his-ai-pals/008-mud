# tests/batch/test_batch_4.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.items.container import Container
from engine.core.skill_system import SkillSystem
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell

class TestBatch4(GameTestBase):

    def test_inventory_full_add_item(self):
        """Verify add_item returns False when inventory is full (direct check)."""
        self.player.inventory.max_slots = 1
        self.player.inventory.slots = [self.player.inventory.slots[0]]
        
        # Fill slot
        i1 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if i1: 
            i1.obj_id = "s1"
            self.player.inventory.add_item(i1)
        
        # Attempt add
        i2 = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        if i2:
            i2.obj_id = "s2"
            success, msg = self.player.inventory.add_item(i2)
            
            self.assertFalse(success)
            self.assertIn("slots", msg.lower())

    def test_npc_move_cooldown(self):
        """Verify NPC movement logic respects the move_cooldown property."""
        from engine.npcs.npc_factory import NPCFactory
        from engine.npcs.ai.movement import perform_wander
        
        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if npc and self.player.current_region_id and self.player.current_room_id:
            npc.current_region_id = self.player.current_region_id
            npc.current_room_id = self.player.current_room_id
            npc.move_cooldown = 1000 # Long cooldown
            npc.last_moved = time.time()
            
            # Act - Try to move immediately
            from engine.npcs.ai.dispatcher import handle_ai
            
            # Should return None because time hasn't passed
            result = handle_ai(npc, self.world, time.time(), self.player)
            self.assertIsNone(result)

    def test_weather_transition_probabilities(self):
        """Verify weather doesn't change every tick (probability check mock)."""
        wm = self.game.weather_manager
        wm.current_weather = "clear"
        
        # Mock random to be > TRANSITION_CHANCE (0.5)
        with patch('random.random', return_value=0.9):
            wm.update_on_time_period_change("summer")
            
        # Should stay same
        self.assertEqual(wm.current_weather, "clear")

    def test_item_value_calculation(self):
        """Verify item value is consistent."""
        # Explicitly define templates to ensure values are deterministic regardless of loaded JSON
        self.world.item_templates["item_gold_coin"] = {"type": "Treasure", "name": "Gold Coin", "value": 1, "stackable": True}
        self.world.item_templates["item_ruby"] = {"type": "Gem", "name": "Ruby", "value": 100}

        i1 = ItemFactory.create_item_from_template("item_gold_coin", self.world)
        if i1:
            self.assertEqual(i1.value, 1)
            
        i2 = ItemFactory.create_item_from_template("item_ruby", self.world)
        if i2:
            self.assertEqual(i2.value, 100) 

    def test_command_case_insensitivity_args(self):
        """Verify arguments are case-insensitive."""
        self.world.item_templates["box"] = {"type": "Container", "name": "Box", "properties": {"is_open": True}}
        box = ItemFactory.create_item_from_template("box", self.world)
        if box and self.player.current_region_id and self.player.current_room_id:
            self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, box)
            
            result = self.game.process_command("CLOSE BOX")
            self.assertIsNotNone(result)
            if result:
                self.assertIn("You close", result)

    def test_container_recursive_weight(self):
        """Verify weight calculation for nested containers."""
        # Note: Current logic doesn't add content weight to container weight (Bag of Holding style)
        # We verify that logic holds for nesting too.
        # FIX: Ensure containers are OPEN and have CAPACITY so items can be added
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", "weight": 1.0,
            "properties": {"is_open": True, "capacity": 1000.0}
        }
        self.world.item_templates["rock"] = {"type": "Item", "name": "Rock", "weight": 10.0}
        
        outer = ItemFactory.create_item_from_template("box", self.world)
        inner = ItemFactory.create_item_from_template("box", self.world)
        rock = ItemFactory.create_item_from_template("rock", self.world)
        
        if outer and inner and rock and isinstance(outer, Container) and isinstance(inner, Container):
            success_inner = inner.add_item(rock) # Inner contents = 10
            self.assertTrue(success_inner, "Failed to add rock to inner container")
            
            success_outer = outer.add_item(inner) # Outer contents = Inner(1)
            self.assertTrue(success_outer, "Failed to add inner container to outer container")
            
            # Outer 'content weight' = Inner.weight (1.0). (Does not recurse into inner contents weight for calculation)
            # get_current_weight sums item.weight of contents.
            # inner.weight is 1.0 (static).
            self.assertEqual(outer.get_current_weight(), 1.0)
            
            # Validate inner logic
            self.assertEqual(inner.get_current_weight(), 10.0)

    def test_quest_fetch_partial_turnin(self):
        """Verify you cannot turn in a quest if you lack full quantity."""
        from engine.npcs.npc_factory import NPCFactory
        
        # Setup Quest
        quest_id = "fetch_partial"
        assert self.player.runtime_state.quests is not None
        self.player.runtime_state.quests.active[quest_id] = {
            "instance_id": quest_id, "type": "fetch", "state": "ready_to_complete",
            "objective": {"item_id": "item_rock", "required_quantity": 5},
            "giver_instance_id": "giver"
        }
        
        # Setup Inventory (Only 3 rocks)
        self.world.item_templates["item_rock"] = {"type": "Item", "name": "Rock"}
        rock = ItemFactory.create_item_from_template("item_rock", self.world)
        if rock: self.player.inventory.add_item(rock, 3)
        
        # Setup NPC
        npc = NPCFactory.create_npc_from_template("villager", self.world, instance_id="giver")
        if npc:
            # Act
            from engine.commands.interaction.npcs import _handle_quest_dialogue
            result = _handle_quest_dialogue(self.player, npc, self.world)
            
            # Assert
            self.assertIn("still need 2 more", result)

    def test_skill_xp_threshold(self):
        """Verify XP required increases with level."""
        req_1 = SkillSystem.get_xp_for_next_level(1)
        req_2 = SkillSystem.get_xp_for_next_level(2)
        
        self.assertGreater(req_2, req_1)

    def test_magic_self_target_explicit(self):
        """Verify casting 'spell on self' works."""
        # Use a unique name to avoid conflicts with loaded data
        spell = Spell("self_heal_unique", "SelfHealUnique", "x", effects=[{"type": "heal", "value": 10}], target_type="friendly")
        register_spell(spell)
        self.player.learn_spell("self_heal_unique")
        self.player.health = 50
        
        result = self.game.process_command("cast SelfHealUnique on self")
        self.assertIsNotNone(result)
        if result:
            self.assertIn("heal yourself", result)
        self.assertGreater(self.player.health, 50)

    def test_save_load_time_metadata(self):
        """Verify game time saves and loads correctly."""
        tm = self.game.time_manager
        tm.initialize_time(5000.0)
        
        state = tm.get_time_state_for_save()
        
        # Simulate restart
        tm.initialize_time(0.0)
        
        # Load
        tm.apply_loaded_time_state(state)
        
        self.assertEqual(tm.game_time, 5000.0)
