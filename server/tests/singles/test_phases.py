# tests/singles/test_phases.py
"""A creature that changes state in a fight: `properties.phases` (engine/npcs/phases.py).

While in a fight it cycles through its phases; an `untouchable` phase cannot be hurt (a blow or an ability misses,
whatever it is) and may answer whoever tries with a `counter` ability that hits everyone in the room, at most once a
cooldown; the creature's friends do not strike at it then; and an NPC in the room can speak a hint at each change.
"""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.core.combat_system import CombatSystem
from engine.magic.effects import apply_spell_effect
from engine.magic.spell_registry import get_spell
from engine.npcs import companions, phases
from engine.npcs import combat as npc_combat
from engine.npcs.npc_factory import NPCFactory
from engine.server import content_set
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

PHASES = [
    {"name": "solid", "seconds": 10, "message": "It hardens.", "hint": {"npc": "captain_kessa", "text": "Now!"}},
    {"name": "mist", "seconds": 5, "untouchable": True, "message": "It thins to mist.",
     "miss_text": "The blow finds only mist in {defender}.", "counter": "fog_breath", "counter_cooldown": 4,
     "hint": {"npc": "captain_kessa", "text": "Hold!"}, "counter_hint": {"npc": "captain_kessa", "text": "Stop!"}},
]


class _Fight(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = "hazevale", "village_square"
        self.drake = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id="phased_probe")
        self.drake.current_region_id, self.drake.current_room_id = "hazevale", "village_square"
        self.drake.max_health = self.drake.health = 100000
        self.drake.properties["phases"] = json.loads(json.dumps(PHASES))
        self.world.add_npc(self.drake)
        npc_combat.enter_combat(self.drake, self.player)
        self.now = self.world.clock.now()

    def kessa(self):
        kessa = next(n for n in self.world.npcs.values() if n.template_id == "captain_kessa")
        kessa.current_region_id, kessa.current_room_id = "hazevale", "village_square"
        return kessa

    def advance(self, seconds):
        self.world.clock.advance(float(seconds))
        self.now = self.world.clock.now()
        return phases.update(self.drake, self.world, self.now)

    def to_mist(self):
        self.advance(0)          # starts the first phase
        self.advance(11)         # and it is over


class TestTheCycle(_Fight):
    def test_it_starts_solid_says_nothing_and_changes_when_the_phase_is_over(self):
        self.assertEqual([], self.advance(0))
        self.assertEqual("solid", phases.current(self.drake)["name"])
        self.assertEqual([], self.advance(9), "not yet")
        self.assertEqual(["It thins to mist."], self.advance(2))
        self.assertEqual("mist", phases.current(self.drake)["name"])
        self.assertEqual(["It hardens."], self.advance(6), "and round again")

    def test_out_of_a_fight_it_rests_in_the_first_phase_and_is_touchable(self):
        self.to_mist()
        self.assertTrue(phases.is_untouchable(self.drake))
        npc_combat.exit_combat(self.drake)
        self.assertEqual([], phases.update(self.drake, self.world, self.now))
        self.assertFalse(phases.is_untouchable(self.drake))
        npc_combat.enter_combat(self.drake, self.player)
        self.advance(0)
        self.assertEqual("solid", phases.current(self.drake)["name"], "a new fight starts from the first phase")

    def test_the_hint_is_spoken_by_someone_in_the_room_and_by_no_one_who_is_not(self):
        kessa = self.kessa()
        self.advance(0)
        lines = self.advance(11)
        self.assertEqual("It thins to mist.", lines[0])
        self.assertTrue([line for line in lines if "Captain Kessa shouts" in line and "Hold!" in line])
        kessa.current_region_id, kessa.current_room_id = "road", "castle_road"
        lines = self.advance(6)
        self.assertEqual(["It hardens."], lines, "Kessa is not here to say it")


class TestAnUntouchablePhase(_Fight):
    def swing(self, count=40):
        hits = 0
        for _ in range(count):
            result = CombatSystem.execute_attack(self.player, self.drake, 50, weapon_name="dark blade", viewer=self.player)
            hits += 1 if result["is_hit"] else 0
        return hits

    def test_in_the_solid_phase_a_blow_lands_as_usual(self):
        self.advance(0)
        self.assertGreater(self.swing(), 0)
        self.assertLess(self.drake.health, self.drake.max_health)

    def test_in_the_mist_a_blow_never_lands_however_many_are_struck(self):
        self.to_mist()
        before = self.drake.health
        self.assertEqual(0, self.swing(80))
        self.assertEqual(before, self.drake.health)

    def test_the_miss_is_told_in_the_phases_own_words(self):
        self.to_mist()
        result = CombatSystem.execute_attack(self.player, self.drake, 50, weapon_name="dark blade", viewer=self.player)
        self.assertTrue(result["message"].startswith("The blow finds only mist in "), result["message"][:80])

    def test_an_ability_that_would_damage_it_passes_through_too(self):
        self.to_mist()
        spell = get_spell("gloom_wave")
        before = self.drake.health
        _value, text = apply_spell_effect(self.player, self.drake, spell, self.player)
        self.assertEqual(before, self.drake.health)
        self.assertIn("passes straight through", text)


class TestTheCounter(_Fight):
    def test_trying_to_hit_it_in_the_mist_is_answered_on_everyone_in_the_room(self):
        self.kessa()
        companions.recruit(self.world, self.player, self.kessa())
        self.to_mist()
        self.player.health, self.kessa().health = 100, 50
        result = CombatSystem.execute_attack(self.player, self.drake, 50, weapon_name="dark blade", viewer=self.player)
        self.assertLess(self.player.health, 100, "the player is hit by the counter")
        self.assertLess(self.kessa().health, 50, "and so is Kessa: it hits everyone")
        self.assertIn("Stop!", result["message"], "and the hint is told with it")

    def test_a_party_swinging_together_is_answered_once_a_cooldown_not_every_time(self):
        self.to_mist()
        self.player.health = 1000
        CombatSystem.execute_attack(self.player, self.drake, 50, weapon_name="dark blade", viewer=self.player)
        after_one = self.player.health
        for _ in range(5):
            CombatSystem.execute_attack(self.player, self.drake, 50, weapon_name="dark blade", viewer=self.player)
        self.assertEqual(after_one, self.player.health, "no second counter inside the cooldown")
        self.world.clock.advance(5.0)
        CombatSystem.execute_attack(self.player, self.drake, 50, weapon_name="dark blade", viewer=self.player)
        self.assertLess(self.player.health, after_one, "and another once it is over")

    def test_not_attacking_costs_nothing(self):
        self.to_mist()
        self.player.health = 100
        self.advance(3)
        self.assertEqual(100, self.player.health)


class TestItsFriendsHoldBack(_Fight):
    def test_a_companion_does_not_strike_at_mist_and_does_again_when_it_hardens(self):
        kessa = self.kessa()
        companions.recruit(self.world, self.player, kessa)
        npc_combat.enter_combat(kessa, self.drake)
        kessa.combat_target = self.drake
        self.to_mist()
        self.assertIsNone(npc_combat.try_attack(kessa, self.world, self.now + 100.0), "she holds her blow")
        self.advance(6)
        self.assertFalse(phases.is_untouchable(self.drake))
        self.assertIsNotNone(npc_combat.try_attack(kessa, self.world, self.now + 200.0), "and strikes when it is solid")


class TestTheValidator(unittest.TestCase):
    def problems(self, phases_value, extra=None):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, package)
        path = package / "data" / "npcs" / "hostiles.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["goblin_scout"].setdefault("properties", {})["phases"] = phases_value
        path.write_text(json.dumps(data), encoding="utf-8")
        return [i.message for i in content_set.validate_content_set(package) if i.severity == "error"]

    def test_a_good_set_of_phases_is_accepted(self):
        self.assertEqual([], [m for m in self.problems(PHASES) if "phases" in m])

    def test_what_is_wrong_is_named(self):
        for bad, needle in (
            ([], "non-empty list"),
            ([{"name": "a"}], "seconds is required"),
            ([{"seconds": 5, "colour": "red"}], "colour is not read"),
            ([{"seconds": 5, "counter": "fog_breath"}], "only answers a blow struck at an untouchable phase"),
            ([{"seconds": 5, "untouchable": True, "counter": "no_such_spell"}], "does not define"),
            ([{"seconds": 5, "hint": {"npc": "nobody_at_all", "text": "x"}}], "not an NPC of this content set"),
            ([{"seconds": 5, "hint": {"npc": "captain_kessa"}}], "text is required"),
            ([{"seconds": 5, "counter_hint": {"npc": "captain_kessa", "text": "x"}}], "there is no counter"),
        ):
            found = self.problems(bad)
            self.assertTrue([m for m in found if needle in m], (bad, needle, found))


if __name__ == "__main__":
    unittest.main()
