# tests/singles/test_story_beats.py
"""The small things that make a story beat read right.

* Essential characters cannot be killed (unless recruited), and a creature felled by another is
  announced.
* A kill's text: experience, then money, as one spaced group; what dropped; then the story, and the
  scene's own words come before the quest update.
* A quest can close on narration (plain) as well as on dialogue (quoted).
* A conversation never ends on a reply that only says goodbye, the mayor's included.
"""

import re
import unittest
from pathlib import Path

from engine.core.quests.closing import closing_text
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)


def _plain(text):
    return _MARKUP.sub("", text)


class _Game:
    def __init__(self, case):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "ff4_slice"),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        case.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="beats").session_id
        self.server.execute_command(self.sid, "char create Cecil")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world

    def say(self, command):
        events = self.server.execute_command(self.sid, command)
        return NL.join(_plain(str(e["payload"])) for e in events if e["type"] == "text")

    def npc(self, template_id):
        return next(n for n in self.world.npcs.values() if n.template_id == template_id)


class TestEssentialCharacters(unittest.TestCase):
    def test_an_essential_character_is_left_on_the_brink_not_killed(self):
        game = _Game(self)
        kessa = game.npc("captain_kessa")
        self.assertIs(True, kessa.properties.get("essential"))
        kessa.take_damage(10_000, "physical")
        self.assertTrue(kessa.is_alive)
        self.assertEqual(1, kessa.health)

    def test_once_recruited_she_can_fall_like_anyone(self):
        game = _Game(self)
        kessa = game.npc("captain_kessa")
        kessa.properties["companion"] = True
        kessa.take_damage(10_000, "physical")
        self.assertFalse(kessa.is_alive)

    def test_an_ordinary_character_can_be_killed(self):
        game = _Game(self)
        guard = game.npc("castle_guard")
        self.assertNotIn("essential", guard.properties)
        guard.take_damage(10_000, "physical")
        self.assertFalse(guard.is_alive)

    def test_the_mayor_and_the_king_are_essential_too(self):
        game = _Game(self)
        for template in ("mayor_of_mistvale", "king_aldous"):
            self.assertIs(True, game.npc(template).properties.get("essential"), template)

    def test_a_creature_felled_by_another_is_announced_once(self):
        from engine.npcs.combat import try_attack

        game = _Game(self)
        game.player.current_region_id, game.player.current_room_id = "varenholt", "courtyard"
        guard = [n for n in game.world.npcs.values() if n.template_id == "castle_guard"][0]
        guard.health = 1
        wolf = NPCFactory.create_npc_from_template("road_wolf", game.world, instance_id="slayer")
        wolf.current_region_id, wolf.current_room_id = "varenholt", "courtyard"
        game.world.add_npc(wolf)
        wolf.combat_target = guard
        wolf.combat_targets = {guard}
        wolf.combat_cooldown = 0
        wolf.attack_cooldown = 0
        said = ""
        for step in range(50):
            said = try_attack(wolf, game.world, 1000.0 + step * 10) or ""
            if not guard.is_alive:
                break
        self.assertFalse(guard.is_alive)
        self.assertIn("defeated", _plain(said))
        self.assertNotIn("falls.", _plain(said), "the kill is announced once, not twice")


class TestWhatAKillSays(unittest.TestCase):
    def test_experience_then_gil_as_a_spaced_group_under_the_blow(self):
        game = _Game(self)
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        goblin = game.npc("goblin_scout")
        goblin.health = 1
        for _ in range(40):
            game.server.tick(game.sid)
        said = game.say("cast dark wave")
        self.assertRegex(said, r"\n\nYou gain \d+ experience!\nYou find \d+ gil\.(\n\n|$)")

    def test_the_scene_speaks_before_the_quest_update_and_each_is_a_paragraph(self):
        game = _Game(self)
        game.world.quest_manager.handle_npc_killed = lambda event, data: "QUEST UPDATE"
        game.world.trigger_runner.fire_npc_killed = lambda player, npc: ["THE SCENE"]
        said = game.world.dispatch_event("npc_killed", {"player": game.player, "npc": game.npc("goblin_scout")})
        paragraphs = _plain(said).split(NL + NL)
        self.assertEqual(["THE SCENE", "QUEST UPDATE"], paragraphs[:2])


class TestTheDrakeFight(unittest.TestCase):
    def test_falling_says_how_to_get_up(self):
        from engine.npcs.combat import try_attack

        game = _Game(self)
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        game.player.health = 1
        wolf = NPCFactory.create_npc_from_template("road_wolf", game.world, instance_id="finisher")
        wolf.current_region_id, wolf.current_room_id = "road", "castle_road"
        game.world.add_npc(wolf)
        wolf.combat_target = game.player
        wolf.combat_targets = {game.player}
        wolf.combat_cooldown = 0
        wolf.attack_cooldown = 0
        said = ""
        for step in range(60):
            said = try_attack(wolf, game.world, 1000.0 + step * 10) or ""
            if not game.player.is_alive:
                break
        self.assertFalse(game.player.is_alive)
        self.assertIn("You have been defeated!", _plain(said))
        self.assertIn("Type 'respawn' to rise again at", _plain(said))

    def test_everyone_in_the_square_can_hurt_the_drake_but_not_end_it(self):
        from engine.npcs.combat import attack

        game = _Game(self)
        drake = NPCFactory.create_npc_from_template("fog_drake", game.world, instance_id="test_drake")
        drake.current_region_id, drake.current_room_id = "mistvale", "village_square"
        game.world.add_npc(drake)
        allies = [game.npc("captain_kessa"), game.npc("innkeeper"), game.npc("mayor_of_mistvale")]
        for ally in allies:
            ally.current_region_id, ally.current_room_id = "mistvale", "village_square"
        start = drake.health
        for _round in range(12):
            for ally in allies:
                attack(ally, drake)
        self.assertLess(drake.health, start, "they land blows")
        self.assertGreater(drake.health, 0, "twelve rounds of the town alone does not kill it: someone has to")

    def test_if_kessa_kills_the_drake_it_counts_for_the_player(self):
        from engine.npcs.combat import try_attack

        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        game.say("give sealed package to mayor")
        for _ in range(20):   # the drake's arrival is drawn out over a few seconds
            game.world.clock.advance(1.0)
            game.server.tick(game.sid)
        drake = game.npc("fog_drake")
        kessa = game.npc("captain_kessa")
        kessa.current_region_id, kessa.current_room_id = "mistvale", "village_square"
        kessa.attack_power = 500
        kessa.attack_cooldown = 0
        kessa.combat_cooldown = 0
        from engine.core import kill_credit
        kill_credit.record_damage(drake, game.player, 60)   # the player did most of the work before she finished it
        gold_before = game.player.runtime_state.gold
        drake.health = 1
        kessa.combat_target = drake
        kessa.combat_targets = {drake}
        said = ""
        for step in range(40):
            said = try_attack(kessa, game.world, 5000.0 + step * 10) or ""
            if not drake.is_alive:
                break
        self.assertFalse(drake.is_alive)
        self.assertTrue(game.player.flags.get("drake_slain"), "the scene that follows the drake's death ran")
        text = _plain(said)
        self.assertIn("Objective complete", text, "and so did the quest")
        self.assertLess(text.index("You gain"), text.index("[Quest Update]"), "experience comes before the quest update")
        self.assertIn("You find", text, "the drake's gil is shared too")
        self.assertGreater(game.player.runtime_state.gold, gold_before)
        self.assertNotIn("Report back to Ryn", text, "the player has not met Ryn")
        self.assertIn("The mayor will know where to send you next.", text)
        self.assertNotIn("cave", text, "the fight is in the square")

    def test_none_of_them_can_be_killed_by_it(self):
        game = _Game(self)
        for template in ("captain_kessa", "innkeeper", "mayor_of_mistvale"):
            npc = game.npc(template)
            npc.take_damage(10_000, "physical")
            self.assertTrue(npc.is_alive, template)


class TestAQuestCanCloseOnNarration(unittest.TestCase):
    def test_narration_is_plain_and_speech_is_quoted(self):
        narrated = {"stages": [{"completion_narration": "The door hums."}], "current_stage_index": 0}
        spoken = {"stages": [{"completion_dialogue": "Well done."}], "current_stage_index": 0}
        both = {"stages": [{"completion_narration": "The door hums.", "completion_dialogue": "Well done."}], "current_stage_index": 0}
        self.assertEqual("The door hums.", _plain(closing_text(narrated, "Thanks")))
        self.assertEqual('"Well done."', _plain(closing_text(spoken)))
        self.assertEqual('The door hums.' + NL + '"Well done."', _plain(closing_text(both)))
        self.assertEqual('"Thanks"', _plain(closing_text({"stages": [{}], "current_stage_index": 0}, "Thanks")))

    def test_handing_over_the_package_is_not_a_quotation(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        said = game.say("give sealed package to mayor")
        self.assertIn("something in it begins to hum", said)
        self.assertNotIn('"The mayor takes the package', said)


class TestHandingOverThePackage(unittest.TestCase):
    def deliver(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        game.server.execute_command(game.sid, "give sealed package to mayor")
        return game

    def raw(self, game, command):
        events = game.server.execute_command(game.sid, command)
        return NL.join(str(e["payload"]) for e in events if e["type"] == "text")

    def test_the_level_it_brings_is_shown_with_its_stat_gains_and_not_typed_out(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        text = self.raw(game, "give sealed package to mayor")
        self.assertIn("You have reached level 2!", text)
        self.assertIn("Stats Increased", text)
        # the story is paced; the numbers are not (they are a paragraph of their own)
        paced = re.findall(r"\[\[PACE:\d+\]\](.*?)\[\[/PACE\]\]", text, re.S)
        self.assertTrue(paced)
        self.assertFalse(any("Stats Increased" in block or "Rewards:" in block for block in paced))

    def test_the_package_was_not_a_gift_arrives_slowly_as_its_own_paragraph(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        text = self.raw(game, "give sealed package to mayor")
        self.assertIn("[[PACE:40]]The package was not a gift.[[/PACE]]", text)
        self.assertIn(NL + NL + "[[PACE:40]]", text)

    def test_the_drake_comes_after_a_few_told_beats_a_moment_apart(self):
        game = _Game(self)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        game.server.execute_command(game.sid, "give sealed package to mayor")
        self.assertFalse([n for n in game.world.npcs.values() if n.template_id == "fog_drake"], "not yet")
        told = []
        for _ in range(12):
            game.world.clock.advance(1.0)
            events = game.server.tick(game.sid) + game.server._flush_background_batch(game.sid)   # as the transports do
            told += [str(e["payload"]) for e in events if e["type"] == "text"]
            if [n for n in game.world.npcs.values() if n.template_id == "fog_drake"]:
                break
        self.assertTrue([n for n in game.world.npcs.values() if n.template_id == "fog_drake"], "and then it comes")
        beats = [_plain(t).strip() for t in told if "fog" in t.lower() or "package" in t.lower() or "drake" in t.lower()]
        self.assertGreaterEqual(len(beats), 3, "a few told moments first")
        self.assertIn("A Fog Drake uncoils", beats[-1])


class TestATransitionsPaceIsChecked(unittest.TestCase):
    def errors_with(self, pace):
        import json
        import shutil
        import tempfile

        from engine.server import content_set as validator

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "ff4_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "ff4_slice", package, ignore=shutil.ignore_patterns("saves", "editor"))
        path = package / "data" / "campaigns" / "the_package.json"
        campaign = json.loads(path.read_text(encoding="utf-8"))
        campaign["nodes"]["deliver"]["transitions"][0]["pace"] = pace
        path.write_text(json.dumps(campaign, indent=2), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_a_name_or_a_speed_passes_and_nonsense_does_not(self):
        self.assertEqual([], self.errors_with("solemn"))
        self.assertEqual([], self.errors_with(30))
        self.assertTrue(any("is not a pace" in m for m in self.errors_with("glacial")))


class TestNoDanglingReplies(unittest.TestCase):
    def test_the_mayor_just_speaks(self):
        game = _Game(self)
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        said = game.say("talk mayor")
        self.assertIn("mayor of Mistvale speaks", said)
        self.assertNotRegex(said, r"(?m)^\s*1\. ")
        self.assertNotIn("reply <number>", said)

    def test_kessa_does_not_tell_you_to_see_someone_who_is_standing_beside_you(self):
        game = _Game(self)
        game.player.flags["kessa_ahead"] = True
        kessa = game.npc("captain_kessa")
        kessa.current_region_id, kessa.current_room_id = "mistvale", "village_square"
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        said = game.say("talk kessa")
        self.assertNotIn("waiting in the square", said)
        self.assertIn("give the mayor the package", said)


if __name__ == "__main__":
    unittest.main()
