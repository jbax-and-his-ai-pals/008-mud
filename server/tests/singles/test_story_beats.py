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

from tests.fixtures import STORY_FIXTURE, skip_the_ff4_opening

REPO_ROOT = Path(__file__).resolve().parents[3]
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)


def _plain(text):
    return _MARKUP.sub("", text)


class _Game:
    """A game of the FF4 slice. By default a frozen copy of it (the engine features this file checks do not depend on
    the story); `story=True` plays the real set, for the classes that are about its story."""

    def __init__(self, case, story=False):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "ff4_slice" if story else STORY_FIXTURE),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        case.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="beats").session_id
        self.server.execute_command(self.sid, "char create Cecil")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        if story:
            skip_the_ff4_opening(self.world, self.player)   # the real slice starts in Mysidia; these tests begin at the king

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

        game = _Game(self, story=True)
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        game.player.health = 1
        wolf = NPCFactory.create_npc_from_template("road_wolf", game.world, instance_id="finisher")
        wolf.current_region_id, wolf.current_room_id = "road", "castle_road"
        game.world.add_npc(wolf)
        wolf.combat_target = game.player
        wolf.combat_targets = {game.player}
        wolf.combat_cooldown = 0
        wolf.attack_cooldown = 0
        wolf.attack_power = 60   # the captain starts in armour now; the point here is what the fall says
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

        game = _Game(self, story=True)
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

        game = _Game(self, story=True)
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
        game = _Game(self, story=True)
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
        game = _Game(self, story=True)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        game.server.execute_command(game.sid, "give sealed package to mayor")
        return game

    def raw(self, game, command):
        events = game.server.execute_command(game.sid, command)
        return NL.join(str(e["payload"]) for e in events if e["type"] == "text")

    def test_the_level_it_brings_is_shown_with_its_stat_gains_and_not_typed_out(self):
        game = _Game(self, story=True)
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
        game = _Game(self, story=True)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        text = self.raw(game, "give sealed package to mayor")
        self.assertIn("[[PACE:40]]The package was not a gift.[[/PACE]]", text)
        self.assertIn(NL + NL + "[[PACE:40]]", text)

    def test_the_drake_comes_after_a_few_told_beats_a_moment_apart(self):
        game = _Game(self, story=True)
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


class TestRynsConversation(unittest.TestCase):
    def at_the_shrine(self):
        game = _Game(self, story=True)
        game.say("talk king")
        game.say("reply 1")
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        game.say("give sealed package to mayor")
        for _ in range(20):
            game.world.clock.advance(1.0)
            game.server.tick(game.sid)
        game.player.current_region_id, game.player.current_room_id = "mistvale", "shrine"
        return game

    def test_before_the_drake_she_explains_the_fog_and_sends_you_to_end_it(self):
        game = self.at_the_shrine()
        game.say("talk ryn")
        said = game.say("reply 1")
        self.assertIn("the fog woke", said)
        self.assertIn("end the thing in the square", said)

    def test_once_it_is_dead_talking_to_her_hands_in_the_quest_and_offers_the_calling(self):
        game = self.at_the_shrine()
        game.npc("fog_drake").take_damage(10_000, "physical")
        game.player.flags["drake_slain"] = True
        for quest in game.player.runtime_state.quests.active.values():
            if "fog_drake" in str(quest.get("template_id", "")):
                quest["state"] = "ready_to_complete"
        said = game.say("talk ryn")
        self.assertIn("[Quest Complete] The Fog Drake", said)
        self.assertIn("The fog thins.", said)
        self.assertNotIn("Teach me", said, "the teaching is for the next talk, not a wall of text on top of the hand-in")
        again = game.say("talk ryn")
        self.assertIn("1. Teach me.", again)
        self.assertTrue(any(k.startswith("quest_fog_drake") for k in game.player.runtime_state.quests.completed))


class TestSeveralLevelsAreOneReport(unittest.TestCase):
    def test_gaining_three_levels_says_so_once_with_the_whole_difference(self):
        game = _Game(self)
        player = game.player
        start_level = player.runtime_state.progression.level
        start_strength = player.stats["strength"]
        start_health = player.max_health
        leveled, report = player.gain_experience(5000)
        gained = player.runtime_state.progression.level - start_level
        self.assertGreaterEqual(gained, 2)
        text = _plain(report)
        self.assertTrue(leveled)
        self.assertIn("You have gained %d levels and are now level %d!" % (gained, player.runtime_state.progression.level), text)
        self.assertEqual(1, text.count("Stats Increased"))
        self.assertIn("Strength: %s -> %s (+%s)" % (start_strength, player.stats["strength"], player.stats["strength"] - start_strength), text)
        self.assertIn("Max Health: %s -> %s" % (start_health, player.max_health), text)

    def test_one_level_reads_as_it_always_did(self):
        game = _Game(self)
        _leveled, report = game.player.gain_experience(game.player.runtime_state.progression.experience_to_level)
        self.assertIn("You have reached level 2!", _plain(report))


class TestNamesAndFlight(unittest.TestCase):
    def test_a_unique_character_is_the_not_a(self):
        from engine.utils.utils import format_name_for_display

        game = _Game(self)
        mayor = game.npc("mayor_of_mistvale")
        guard = game.npc("castle_guard")
        self.assertIn("The ", _plain(format_name_for_display(game.player, mayor, True)))
        self.assertIn("the ", _plain(format_name_for_display(game.player, mayor, False)))
        self.assertIn("A ", _plain(format_name_for_display(game.player, guard, True)))

    def test_fleeing_through_in_names_the_place_not_the_in(self):
        from engine.npcs.ai.combat_logic import try_flee

        game = _Game(self)
        mayor = game.npc("mayor_of_mistvale")
        mayor.current_region_id, mayor.current_room_id = "mistvale", "village_square"
        game.player.current_region_id, game.player.current_room_id = "mistvale", "village_square"
        region = game.world.get_region("mistvale")
        square = region.get_room("village_square")
        original = dict(square.exits)
        square.exits.clear()
        square.exits["in"] = original["in"]
        said = _plain(try_flee(mayor, game.world, game.player) or "")
        self.assertIn("flees into the Fogwatch Inn!", said)
        self.assertNotIn("the in!", said)
        self.assertTrue(said.startswith("The mayor of Mistvale"), said)

    def test_a_compass_flight_still_says_to_the_direction(self):
        from engine.npcs.ai.combat_logic import try_flee

        game = _Game(self)
        goblin = game.npc("goblin_scout")
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        room = game.world.get_region("road").get_room("castle_road")
        goblin.current_region_id, goblin.current_room_id = "road", "castle_road"
        room.exits.clear()
        room.exits["north"] = next(iter(game.world.get_region("road").rooms))
        said = _plain(try_flee(goblin, game.world, game.player) or "")
        self.assertIn("flees to the north!", said)


class TestACastSummonsOnce(unittest.TestCase):
    def test_a_quake_across_three_enemies_still_calls_one_titan_and_says_how_it_leaves(self):
        game = _Game(self)
        game.player.runtime_state.magic.known_spells.add("call_titan")
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        for index in range(3):
            foe = NPCFactory.create_npc_from_template("goblin_scout", game.world, instance_id="triple_%d" % index)
            foe.current_region_id, foe.current_room_id = "road", "castle_road"
            game.world.add_npc(foe)
        game.say("cast call titan")
        self.assertEqual(1, len([n for n in game.world.npcs.values() if n.template_id == "titan_minion" and n.is_alive]))
        told = ""
        for _ in range(12):
            game.world.clock.advance(1.0)
            events = game.server.tick(game.sid) + game.server._flush_background_batch(game.sid)
            told += NL.join(_plain(str(e["payload"])) for e in events if e["type"] == "text")
        self.assertIn("The Titan sinks back into the earth.", told)


class TestATransitionsPaceIsChecked(unittest.TestCase):
    def errors_with(self, pace):
        import json
        import shutil
        import tempfile

        from engine.server import content_set as validator

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, package, ignore=shutil.ignore_patterns("saves", "editor"))
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
