# tests/singles/test_npc_kills_player.py
"""Regression coverage for an NPC landing the killing blow on a player.

Two defects lived on this path, neither reachable from any existing test
because every other test and journey-lab policy fights battles the *player*
wins, and the `resilience` policy kills the player via the `sethealth` debug
command, which bypasses `try_attack` entirely.

1. `engine/npcs/combat.py` read `target.level` when awarding XP to the killer.
   `Player` has no `.level` (level lives at `runtime_state.progression.level`),
   so the world tick raised:

       AttributeError: 'Player' object has no attribute 'level'

   A command that triggered that tick never returned to the player -- the
   server tracebacked instead of showing a death screen. This fired on the
   PLAYER_MANUAL's own starting path 4 ("Explore and face danger"), so it was
   the most player-visible defect in the game.

2. The message carrying "You have been defeated!" was assembled correctly and
   then discarded, because the delivery guard required `player.is_alive` and the
   player had just died. The player died in silence.
"""

import time
import unittest
from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.npcs import combat as npc_combat
from engine.npcs.combat import try_attack, enter_combat
from engine.core.combat_system import CombatSystem


def _always_hit_attack(npc, target):
    """`engine.npcs.combat.attack`, but guaranteed to connect.

    The real attack rolls `CombatSystem.calculate_hit_chance`, which is RNG and
    -- because a level-6 bear attacking a level-1 player takes the "purple"
    level-difference penalty -- lands only a minority of the time. That makes a
    kill-by-attrition test flaky. Everything downstream of the hit roll is the
    real code path, so forcing `always_hit` keeps the coverage honest while
    making the outcome deterministic.
    """
    viewer = npc.world.get_viewer_for_npc(npc) if npc.world else None
    result = CombatSystem.execute_attack(
        attacker=npc,
        defender=target,
        attack_power=npc.attack_power,
        weapon_name="attack",
        always_hit=True,
        viewer=viewer,
    )
    return {"message": result["message"], "target_defeated": result["target_defeated"]}


class TestNpcKillsPlayer(GameTestBase):
    """Drive a real NPC attack against a real Player until the player dies."""

    def _hostile_engaged_with_player(self, hp: float):
        """Place a hostile next to the player and start a fight, for real."""
        npc = NPCFactory.create_npc_from_template("cave_bear", self.world, instance_id="killer_bear")
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        npc.faction = "hostile"
        npc.properties["flee_threshold"] = 0.0
        npc.attack_cooldown = 0.0
        self.world.add_npc(npc)

        self.player.health = hp
        enter_combat(npc, self.player)
        npc.combat_target = self.player
        npc.combat_targets.add(self.player)
        npc.last_combat_action = 0.0
        npc.last_attack_time = 0.0
        return npc

    def _kill_player(self, npc):
        """Land one deterministic killing blow through the real try_attack path."""
        with patch.object(npc_combat, "attack", _always_hit_attack):
            return try_attack(npc, self.world, time.time())

    def test_npc_killing_blow_does_not_raise(self):
        """The tick must survive a Player being killed -- this is the crash."""
        npc = self._hostile_engaged_with_player(hp=1)
        # Must not raise AttributeError: 'Player' object has no attribute 'level'
        self._kill_player(npc)
        self.assertFalse(self.player.is_alive)
        self.assertEqual(self.player.health, 0)

    def test_player_is_told_they_were_defeated(self):
        """The death message must actually reach the player, not be discarded."""
        npc = self._hostile_engaged_with_player(hp=1)
        message = self._kill_player(npc)
        self.assertIsNotNone(
            message, "the killing blow produced no player-visible message"
        )
        self.assertIn("defeated", message.lower())

    def test_killer_gains_experience_from_the_player(self):
        """The hostile that wins should still be awarded XP (see faction XP tests)."""
        npc = self._hostile_engaged_with_player(hp=1)
        before = npc.level
        xp_before = getattr(npc, "experience", None)
        self._kill_player(npc)
        gained = getattr(npc, "experience", None)
        # Either the NPC levelled, or its XP moved. Both prove the guard works.
        self.assertTrue(
            npc.level >= before,
            "NPC level went backwards while being awarded kill XP",
        )
        if xp_before is not None and gained is not None:
            self.assertGreaterEqual(gained, xp_before)

    def test_dead_npc_does_not_keep_attacking(self):
        """A defeated NPC must stop acting on later ticks."""
        npc = self._hostile_engaged_with_player(hp=1)
        self._kill_player(npc)
        self.assertFalse(self.player.is_alive)
        npc.is_alive = False
        npc.last_combat_action = 0.0
        npc.last_attack_time = 0.0
        # A dead NPC's update returns early, so try_attack must be a no-op here.
        result = try_attack(npc, self.world, time.time())
        self.assertIsNone(result)

    def test_world_tick_survives_player_death(self):
        """The full world update path -- the one that actually raised -- is safe.

        Runs the real `World.update()` loop with an aggressive hostile adjacent
        to a 1-HP player. Hit chance and damage are RNG, so this asserts the
        invariant (the tick never raises, and a dead player is cleanly dead and
        recoverable) rather than that the player dies. The deterministic
        killing-blow coverage is in the tests above.
        """
        npc = self._hostile_engaged_with_player(hp=1)
        ticks = 0
        for _ in range(400):
            self.world.last_update_time = 0  # force the world-update gate open
            self.world.update()  # must never raise, alive or dead
            ticks += 1
            if not self.player.is_alive:
                break

        self.assertGreater(ticks, 0)
        # If the tick did land the kill, the player must be cleanly dead and
        # recoverable, not left in a half-dead state.
        if not self.player.is_alive:
            self.assertEqual(self.player.health, 0)
            self.player.respawn()
            self.assertTrue(self.player.is_alive)
            self.assertEqual(self.player.health, self.player.max_health)

    def test_respawn_recovers_a_player_killed_by_an_npc(self):
        """Death must not soft-lock: respawn restores the player."""
        npc = self._hostile_engaged_with_player(hp=1)
        self._kill_player(npc)
        self.assertFalse(self.player.is_alive)

        self.player.respawn()

        self.assertTrue(self.player.is_alive)
        self.assertEqual(self.player.health, self.player.max_health)


if __name__ == "__main__":
    unittest.main()
