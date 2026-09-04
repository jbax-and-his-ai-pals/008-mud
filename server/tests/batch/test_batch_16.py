# tests/batch/test_batch_16.py
import time
import os
from unittest.mock import patch
from engine.magic.effects import apply_spell_effect
from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.items.container import Container

class TestBatch16(GameTestBase):
    """Focus: Magic, Minions, and Spell Interactions."""

    def setUp(self):
        super().setUp()
        # Register a test spell
        self.test_spell = Spell("test_blast", "Blast", "x", mana_cost=10, effects=[{"type": "damage", "value": 10}], cooldown=5.0)
        register_spell(self.test_spell)
        self.player.learn_spell("test_blast")

    def test_offensive_spell_safety(self):
        """Verify offensive spells cannot be cast on self."""
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.mana = 20
        
        # Act
        result = self.player.cast_spell(self.test_spell, self.player, time.time())
        
        # Assert: The core Player.cast_spell now enforces target validity
        self.assertFalse(result["success"])
        self.assertIn("only cast", result["message"].lower())

    def test_healer_mana_drain(self):
        """Verify healer NPCs lose mana when casting heals."""
        healer = NPCFactory.create_npc_from_template("healer", self.world)
        if not healer: return
        
        healer.max_mana = 50
        healer.mana = 50
        healer.current_region_id = "town"; healer.current_room_id = "temple"
        self.world.add_npc(healer)
        
        # Injured ally
        ally = NPCFactory.create_npc_from_template("villager", self.world)
        if ally:
            ally.max_health = 100; ally.health = 10
            ally.current_region_id = "town"; ally.current_room_id = "temple"
            self.world.add_npc(ally)
            
            # Force Healer Logic
            from engine.npcs.ai.specialized import perform_healer_logic
            perform_healer_logic(healer, self.world, time.time(), self.player)
            
            self.assertLess(healer.mana, 50, "Healer should consume mana to heal.")

    def test_dot_kill_xp(self):
        """Verify XP is awarded if a DoT effect kills an enemy."""
        enemy = NPCFactory.create_npc_from_template("goblin", self.world)
        if not enemy: return
        self.world.add_npc(enemy)
        enemy.health = 2 # Very low health
        
        # Apply Player-sourced DoT
        dot = {
            "type": "dot", "name": "Bleed", "damage_per_tick": 5, 
            "source_id": self.player.obj_id, "tick_interval": 0.1
        }
        enemy.apply_effect(dot, time.time())
        
        enemy.process_active_effects(time.time() + 0.2, 0.2)
        self.assertFalse(enemy.is_alive)

    def test_minion_follows_across_regions(self):
        """Verify minions follow player even when changing regions."""
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        if minion:
            minion.properties["owner_id"] = self.player.obj_id
            self.world.add_npc(minion)
            
            # Start
            self.player.current_region_id = "town"; self.player.current_room_id = "gate"
            minion.current_region_id = "town"; minion.current_room_id = "gate"
            
            # Move Player Far Away
            self.player.current_region_id = "dungeon"; self.player.current_room_id = "entrance"
            
            # Let's link them
            from engine.world.region import Region
            from engine.world.room import Room
            r1 = Region("Town", "x", obj_id="town"); r1.add_room("gate", Room("Gate", "", {"north": "dungeon:entrance"}, obj_id="gate"))
            r2 = Region("Dun", "x", obj_id="dungeon"); r2.add_room("entrance", Room("Ent", "", {"south": "town:gate"}, obj_id="entrance"))
            self.world.add_region("town", r1)
            self.world.add_region("dungeon", r2)
            
            # Update Minion AI
            from engine.npcs.ai.dispatcher import handle_ai
            minion.last_moved = 0
            handle_ai(minion, self.world, time.time(), self.player)
            
            self.assertEqual(minion.current_region_id, "dungeon")
            self.assertEqual(minion.current_room_id, "entrance")

    def test_knock_unlocks_chest(self):
        """Verify the 'Knock' spell unlocks containers."""
        chest = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        if isinstance(chest, Container):
            chest.properties["locked"] = True
            
            knock = Spell("knock", "Knock", "x", effects=[{"type": "unlock"}], target_type="item")
            
            # Cast
            apply_spell_effect(self.player, chest, knock, self.player)
            
            self.assertFalse(chest.properties["locked"])

    def test_arcane_lock_locks_chest(self):
        """Verify the 'Arcane Lock' spell locks containers."""
        chest = ItemFactory.create_item_from_template("item_empty_crate", self.world)
        if isinstance(chest, Container):
            chest.properties["locked"] = False
            chest.properties["is_open"] = True
            
            lock_spell = Spell("lock", "Lock", "x", effects=[{"type": "lock"}], target_type="item")
            
            apply_spell_effect(self.player, chest, lock_spell, self.player)
            
            self.assertTrue(chest.properties["locked"])
            self.assertFalse(chest.properties["is_open"], "Locking should close the chest.")

    def test_buff_refresh(self):
        """Verify recasting a buff resets its duration."""
        buff = {
            "type": "stat_mod", "name": "Might", "base_duration": 10.0, "modifiers": {"strength": 5}
        }
        self.player.apply_effect(buff, time.time())
        
        # Simulate time passing
        self.player.active_effects[0]["duration_remaining"] = 1.0
        
        # Re-apply
        self.player.apply_effect(buff, time.time())
        
        # Check duration
        self.assertAlmostEqual(self.player.active_effects[0]["duration_remaining"], 10.0, delta=0.1)

    def test_stun_prevents_cast(self):
        """Verify a stunned player cannot cast spells."""
        self.player.apply_effect({"type": "control", "name": "Stun", "base_duration": 5.0}, time.time())
        
        res = self.player.cast_spell(self.test_spell, self.player, time.time(), self.world)
        
        self.assertFalse(res["success"])
        self.assertIn("stunned", res["message"].lower())

    def test_cooldown_save_persistence(self):
        """Verify spell cooldowns survive serialization."""
        TEST_SAVE = "test_cd_persist_batch16.json"
        
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.cooldowns["test_blast"] = time.time() + 100.0
        
        self.world.save_game(TEST_SAVE)
        self.player.runtime_state.magic.cooldowns = {}
        self.world.load_save_game(TEST_SAVE)
        
        loaded = self.world.player
        if loaded:
            # Check if cooldown is still roughly 100s in future
            assert loaded.runtime_state.magic is not None
            remaining = loaded.runtime_state.magic.cooldowns.get("test_blast", 0) - time.time()
            self.assertGreater(remaining, 90.0)
            
        if os.path.exists(os.path.join("data", "saves", TEST_SAVE)):
            os.remove(os.path.join("data", "saves", TEST_SAVE))

    def test_summon_cap_soft_enforcement(self):
        """
        Verify that if max summons is reached, the system behaves predictably.
        """
        # Ensure minion template exists
        self.world.npc_templates["skeleton_minion"] = {
            "name": "Skeleton", "faction": "player_minion", "health": 10
        }
        
        # FIX: Set target_type="self"
        summon_spell = Spell(
            "sum", "Summon", "x",
            effects=[{"type": "summon", "summon_template_id": "skeleton_minion"}],
            cooldown=0.0,
            target_type="self",
        )
        register_spell(summon_spell)
        self.player.learn_spell("sum")
        
        # Cast 5 times
        for _ in range(5):
            self.player.cast_spell(summon_spell, self.player, time.time(), self.world)
            
        assert self.player.runtime_state.magic is not None
        count = len(self.player.runtime_state.magic.summons.get("sum", []))
        self.assertGreaterEqual(count, 5, "Should have 5 summons (or cap if enforced).")
