# tests/singles/test_companion_recovery.py
"""A companion that falls back hurt rests, stays out of fights, and comes back to the player once it is well.

Before this, a companion that fled a fight dropped out of the story silently: it stood where it ended up, was drawn
straight back into the next fight at the same low health, and told the player nothing. Now it is *recovering*: it
says so when it falls back, rests wherever it is, and rejoins (walking to find the player if it has to) when it is back
to `rejoin_health` of its health and the player is not fighting. A conversation can tell the two states apart
(`companion_recovering`), and `companions` and the sheet say so.
"""

import re
import unittest

from engine import conditions
from engine.npcs import companions
from engine.npcs import ai as npc_ai
from engine.npcs.ai.combat_logic import try_flee
from engine.npcs.npc_factory import NPCFactory
from tests.fixtures import GameTestBase

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class _Hurt(GameTestBase):
    def setUp(self):
        super().setUp()
        self.companion = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="the_companion")
        self.world.add_npc(self.companion)
        self.companion.name = "Brannoc"
        self.companion.properties.pop("essential", None)
        self.companion.current_region_id, self.companion.current_room_id = self.player.current_region_id, self.player.current_room_id
        companions.recruit(self.world, self.player, self.companion)
        self.companion.health = max(1, int(self.companion.max_health * 0.1))

    def fall_back(self):
        return try_flee(self.companion, self.world, self.player)

    def owner_fights(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="a_goblin")
        self.world.add_npc(goblin)
        goblin.current_region_id, goblin.current_room_id = self.player.current_region_id, self.player.current_room_id
        self.player.enter_combat(goblin)
        return goblin


class TestFallingBack(_Hurt):
    def test_a_hurt_companion_says_so_and_is_recovering(self):
        said = _MARKUP.sub("", self.fall_back() or "")
        self.assertRegex(said, r"Brannoc.* falls back")
        self.assertIn("will rejoin you once recovered", said)
        self.assertTrue(companions.is_recovering(self.companion))
        self.assertNotEqual(self.player.current_room_id, self.companion.current_room_id, "and it has gone")

    def test_a_creature_that_is_not_a_companion_just_flees(self):
        goblin = NPCFactory.create_npc_from_template("goblin", self.world, instance_id="runner")
        self.world.add_npc(goblin)
        goblin.current_region_id, goblin.current_room_id = self.player.current_region_id, self.player.current_room_id
        said = _MARKUP.sub("", try_flee(goblin, self.world, self.player) or "")
        self.assertIn("flees", said)
        self.assertFalse(companions.is_recovering(goblin))


class TestRecovering(_Hurt):
    def test_it_keeps_out_of_the_players_fights_while_it_rests(self):
        self.fall_back()
        self.companion.current_room_id = self.player.current_room_id   # beside the player again
        self.owner_fights()
        npc_ai.handle_ai(self.companion, self.world, self.world.clock.now(), self.player)
        self.assertFalse(self.companion.in_combat, "it does not join the fight")

    def test_it_is_left_behind_when_the_player_moves_on_and_comes_to_find_them(self):
        self.fall_back()
        self.companion.current_region_id, self.companion.current_room_id = self.player.current_region_id, self.player.current_room_id
        here = (self.player.current_region_id, self.player.current_room_id)
        moved = companions.travel_with(self.world, self.player, *here)
        self.assertEqual([], moved, "a recovering companion does not tag along")

    def test_it_rejoins_once_well_enough_and_says_so(self):
        self.fall_back()
        self.companion.current_region_id, self.companion.current_room_id = self.player.current_region_id, self.player.current_room_id
        now = self.world.clock.now()
        self.assertIsNone(companions.recovery_step(self.companion, self.world, now, self.player))
        self.assertTrue(companions.is_recovering(self.companion), "still too hurt")
        self.companion.health = int(self.companion.max_health * 0.7)
        told = companions.recovery_step(self.companion, self.world, now, self.player)
        self.assertIn("has recovered and rejoins you", told)
        self.assertFalse(companions.is_recovering(self.companion))

    def test_one_elsewhere_sends_word_that_it_is_coming(self):
        self.fall_back()
        self.assertNotEqual(self.player.current_room_id, self.companion.current_room_id)
        self.companion.health = self.companion.max_health
        self.assertIsNone(companions.recovery_step(self.companion, self.world, self.world.clock.now(), self.player))
        notes = [text for who, text in self.world.pending_player_notices if who is self.player]
        self.assertTrue([n for n in notes if "has recovered and is coming to find you" in n], notes)
        self.assertFalse(companions.is_recovering(self.companion))

    def test_it_does_not_rejoin_in_the_middle_of_the_players_fight(self):
        self.fall_back()
        self.companion.health = self.companion.max_health
        self.owner_fights()
        companions.recovery_step(self.companion, self.world, self.world.clock.now(), self.player)
        self.assertTrue(companions.is_recovering(self.companion))

    def test_the_threshold_can_be_set_on_the_template(self):
        self.fall_back()
        self.companion.properties["rejoin_health"] = 0.9
        self.companion.health = int(self.companion.max_health * 0.7)
        companions.recovery_step(self.companion, self.world, self.world.clock.now(), self.player)
        self.assertTrue(companions.is_recovering(self.companion))

    def test_resting_heals_it_wherever_it_is(self):
        self.fall_back()
        before = self.companion.health
        self.companion.last_regen_time = 0
        companions.recovery_step(self.companion, self.world, self.world.clock.now() + 10_000, self.player)
        self.assertGreater(self.companion.health, before)


class TestWhatThePlayerCanSee(_Hurt):
    def test_a_conversation_can_tell_recovering_from_well(self):
        well = {"kind": "companion_recovering", "npc_id": "village_elder"}
        self.assertFalse(conditions.evaluate(well, self.player).satisfied)
        self.fall_back()
        self.assertTrue(conditions.evaluate(well, self.player).satisfied)
        self.assertTrue(conditions.evaluate({"kind": "companion_recovering"}, self.player).satisfied, "or any companion")

    def test_the_list_and_the_sheet_say_so(self):
        self.fall_back()
        self.companion.current_region_id, self.companion.current_room_id = self.player.current_region_id, self.player.current_room_id
        self.assertIn("recovering", _MARKUP.sub("", self.game.process_command("companions")))
        self.assertIn("Recovering: resting until health is back to 60%", _MARKUP.sub("", self.game.process_command("companions Brannoc")))


if __name__ == "__main__":
    unittest.main()
