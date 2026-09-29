# tests/singles/test_adaptation_slices.py
"""Play the two adaptation slices' load-bearing moments.

`zelda_slice` (an action-adventure shape: an overworld, two dungeons, key items,
two shards and a tower) and `ff4_slice` (a story-driven console-RPG shape: a
throne-room choice, a courier run, a boss that arrives with the plot, a summoner
child) were written to see how far the engine stretches. These tests hold the
things they lean on so a change to the engine cannot quietly take them away:
item-gated exits, a lever's hidden exit, an element that opens a wall, two
hazards ticking on their own clocks, a campaign that hands one quest to the next,
an NPC moved by a dialogue effect, a boss spawned when a stage begins.

Nothing here depends on luck: bosses are set to one hit point, and everything else
is arranged directly. See docs/design/adaptation_slices.md for what the slices
found that the engine could not do.
"""

import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from engine.dialogue.effects import apply_effects
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from toolkit import content_set_validator as validator  # noqa: E402

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


class _Slice(unittest.TestCase):
    SET_ID = ""

    def setUp(self):
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(REPO_ROOT / "content_sets" / self.SET_ID),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="slice").session_id
        self.say("char create Tester")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world

    # -- driving -----------------------------------------------------------------
    def say(self, command):
        events = self.server.execute_command(self.sid, command)
        text = "\n".join(str(e.get("payload")) for e in events if e.get("type") in ("text", "error"))
        return _MARKUP.sub("", text)

    def tick(self, count=1):
        text = []
        for _ in range(count):
            text.append(_MARKUP.sub("", "\n".join(str(e.get("payload")) for e in self.server.tick(self.sid)
                                                  if e.get("type") in ("text", "error"))))
        return "\n".join(t for t in text if t)

    def at(self, region, room):
        self.player.current_region_id, self.player.current_room_id = region, room

    def where(self):
        return "%s:%s" % (self.player.current_region_id, self.player.current_room_id)

    def give(self, item_id):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.assertIsNotNone(item, item_id)
        self.player.inventory.add_item(item)

    def holds(self, item_id):
        return any(slot.item and slot.item.obj_id == item_id for slot in self.player.inventory.slots)

    def npcs(self, template_id):
        return [n for n in self.world.npcs.values() if n.template_id == template_id and n.is_alive]

    def kill(self, template_id, name):
        """Drop the named NPC to one hit point and swing until it falls."""
        foe = self.npcs(template_id)[0]
        self.at(foe.current_region_id, foe.current_room_id)
        foe.health = 1
        self.player.health = self.player.max_health = 500
        for _ in range(80):
            if not foe.is_alive:
                return
            self.say("attack %s" % name)
            self.tick(21)
        self.fail("%s did not fall" % template_id)

    def quest_states(self):
        return {q.get("title"): q.get("state") for q in self.player.runtime_state.quests.active.values()}


class TestZeldaSlice(_Slice):
    SET_ID = "zelda_slice"

    def test_the_hermit_gives_a_sword_once(self):
        self.at("caves", "hermit_cave")
        self.say("talk hermit")
        self.say("reply 1")
        self.assertTrue(self.holds("item_wooden_sword"))
        self.assertTrue(self.player.flags.get("got_the_sword"))
        again = self.say("talk hermit")
        self.assertNotIn("Thank you", again, "the gift is offered only until it has been taken")

    def _ask_the_hermit_who_he_is(self):
        self.at("caves", "hermit_cave")
        self.say("talk hermit")
        self.say("reply 1")   # the sword
        self.say("reply 1")   # "I will."
        self.say("talk hermit")
        return self.say("reply 2")   # the tower, then: who are you?

    def test_the_hermit_vanishes_when_asked_who_he_is(self):
        """He is taken out of the world: no corpse, no loot, and no timer to bring him back."""
        said = self._ask_the_hermit_who_he_is()
        self.assertEqual([], self.npcs("hermit"))
        self.assertIs(True, self.player.flags.get("hermit_gone"))
        self.assertIn("only a cave", said)
        self.assertEqual([], [e for e in self.world.respawn_manager.respawn_queue if e.get("template_id") == "hermit"])
        self.assertEqual([], self.world.get_npcs_in_room("caves", "hermit_cave"))
        self.assertNotIn("CONVERSATION WITH THE HERMIT", self.say("talk hermit"))
        self.assertTrue(self.holds("item_wooden_sword"), "what he gave stays given")

    def test_the_hermit_does_not_come_back_however_long_you_wait(self):
        self._ask_the_hermit_who_he_is()
        self.tick(120)
        self.assertEqual([], self.npcs("hermit"))

    def test_a_heart_container_raises_the_maximum_and_heals(self):
        """It used to heal 200 and leave you as you were; now it is treasure."""
        self.give("item_heart_container")
        before = self.player.max_health
        self.player.health = 1
        said = self.say("use heart container")
        self.assertEqual(before + 10, self.player.max_health)
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertIn("sturdier", said)
        self.assertFalse(self.holds("item_heart_container"), "and it is used up")

    def test_the_pool_fairy_refills_health_and_mana_for_nothing(self):
        self.at("caves", "fairy_pool")
        magic = self.player.runtime_state.magic
        self.player.health, magic.mana = 1, 0
        gold = self.player.runtime_state.gold
        self.say("talk fairy")
        self.say("reply 1")
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(magic.max_mana, magic.mana)
        self.assertEqual(gold, self.player.runtime_state.gold, "the pool is free")

    def test_a_boss_hall_opens_only_to_its_key(self):
        self.at("mossroot", "mossy_gallery")
        self.say("go west")
        self.assertEqual("mossroot:mossy_gallery", self.where())
        self.give("item_key_mossroot")
        self.say("go west")
        self.assertEqual("mossroot:boss_hall", self.where())

    def test_a_raft_carries_you_to_the_island(self):
        self.at("aldermark", "lake_dock")
        self.say("go east")
        self.assertEqual("aldermark:lake_dock", self.where())
        self.give("item_raft")
        self.say("go east")
        self.assertEqual("drowned_vault:island_landing", self.where())

    def test_a_lever_reveals_a_hidden_exit(self):
        self.at("mossroot", "root_hall")
        self.say("go down")
        self.assertEqual("mossroot:root_hall", self.where())
        self.assertIn("grinding", self.say("pull loose stone"))
        self.say("go down")
        self.assertEqual("mossroot:secret_larder", self.where())

    def test_a_bomb_opens_a_cracked_wall_and_the_wall_closes_again(self):
        self.at("drowned_vault", "bomb_chamber")
        self.say("go north")
        self.assertEqual("drowned_vault:bomb_chamber", self.where())
        magic = self.player.runtime_state.magic
        magic.known_spells.add("bomb")
        magic.mana = magic.max_mana = 100
        self.assertIn("bursts", self.say("cast bomb on here"))
        self.say("go north")
        self.assertEqual("drowned_vault:key_niche", self.where())
        # Documented limit: a bombed wall does not stay bombed. `env_interactions`
        # revert after their `duration`, so a wall that should stay open cannot be
        # written yet. If that is ever fixed, this is the line that should change.
        self.say("go south")
        self.tick(1300)
        self.say("go north")
        self.assertEqual("drowned_vault:bomb_chamber", self.where())

    def test_two_hazards_tick_on_their_own_clocks(self):
        self.at("drowned_vault", "flooded_hall")
        text = self.tick(150).lower()
        self.assertIn("toxic fumes", text)
        self.assertIn("freezes your skin", text)

    def test_the_shards_forge_the_triad_and_the_triad_opens_the_tower(self):
        self.at("aldermark", "tower_approach")
        self.say("go north")
        self.assertEqual("aldermark:tower_approach", self.where(), "the sealed door needs the Triad")

        self.at("aldermark", "village_green")
        self.give("item_shard_courage")
        self.say("talk sage")
        self.assertNotIn("I have both shards", self.say("talk sage"), "one shard is not enough to forge")
        self.give("item_shard_wisdom")
        self.say("talk sage")
        self.say("reply I have both shards")
        self.assertTrue(self.holds("item_triad"))
        self.assertFalse(self.holds("item_shard_courage"))

        self.at("aldermark", "tower_approach")
        self.say("go north")
        self.assertEqual("dread_tower:tower_gate", self.where())

    def test_a_campaign_hands_each_quest_to_the_next(self):
        self.at("aldermark", "village_green")
        self.say("talk sage")
        self.say("reply 1")
        self.assertIn("The Shard of Courage", self.quest_states())

        self.kill("horned_wyrm", "wyrm")
        self.assertEqual("ready_to_complete", self.quest_states()["The Shard of Courage"])
        hall = self.world.get_region("mossroot").get_room("boss_hall")
        self.assertTrue(any(item.obj_id == "item_shard_courage" for item in hall.items), "the wyrm's shard lies where it fell")
        self.at("aldermark", "village_green")
        self.assertIn("Quest Complete", self.say("talk sage complete"))
        self.assertIn("The Shard of Wisdom", self.quest_states(), "completing a quest starts the next campaign node")


class TestFF4Slice(_Slice):
    SET_ID = "ff4_slice"

    def setUp(self):
        super().setUp()
        self.say("equip dark blade")

    def _question_the_king(self):
        self.say("talk king")
        self.say("reply 2")

    def test_questioning_the_king_costs_the_seal_and_is_remembered(self):
        self.assertTrue(self.holds("item_commander_seal"))
        self._question_the_king()
        self.assertFalse(self.holds("item_commander_seal"))
        self.assertIs(True, self.player.flags.get("questioned_king"))
        self.assertIn("The King's Package", self.quest_states())
        self.assertTrue(self.holds("package_of_the_king"), "a courier run hands you its package")
        self.assertNotIn("slaughter", self.say("talk king"), "the choice cannot be made twice")

    def test_one_choice_sets_two_flags_and_the_one_it_shares_closes_both_answers(self):
        """`set_flag` takes a list: which way you went, and that the king has spoken."""
        self.say("talk king")
        self.say("reply 1")
        self.assertIs(True, self.player.flags.get("obeyed_king"))
        self.assertIs(True, self.player.flags.get("king_ordered"))
        self.assertNotIn("questioned_king", self.player.flags)
        self.assertIn("The King's Package", self.quest_states())
        again = self.say("talk king")
        self.assertNotIn("At once", again, "the choice cannot be made twice")
        self.assertNotIn("slaughter", again, "and the other answer closed with it")

    def test_the_chancellor_unmasks_into_a_fiend(self):
        self.at("varenholt", "throne_room")
        self.assertEqual(1, len(self.npcs("chancellor")))
        self.say("talk chancellor")
        said = self.say("reply 1")
        self.assertEqual([], self.npcs("chancellor"))
        fiends = self.npcs("chancellor_fiend")
        self.assertEqual(1, len(fiends))
        self.assertEqual(("varenholt", "throne_room"), (fiends[0].current_region_id, fiends[0].current_room_id))
        self.assertIs(True, self.player.flags.get("chancellor_unmasked"))
        self.assertIn("too many teeth", said)
        self.assertNotIn("CONVERSATION WITH THE CHANCELLOR", self.say("talk chancellor"))

    def test_the_unmasked_fiend_can_be_fought_and_stays_dead(self):
        self.at("varenholt", "throne_room")
        self.say("talk chancellor")
        self.say("reply 1")
        self.kill("chancellor_fiend", "thing")
        self.assertEqual([], self.npcs("chancellor_fiend"))
        self.tick(400)
        self.assertEqual([], self.npcs("chancellor_fiend"), "a fiend that was killed is not brought back")
        self.assertEqual([], self.npcs("chancellor"), "and the chancellor never returns")

    def test_the_inn_charges_for_a_room_and_restores_the_traveller(self):
        self.at("mistvale", "village_square")
        magic = self.player.runtime_state.magic
        self.player.runtime_state.gold = 50
        self.player.health, magic.mana = 1, 0
        self.say("talk innkeeper")
        said = self.say("reply 1")
        self.assertEqual(20, self.player.runtime_state.gold)
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(magic.max_mana, magic.mana)
        self.assertIn("sleep", said)

    def test_the_inn_does_not_offer_a_room_to_someone_who_cannot_pay(self):
        self.at("mistvale", "village_square")
        self.player.runtime_state.gold = 5
        self.player.health = 1
        offered = self.say("talk innkeeper")
        self.assertNotIn("take the room", offered, "the paid choice is not shown to someone who cannot pay")
        self.assertIn("Not tonight", offered)
        self.say("reply 1")   # all that is left to say is "Not tonight."
        self.assertEqual(5, self.player.runtime_state.gold)
        self.assertEqual(1, self.player.health)

    def test_a_dialogue_effect_sends_a_friend_ahead(self):
        self._question_the_king()
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")
        kessa = self.npcs("captain_kessa")[0]
        self.assertEqual(("mistvale", "village_square"), (kessa.current_region_id, kessa.current_room_id))

    def test_delivering_the_package_brings_the_boss(self):
        self._question_the_king()
        self.at("mistvale", "village_square")
        self.assertEqual([], self.npcs("fog_drake"), "the drake is not in the world until its stage begins")
        self.assertIn("Quest Complete", self.say("give sealed package to mayor"))
        self.assertIn("The Fog Drake", self.quest_states())
        drake = self.npcs("fog_drake")
        self.assertEqual(1, len(drake))
        self.assertEqual(("mistvale", "village_square"), (drake[0].current_region_id, drake[0].current_room_id))

    def test_the_summoner_teaches_the_calling_and_the_titan_arrives(self):
        self._question_the_king()
        self.at("mistvale", "village_square")
        self.say("give sealed package to mayor")
        self.kill("fog_drake", "drake")
        self.at("mistvale", "shrine")
        self.assertIn("Quest Complete", self.say("talk ryn complete"))
        self.say("talk ryn")
        self.say("reply 1")
        self.say("reply 1")
        self.assertIn("call_titan", self.player.runtime_state.magic.known_spells)

        magic = self.player.runtime_state.magic
        magic.mana = magic.max_mana = 100
        self.say("cast call titan")
        titans = self.npcs("titan_minion")
        self.assertEqual(1, len(titans))
        self.assertEqual(("mistvale", "shrine"), (titans[0].current_region_id, titans[0].current_room_id))

        self.assertIn("Paladin", self.say("title paladin"), "the class-change stand-in can be claimed")


class TestKnownLimits(_Slice):
    """What the engine cannot do yet, pinned so closing each gap is a visible diff.

    Every test here passes today and describes a limit, not a wish. Each carries the
    plan item that flips it (docs/plan/chunks-of-work.md, chunk 7): the assertion is
    reversed in that item's commit, which is what proves the item did something. The
    bomb wall's limit is pinned above, in `test_a_bomb_opens_a_cracked_wall_and_the_
    wall_closes_again`, and flips in item 3.3.
    """

    SET_ID = "zelda_slice"

    def _context(self):
        return {"player": self.player, "world": self.world}

    # FLIP in item 3.2: a key is spent at the commit point, once.
    def test_limit_a_key_is_never_consumed(self):
        self.at("mossroot", "mossy_gallery")
        self.give("item_key_mossroot")
        self.say("go west")
        self.assertEqual("mossroot:boss_hall", self.where())
        self.assertTrue(self.holds("item_key_mossroot"), "the door opened and the key is still in the pack")

    # FLIP in item 5.2: a placed hostile with an authored respawn_cooldown comes back.
    def test_limit_a_placed_hostile_never_respawns(self):
        self.kill("slime_blob", "blob")
        self.tick(9200)  # 920 s of game time, five times the blob's authored 180
        self.assertEqual([], self.npcs("slime_blob"))

    # FLIP in item 5.1: a template's own max_health is the maximum.
    def test_limit_a_template_max_health_is_ignored(self):
        template = self.world.npc_templates["slime_blob"]
        template["max_health"] = 777
        self.addCleanup(template.pop, "max_health", None)
        npc = NPCFactory.create_npc_from_template("slime_blob", self.world, "probe_blob")
        self.assertNotEqual(777, npc.max_health)

    # FLIP in item 5.3: a hazard a fresh hero shrugs off draws a validator warning.
    def test_limit_a_hazard_below_the_resistance_draws_no_warning(self):
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        package = scratch / "zelda_slice"
        shutil.copytree(REPO_ROOT / "content_sets" / "zelda_slice", package, ignore=shutil.ignore_patterns("saves", "editor"))
        vault = package / "data" / "regions" / "drowned_vault.json"
        region = json.loads(vault.read_text(encoding="utf-8"))
        region["rooms"]["flooded_hall"]["properties"]["hazards"] = [{"type": "poison_gas", "damage": 1}]
        vault.write_text(json.dumps(region), encoding="utf-8")
        _definition, issues = validator.load_content_set(package)
        about_it = [issue.message for issue in issues if "flooded_hall" in issue.message and "hazard" in issue.message.lower()]
        self.assertEqual([], about_it)


class TestPersistence(unittest.TestCase):
    """A single-player story keeps its character and its world across a restart.

    This is the pin `test_limit_a_restart_forgets_the_character_and_the_lever` turned
    over: the running server used to persist nothing (both transports built an
    in-memory database, and nothing read a saved character back).
    """

    def _db(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)  # registered first, runs last
        return str(Path(scratch) / "state.sqlite3")

    def _boot(self, set_id, db, **options):
        return HeadlessServer(
            db_path=db,
            content_set_path=str(REPO_ROOT / "content_sets" / set_id),
            deterministic_test_mode=True,
            default_presentation_mode="player",
            **options,
        )

    def _join(self, server, name, player_id):
        session = server.create_session(player_id=player_id).session_id
        events = server.execute_command(session, "char create %s" % name)
        text = _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in events if e.get("type") == "text"))
        return session, text

    def _say(self, server, session, command):
        events = server.execute_command(session, command)
        return _MARKUP.sub("", "\n".join(str(e.get("payload")) for e in events if e.get("type") in ("text", "error")))

    def _holds(self, player, item_id):
        return any(slot.item and slot.item.obj_id == item_id for slot in player.inventory.slots)

    def test_zelda_keeps_the_character_the_lever_and_the_pack(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = "caves", "hermit_cave"
        self._say(first, sid, "talk hermit")
        self._say(first, sid, "reply 1")
        hero.current_region_id, hero.current_room_id = "mossroot", "root_hall"
        self._say(first, sid, "pull loose stone")
        self.assertIn("down", first.world.get_region("mossroot").get_room("root_hall").exits)
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid2, welcome = self._join(second, "Restarter", "a-different-transport-id")
        self.assertIn("Welcome back", welcome)
        again = second.get_player_for_session(sid2)
        self.assertTrue(self._holds(again, "item_wooden_sword"))
        self.assertTrue(again.flags.get("got_the_sword"))
        self.assertEqual(("mossroot", "root_hall"), (again.current_region_id, again.current_room_id))
        self.assertIn("down", second.world.get_region("mossroot").get_room("root_hall").exits,
                      "the lever's door is still open")

    def test_a_vanished_hermit_is_still_gone_after_a_restart(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = "caves", "hermit_cave"
        for command in ("talk hermit", "reply 1", "reply 1", "talk hermit", "reply 2"):
            self._say(first, sid, command)
        self.assertEqual([], [n for n in first.world.npcs.values() if n.template_id == "hermit"])
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Restarter", "another-id")
        again = second.get_player_for_session(sid2)
        self.assertEqual([], [n for n in second.world.npcs.values() if n.template_id == "hermit"],
                         "the static placement is not put back over the world's own memory")
        self.assertTrue(again.flags.get("hermit_gone"))

    def test_an_unmasked_chancellor_is_still_a_fiend_after_a_restart(self):
        db = self._db()
        first = self._boot("ff4_slice", db)
        sid, _ = self._join(first, "Caelan", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = "varenholt", "throne_room"
        self._say(first, sid, "talk chancellor")
        self._say(first, sid, "reply 1")
        first.shutdown()

        second = self._boot("ff4_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Caelan", "another-id")
        fiends = [n for n in second.world.npcs.values() if n.template_id == "chancellor_fiend" and n.is_alive]
        self.assertEqual(1, len(fiends), "the fiend was spawned mid-game and is still there")
        self.assertEqual(("varenholt", "throne_room"), (fiends[0].current_region_id, fiends[0].current_room_id))
        self.assertEqual([], [n for n in second.world.npcs.values() if n.template_id == "chancellor"],
                         "and the chancellor is still gone")

    def test_a_raised_maximum_and_a_paid_rest_survive_a_restart(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.inventory.add_item(ItemFactory.create_item_from_template("item_heart_container", first.world))
        before = hero.max_health
        self._say(first, sid, "use heart container")
        self.assertEqual(before + 10, hero.max_health)
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Restarter", "another-id")
        again = second.get_player_for_session(sid2)
        self.assertEqual(before + 10, again.max_health, "a heart container is permanent")
        self.assertFalse(self._holds(again, "item_heart_container"))

    def test_ff4_keeps_the_choice_the_quest_and_a_friend_who_moved(self):
        db = self._db()
        first = self._boot("ff4_slice", db)
        sid, _ = self._join(first, "Caelan", "transport-1")
        hero = first.get_player_for_session(sid)
        self._say(first, sid, "talk king")
        self._say(first, sid, "reply 2")
        hero.current_region_id, hero.current_room_id = "varenholt", "barracks"
        self._say(first, sid, "talk kessa")
        self._say(first, sid, "reply 1")
        first.shutdown()

        second = self._boot("ff4_slice", db)
        self.addCleanup(second.shutdown)
        sid2, welcome = self._join(second, "Caelan", "another-id")
        self.assertIn("Welcome back", welcome)
        again = second.get_player_for_session(sid2)
        self.assertIs(True, again.flags.get("questioned_king"))
        self.assertIn("The King's Package", [q.get("title") for q in again.runtime_state.quests.active.values()])
        self.assertTrue(self._holds(again, "package_of_the_king"))
        self.assertFalse(self._holds(again, "item_commander_seal"))
        kessa = next(n for n in second.world.npcs.values() if n.template_id == "captain_kessa")
        self.assertEqual(("mistvale", "village_square"), (kessa.current_region_id, kessa.current_room_id))

    def test_the_last_autosave_survives_a_crash_with_no_shutdown(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        self.addCleanup(first.shutdown)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = "mossroot", "root_hall"
        self._say(first, sid, "pull loose stone")
        for _ in range(80):  # eight seconds of simulated time, past the autosave interval
            first.tick(sid)
        self.assertTrue(first.persistence.flush(5))

        second = self._boot("zelda_slice", db)  # the first server is never shut down
        self.addCleanup(second.shutdown)
        _sid, welcome = self._join(second, "Restarter", "after-the-crash")
        self.assertIn("Welcome back", welcome)
        self.assertIn("down", second.world.get_region("mossroot").get_room("root_hall").exits)

    def test_the_save_command_tells_the_truth(self):
        durable = self._boot("zelda_slice", self._db())
        self.addCleanup(durable.shutdown)
        sid, _ = self._join(durable, "Restarter", "transport-1")
        self.assertIn("saved automatically as you play", self._say(durable, sid, "save"))

        shared = self._boot("fantasy_frontier", self._db())
        self.addCleanup(shared.shutdown)
        sid, _ = self._join(shared, "Restarter", "transport-1")
        self.assertIn("does not keep progress", self._say(shared, sid, "save"))

    def test_a_different_name_is_not_given_the_saved_game(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        self._join(first, "Restarter", "transport-1")
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid, text = self._join(second, "Intruder", "transport-2")
        self.assertIn("Restarter", text)
        self.assertIn("--new-game", text)
        self.assertIsNone(second.get_player_for_session(sid))

    def test_new_game_starts_over(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        self._join(first, "Restarter", "transport-1")
        first.shutdown()

        second = self._boot("zelda_slice", db, new_game=True)
        self.addCleanup(second.shutdown)
        sid, text = self._join(second, "Somebody Else", "transport-2")
        self.assertIn("Character created", text)
        self.assertIsNotNone(second.get_player_for_session(sid))

    def test_ephemeral_keeps_nothing(self):
        db = self._db()
        first = self._boot("zelda_slice", db, ephemeral=True)
        self._join(first, "Restarter", "transport-1")
        first.shutdown()
        self.assertFalse(os.path.exists(db), "an ephemeral server writes no file")

        second = self._boot("zelda_slice", db, ephemeral=True)
        self.addCleanup(second.shutdown)
        _sid, text = self._join(second, "Restarter", "transport-2")
        self.assertIn("Character created", text)

    def test_a_shared_world_is_left_as_it_was(self):
        """Multi-player identity is not decided (Decision 7), so a shard does not resume anyone."""
        db = self._db()
        first = self._boot("fantasy_frontier", db)
        self._join(first, "Restarter", "transport-1")
        first.shutdown()

        second = self._boot("fantasy_frontier", db)
        self.addCleanup(second.shutdown)
        _sid, text = self._join(second, "Restarter", "transport-2")
        self.assertIn("Character created", text)
        self.assertNotIn("Welcome back", text)

    def test_a_save_from_a_different_version_of_the_game_is_not_overwritten(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        self._join(first, "Restarter", "transport-1")
        first.shutdown()

        from engine.server.persistence.sqlite_store import SqliteStore
        store = SqliteStore(db)
        world = store.load_world_state("world")
        world["envelope"]["content_set"]["version"] = "9.9.9"
        store.queue_world_state("world", world)
        store.close()

        second = self._boot("zelda_slice", db)
        self.assertFalse(second.durable_persistence, "the server will not write over a save it cannot read")
        self.assertTrue(any("9.9.9" in note for note in second.persistence_notices))
        second.shutdown()
        store = SqliteStore(db)
        self.addCleanup(store.close)
        self.assertEqual("9.9.9", store.load_world_state("world")["envelope"]["content_set"]["version"])


if __name__ == "__main__":
    unittest.main()
