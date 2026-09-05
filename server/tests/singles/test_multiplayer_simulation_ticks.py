import time
import unittest
from unittest.mock import patch

from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell
from engine.npcs.npc_factory import NPCFactory
from engine.player.core import Player
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER
from engine.world.region import Region
from engine.world.room import Room


class TestMultiplayerSimulationTicks(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True)

        self.session_a = self.server.create_session(player_id="tick_player_a")
        self.session_b = self.server.create_session(player_id="tick_player_b")
        self.session_c = self.server.create_session(player_id="tick_player_c")
        for session in (self.session_a, self.session_b, self.session_c):
            self.server.mark_session_connected(session.session_id)

        self.server.execute_command(self.session_a.session_id, "char create TickA")
        self.server.execute_command(self.session_b.session_id, "char create TickB")
        self.server.execute_command(self.session_c.session_id, "char create TickC")

        self.player_a = self.server.get_player_for_session(self.session_a.session_id)
        self.player_b = self.server.get_player_for_session(self.session_b.session_id)
        self.player_c = self.server.get_player_for_session(self.session_c.session_id)
        assert self.player_a is not None
        assert self.player_b is not None
        assert self.player_c is not None

        region = Region("Tick Region", "Isolated multiplayer tick test.", obj_id="tick_region")
        shared_room = Room("Shared Room", "A controlled multiplayer room.", obj_id="shared_room")
        offroom = Room("Offroom", "A disconnected observer room.", obj_id="offroom")
        shared_room.exits["east"] = "offroom"
        offroom.exits["west"] = "shared_room"
        region.add_room("shared_room", shared_room)
        region.add_room("offroom", offroom)
        self.server.world.add_region("tick_region", region)

        self.player_a.current_region_id = "tick_region"
        self.player_a.current_room_id = "shared_room"
        self.player_b.current_region_id = "tick_region"
        self.player_b.current_room_id = "shared_room"
        self.player_c.current_region_id = "tick_region"
        self.player_c.current_room_id = "offroom"
        self.server.world.player = self.player_c

    def tearDown(self) -> None:
        self.server.shutdown()

    def _force_tick(self) -> list[tuple]:
        self.server.world.last_update_time = 0.0
        return self.server.world.update()

    def test_world_update_hostile_targets_colocated_player_when_legacy_player_elsewhere(self) -> None:
        self.server.world.npc_templates["tick_hostile"] = {
            "name": "Tick Hostile",
            "faction": "hostile",
            "level": 1,
            "health": 10,
            "properties": {"aggression": 1.0},
        }
        hostile = NPCFactory.create_npc_from_template("tick_hostile", self.server.world)
        self.assertIsNotNone(hostile)
        if hostile is None:
            return

        hostile.current_region_id = "tick_region"
        hostile.current_room_id = "shared_room"
        self.server.world.add_npc(hostile)

        with patch("engine.npcs.ai.combat_logic.random.choice", side_effect=lambda seq: seq[0]), patch(
            "engine.npcs.ai.combat_logic.random.random", return_value=0.0
        ):
            self._force_tick()

        self.assertTrue(hostile.in_combat)
        self.assertIn(self.player_a, hostile.combat_targets)
        self.assertNotIn(self.player_c, hostile.combat_targets)

    def test_world_update_healer_supports_other_player_in_room(self) -> None:
        heal_spell = Spell(
            spell_id="tick_heal",
            name="Tick Heal",
            description="Restores health.",
            mana_cost=5,
            cooldown=0.0,
            effects=[{"type": "heal", "value": 20}],
            target_type="friendly",
            level_required=1,
            cast_message="{caster_name} casts {spell_name}!",
        )
        register_spell(heal_spell)

        healer = NPCFactory.create_npc_from_template("wandering_mage", self.server.world)
        self.assertIsNotNone(healer)
        if healer is None:
            return

        healer.behavior_type = "healer"
        healer.usable_spells = ["tick_heal"]
        healer.mana = 20
        healer.current_region_id = "tick_region"
        healer.current_room_id = "shared_room"
        self.server.world.add_npc(healer)

        self.player_b.health = 1
        start_health = self.player_b.health

        messages = self._force_tick()

        self.assertGreater(self.player_b.health, start_health)
        self.assertTrue(any("casts Tick Heal" in message for _location, message in messages))

    @patch("engine.npcs.combat.random.random", return_value=0.0)
    def test_world_update_minion_kill_credit_routes_to_owner_not_room_viewer(self, _mock_random) -> None:
        minion = NPCFactory.create_npc_from_template("skeleton_minion", self.server.world)
        target = NPCFactory.create_npc_from_template("giant_rat", self.server.world)
        self.assertIsNotNone(minion)
        self.assertIsNotNone(target)
        if minion is None or target is None:
            return

        self.player_a.current_room_id = "offroom"
        self.player_b.current_room_id = "shared_room"

        minion.current_region_id = "tick_region"
        minion.current_room_id = "shared_room"
        minion.properties["owner_id"] = self.player_a.obj_id
        target.current_region_id = "tick_region"
        target.current_room_id = "shared_room"
        target.health = 1

        self.server.world.add_npc(minion)
        self.server.world.add_npc(target)
        minion.enter_combat(target)
        minion.combat_cooldown = 0.0
        minion.attack_cooldown = 0.0
        minion.last_attack_time = 0.0
        minion.last_combat_action = 0.0

        start_owner_xp = self.player_a.runtime_state.progression.experience
        start_viewer_xp = self.player_b.runtime_state.progression.experience

        self._force_tick()

        self.assertFalse(target.is_alive)
        self.assertGreater(self.player_a.runtime_state.progression.experience, start_owner_xp)
        self.assertEqual(start_viewer_xp, self.player_b.runtime_state.progression.experience)


if __name__ == "__main__":
    unittest.main()
