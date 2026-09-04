# tests/batch/test_batch_9.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.items.container import Container
from engine.items.key import Key
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.core.skill_system import SkillSystem, MAX_SKILL_LEVEL
from engine.config import TIME_DAYS_PER_MONTH, TIME_MONTHS_PER_YEAR

class TestBatch9(GameTestBase):

    def test_inventory_weight_nested_containers(self):
        """Verify containers act like Bags of Holding (internal items don't add to player weight)."""
        if not self.player:
            self.fail("Player not initialized.")
            return

        # 1. Setup Items
        # Heavy item (100 lbs)
        self.world.item_templates["anvil"] = {"type": "Item", "name": "Anvil", "weight": 100.0}
        # Bag (1 lb, Capacity 200)
        self.world.item_templates["bag"] = {
            "type": "Container", "name": "Bag", "weight": 1.0, 
            "properties": {"capacity": 200.0, "is_open": True}
        }
        
        anvil = ItemFactory.create_item_from_template("anvil", self.world)
        bag = ItemFactory.create_item_from_template("bag", self.world)
        
        self.assertIsNotNone(anvil)
        self.assertIsNotNone(bag)

        if anvil and isinstance(bag, Container):
            # 2. Put Bag in Inventory
            self.player.inventory.add_item(bag)
            base_weight = self.player.inventory.get_total_weight()
            self.assertEqual(base_weight, 1.0)
            
            # 3. Put Anvil in Bag
            bag.add_item(anvil)
            
            # 4. Assert Player Weight is unchanged (1.0), not 101.0
            new_weight = self.player.inventory.get_total_weight()
            self.assertEqual(new_weight, 1.0, "Container should mask contents weight.")
            
            # 5. Assert Bag Weight calculation works locally
            self.assertEqual(bag.get_current_weight(), 100.0)

    def test_key_fuzzy_matching(self):
        """Verify keys match containers by name if IDs don't match."""
        if not self.player: return

        # 1. Setup Container "Brass Chest"
        self.world.item_templates["chest"] = {
            "type": "Container", "name": "Brass Chest", 
            "properties": {"locked": True, "key_id": None} # No explicit ID
        }
        chest = ItemFactory.create_item_from_template("chest", self.world)
        
        # 2. Setup Key "Brass Key"
        self.world.item_templates["key"] = {"type": "Key", "name": "Brass Key"}
        key = ItemFactory.create_item_from_template("key", self.world)
        
        self.assertIsNotNone(chest)
        self.assertIsNotNone(key)

        # Validate location strings for Pylance
        rid = self.player.current_region_id
        room_id = self.player.current_room_id
        
        if chest and key and rid and room_id:
            self.player.inventory.add_item(key)
            self.world.add_item_to_room(rid, room_id, chest)
            
            # 3. Act
            # Use keyword argument 'target' to satisfy Item.use signature (self, user, **kwargs)
            # and Key.use signature (self, user, target=None, **kwargs) simultaneously for checkers.
            msg = key.use(self.player, target=chest)
            
            # 4. Assert
            self.assertIn("unlock", msg)
            self.assertFalse(chest.properties["locked"])

    def test_command_look_equipment(self):
        """Verify 'look' command finds equipped items."""
        if not self.player: return

        # 1. Equip Sword
        sword = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.assertIsNotNone(sword)
        
        if sword:
            self.player.inventory.add_item(sword)
            self.player.equip_item(sword)
            self.assertEqual(self.player.equipment["main_hand"], sword)
            
            # 2. Look at it
            result = self.game.process_command("look iron sword")
            
            # 3. Assert
            self.assertIsNotNone(result)
            if result:
                # Use lower() to match the template name "iron sword" which is lowercase in data
                self.assertIn("iron sword", result.lower())
                self.assertIn("Equip Slot", result)

    def test_quest_deliver_wrong_npc(self):
        """Verify delivering a quest item to the wrong NPC fails."""
        if not self.player: return

        # 1. Setup Quest
        q_id = "deliver_fail_test"
        self.player.runtime_state.quests.active[q_id] = {
            "instance_id": q_id, "type": "deliver", "state": "active",
            "objective": {
                "type": "deliver",
                "item_instance_id": "pkg_id",
                "recipient_instance_id": "correct_npc_id",
                "recipient_name": "Correct NPC"
            }
        }
        
        # 2. Setup Package
        self.world.item_templates["package"] = {"type": "Item", "name": "Package"}
        pkg = ItemFactory.create_item_from_template("package", self.world)
        if pkg:
            pkg.obj_id = "pkg_id"
            self.player.inventory.add_item(pkg)
            
        # 3. Setup Wrong NPC
        wrong_npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        if wrong_npc:
            wrong_npc.obj_id = "wrong_npc_id"
            wrong_npc.name = "Wrong Guy"
            wrong_npc.current_region_id = self.player.current_region_id
            wrong_npc.current_room_id = self.player.current_room_id
            self.world.add_npc(wrong_npc)
            
            # 4. Act
            result = self.game.process_command("give Package to Wrong Guy")
            
            # 5. Assert
            self.assertIsNotNone(result)
            if result:
                self.assertIn("should give the Package to Correct NPC", result)
                self.assertIn("not Wrong Guy", result)
            
            # Verify item still in inventory
            self.assertEqual(self.player.inventory.count_item("pkg_id"), 1)

    def test_skill_cap_boundary(self):
        """Verify skills cannot exceed MAX_SKILL_LEVEL."""
        if not self.player: return

        skill = "archery"
        self.player.add_skill(skill, MAX_SKILL_LEVEL - 1)
        
        # 1. Level up to max
        req = SkillSystem.get_xp_for_next_level(MAX_SKILL_LEVEL - 1)
        msg = SkillSystem.grant_xp(self.player, skill, req)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["level"], MAX_SKILL_LEVEL)
        self.assertIn("increased", msg)
        
        # 2. Try to level past max
        msg_overflow = SkillSystem.grant_xp(self.player, skill, 10000)
        self.assertEqual(self.player.runtime_state.progression.skills[skill]["level"], MAX_SKILL_LEVEL)
        self.assertEqual(msg_overflow, "")

    def test_command_help_specific(self):
        """Verify help <command> returns detailed info."""
        # 1. Act
        result = self.game.process_command("help look")
        
        # 2. Assert
        self.assertIsNotNone(result)
        if result:
            self.assertIn("COMMAND: LOOK", result.upper()) # Title check
            self.assertIn("Usage:", result)
            self.assertIn("aliases", result.lower())

    def test_npc_no_spawn_flag(self):
        """Verify spawner skips rooms with 'no_monster_spawn' property."""
        spawner = self.world.spawner
        
        # 1. Setup Region
        region = self.world.get_region("town")
        if not region: 
            self.fail("Town region missing")
            return
            
        region.spawner_config = {"monster_types": {"goblin": 1}}
        region.properties["safe_zone"] = False # Ensure region is theoretically unsafe
        
        # 2. Setup Room with Flag
        from engine.world.room import Room
        safe_room = Room("Holy Ground", "Sanctuary", obj_id="holy_room")
        safe_room.properties["no_monster_spawn"] = True
        region.add_room("holy_room", safe_room)
        
        # Set player somewhere else so spawn isn't blocked by player presence
        self.player.current_region_id = "town"
        self.player.current_room_id = "other_room"
        self.world.current_region_id = "town"
        self.world.current_room_id = "other_room"
        
        # 3. Act: Trigger Spawn Logic internally
        # We invoke _spawn_monsters_in_region directly to test logic
        initial_count = len(self.world.npcs)
        
        # Clear other rooms from consideration for this test
        original_rooms = region.rooms.copy()
        region.rooms = {
            "holy_room": safe_room,
            "other_room": Room("Player is Here", "x", obj_id="other_room") # Player loc
        }
        
        with patch('random.random', return_value=0.0):
            spawner._spawn_monsters_in_region(region)
            
        # Restore
        region.rooms = original_rooms
        
        # 4. Assert
        self.assertEqual(len(self.world.npcs), initial_count, "Should not spawn in no_monster_spawn room.")

    def test_year_rollover(self):
        """Verify date advances correctly at end of year."""
        tm = self.game.time_manager
        
        # 1. Set to last second of Year 1
        # Year 1, Month 12, Day 30, 23:59:59 (assuming 30 days/month, 12 months)
        # Total days = 360.
        seconds_per_year = 360 * 86400.0
        tm.initialize_time(seconds_per_year - 1.0)
        
        self.assertEqual(tm.year, 1)
        
        # 2. Advance 2 seconds
        # Need to convert game seconds to real seconds for update()
        # default config: 1200 real sec = 1 game day (86400 game sec) -> Ratio ~72
        # We can just manipulate game_time directly and call recalculate
        tm.game_time += 2.0
        tm._recalculate_date_from_game_time()
        
        # 3. Assert
        self.assertEqual(tm.year, 2)
        self.assertEqual(tm.month, 1)
        self.assertEqual(tm.day, 1)

    def test_player_death_xp_retention(self):
        """Verify XP is retained on death (current design)."""
        if not self.player: return

        # 1. Gain XP
        self.player.experience = 50
        
        # 2. Die
        self.player.die(self.world)
        self.assertFalse(self.player.is_alive)
        
        # 3. Respawn
        self.player.respawn()
        
        # 4. Assert
        self.assertEqual(self.player.experience, 50, "XP should be retained after respawn.")

    def test_consumable_learn_spell_known(self):
        """Verify using a scroll for a known spell does not consume it."""
        if not self.player: return

        # 1. Teach spell
        spell_id = "test_spell"
        spell = Spell(
            spell_id, "Test", "x",
            effects=[{"type": "damage", "value": 1}],
            level_required=1,
            mana_cost=5,
        )
        register_spell(spell)
        self.player.learn_spell(spell_id)
        
        # 2. Create Scroll
        self.world.item_templates["scroll"] = {
            "type": "Consumable", "name": "Scroll", "value": 1,
            "properties": {"effect_type": "learn_spell", "spell_to_learn": spell_id, "uses": 1}
        }
        scroll = ItemFactory.create_item_from_template("scroll", self.world)
        self.assertIsNotNone(scroll)
        
        if scroll:
            self.player.inventory.add_item(scroll)
            
            # 3. Use
            msg = scroll.use(self.player)
            
            # 4. Assert
            self.assertIn("already know", msg.lower())
            self.assertEqual(scroll.get_property("uses"), 1, "Scroll should not be consumed.")
            self.assertEqual(self.player.inventory.count_item("scroll"), 1)
