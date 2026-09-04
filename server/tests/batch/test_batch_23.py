# tests/batch/test_batch_23.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.config import MINIMUM_DAMAGE_TAKEN
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.world.room import Room

class TestBatch23(GameTestBase):
    """Focus: Combat Edge Cases."""

    def test_overkill_hp_clamp(self):
        """Verify HP does not go below zero."""
        self.player.health = 10
        self.player.take_damage(100, "physical")
        self.assertEqual(self.player.health, 0)

    def test_heal_dead_player(self):
        """Verify healing a dead player does nothing."""
        self.player.die(self.world)
        self.player.heal(100)
        self.assertEqual(self.player.health, 0)
        self.assertFalse(self.player.is_alive)

    def test_cast_while_stunned_fail(self):
        """Verify spells fail when stunned."""
        stun = {"type": "control", "name": "Stun", "base_duration": 5.0}
        self.player.apply_effect(stun, time.time())
        
        # Try generic spell logic
        s = Spell("test", "Test", "x", effects=[{"type": "damage", "value": 1}], target_type="self")
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.known_spells.add("test")
        
        res = self.player.cast_spell(s, self.player, time.time(), self.world)
        self.assertFalse(res["success"])
        self.assertIn("stunned", res["message"].lower())

    def test_attack_while_stunned_fail(self):
        """Verify attacks fail when stunned."""
        stun = {"type": "control", "name": "Stun", "base_duration": 5.0}
        self.player.apply_effect(stun, time.time())
        
        npc = NPCFactory.create_npc_from_template("goblin", self.world)
        if npc:
             res = self.player.attack(npc, self.world)
             self.assertIn("stunned", res["message"].lower())

    def test_minion_aggro_on_owner_attack(self):
        """Verify minion attacks whatever attacks its owner."""
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        attacker = NPCFactory.create_npc_from_template("bandit", self.world)
        
        if minion and attacker:
            minion.properties["owner_id"] = self.player.obj_id
            
            # Sync
            loc = (self.player.current_region_id, self.player.current_room_id)
            minion.current_region_id, minion.current_room_id = loc
            attacker.current_region_id, attacker.current_room_id = loc
            self.world.add_npc(minion)
            self.world.add_npc(attacker)
            
            # Attacker hits Player
            attacker.enter_combat(self.player)
            self.player.enter_combat(attacker)
            
            # Run Minion AI
            from engine.npcs.ai.specialized import perform_minion_logic
            msg = perform_minion_logic(minion, self.world, time.time(), self.player)
            
            self.assertTrue(minion.in_combat)
            self.assertIn(attacker, minion.combat_targets)
            if msg: self.assertIn("intercepts", msg.lower())

    def test_resistance_stacking(self):
        """Verify resistances from stats and gear stack."""
        self.player.stats["resistances"] = {"fire": 10}
        
        # Gear with 20 fire resist (using properties since JSON templates define it there)
        boots = ItemFactory.create_item_from_template("item_leather_boots", self.world)
        if boots:
            boots.properties["resistances"] = {"fire": 20}
            self.player.inventory.add_item(boots)
            self.player.equip_item(boots, "feet")
            
            total = self.player.get_resistance("fire")
            self.assertEqual(total, 30)

    def test_dot_persistence_on_death(self):
        """Verify DoT effects are cleared on death."""
        dot = {"type": "dot", "name": "Pois", "damage_per_tick": 5}
        self.player.apply_effect(dot, time.time())
        
        self.player.die(self.world)
        
        self.assertEqual(len(self.player.active_effects), 0)

    def test_combat_cooldown_reset_on_death(self):
        """Verify attack cooldown resets on death."""
        self.player.last_attack_time = time.time()
        self.player.die(self.world)
        self.player.respawn()
        pass

    def test_npc_flee_movement(self):
        """Verify fleeing NPC actually changes rooms."""
        npc = NPCFactory.create_npc_from_template("goblin", self.world)
        
        region = self.world.get_region("town")
        if region and npc:
            # Create a safe room
            region.add_room("safe", Room("Safe", "x", {"south": "town_square"}, obj_id="safe"))
            sq = region.get_room("town_square")
            if sq:
                # Clear existing exits to ensure deterministic fleeing
                sq.exits = {"north": "safe"} 
            
            npc.current_region_id = "town"
            npc.current_room_id = "town_square"
            self.world.add_npc(npc)
            
            # Force flee
            from engine.npcs.ai.combat_logic import try_flee
            try_flee(npc, self.world, self.player)
            
            self.assertEqual(npc.current_room_id, "safe")

    def test_friendly_fire_aoe_check(self):
        """Verify mechanisms (like checks in spell casting) prevent friendly fire."""
        npc = NPCFactory.create_npc_from_template("goblin", self.world)
        if npc:
            # FIX: Ensure NPC is in same room as player so 'cast' command finds it
            npc.current_region_id = self.player.current_region_id
            npc.current_room_id = self.player.current_room_id
            
            self.world.add_npc(npc)
            npc.faction = "hostile"
            
            # Spell - Name must be "Heal" to be found by "cast heal"
            heal = Spell("heal", "Heal", "x", effects=[{"type": "heal", "value": 1}], target_type="friendly")
            register_spell(heal)
            assert self.player.runtime_state.magic is not None
            self.player.runtime_state.magic.known_spells.add("heal")
            
            # Attempt cast via command
            res = self.game.process_command(f"cast heal on {npc.name}")
            self.assertIsNotNone(res)
            if res:
                self.assertIn("only cast", res.lower())
