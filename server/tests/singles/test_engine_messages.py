# tests/singles/test_engine_messages.py
"""The engine's own words for the moments every game has are a content set's to say its own way (`ruleset.messages`)."""

import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from engine.utils import messages

REPO_ROOT = Path(__file__).resolve().parents[3]
FF4 = REPO_ROOT / "content_sets" / "ff4_slice"
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)


def _plain(text):
    return _MARKUP.sub("", text)


class _Game:
    def __init__(self, case, say=None):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(FF4), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        case.addCleanup(self.server.shutdown)
        self.world = self.server.world
        if say is not None:
            original = self.world.ruleset_section
            self.world.ruleset_section = lambda name: dict(say) if name == "messages" else original(name)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Cecil")
        self.player = self.server.get_player_for_session(self.sid)

    def run(self, command):
        events = self.server.execute_command(self.sid, command)
        return _plain(NL.join(str(e["payload"]) for e in events if e["type"] == "text"))


class TestTheEnginesOwnWords(unittest.TestCase):
    def test_every_message_has_words_and_says_which_fields_it_may_use(self):
        for key, (text, fields) in messages.MESSAGES.items():
            self.assertEqual([], messages.template_problems(text, key), key)
            self.assertEqual(text.format(**{name: "x" for name in fields}), messages.message(None, key, **{name: "x" for name in fields}))

    def test_a_template_may_only_use_its_own_fields(self):
        self.assertEqual([], messages.template_problems("{amount} gained", "kill_experience"))
        self.assertTrue(messages.template_problems("{gold} gained", "kill_experience"))
        self.assertTrue(messages.template_problems("{amount.real}", "kill_experience"))
        self.assertTrue(messages.template_problems("{amount:>5}", "kill_experience"))
        self.assertTrue(messages.template_problems("{amount", "kill_experience"))
        self.assertTrue(messages.template_problems("   ", "kill_experience"))
        self.assertTrue(messages.template_problems(5, "kill_experience"))
        self.assertTrue(messages.template_problems("x", "no_such_message"))

    def test_an_unusable_template_never_breaks_the_moment(self):
        class World:
            def ruleset_section(self, name):
                return {"kill_experience": "{nonsense}"}

        self.assertEqual("You gain 5 experience!", messages.message(World(), "kill_experience", amount=5))


class TestASetSaysItsOwn(unittest.TestCase):
    def test_a_set_that_says_nothing_reads_as_it_always_did(self):
        game = _Game(self)
        _leveled, report = game.player.gain_experience(game.player.runtime_state.progression.experience_to_level)
        self.assertIn("You have reached level 2!", _plain(report))

    def test_the_level_headlines(self):
        game = _Game(self, {"level_reached": "Level {level} at last!", "levels_gained": "{count} levels in one go: now {level}."})
        _l, one = game.player.gain_experience(game.player.runtime_state.progression.experience_to_level)
        self.assertIn("Level 2 at last!", _plain(one))
        _l, many = game.player.gain_experience(5000)
        self.assertRegex(_plain(many), r"\d+ levels in one go: now \d+\.")

    def test_a_kills_rewards(self):
        game = _Game(self, {"kill_experience": "{amount} experience earned.", "kill_gold": "{amount} {currency} found."})
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        goblin = next(n for n in game.world.npcs.values() if n.template_id == "goblin_scout")
        goblin.health = 1
        for _ in range(40):
            game.server.tick(game.sid)
        said = game.run("cast dark wave")
        self.assertRegex(said, r"\d+ experience earned\.")
        self.assertRegex(said, r"\d+ gil found\.")
        self.assertNotIn("You gain", said)

    def test_a_blows_rewards_too(self):
        # the sword's kill is a different path from the ability's
        game = _Game(self, {"kill_experience": "{amount} experience earned.", "kill_gold": "{amount} {currency} found."})
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        goblin = next(n for n in game.world.npcs.values() if n.template_id == "goblin_scout")
        goblin.health = 1
        goblin.loot_table = {"gold_value": {"chance": 1.0, "quantity": [7, 7]}}
        for _ in range(40):
            game.server.tick(game.sid)
        said = ""
        for _ in range(30):
            said = game.run("attack goblin scout")
            if not goblin.is_alive:
                break
            for _tick in range(60):
                game.server.tick(game.sid)
        self.assertFalse(goblin.is_alive)
        self.assertRegex(said, r"\d+ experience earned\.")
        self.assertIn("7 gil found.", said)
        self.assertNotIn("You gain", said)

    def test_falling_in_battle(self):
        from engine.npcs.combat import try_attack

        game = _Game(self, {"defeated": "Darkness takes you.", "respawn_hint": "Say 'respawn' to wake in {place}."})
        game.player.current_region_id, game.player.current_room_id = "road", "castle_road"
        game.player.health = 1
        wolf = NPCFactory.create_npc_from_template("road_wolf", game.world, instance_id="finisher")
        wolf.current_region_id, wolf.current_room_id = "road", "castle_road"
        game.world.add_npc(wolf)
        wolf.combat_target, wolf.combat_targets = game.player, {game.player}
        wolf.combat_cooldown = wolf.attack_cooldown = 0
        said = ""
        for step in range(60):
            said = try_attack(wolf, game.world, 1000.0 + step * 10) or ""
            if not game.player.is_alive:
                break
        self.assertFalse(game.player.is_alive)
        self.assertIn("Darkness takes you.", _plain(said))
        self.assertRegex(_plain(said), r"Say 'respawn' to wake in .+\.")
        self.assertNotIn("You have been defeated", said)

    def test_a_summon_leaving_and_a_quest_handed_in(self):
        from engine.core.quests.closing import completion_report

        game = _Game(self, {"summon_departs": "{name} fades.", "quest_complete": "Done: {title}"})
        titan = NPCFactory.create_npc_from_template("skeleton_minion", game.world, instance_id="leaver") if False else None
        for template in ("titan_minion",):
            titan = NPCFactory.create_npc_from_template(template, game.world, instance_id="leaver")
        titan.properties["is_summoned"] = True
        titan.properties.pop("despawn_message", None)
        self.assertEqual("Titan fades.", titan.despawn(game.world, silent=False))
        self.assertIn("Done: The Fog Drake", _plain(completion_report("The Fog Drake", "", "", game.world)))
        self.assertIn("[Quest Complete] The Fog Drake", _plain(completion_report("The Fog Drake")), "and without a world, the engine's own words")

    def test_a_players_share_of_a_kill_somewhere_else(self):
        from engine.core import kill_credit

        server = HeadlessServer(db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "fantasy_frontier"),
                                deterministic_test_mode=True, default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        original = server.world.ruleset_section
        server.world.ruleset_section = lambda name: {"shared_experience": "+{amount} for {name}"} if name == "messages" else original(name)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Hero")
        player = server.get_player_for_session(sid)
        enemy = NPCFactory.create_npc_from_template("goblin", server.world, instance_id="target")
        enemy.current_region_id, enemy.current_room_id = player.current_region_id, player.current_room_id
        server.world.add_npc(enemy)
        kill_credit.award_participants(server.world, enemy, [(player, 0.5)])
        notice = [text for who, text in server.world.pending_player_notices if who is player][0]
        self.assertRegex(_plain(notice), r"^\+\d+ for .*goblin")


class TestTheValidator(unittest.TestCase):
    def errors_with(self, section):
        from engine.server import content_set as validator

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "ff4_slice"
        shutil.copytree(FF4, package, ignore=shutil.ignore_patterns("saves", "editor"))
        path = package / "rules" / "ruleset.json"
        rules = json.loads(path.read_text(encoding="utf-8"))
        rules["messages"] = section
        path.write_text(json.dumps(rules, indent=2), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        return [i.message for i in issues if i.severity == "error"]

    def test_good_messages_pass(self):
        self.assertEqual([], self.errors_with({}))
        self.assertEqual([], self.errors_with({"kill_experience": "{amount} xp!", "defeated": "You fall.", "respawn_hint": "Wake at {place}."}))

    def test_bad_messages_are_refused_and_say_what_would_work(self):
        errors = self.errors_with({"kill_expereince": "x"})
        self.assertTrue(any("kill_expereince" in m and "kill_experience" in m for m in errors), errors)
        errors = self.errors_with({"kill_experience": "{gold} earned"})
        self.assertTrue(any("messages.kill_experience" in m and "{amount}" in m for m in errors), errors)
        errors = self.errors_with({"defeated": "{amount}"})
        self.assertTrue(any("messages.defeated" in m and "none" in m for m in errors), errors)
        self.assertTrue(any("must be text" in m for m in self.errors_with({"defeated": 5})))
        self.assertTrue(any("must be an object" in m for m in self.errors_with("loud")))


if __name__ == "__main__":
    unittest.main()
