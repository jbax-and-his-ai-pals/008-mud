# tests/singles/test_advanced_ai.py
import time
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import handle_ai
from engine.player.core import Player
from engine.world.region import Region
from engine.world.room import Room

class TestAdvancedAI(GameTestBase):
    
    def test_npc_fleeing(self):
        """Verify NPCs flee when health is critical."""
        # 1. Setup Hostile
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        self.assertIsNotNone(goblin, "Failed to create goblin")
        
        if goblin:
            self.world.add_npc(goblin)
            # Must be in a room with exits to flee TO
            goblin.current_region_id = "town"
            goblin.current_room_id = "town_square"
            
            # 2. Force Low Health
            goblin.health = 1 
            goblin.flee_threshold = 0.5
            
            # Put in combat so flee logic triggers
            self.player.enter_combat(goblin)
            goblin.enter_combat(self.player)
            
            # 3. Act
            handle_ai(goblin, self.world, time.time(), self.player)
            
            # 4. Assert
            self.assertNotEqual(goblin.current_room_id, "town_square", "Goblin should have fled.")
            self.assertFalse(goblin.in_combat, "Fleeing should exit combat.")

    def test_minion_following(self):
        """Verify summoned minions follow the player."""
        # 1. Summon Minion
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        self.assertIsNotNone(minion, "Failed to create minion")
        
        if minion:
            minion.properties["owner_id"] = self.player.obj_id
            self.world.add_npc(minion)
            
            # Reset Cooldown
            minion.last_moved = 0 
            
            # Start together in Town Square
            self.player.current_region_id = "town"
            self.player.current_room_id = "town_square"
            minion.current_region_id = "town"
            minion.current_room_id = "town_square"
            
            # 2. Move Player to adjacent room
            self.player.current_room_id = "north_gate_road" 
            
            # DIAGNOSTIC: Verify path exists before AI run
            path = self.world.find_path("town", "town_square", "town", "north_gate_road")
            self.assertEqual(path, ["north"], "Map data check failed: Path should exist between square and gate road.")

            # 3. Act (Minion AI Tick)
            handle_ai(minion, self.world, time.time(), self.player)
            
            # 4. Assert
            self.assertEqual(minion.current_room_id, "north_gate_road", "Minion should follow player.")

    def test_minion_combat_assist(self):
        """Verify minions attack their owner's target."""
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        target = NPCFactory.create_npc_from_template("goblin", self.world)
        
        if minion and target:
            minion.properties["owner_id"] = self.player.obj_id
            self.world.add_npc(minion)
            self.world.add_npc(target)
            
            minion.last_moved = 0
            
            loc = ("town", "town_square")
            self.player.current_region_id = loc[0]
            self.player.current_room_id = loc[1]
            minion.current_region_id = loc[0]
            minion.current_room_id = loc[1]
            target.current_region_id = loc[0]
            target.current_room_id = loc[1]
            
            # 1. Player attacks Target
            self.player.enter_combat(target)
            self.player.combat_target = target
            
            # 2. Act (Minion AI Tick)
            handle_ai(minion, self.world, time.time(), self.player)
            
            # 3. Assert
            self.assertTrue(minion.in_combat)
            self.assertIn(target, minion.combat_targets, "Minion should target the goblin.")

    def test_healer_can_heal_other_player_in_room_not_just_passed_viewer(self):
        """Verify healer support logic scans all co-located players in a multiplayer room."""
        heal_spell = Spell(
            spell_id="npc_heal_test",
            name="NPC Heal",
            description="Restore health",
            mana_cost=5,
            cooldown=0.0,
            effects=[{"type": "heal", "value": 20}],
            target_type="friendly",
            level_required=1,
            cast_message="{caster_name} casts {spell_name}!",
        )
        register_spell(heal_spell)

        healer = NPCFactory.create_npc_from_template("wandering_mage", self.world)
        self.assertIsNotNone(healer)

        if healer:
            region = Region("Healer Region", "Isolated healer test.", obj_id="healer_region")
            room = Room("Healer Room", "Only healer and players are here.", obj_id="healer_room")
            region.add_room("healer_room", room)
            self.world.add_region("healer_region", region)

            other_player = Player("WoundedHero", obj_id="wounded_hero", world=self.world)
            other_player.world = self.world
            other_player.current_region_id = "healer_region"
            other_player.current_room_id = "healer_room"
            other_player.health = 1
            self.world.players[other_player.obj_id] = other_player

            self.player.current_region_id = "healer_region"
            self.player.current_room_id = "offroom"

            healer.behavior_type = "healer"
            healer.usable_spells = ["npc_heal_test"]
            healer.mana = 20
            healer.current_region_id = "healer_region"
            healer.current_room_id = "healer_room"
            self.world.add_npc(healer)

            start_health = other_player.health
            result = handle_ai(healer, self.world, time.time(), self.player)

            self.assertIsNotNone(result)
            self.assertIn("casts NPC Heal", result or "")
            self.assertGreater(other_player.health, start_health, "Healer should restore the co-located player's health.")
