# tests/batch/test_batch_6.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.core.skill_system import SkillSystem
from engine.core.combat_system import CombatSystem

class TestBatch6(GameTestBase):

    def test_faction_assist(self):
        """Verify friendly NPCs assist each other in combat."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # Ensure template exists
        self.world.npc_templates["town_guard"] = {
            "name": "Town Guard", "faction": "friendly", "health": 50, "level": 5
        }

        guard1 = NPCFactory.create_npc_from_template("town_guard", self.world, instance_id="g1")
        guard2 = NPCFactory.create_npc_from_template("town_guard", self.world, instance_id="g2")
        
        self.assertIsNotNone(guard1, "Failed to create Guard 1")
        self.assertIsNotNone(guard2, "Failed to create Guard 2")

        if guard1 and guard2:
            guard1.current_region_id = self.player.current_region_id
            guard1.current_room_id = self.player.current_room_id
            guard2.current_region_id = self.player.current_region_id
            guard2.current_room_id = self.player.current_room_id
            self.world.add_npc(guard1)
            self.world.add_npc(guard2)
            
            # 1. Player Attacks G1
            self.player.enter_combat(guard1)
            guard1.enter_combat(self.player)
            
            # 2. Trigger AI Scan for G2
            from engine.npcs.ai.combat_logic import scan_for_targets
            scan_for_targets(guard2, self.world, self.player)
            
            # 3. Assert G2 targets Player (assisting G1)
            self.assertTrue(guard2.in_combat, "Guard 2 should enter combat.")
            self.assertIn(self.player, guard2.combat_targets, "Guard 2 should target the player.")

    def test_loot_corpse(self):
        """Verify looting a corpse moves item to inventory."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Ensure Item Template exists for loot
        self.world.item_templates["item_gold_coin"] = {"type": "Treasure", "name": "Gold Coin"}
        
        # 2. Create Goblin
        self.world.npc_templates["goblin"] = {
            "name": "Goblin", "faction": "hostile", "health": 10
        }
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        self.assertIsNotNone(goblin, "Failed to create goblin.")

        if goblin:
            # Force loot table
            goblin.loot_table = {"item_gold_coin": {"chance": 1.0, "quantity": [1, 1]}}
            
            # Set location so items drop there
            goblin.current_region_id = self.player.current_region_id
            goblin.current_room_id = self.player.current_room_id
            
            # Die -> Drops items to room
            dropped = goblin.die(self.world)
            self.assertEqual(len(dropped), 1)
            
            # Pick Up
            self.game.process_command("get gold coin")
            self.assertEqual(self.player.inventory.count_item("item_gold_coin"), 1)

    def test_spell_learning_consumption(self):
        """Verify scroll is consumed upon learning spell."""
        if not self.player: return

        spell = Spell(
            "test_learn", "Learn Me", "x",
            effects=[{"type": "damage", "value": 1}],
            level_required=1,
            mana_cost=5,
        )
        register_spell(spell)
        
        self.world.item_templates["scroll_learn"] = {
            "type": "Consumable", "name": "Scroll", "value": 1,
            "properties": {"effect_type": "learn_spell", "spell_to_learn": "test_learn", "uses": 1}
        }
        scroll = ItemFactory.create_item_from_template("scroll_learn", self.world)
        self.assertIsNotNone(scroll, "Failed to create scroll.")

        if scroll:
            self.player.inventory.add_item(scroll)
            
            # Use item directly to bypass command parsing variables
            msg = scroll.use(self.player)
            
            self.assertIn("successfully learn", msg)
            self.assertIn("test_learn", self.player.runtime_state.magic.known_spells)
            self.assertEqual(scroll.get_property("uses"), 0)

    def test_skill_xp_ui_feedback(self):
        """Verify skill gain produces user feedback."""
        if not self.player: return

        self.player.add_skill("mining", 1)
        
        # Grant XP -> Level Up
        # Need 100 XP to level 1->2
        msg = SkillSystem.grant_xp(self.player, "mining", 100)
        
        self.assertIn("mining skill has increased to 2", msg)

    def test_inventory_capacity_hard_cap(self):
        """Verify inventory absolutely refuses items past max slots."""
        if not self.player: return

        self.player.inventory.max_slots = 1
        self.player.inventory.slots = [self.player.inventory.slots[0]]
        
        self.world.item_templates["sword"] = {"type": "Weapon", "name": "Sword", "stackable": False}

        i1 = ItemFactory.create_item_from_template("sword", self.world)
        i2 = ItemFactory.create_item_from_template("sword", self.world)
        
        self.assertIsNotNone(i1)
        self.assertIsNotNone(i2)

        if i1 and i2:
            i1.obj_id="s1"
            i2.obj_id="s2"
        
            self.player.inventory.add_item(i1) # Full
            
            success, msg = self.player.inventory.add_item(i2)
            self.assertFalse(success)
            self.assertEqual(self.player.inventory.count_item("s2"), 0)

    def test_damage_variance(self):
        """Verify damage calculations include randomness."""
        if not self.player: return

        # 1. Force stats
        self.player.runtime_state.combat.attack_power = 10
        self.player.stats["strength"] = 10 # +0 bonus
        # Base damage = 10
        
        # 2. Calculate range (Player variance -1 to +2)
        # 9 to 12
        
        damages = set()
        self.world.npc_templates["goblin"] = {"name": "Goblin", "faction": "hostile", "health": 1000}
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        self.assertIsNotNone(target)

        if target:
            # 3. Simulate multiple hits
            # We need to bypass hit chance to verify dmg variance specifically
            for _ in range(20):
                dmg = CombatSystem.calculate_physical_damage(self.player, target, 10)
                damages.add(dmg)
                
            self.assertTrue(len(damages) > 1, "Damage should vary.")
            for d in damages:
                self.assertGreaterEqual(d, 9)
                self.assertLessEqual(d, 12)

    def test_teleport_validation(self):
        """Verify teleport command handles invalid input gracefully."""
        if not self.player: return
        
        res_invalid = self.game.process_command("teleport invalid_region room")
        self.assertIsNotNone(res_invalid)
        if res_invalid:
            self.assertIn("Could not find", res_invalid)
        
        # Ensure target region exists
        from engine.world.region import Region
        from engine.world.room import Room
        if "town" not in self.world.regions:
            r = Region("Town", "x", obj_id="town")
            r.add_room("town_square", Room("Square", "x", obj_id="town_square"))
            self.world.add_region("town", r)

        # Valid
        res_valid = self.game.process_command("teleport town town_square")
        self.assertIsNotNone(res_valid)
        if res_valid:
            self.assertIn("Teleported to", res_valid)
        
        self.assertEqual(self.player.current_room_id, "town_square")

    def test_gold_transfer(self):
        """Verify selling transfers gold value to player."""
        if not self.player: return

        # 1. Setup Item (Value 100)
        self.world.item_templates["gem"] = {"type": "Gem", "name": "Gem", "value": 100}
        gem = ItemFactory.create_item_from_template("gem", self.world)
        self.assertIsNotNone(gem)

        if gem:
            self.player.inventory.add_item(gem)
            self.player.runtime_state.gold = 0
            
            # 2. Setup Vendor
            merchant = NPCFactory.create_npc_from_template("merchant", self.world)
            if not merchant:
                merchant = NPCFactory.create_npc_from_template("wandering_villager", self.world)
            
            self.assertIsNotNone(merchant, "Failed to create merchant.")
            
            if merchant:
                # FIX: Explicitly ensure the merchant buys "Gem" for this test, as the default template might not.
                merchant.properties["is_vendor"] = True
                buy_types = merchant.properties.get("buys_item_types", [])
                if "Gem" not in buy_types:
                    buy_types.append("Gem")
                    merchant.properties["buys_item_types"] = buy_types
                # This test spawns the "merchant" template as a generic
                # stand-in vendor and expects the global default sell rate,
                # not the merchant's own (deliberately lower) general-store
                # rate.
                merchant.properties["sell_rate_multiplier"] = 0.4

                self.world.add_npc(merchant)
                if self.player.current_region_id and self.player.current_room_id:
                    merchant.current_region_id = self.player.current_region_id
                    merchant.current_room_id = self.player.current_room_id
                
                # 3. Sell (Mult 0.4 -> 40g)
                self.player.trading_with = merchant.obj_id
                result = self.game.process_command("sell Gem")
                
                self.assertEqual(self.player.runtime_state.gold, 40)

    def test_key_ring_auto_select(self):
        """Verify having multiple keys automatically uses the correct one."""
        if not self.player: return

        # Setup Chest (Key A)
        self.world.item_templates["chest"] = {"type": "Container", "name": "Chest", "properties": {"locked": True, "key_id": "key_a"}}
        chest = ItemFactory.create_item_from_template("chest", self.world)
        self.assertIsNotNone(chest)

        if chest:
            if self.player.current_region_id and self.player.current_room_id:
                self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, chest)
        
        # Setup Keys
        self.world.item_templates["item_rusty_key"] = {"type": "Key", "name": "Rusty Key"}
        key_b = ItemFactory.create_item_from_template("item_rusty_key", self.world)
        key_a = ItemFactory.create_item_from_template("item_rusty_key", self.world)
        
        self.assertIsNotNone(key_a)
        self.assertIsNotNone(key_b)

        if key_a and key_b:
            key_b.obj_id = "key_b"
            key_a.obj_id = "key_a"
            key_a.name="Key A"
            
            self.player.inventory.add_item(key_b)
            self.player.inventory.add_item(key_a)
            
            # Act: Use "Key A" explicitly
            res = self.game.process_command("use Key A on Chest")
            self.assertIsNotNone(res)
            if res:
                self.assertIn("You unlock", res)
            if chest:
                self.assertFalse(chest.properties["locked"])

    def test_consumable_max_uses(self):
        """Verify multi-use item consumption."""
        if not self.player: return

        self.world.item_templates["flask"] = {
            "type": "Consumable", "name": "Flask", "value": 10,
            "properties": {"uses": 2, "max_uses": 2, "effect_type": "heal", "effect_value": 1}
        }
        flask = ItemFactory.create_item_from_template("flask", self.world)
        self.assertIsNotNone(flask, "Failed to create flask.")

        if flask:
            self.player.inventory.add_item(flask)
            
            # Use 1
            res1 = flask.use(self.player)
            self.assertEqual(flask.get_property("uses"), 1)
            self.assertIn("1/2 uses remaining", res1)
            
            # Use 2
            res2 = flask.use(self.player)
            self.assertEqual(flask.get_property("uses"), 0)
            self.assertIn("used up", res2)
