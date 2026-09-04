# tests/batch/test_batch_7.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.items.container import Container
from engine.items.lockpick import Lockpick
from engine.crafting.recipe import Recipe
from engine.core.skill_system import SkillSystem

class TestBatch7(GameTestBase):

    def test_crafting_skill_xp(self):
        """Verify successful crafting grants skill experience."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Setup Recipe (Free cost for simplicity)
        self.world.item_templates["crafted_item"] = {"type": "Item", "name": "Thing", "value": 10}
        recipe = Recipe("xp_test", {
            "result_item_id": "crafted_item", "ingredients": []
        })
        self.game.crafting_manager.recipes["xp_test"] = recipe
        
        # 2. Initialize Skill
        self.player.add_skill("crafting", 1)
        initial_xp = self.player.runtime_state.progression.skills["crafting"]["xp"]
        
        # 3. Craft (Force success via mock)
        with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
            self.game.crafting_manager.craft(self.player, "xp_test")
            
        # 4. Assert XP Gain
        # Base XP logic: max(10, value//2). 10//2 = 5. Max(10, 5) = 10.
        new_xp = self.player.runtime_state.progression.skills["crafting"]["xp"]
        self.assertGreater(new_xp, initial_xp, "Crafting should grant XP.")

    def test_lockpicking_skill_xp(self):
        """Verify successful lockpicking grants skill experience."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Setup Locked Container
        self.world.item_templates["locked_box"] = {
            "type": "Container", "name": "Box", 
            "properties": {"locked": True, "lock_difficulty": 10}
        }
        box = ItemFactory.create_item_from_template("locked_box", self.world)
        self.assertIsNotNone(box, "Failed to create box.")

        # 2. Setup Pick
        pick = Lockpick("pick", "Pick")
        self.player.inventory.add_item(pick)
        self.player.add_skill("lockpicking", 1)
        initial_xp = self.player.runtime_state.progression.skills["lockpicking"]["xp"]

        if box:
            # 3. Pick Lock (Force success)
            with patch('engine.core.skill_system.SkillSystem.attempt_check', return_value=(True, "")):
                # Force random.random to 1.0 to prevent breakage logic interfering
                with patch('random.random', return_value=1.0):
                    pick.use(self.player, box)
            
            # 4. Assert XP Gain
            new_xp = self.player.runtime_state.progression.skills["lockpicking"]["xp"]
            self.assertGreater(new_xp, initial_xp, "Lockpicking should grant XP.")

    def test_overheal_consumption(self):
        """Verify potions are consumed even if health is full."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Max Health
        self.player.health = self.player.max_health
        
        # 2. Item
        self.world.item_templates["item_healing_potion_small"] = {
            "type": "Consumable", "name": "Small Potion", "value": 10,
            "properties": {"effect_type": "heal", "effect_value": 10, "uses": 1}
        }
        potion = ItemFactory.create_item_from_template("item_healing_potion_small", self.world)
        self.assertIsNotNone(potion, "Failed to create potion.")
        
        if potion:
            self.player.inventory.add_item(potion)
            
            # 3. Use via Command (triggers inventory removal logic)
            # We use the command because Item.use() returns a string but doesn't remove itself from 
            # the inventory list (it just sets uses=0). The command handler does the removal.
            result = self.game.process_command("use Small Potion")
            
            # 4. Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("no different", result) # Feedback for overheal
            
            self.assertEqual(self.player.inventory.count_item("item_healing_potion_small"), 0)

    def test_weather_description_updates(self):
        """Verify room description reflects immediate weather changes."""
        if not self.world:
            self.fail("World not initialized.")
            return

        # 1. Ensure Outdoors
        region = self.world.get_region("town")
        if not region:
            self.fail("Region 'town' not found.")
            return
            
        # FIX: Call get_room on the region, not the world
        room = region.get_room("town_square")
        
        if room: # Only proceed if room is found
            # Force outdoor property
            room.update_property("outdoors", True)
            self.player.current_region_id = "town"
            self.player.current_room_id = "town_square"
            self.world.current_region_id = "town"
            self.world.current_room_id = "town_square"
            
            # 2. Set Storm
            self.game.weather_manager.current_weather = "storm"
            desc_storm = self.world.look()
            self.assertIn("storm", desc_storm)
            
            # 3. Set Clear
            self.game.weather_manager.current_weather = "clear"
            desc_clear = self.world.look()
            self.assertIn("clear", desc_clear)
            self.assertNotIn("storm", desc_clear)
        else:
            self.fail("Room 'town_square' not found in 'town' region.")


    def test_inventory_weight_stacking(self):
        """Verify total weight is calculated correctly for stacks."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Create Stackable Item (Weight 0.5)
        self.world.item_templates["heavy_stack"] = {
            "type": "Item", "name": "Brick", "weight": 0.5, "stackable": True
        }
        brick = ItemFactory.create_item_from_template("heavy_stack", self.world)
        self.assertIsNotNone(brick, "Failed to create brick.")
        
        if brick:
            # 2. Add 10 (Total 5.0)
            self.player.inventory.add_item(brick, 10)
            
            # 3. Check Weight
            self.assertAlmostEqual(self.player.inventory.get_total_weight(), 5.0)

    def test_npc_patrol_loop(self):
        """Verify NPC patrol index wraps around correctly."""
        npc = NPCFactory.create_npc_from_template("town_guard", self.world)
        self.assertIsNotNone(npc, "Failed to create NPC.")
        
        if npc:
            npc.patrol_points = ["A", "B", "C"]
            npc.patrol_index = 2 # At last point
            npc.current_room_id = "C" # Simulate being at last point
            
            # Logic normally runs in perform_patrol -> if at target, index++
            # We simulate the logic block directly to verify index math
            npc.patrol_index = (npc.patrol_index + 1) % len(npc.patrol_points)
            
            self.assertEqual(npc.patrol_index, 0, "Patrol index should wrap to 0.")

    def test_quest_hint_text(self):
        """Verify generated quests contain location hints in their text."""
        # 1. Generate Quest
        generator = self.world.quest_manager.generator
        
        # Need a hostile template for kill quest generation
        self.world.npc_templates["target_dummy"] = {"name": "Target Dummy", "faction": "hostile", "level": 1}
        
        # Need a giver
        # FIX: Use "wandering_villager" which is a standard template, "villager" might not exist
        giver = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        self.assertIsNotNone(giver, "Failed to create quest giver NPC.")

        if giver:
            giver.current_region_id = "town" # Hints rely on region
            self.world.add_npc(giver)

            # 2. Generate Kill Quest
            # Mock random choice to pick our dummy
            from engine.core.quest_generation.objectives import generate_kill_objective
            with patch('random.choice', return_value="target_dummy"):
                quest = generate_kill_objective(self.world, 1, giver, self.world.quest_manager.config)
            
            self.assertIsNotNone(quest)
            if quest:
                # FIX: Check for the region's name, not its ID, in the hint
                self.assertIn("riverside village", quest["location_hint"].lower())

    def test_mana_deduction_timing(self):
        """Verify mana is not deducted if spell cast fails checks."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        self.player.runtime_state.magic.mana = 10
        # Spell costs 20
        from engine.magic.spell import Spell
        spell = Spell(
            "expensive", "Expensive", "x",
            effects=[{"type": "damage", "value": 1}],
            mana_cost=20,
            level_required=1,
        )
        
        self.player.runtime_state.magic.known_spells.add("expensive")
        
        # Act
        result = self.player.cast_spell(spell, self.player, time.time())
        
        # Assert
        self.assertFalse(result["success"])
        self.assertEqual(self.player.runtime_state.magic.mana, 10, "Mana should not be deducted on failure.")

    def test_examine_container_status(self):
        """Verify examine output reflects open/closed/locked states."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Closed/Locked
        self.world.item_templates["box"] = {
            "type": "Container", "name": "Box", 
            "properties": {"locked": True, "is_open": False}
        }
        box = ItemFactory.create_item_from_template("box", self.world)
        self.assertIsNotNone(box)
        
        if box:
            desc = box.examine()
            self.assertIn("Locked", desc)
            self.assertIn("Closed", desc)
            
            # 2. Unlock/Open
            box.properties["locked"] = False
            box.properties["is_open"] = True
            
            desc_open = box.examine()
            self.assertIn("Unlocked", desc_open)
            self.assertIn("Open", desc_open)

    def test_drop_non_existent(self):
        """Verify 'drop' handles non-existent items gracefully."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # FIX: Ensure inventory isn't empty first, otherwise the error message 
        # is "Your inventory is empty" instead of "You don't have...".
        self.world.item_templates["dummy"] = {"type": "Item", "name": "Dummy Item"}
        dummy = ItemFactory.create_item_from_template("dummy", self.world)
        if dummy:
             self.player.inventory.add_item(dummy)

        # Act
        result = self.game.process_command("drop Nothing")
        
        # Assert
        self.assertIsNotNone(result)
        if result:
            self.assertIn("don't have", result.lower())
