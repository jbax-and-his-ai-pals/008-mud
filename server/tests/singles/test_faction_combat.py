# tests/singles/test_faction_combat.py
import time
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs.ai import scan_for_targets
from engine.player.core import Player
from engine.world.region import Region
from engine.world.room import Room

class TestFactionCombat(GameTestBase):

    def setUp(self):
        super().setUp()
        # Setup templates
        self.world.npc_templates["hostile_mob"] = {
            "name": "Hostile", "faction": "hostile", "level": 1, "health": 10,
            "properties": {"aggression": 1.0}
        }
        self.world.npc_templates["friendly_mob"] = {
            "name": "Friendly", "faction": "friendly", "level": 1, "health": 10
        }

    def test_minion_targets_hostile(self):
        """Verify a player's minion proactively attacks hostiles in the room."""
        # 1. Create Hostile and Minion
        hostile = NPCFactory.create_npc_from_template("hostile_mob", self.world)
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.world)
        
        if hostile and minion:
            hostile.current_region_id = "town"; hostile.current_room_id = "town_square"
            minion.current_region_id = "town"; minion.current_room_id = "town_square"
            minion.properties["owner_id"] = self.player.obj_id
            
            self.world.add_npc(hostile)
            self.world.add_npc(minion)
            
            # 2. Update Minion AI
            from engine.npcs.ai.specialized import perform_minion_logic
            perform_minion_logic(minion, self.world, time.time(), self.player)
            
            # 3. Assert: Minion should have entered combat with the hostile
            self.assertTrue(minion.in_combat)
            self.assertIn(hostile, minion.combat_targets)

    def test_hostile_ignores_friendly_if_aggression_low(self):
        """Verify hostiles prioritize targets based on aggression settings."""
        hostile = NPCFactory.create_npc_from_template("hostile_mob", self.world)
        friendly = NPCFactory.create_npc_from_template("friendly_mob", self.world)
        
        if hostile and friendly:
            hostile.current_region_id = "town"; hostile.current_room_id = "town_square"
            friendly.current_region_id = "town"; friendly.current_room_id = "town_square"
            hostile.aggression = 0.0 # Will not initiate combat
            
            self.world.add_npc(hostile)
            self.world.add_npc(friendly)
            
            scan_for_targets(hostile, self.world, self.player)
            self.assertFalse(hostile.in_combat, "Hostile with 0 aggression should not start a fight.")

    def test_hostile_scans_all_players_in_room_not_just_passed_viewer(self):
        """Verify proactive targeting can find another co-located player in multiplayer."""
        hostile = NPCFactory.create_npc_from_template("hostile_mob", self.world)

        if hostile:
            region = Region("Scan Region", "Isolated scan test.", obj_id="scan_region")
            room = Room("Scan Room", "Only players and the hostile are here.", obj_id="scan_room")
            region.add_room("scan_room", room)
            self.world.add_region("scan_region", region)

            other_player = Player("OffRoomViewer", obj_id="offroom_viewer", world=self.world)
            other_player.world = self.world
            other_player.current_region_id = "scan_region"
            other_player.current_room_id = "offroom"
            self.world.players[other_player.obj_id] = other_player

            self.player.current_region_id = "scan_region"
            self.player.current_room_id = "scan_room"

            hostile.current_region_id = "scan_region"
            hostile.current_room_id = "scan_room"
            hostile.aggression = 1.0
            self.world.add_npc(hostile)

            scan_for_targets(hostile, self.world, other_player)

            self.assertTrue(hostile.in_combat, "Hostile should engage a co-located player.")
            self.assertIn(self.player, hostile.combat_targets)
