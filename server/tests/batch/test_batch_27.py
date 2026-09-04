# tests/batch/test_batch_27.py
import time
from unittest.mock import patch
from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.items.resource_node import ResourceNode
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.world.region import Region
from engine.world.room import Room

class TestBatch27(GameTestBase):
    """Focus: Reputation, AoE, and Gathering."""

    def _setup_isolated_room(self):
        """Helper to create a clean room with no default NPCs."""
        region = Region("Test Region", "x", obj_id="test_region")
        room = Room("Arena", "Empty.", obj_id="arena")
        region.add_room("arena", room)
        self.world.add_region("test_region", region)
        
        # Move player there
        self.player.current_region_id = "test_region"
        self.player.current_room_id = "arena"
        self.world.current_region_id = "test_region"
        self.world.current_room_id = "arena"
        return "test_region", "arena"

    def test_reputation_hostility(self):
        """Verify high reputation makes hostile faction neutral."""
        # Setup clean room so Bandit doesn't attack guards
        self._setup_isolated_room()

        bandit = NPCFactory.create_npc_from_template("bandit", self.world)
        if not bandit: return
        self.world.add_npc(bandit)
        
        # Sync location
        bandit.current_region_id = self.player.current_region_id
        bandit.current_room_id = self.player.current_room_id
        
        # 1. Check Default Relation (-100)
        from engine.npcs.combat import get_relation_to
        rel_default = get_relation_to(bandit, self.player)
        self.assertEqual(rel_default, -100)
        
        # 2. Increase Rep
        self.player.reputation["hostile"] = 100 # Neutralize hatred
        
        # 3. Check New Relation (0)
        rel_new = get_relation_to(bandit, self.player)
        self.assertEqual(rel_new, 0)
        
        # 4. Verify AI doesn't attack (Player is the only target in the isolated room)
        from engine.npcs.ai.combat_logic import scan_for_targets
        msg = scan_for_targets(bandit, self.world, self.player)
        self.assertIsNone(msg, f"Bandit attacked despite neutral rep: {msg}")

    def test_aoe_spell_targeting(self):
        """Verify AoE spell hits enemies but ignores friends."""
        self._setup_isolated_room()

        # 1. Setup Spell
        aoe = Spell("firestorm", "Fire", "x", effects=[{"type": "damage", "value": 10}], target_type="all_enemies")
        register_spell(aoe)
        assert self.player.runtime_state.magic is not None
        self.player.runtime_state.magic.known_spells.add("firestorm")
        
        # 2. Setup NPCs
        goblin = NPCFactory.create_npc_from_template("goblin", self.world) # Hostile
        villager = NPCFactory.create_npc_from_template("wandering_villager", self.world) # Friendly
        
        if goblin and villager:
            loc = (self.player.current_region_id, self.player.current_room_id)
            goblin.current_region_id, goblin.current_room_id = loc
            villager.current_region_id, villager.current_room_id = loc
            
            self.world.add_npc(goblin)
            self.world.add_npc(villager)
            
            g_health = goblin.health
            v_health = villager.health
            
            # 3. Cast
            res = self.player.cast_spell(aoe, None, time.time(), self.world)
            self.assertTrue(res["success"])
            
            # 4. Assertions
            self.assertLess(goblin.health, g_health, "Goblin should be hit")
            self.assertEqual(villager.health, v_health, "Villager should be safe")

    def test_gathering_mechanic(self):
        """Verify gathering requires tool and yields item."""
        self._setup_isolated_room()

        # 1. Setup Node
        self.world.item_templates["ore_node"] = {
            "type": "ResourceNode", "name": "Iron Vein",
            "properties": {"resource_item_id": "item_iron_ingot", "tool_required": "pickaxe", "charges": 1}
        }
        node = ItemFactory.create_item_from_template("ore_node", self.world)
        
        # 2. Setup Tool
        self.world.item_templates["pick"] = {"type": "Item", "name": "Pickaxe", "properties": {"tool_type": "pickaxe"}}
        pick = ItemFactory.create_item_from_template("pick", self.world)
        
        if node and pick:
             if self.player.current_region_id and self.player.current_room_id:
                 self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, node)
                 
                 # Try without tool
                 res_fail = self.game.process_command("gather Iron Vein")
                 self.assertIsNotNone(res_fail)
                 if res_fail:
                    self.assertIn("need a pickaxe", res_fail)
                 
                 # Add tool
                 self.player.inventory.add_item(pick)
                 
                 # Try with tool
                 res_success = self.game.process_command("gather Iron Vein")
                 self.assertIsNotNone(res_success)
                 if res_success:
                    self.assertIn("You gather iron ingot", res_success)
                 self.assertEqual(self.player.inventory.count_item("item_iron_ingot"), 1)
                 
                 # Check depletion
                 self.assertEqual(node.get_property("charges"), 0)

    def test_gather_depleted_node(self):
        """Verify gathering fails on depleted node."""
        self._setup_isolated_room()

        node = ResourceNode("test_node", "Node", charges=0, tool_required="hand")
        if node:
             if self.player.current_region_id and self.player.current_room_id:
                 self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, node)
                 
                 # Mock tool presence (hand)
                 self.world.item_templates["hand"] = {"type": "Item", "name": "Hand", "properties": {"tool_type": "hand"}}
                 hand = ItemFactory.create_item_from_template("hand", self.world)
                 if hand: self.player.inventory.add_item(hand)
                 
                 res = self.game.process_command("gather Node")
                 self.assertIsNotNone(res)
                 if res:
                    self.assertIn("depleted", res)

    def test_npc_schedule_aggression_override(self):
        """Verify NPC becomes aggressive during specific schedule time."""
        # Use isolated room to ensure clean combat scanning
        rid, rmid = self._setup_isolated_room()

        npc = NPCFactory.create_npc_from_template("wandering_villager", self.world)
        self.assertIsNotNone(npc, "Failed to create villager")
        if not npc: return
        
        npc.faction = "friendly"
        npc.behavior_type = "scheduled"
        
        # Schedule with override
        npc.schedule = {
            "12": {
                "region_id": rid, 
                "room_id": rmid,
                "activity": "hunting",
                "behavior_override": "aggressive"
            }
        }
        
        npc.current_region_id = rid
        npc.current_room_id = rmid
        
        self.world.add_npc(npc)
        
        # Setup Goblin
        goblin = NPCFactory.create_npc_from_template("goblin", self.world)
        self.assertIsNotNone(goblin, "Failed to create goblin")
        
        if goblin:
            goblin.current_region_id = rid
            goblin.current_room_id = rmid
            goblin.is_alive = True
            self.world.add_npc(goblin)
            
            # Ensure goblin is hostile
            self.assertEqual(goblin.faction, "hostile")
            
            # Verify hostility logic
            from engine.npcs.combat import is_hostile_to
            self.assertTrue(is_hostile_to(npc, goblin), "Villager should consider Goblin hostile")
            
            # Time 12:00
            self.game.time_manager.hour = 12
            
            # Run AI
            from engine.npcs.ai.dispatcher import handle_ai
            
            # Force RNG to 0.0 to ensure attack roll passes inside scan_for_targets
            with patch('random.random', return_value=0.0):
                handle_ai(npc, self.world, time.time(), self.player)
            
            # Assert combat started
            self.assertTrue(npc.in_combat, "Villager should attack hostile while on 'aggressive' schedule override")
            self.assertIn(goblin, npc.combat_targets)
