# tests/singles/test_shared_kill_experience.py
"""Experience for a kill is shared by everyone who hurt the creature, in proportion to the damage.

However many players fought it, and whoever struck the last blow. NPC allies take a share of the
damage but earn no experience, so what they did is simply not paid out. Nobody who barely touched it
is a participant.
"""

import re
import unittest
from pathlib import Path

from engine.core import kill_credit
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from engine.utils.utils import calculate_xp_gain

from tests.fixtures import STORY_FIXTURE

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)


class _Table:
    """A server with `count` players standing together in front of one enemy."""

    def __init__(self, case, count, health=100, content="fantasy_frontier", template="goblin"):
        # A shared world, because the story set lets only its first player play.
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(STORY_FIXTURE if content == "story_fixture" else REPO_ROOT / "content_sets" / content),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        case.addCleanup(self.server.shutdown)
        self.world = self.server.world
        self.sessions, self.players = [], []
        self.events = []   # everything the server sent while the fight was fought
        for index in range(count):
            sid = self.server.create_session(player_id=f"hero{index}").session_id
            self.server.execute_command(sid, f"char create Hero{index}")
            player = self.server.get_player_for_session(sid)
            self.sessions.append(sid)
            self.players.append(player)
        self.place = (self.players[0].current_region_id, self.players[0].current_room_id)
        for player in self.players:
            player.current_region_id, player.current_room_id = self.place
        self.enemy = NPCFactory.create_npc_from_template(template, self.world, instance_id="shared_target")
        self.enemy.current_region_id, self.enemy.current_room_id = self.place
        self.enemy.health = self.enemy.max_health = health
        self.world.add_npc(self.enemy)

    def finish_it(self, session_id, name):
        """The player swings until the enemy is down (a swing can miss, and has a cooldown)."""
        for _ in range(40):
            self.events.extend(self.server.execute_command(session_id, f"attack {name}"))
            if not self.enemy.is_alive:
                self.events.extend(self.server.tick(session_id))
                return
            for _tick in range(60):
                self.events.extend(self.server.tick(session_id))

    def hurt(self, player, amount):
        kill_credit.record_damage(self.enemy, player, amount)

    def expected(self, player, share):
        return max(1, int(round(calculate_xp_gain(player.runtime_state.progression.level, self.enemy.level, self.enemy.max_health) * share)))


class TestTheTally(unittest.TestCase):
    def test_shares_are_each_players_part_of_all_the_damage(self):
        table = _Table(self, 3)
        a, b, c = table.players
        table.hurt(a, 50)
        table.hurt(b, 30)
        table.hurt(c, 20)
        shares = {player.name: share for player, share in kill_credit.player_shares(table.enemy)}
        self.assertAlmostEqual(0.5, shares["Hero0"])
        self.assertAlmostEqual(0.3, shares["Hero1"])
        self.assertAlmostEqual(0.2, shares["Hero2"])

    def test_an_allys_damage_takes_a_share_that_is_not_paid_out(self):
        table = _Table(self, 1, content="story_fixture", template="goblin_scout")
        kessa = next(n for n in table.world.npcs.values() if n.template_id == "captain_kessa")
        table.hurt(table.players[0], 60)
        kill_credit.record_damage(table.enemy, kessa, 40)
        shares = kill_credit.player_shares(table.enemy)
        self.assertEqual(1, len(shares))
        self.assertAlmostEqual(0.6, shares[0][1])

    def test_an_owned_creatures_blows_count_for_its_owner(self):
        table = _Table(self, 1)
        player = table.players[0]
        pet = NPCFactory.create_npc_from_template("goblin", table.world, instance_id="pet")
        pet.properties["owner_id"] = player.obj_id
        table.world.add_npc(pet)
        kill_credit.record_damage(table.enemy, pet, 25)
        table.hurt(player, 25)
        self.assertAlmostEqual(1.0, kill_credit.player_shares(table.enemy)[0][1])

    def test_a_graze_does_not_make_a_participant(self):
        table = _Table(self, 2)
        table.hurt(table.players[0], 97)
        table.hurt(table.players[1], 3)
        self.assertEqual(["Hero0"], [player.name for player, _ in kill_credit.player_shares(table.enemy)])

    def test_with_no_tally_the_killer_has_it_all(self):
        self.assertEqual(1.0, kill_credit.share_of(object(), []))


class TestWhoGetsWhat(unittest.TestCase):
    def test_a_kill_pays_each_participant_their_share_whoever_struck_last(self):
        table = _Table(self, 3)
        a, b, c = table.players
        table.hurt(a, 50)
        table.hurt(b, 30)
        table.enemy.health = 1
        before = [p.runtime_state.progression.experience for p in table.players]
        table.finish_it(table.sessions[2], "goblin")   # c lands the blow
        self.assertFalse(table.enemy.is_alive)
        gained = [p.runtime_state.progression.experience - b0 for p, b0 in zip(table.players, before)]
        # a and b are told, wherever they are (a message addressed to their own session); c's is in the kill's own text
        told = {ev["session_id"] for ev in table.events if ev["type"] == "text" and "for your part in defeating" in str(ev["payload"])}
        self.assertEqual({table.sessions[0], table.sessions[1]}, told)
        self.assertGreater(gained[1], 0, "the smaller share still earned something")
        self.assertGreater(gained[0], gained[1], "and the bigger share paid more")
        self.assertGreater(gained[2], 0, "and the one who finished it earned something too")

    def test_a_lone_player_still_gets_all_of_it(self):
        table = _Table(self, 1)
        player = table.players[0]
        table.enemy.health = 1
        before = player.runtime_state.progression.experience
        table.finish_it(table.sessions[0], "goblin")
        self.assertFalse(table.enemy.is_alive)
        full = calculate_xp_gain(1, table.enemy.level, table.enemy.max_health)
        self.assertGreaterEqual(player.runtime_state.progression.experience - before, full, "all of it (and the first-meeting bonus)")

    def test_someone_who_only_helped_is_told_when_an_ally_makes_the_kill(self):
        from engine.npcs.combat import try_attack

        table = _Table(self, 1, content="story_fixture", template="goblin_scout")
        player = table.players[0]
        kessa = next(n for n in table.world.npcs.values() if n.template_id == "captain_kessa")
        table.place = ("road", "castle_road")
        player.current_region_id, player.current_room_id = table.place
        table.enemy.current_region_id, table.enemy.current_room_id = table.place
        kessa.current_region_id, kessa.current_room_id = table.place
        table.hurt(player, 60)
        table.enemy.health = 1
        kessa.attack_power, kessa.attack_cooldown, kessa.combat_cooldown = 500, 0, 0
        kessa.combat_target, kessa.combat_targets = table.enemy, {table.enemy}
        before = player.runtime_state.progression.experience
        said = ""
        for step in range(40):
            said = try_attack(kessa, table.world, 9000.0 + step * 10) or ""
            if not table.enemy.is_alive:
                break
        self.assertFalse(table.enemy.is_alive)
        self.assertGreater(player.runtime_state.progression.experience, before, "their part earned them experience")
        self.assertIn("for your part in defeating", said, "the player watching is told in the kill's own message")
        self.assertEqual([], [text for who, text in table.world.pending_player_notices if who is player])


class TestMoneyIsSharedLikeExperience(unittest.TestCase):
    def test_the_gold_a_kill_drops_is_split_by_the_same_shares(self):
        table = _Table(self, 2)
        a, b = table.players
        for player in table.players:
            player.runtime_state.gold = 0
        table.enemy.loot_table = {"gold_value": {"chance": 1.0, "quantity": [100, 100]}}
        table.hurt(a, 75)
        table.hurt(b, 25)
        table.enemy.health = 1
        table.finish_it(table.sessions[1], "goblin")   # b lands the blow
        self.assertFalse(table.enemy.is_alive)
        # (the killing blow itself is a little damage on the tally too, hence the slack)
        self.assertAlmostEqual(75, a.runtime_state.gold, delta=2)
        self.assertAlmostEqual(25, b.runtime_state.gold, delta=2)


class TestTheSharingIsConfigurable(unittest.TestCase):
    def table_with(self, rules, players=3):
        table = _Table(self, players)
        original = table.world.ruleset_section
        table.world.ruleset_section = lambda name: {"experience_sharing": rules} if name == "combat" else original(name)
        return table

    def test_equal_pays_every_participant_the_same(self):
        table = self.table_with({"mode": "equal"})
        a, b, _c = table.players
        table.hurt(a, 80)
        table.hurt(b, 20)
        self.assertEqual([0.5, 0.5], sorted(share for _p, share in kill_credit.player_shares(table.enemy)))

    def test_killer_pays_the_killing_blow_everything_and_nobody_else_anything(self):
        table = self.table_with({"mode": "killer"})
        a, b, c = table.players
        table.hurt(a, 80)
        table.hurt(b, 20)
        self.assertEqual([], kill_credit.player_shares(table.enemy))
        self.assertEqual(1.0, kill_credit.share_of(c, [], table.world))
        table.enemy.health = 1
        before = [p.runtime_state.progression.experience for p in table.players]
        table.finish_it(table.sessions[2], "goblin")
        gained = [p.runtime_state.progression.experience - b0 for p, b0 in zip(table.players, before)]
        self.assertEqual([0, 0], gained[:2], "those who only helped earn nothing")
        self.assertGreater(gained[2], 0)

    def test_the_minimum_share_can_be_raised(self):
        table = self.table_with({"min_share": 0.4})
        a, b, c = table.players
        table.hurt(a, 50)
        table.hurt(b, 30)
        table.hurt(c, 20)
        self.assertEqual(["Hero0"], [player.name for player, _share in kill_credit.player_shares(table.enemy)])

    def test_nonsense_falls_back_to_the_defaults(self):
        table = self.table_with({"mode": "everyone", "min_share": "lots"})
        self.assertEqual(("proportional", kill_credit.MIN_SHARE), kill_credit.sharing_settings(table.world))


class TestTheValidator(unittest.TestCase):
    def setUp(self):
        import json
        import shutil
        import tempfile

        self.json = json
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def errors_with(self, sharing):
        from engine.server import content_set as validator

        path = self.package / "rules" / "ruleset.json"
        rules = self.json.loads(path.read_text(encoding="utf-8"))
        rules.setdefault("combat", {})["experience_sharing"] = sharing
        path.write_text(self.json.dumps(rules, indent=2), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [i.message for i in issues if i.severity == "error"]

    def test_good_settings_pass(self):
        for good in ({"mode": "equal"}, {"mode": "killer", "min_share": 0}, {"min_share": 0.25}, {}):
            self.assertEqual([], self.errors_with(good), good)

    def test_bad_settings_are_refused_with_what_would_work(self):
        self.assertTrue(any("proportional" in m and "mode" in m for m in self.errors_with({"mode": "fair"})))
        self.assertTrue(any("min_share" in m for m in self.errors_with({"min_share": 1})))
        self.assertTrue(any("min_share" in m for m in self.errors_with({"min_share": "most"})))
        self.assertTrue(any("is not read" in m for m in self.errors_with({"split": 2})))
        self.assertTrue(any("must be an object" in m for m in self.errors_with("equal")))


if __name__ == "__main__":
    unittest.main()
