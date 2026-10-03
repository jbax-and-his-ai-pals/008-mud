# tests/singles/test_scene_resume_and_credit.py
"""Four things that had to be true for the story slice to be a safe proof of the engine.

1. A scene that is part-told when the server stops carries on after a restart (the drake arrives).
2. Quest stages, and NPC properties, are checked: wrong types and near-miss names are reported.
3. One hand-in report and one "ready" instruction serve every kind of quest.
4. A friend's kill counts for every player present, and old blows stop counting.
"""

import json
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path

from engine.core import kill_credit
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
FF4 = REPO_ROOT / "content_sets" / "ff4_slice"
_MARKUP = re.compile(r"\[\[[^\]]*\]\]")
NL = chr(10)


def _plain(text):
    return _MARKUP.sub("", text)


def _drakes(world):
    return [n for n in world.npcs.values() if n.template_id == "fog_drake" and n.is_alive]


def _deliver_the_package(server, sid):
    server.execute_command(sid, "talk king")
    server.execute_command(sid, "reply 1")
    player = server.get_player_for_session(sid)
    player.current_region_id, player.current_room_id = "mistvale", "village_square"
    server.execute_command(sid, "give sealed package to mayor")
    return player


def _run(server, sid, seconds):
    told = []
    for _ in range(seconds):
        server.world.clock.advance(1.0)
        events = server.tick(sid) + server._flush_background_batch(sid)   # as the transports do
        told += [_plain(str(e["payload"])) for e in events if e["type"] == "text"]
    return NL.join(told)


class TestASceneSurvivesARestart(unittest.TestCase):
    def boot(self, db):
        return HeadlessServer(db_path=db, content_set_path=str(FF4), deterministic_test_mode=True,
                              default_presentation_mode="player")

    def test_the_drake_still_comes_after_a_restart_in_the_middle_of_its_arrival(self):
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        db = os.path.join(tmp, "story.sqlite3")
        first = self.boot(db)
        sid = first.create_session(player_id="hero").session_id
        first.execute_command(sid, "char create Cecil")
        _deliver_the_package(first, sid)
        _run(first, sid, 5)   # two of the four beats have been told
        self.assertEqual([], _drakes(first.world), "not yet")
        first.persist_player_snapshot(sid)
        first.shutdown()

        second = self.boot(db)
        self.addCleanup(second.shutdown)
        sid = second.create_session(player_id="hero").session_id
        second.execute_command(sid, "char create Cecil")
        told = _run(second, sid, 20)
        self.assertEqual(1, len(_drakes(second.world)), "the quest has its creature again")
        self.assertIn("A Fog Drake uncoils from the mist", told)
        self.assertNotIn("The hum climbs", told, "what was already told is not told twice")

    def test_a_scene_that_lost_its_schedule_is_picked_up_again(self):
        server = self.boot(":memory:")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Cecil")
        _deliver_the_package(server, sid)
        server.world.scheduled_actions.clear()   # what a restart does to the in-memory schedule
        _run(server, sid, 20)
        self.assertEqual(1, len(_drakes(server.world)))

    def test_it_is_only_told_and_spawned_once(self):
        server = self.boot(":memory:")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Cecil")
        _deliver_the_package(server, sid)
        told = _run(server, sid, 40)
        self.assertEqual(1, len(_drakes(server.world)))
        self.assertEqual(1, told.count("A Fog Drake uncoils"))


class TestQuestStagesAndNpcPropertiesAreChecked(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.package = self.tmp / "ff4_slice"
        shutil.copytree(FF4, self.package, ignore=shutil.ignore_patterns("saves", "editor"))

    def issues_with(self, quest_edit=None, npc_edit=None):
        from engine.server import content_set as validator

        if quest_edit:
            path = self.package / "data" / "quests" / "quests.json"
            quests = json.loads(path.read_text(encoding="utf-8"))
            quest_edit(quests["quest_fog_drake"]["stages"][0])
            path.write_text(json.dumps(quests, indent=2), encoding="utf-8")
        if npc_edit:
            path = self.package / "data" / "npcs" / "people.json"
            people = json.loads(path.read_text(encoding="utf-8"))
            npc_edit(people["innkeeper"]["properties"])
            path.write_text(json.dumps(people, indent=2), encoding="utf-8")
        _definition, issues = validator.load_content_set(self.package)
        return [(i.severity, i.message) for i in issues]

    def messages(self, severity, **edits):
        return [m for s, m in self.issues_with(**edits) if s == severity]

    def test_the_shipped_stage_is_clean(self):
        self.assertEqual([], self.messages("error"))
        self.assertFalse([m for m in self.messages("warning") if "stage" in m])

    def test_text_fields_must_be_text(self):
        for field in ("ready_text", "completion_narration", "completion_dialogue", "start_dialogue"):
            errors = self.messages("error", quest_edit=lambda stage, f=field: stage.__setitem__(f, 5))
            self.assertTrue(any(field in m and "must be text" in m for m in errors), field)

    def test_the_spawn_on_start_shape_is_checked(self):
        errors = self.messages("error", quest_edit=lambda stage: stage["spawn_on_start"].pop("room_id"))
        self.assertTrue(any("spawn_on_start" in m and "room_id" in m for m in errors))
        errors = self.messages("error", quest_edit=lambda stage: stage["spawn_on_start"].__setitem__("template_id", "no_such_beast"))
        self.assertTrue(any("no_such_beast" in m for m in errors))
        errors = self.messages("error", quest_edit=lambda stage: stage["spawn_on_start"].__setitem__("room_id", "no_such_room"))
        self.assertTrue(any("no_such_room" in m for m in errors))

    def test_intro_beats_are_checked(self):
        def edit(beats):
            return lambda stage: stage["spawn_on_start"].__setitem__("intro", beats)

        self.assertEqual([], self.messages("error", quest_edit=edit([{"text": "Hm.", "after": 0, "pace": 40}])))
        for bad, needle in (
            ("not a list", "must be a list"),
            ([{"text": "", "after": 1}], "text"),
            ([{"text": "ok", "after": "soon"}], "after"),
            ([{"text": "ok", "after": -1}], "after"),
            ([{"text": "ok", "pace": "warp"}], "pace"),
            ([{"text": "ok", "mood": "grim"}], "mood"),
            (["just text"], "must be an object"),
        ):
            errors = self.messages("error", quest_edit=edit(bad))
            self.assertTrue(any("intro" in m and needle in m for m in errors), (bad, errors))

    def test_an_unknown_stage_key_is_a_warning_naming_what_is_known(self):
        warnings = self.messages("warning", quest_edit=lambda stage: stage.__setitem__("ready_txt", "x"))
        self.assertTrue(any("ready_txt" in m and "ready_text" in m for m in warnings), warnings)

    def test_despawn_message_must_be_text_and_a_near_miss_property_is_flagged(self):
        errors = self.messages("error", npc_edit=lambda props: props.__setitem__("despawn_message", 5))
        self.assertTrue(any("despawn_message" in m for m in errors))
        warnings = self.messages("warning", npc_edit=lambda props: props.__setitem__("essentail", True))
        self.assertTrue(any("essentail" in m and "essential" in m for m in warnings), warnings)
        warnings = self.messages("warning", npc_edit=lambda props: props.__setitem__("flavour_of_the_week", True))
        self.assertFalse(any("flavour_of_the_week" in m for m in warnings), "an unrelated key is the author's own")


class TestOneReportAndOneInstruction(unittest.TestCase):
    def test_a_completion_report_is_the_title_the_closing_and_the_rewards_in_paragraphs(self):
        from engine.core.quests.closing import completion_report

        text = _plain(completion_report("The King's Package", "It hums.", "Rewards: 1 XP"))
        self.assertEqual("[Quest Complete] The King's Package" + NL + "It hums." + NL + NL + "Rewards: 1 XP", text)
        self.assertEqual("[Quest Complete] T", _plain(completion_report("T")))

    def test_a_stage_says_what_to_do_next_for_every_kind_of_objective(self):
        from engine.core.quests.tracker import handle_resource_gathered

        server = HeadlessServer(db_path=":memory:", content_set_path=str(FF4), deterministic_test_mode=True,
                                default_presentation_mode="player")
        self.addCleanup(server.shutdown)
        sid = server.create_session(player_id="hero").session_id
        server.execute_command(sid, "char create Cecil")
        player = server.get_player_for_session(sid)
        manager = server.world.quest_manager

        def quest(ready_text):
            stage = {"stage_index": 0, "description": "Gather.", "turn_in_id": "ryn",
                     "objective": {"type": "gather_types", "required_item_ids": ["herb"], "gathered_item_ids": []}}
            if ready_text:
                stage["ready_text"] = ready_text
            return {"title": "Herbs", "state": "active", "stages": [stage], "current_stage_index": 0,
                    "instance_id": "herbs_1", "template_id": "herbs"}

        player.runtime_state.quests.active["herbs_1"] = quest("Take them to the shrine.")
        said = _plain(handle_resource_gathered(manager, player, "herb") or "")
        self.assertIn("Take them to the shrine.", said)
        self.assertNotIn("Report back to", said)

        player.runtime_state.quests.active["herbs_1"] = quest("")
        said = _plain(handle_resource_gathered(manager, player, "herb") or "")
        self.assertIn("Report back to", said, "a stage that says nothing gets the usual line")

    def test_ready_instruction_prefers_the_stage_and_falls_back(self):
        from engine.core.quests.closing import ready_instruction

        data = {"stages": [{"ready_text": "Go."}], "current_stage_index": 0}
        self.assertEqual("Go.", ready_instruction(data, "Report back to X."))
        self.assertEqual("Report back to X.", ready_instruction({"stages": [{}], "current_stage_index": 0}, "Report back to X."))


class _Table:
    def __init__(self, case, players=2):
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=str(REPO_ROOT / "content_sets" / "fantasy_frontier"),
            deterministic_test_mode=True, default_presentation_mode="player",
        )
        case.addCleanup(self.server.shutdown)
        self.world = self.server.world
        self.sessions, self.players = [], []
        for index in range(players):
            sid = self.server.create_session(player_id=f"hero{index}").session_id
            self.server.execute_command(sid, f"char create Hero{index}")
            self.sessions.append(sid)
            self.players.append(self.server.get_player_for_session(sid))
        self.place = (self.players[0].current_region_id, self.players[0].current_room_id)
        for player in self.players:
            player.current_region_id, player.current_room_id = self.place

    def creature(self, instance_id, **fields):
        npc = NPCFactory.create_npc_from_template("goblin", self.world, instance_id=instance_id)
        npc.current_region_id, npc.current_room_id = self.place
        for key, value in fields.items():
            setattr(npc, key, value)
        self.world.add_npc(npc)
        return npc


class TestAFriendsKillCountsForEveryoneThere(unittest.TestCase):
    def test_each_player_present_hears_of_it_and_the_others_are_told_wherever_they_are(self):
        from engine.npcs.combat import try_attack

        table = _Table(self, 3)
        ally = table.creature("ally", faction="friendly", attack_power=500, attack_cooldown=0, combat_cooldown=0)
        enemy = table.creature("enemy")
        enemy.health = 1
        credited = []

        def dispatch(event, data):
            credited.append(data["player"].name)
            return "QUEST UPDATE for " + data["player"].name

        table.world.dispatch_event = dispatch
        ally.combat_target, ally.combat_targets = enemy, {enemy}
        said = ""
        for step in range(40):
            said = try_attack(ally, table.world, 9000.0 + step * 10) or ""
            if not enemy.is_alive:
                break
        self.assertFalse(enemy.is_alive)
        self.assertEqual(["Hero0", "Hero1", "Hero2"], sorted(credited), "everyone standing there")
        self.assertIn("QUEST UPDATE for Hero0", said, "the one watching reads it in the kill's own message")
        self.assertNotIn("QUEST UPDATE for Hero1", said)
        notified = {player.name: text for player, text in table.world.pending_player_notices}
        self.assertEqual("QUEST UPDATE for Hero1", notified.get("Hero1"))
        self.assertEqual("QUEST UPDATE for Hero2", notified.get("Hero2"))

    def test_a_player_somewhere_else_is_not_credited(self):
        from engine.npcs.combat import try_attack

        table = _Table(self, 2)
        far = table.players[1]
        region = next(r for r in table.world.regions.values() if r.rooms)
        far.current_region_id, far.current_room_id = region.obj_id, next(iter(region.rooms))
        if (far.current_region_id, far.current_room_id) == table.place:
            self.skipTest("the world has one room to stand in")
        ally = table.creature("ally", faction="friendly", attack_power=500, attack_cooldown=0, combat_cooldown=0)
        enemy = table.creature("enemy")
        enemy.health = 1
        credited = []
        table.world.dispatch_event = lambda event, data: credited.append(data["player"].name)
        ally.combat_target, ally.combat_targets = enemy, {enemy}
        for step in range(40):
            try_attack(ally, table.world, 9000.0 + step * 10)
            if not enemy.is_alive:
                break
        self.assertEqual(["Hero0"], credited)


class TestOldBlowsStopCounting(unittest.TestCase):
    def table_with(self, rules):
        table = _Table(self, 2)
        original = table.world.ruleset_section
        table.world.ruleset_section = lambda name: {"experience_sharing": rules} if name == "combat" else original(name)
        return table

    def shares(self, enemy):
        return {player.name: share for player, share in kill_credit.player_shares(enemy)}

    def test_a_blow_is_forgotten_after_the_memory_runs_out(self):
        table = self.table_with({"memory_seconds": 60})
        a, b = table.players
        enemy = table.creature("enemy", max_health=200, health=200)
        kill_credit.record_damage(enemy, a, 50, 200)
        table.world.clock.advance(61)
        kill_credit.record_damage(enemy, b, 10, 150)
        self.assertEqual({"Hero1": 1.0}, self.shares(enemy))

    def test_a_recent_blow_still_counts(self):
        table = self.table_with({"memory_seconds": 60})
        a, b = table.players
        enemy = table.creature("enemy", max_health=200, health=200)
        kill_credit.record_damage(enemy, a, 50, 200)
        table.world.clock.advance(30)
        kill_credit.record_damage(enemy, b, 50, 150)
        self.assertEqual({"Hero0": 0.5, "Hero1": 0.5}, self.shares(enemy))

    def test_zero_memory_never_forgets(self):
        table = self.table_with({"memory_seconds": 0})
        a, b = table.players
        enemy = table.creature("enemy", max_health=200, health=200)
        kill_credit.record_damage(enemy, a, 50, 200)
        table.world.clock.advance(10 ** 6)
        kill_credit.record_damage(enemy, b, 50, 150)
        self.assertEqual({"Hero0": 0.5, "Hero1": 0.5}, self.shares(enemy))

    def test_a_creature_at_full_health_starts_a_new_tally(self):
        table = self.table_with({})
        a, b = table.players
        enemy = table.creature("enemy", max_health=200, health=200)
        kill_credit.record_damage(enemy, a, 50, 200)   # a hurt it, and it has since healed
        kill_credit.record_damage(enemy, b, 20, enemy.max_health)   # b meets it at full health
        self.assertEqual({"Hero1": 1.0}, self.shares(enemy))

    def test_the_memory_is_configurable_and_checked(self):
        table = self.table_with({"memory_seconds": 12})
        self.assertEqual(12.0, kill_credit.memory_seconds(table.world))
        bad = self.table_with({"memory_seconds": "long"})
        self.assertEqual(float(kill_credit.DEFAULT_MEMORY_SECONDS), kill_credit.memory_seconds(bad.world))

        from engine.server import content_set as validator

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        package = tmp / "ff4_slice"
        shutil.copytree(FF4, package, ignore=shutil.ignore_patterns("saves", "editor"))
        path = package / "rules" / "ruleset.json"
        for value, should_pass in ((0, True), (90, True), (-1, False), ("soon", False), (True, False)):
            rules = json.loads(path.read_text(encoding="utf-8"))
            rules.setdefault("combat", {})["experience_sharing"] = {"memory_seconds": value}
            path.write_text(json.dumps(rules, indent=2), encoding="utf-8")
            _definition, issues = validator.load_content_set(package)
            errors = [i.message for i in issues if i.severity == "error"]
            self.assertEqual(should_pass, errors == [], (value, errors))


if __name__ == "__main__":
    unittest.main()
