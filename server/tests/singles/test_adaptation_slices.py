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
from tests.fixtures import skip_the_ff4_opening
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

    def kill(self, template_id, name, room=None):
        """Drop the named NPC (the one standing in `room`, if given) to one hit point and swing until it falls."""
        foe = [n for n in self.npcs(template_id) if room is None or n.current_room_id == room][0]
        self.at(foe.current_region_id, foe.current_room_id)
        foe.health = 1
        self.player.health = self.player.max_health = 500
        printed = []
        for _ in range(80):
            if not foe.is_alive:
                return " ".join(printed)
            printed.append(self.say("attack %s" % name))
            printed.append(self.tick(21))
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

    def test_the_tower_stair_is_shuttered_until_its_guard_is_dead(self):
        """A kill-all room: the way up is a `room_clear` condition, not a key."""
        self.at("dread_tower", "throne_stair")
        refused = self.say("go up")
        self.assertEqual("dread_tower:throne_stair", self.where())
        self.assertIn("shutters", refused)
        self.kill("bone_soldier", "bone", room="throne_stair")
        self.at("dread_tower", "throne_stair")
        self.say("go up")
        self.assertEqual("dread_tower:malgrath_hall", self.where())

    def test_a_room_that_fills_again_shuts_the_stair_again(self):
        """`room_clear` is stateless: it is asked afresh, so a new guard closes the way."""
        self.at("dread_tower", "throne_stair")
        self.kill("bone_soldier", "bone", room="throne_stair")
        self.at("dread_tower", "throne_stair")
        self.world.spawn_npc("bone_soldier", "dread_tower", "throne_stair", instance_id="soldier_again")
        self.say("go up")
        self.assertEqual("dread_tower:throne_stair", self.where())

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

    def test_the_wyrms_hall_sets_a_scene_once_for_each_player(self):
        self.at("mossroot", "mossy_gallery")
        self.give("item_key_mossroot")
        first = self.say("go west")
        self.assertIn("Something vast lifts its head", first)
        self.player.runtime_state.combat.in_combat = False
        self.at("mossroot", "mossy_gallery")
        self.assertNotIn("Something vast", self.say("go west"), "a scene plays once")

    def test_the_boss_door_seals_behind_you_and_opens_when_the_wyrm_dies(self):
        self.at("mossroot", "mossy_gallery")
        self.give("item_key_mossroot")
        self.say("go west")
        hall = self.world.get_region("mossroot").get_room("boss_hall")
        self.assertNotIn("east", hall.exits, "the way back is sealed")
        self.assertIn("cannot go", self.say("go east"))
        printed = self.kill("horned_wyrm", "wyrm")
        self.assertIn("door grinds open", printed)
        self.assertIn("east", hall.exits, "and the wyrm's death reopens it")
        self.at("mossroot", "boss_hall")
        self.say("go east")
        self.assertEqual("mossroot:mossy_gallery", self.where())

    def test_the_shutters_announce_themselves_when_the_stair_is_cleared(self):
        self.at("dread_tower", "throne_stair")
        printed = self.kill("bone_soldier", "bone", room="throne_stair")
        self.assertIn("shutters shudder", printed)

    def test_the_tower_gate_swings_open_as_if_it_had_been_waiting(self):
        self.at("aldermark", "tower_approach")
        self.give("item_triad")
        self.assertIn("as if it had been waiting", self.say("go north"))

    def test_the_sage_sends_you_to_the_tower_only_once_the_triad_is_forged(self):
        self.at("aldermark", "village_green")
        self.player.flags["campaign_begun"] = True
        self.assertNotIn("Send me to the tower", self.say("talk sage"))
        self.say("reply 1")   # "Not yet."
        self.player.flags["triad_forged"] = True
        offered = self.say("talk sage")
        self.assertIn("Send me to the tower", offered)
        self.say("reply 1")
        self.assertEqual("aldermark:tower_approach", self.where())

    def test_the_campaign_waits_at_the_forge_until_the_sage_forges_the_triad(self):
        self.at("aldermark", "village_green")
        self.say("talk sage")
        self.say("reply 1")   # "Tell me what to do."
        campaign = self.player.runtime_state.quests.active_campaigns["restore_the_triad"]
        campaign["current_node"] = "forge"   # both shard quests done
        self.give("item_shard_courage")
        self.give("item_shard_wisdom")
        self.assertNotIn("The Black Tower", self.quest_states(), "the tower waits on the sage, not on the second shard")
        self.assertEqual("forge", campaign["current_node"])
        self.say("talk sage")
        self.say("reply 1")   # "I have both shards."
        self.assertEqual("tower", campaign["current_node"], "forging the Triad is what moves the campaign on")
        self.assertIn("The Black Tower", self.quest_states())

    def test_a_small_key_is_spent_by_the_door_it_opens(self):
        self.at("mossroot", "mossy_gallery")
        refused = self.say("go east")
        self.assertEqual("mossroot:mossy_gallery", self.where())
        self.assertIn("barred", refused)
        self.give("item_small_key")
        opened = self.say("go east")
        self.assertEqual("mossroot:key_chamber", self.where())
        self.assertFalse(self.holds("item_small_key"), "the key is spent")
        self.assertIn("spend the small key", opened)
        self.say("go west")
        self.say("go east")
        self.assertEqual("mossroot:key_chamber", self.where(), "and the door then stays open for this player")

    def test_two_small_keys_open_two_doors_and_no_more(self):
        self.give("item_small_key")
        self.give("item_small_key")
        self.at("mossroot", "mossy_gallery")
        self.say("go east")
        self.at("drowned_vault", "flooded_hall")
        self.say("go east")
        self.assertEqual("drowned_vault:cistern", self.where())
        self.assertFalse(self.holds("item_small_key"))

    def test_a_boss_key_is_kept_and_a_small_key_is_not(self):
        """Boss doors are room locks (`locked_by`) and keep their key; small-key doors spend it."""
        self.at("mossroot", "mossy_gallery")
        self.give("item_key_mossroot")
        self.say("go west")
        self.assertEqual("mossroot:boss_hall", self.where())
        self.assertTrue(self.holds("item_key_mossroot"))

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

    def test_a_bomb_opens_a_cracked_wall_and_the_wall_stays_open(self):
        self.at("drowned_vault", "bomb_chamber")
        self.say("go north")
        self.assertEqual("drowned_vault:bomb_chamber", self.where())
        magic = self.player.runtime_state.magic
        magic.known_spells.add("bomb")
        magic.mana = magic.max_mana = 100
        self.assertIn("bursts", self.say("cast bomb on here"))
        self.say("go north")
        self.assertEqual("drowned_vault:key_niche", self.where())
        # The reaction is `permanent`: a bombed wall stays bombed, however long you
        # leave it (it used to close again after its 120 s).
        self.say("go south")
        self.tick(1300)
        self.say("go north")
        self.assertEqual("drowned_vault:key_niche", self.where())

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

    # Flipped by item 5.1: a template's own max_health is the maximum.
    def test_a_template_max_health_is_the_maximum(self):
        template = self.world.npc_templates["slime_blob"]
        template["max_health"] = 777
        self.addCleanup(template.pop, "max_health", None)
        npc = NPCFactory.create_npc_from_template("slime_blob", self.world, "probe_blob")
        self.assertEqual(777, npc.max_health)
        self.assertEqual(777, npc.health, "and it starts at full, not wounded")

    def test_the_slices_state_their_monsters_health_rather_than_solving_for_constitution(self):
        for template_id in ("horned_wyrm", "malgrath"):
            template = self.world.npc_templates[template_id]
            self.assertIn("max_health", template)
            self.assertNotIn("health", template)
            npc = NPCFactory.create_npc_from_template(template_id, self.world, "probe_" + template_id)
            self.assertEqual((template["max_health"], template["max_health"]), (npc.max_health, npc.health))

    # Flipped by item 5.2: a placed hostile with an authored respawn_cooldown comes back.
    def test_a_placed_monster_refills_the_dungeon_once_the_player_has_left(self):
        self.kill("slime_blob", "blob")
        self.tick(9200)  # 920 s of game time, five times the blob's authored 180
        self.assertEqual([], self.npcs("slime_blob"), "not while the player is standing where it fell")
        self.at("aldermark", "village_green")
        self.tick(10)
        self.assertEqual(1, len(self.npcs("slime_blob")), "and it is back when the room is empty")

    def test_a_dungeon_boss_stays_dead(self):
        self.kill("horned_wyrm", "wyrm")
        self.at("aldermark", "village_green")
        self.tick(9200)
        self.assertEqual([], self.npcs("horned_wyrm"))

    def test_the_fairy_will_come_along_and_the_pool_heals_her_too_only_while_she_is_with_you(self):
        from engine.npcs import companions

        fairy = self.npcs("pool_fairy")[0]
        self.at(fairy.current_region_id, fairy.current_room_id)
        self.say("talk fairy")
        self.say("reply 2")   # "Come with me."
        self.assertEqual([fairy], companions.companions_of(self.world, self.player))
        self.assertEqual(1, companions.max_companions(self.world), "one companion at a time in this world")
        fairy.health = 1
        self.player.health = 1
        self.say("talk fairy")
        self.say("reply 1")   # bathe
        self.assertEqual(fairy.max_health, fairy.health)
        self.assertEqual(self.player.max_health, self.player.health)


class TestFF4Slice(_Slice):
    SET_ID = "ff4_slice"

    def setUp(self):
        super().setUp()
        skip_the_ff4_opening(self.world, self.player)   # these tests begin at the king; the opening has its own

    def _question_the_king(self):
        self.say("talk king")
        self.say("reply 2")

    def _let_scenes_play(self, seconds=90):
        """A scene is told over several moments; let them pass."""
        for _ in range(seconds):
            self.world.clock.advance(1.0)
            self.server.tick(self.sid)

    def _kessa_joins(self):
        """Kessa, in the player's room, as a companion."""
        kessa = self.npcs("captain_kessa")[0]
        kessa.current_region_id, kessa.current_room_id = self.player.current_region_id, self.player.current_room_id
        apply_effects({"recruit": "captain_kessa"}, {"player": self.player, "world": self.world})

    def test_the_king_seals_the_package_in_a_scene_before_the_first_quest(self):
        self.say("talk king")
        printed = self.say("reply 1")   # "At once, my king."
        self.assertIn("presses his seal", printed)
        self.assertIn("The King's Package", self.quest_states(), "the cutscene hands straight on to the quest")

    def test_the_kings_first_audience_says_how_to_answer(self):
        self.assertIn("reply <number>", self.say("talk king"))

    def test_a_reply_reads_as_a_transcript_not_a_new_conversation(self):
        opening = self.say("talk king")
        self.assertIn('King Aldous speaks: "The Water Crystal, at last', opening, "an opening reads like every other line")
        self.assertNotIn("CONVERSATION WITH", opening)
        self.assertIn("reply <number>", opening)
        answered = self.say("reply 3")
        lines = [line for line in answered.splitlines() if line.strip()]
        self.assertEqual('You reply: "Tell me again what the package is."', lines[0], "what you said comes first, without its number")
        self.assertIn('King Aldous speaks: "It is a gift for the mayor. Nothing more."', answered)
        self.assertNotIn("CONVERSATION WITH", answered, "no header the second time round")
        self.assertNotIn("reply <number>", answered, "and no repeated instructions")
        self.assertIn("1. I will go.", answered, "the next replies are still numbered")

    def test_ending_a_conversation_says_what_you_said(self):
        self.say("talk king")
        self.say("reply 3")
        ending = self.say("reply 1")
        self.assertIn('You reply: "I will go."', ending)
        self.assertNotIn("conversation ends", ending)

    def test_the_king_has_the_last_word_when_you_obey(self):
        self.say("talk king")
        answered = self.say("reply 1")
        self.assertIn('King Aldous speaks: "Good. You will leave first thing tomorrow', answered)
        self.assertIn("Find her in the barracks to discuss", answered, "and he points you at Kessa")
        self.assertNotRegex(answered, r"(?m)^\s*1\. ", "there is nothing left to answer")
        self.assertNotIn("(That seems to be all.)", answered)
        self.at("varenholt", "throne_room")
        self.assertIn("You have your orders", self.say("talk king"), "and the conversation really is over: talking again opens a new one")

    def test_the_king_has_the_last_word_when_he_dismisses_you(self):
        self.say("talk king")
        answered = self.say("reply 2")
        self.assertIn("you are no captain of mine", answered.lower().replace("then you", "you"))
        self.assertNotRegex(answered, r"(?m)^\s*1\. ")

    def test_the_sealed_package_is_as_heavy_as_it_is_said_to_be(self):
        self.say("talk king")
        self.say("reply 1")
        package = next(slot.item for slot in self.player.inventory.slots if slot.item and slot.item.name.lower() == "sealed package")
        self.assertGreaterEqual(package.weight, 3, "heavier than it looks, so not a third of a pound")

    def test_the_king_does_not_repeat_his_greeting_once_he_has_spoken(self):
        first = self.say("talk king")
        self.assertIn("The Water Crystal, at last", first)
        self.say("reply 4")   # "I will go." agrees, and the guards walk you out
        self.at("varenholt", "throne_room")   # (the door is shut to a player; this puts him back to ask again)
        again = self.say("talk king")
        self.assertNotIn("The Water Crystal, at last", again)
        self.assertIn("You have your orders", again)
        self.assertNotIn("slaughter", again, "the choices that settled things are not offered again")

    def test_the_king_remembers_that_you_obeyed_or_questioned_him(self):
        self.say("talk king")
        self.say("reply 1")
        self.at("varenholt", "throne_room")
        self.assertIn("You have your orders", self.say("talk king"))

    def test_a_captain_who_questioned_the_king_is_greeted_differently(self):
        self._question_the_king()
        self.at("varenholt", "throne_room")
        again = self.say("talk king")
        self.assertIn("Deliver the package, courier", again)
        self.assertNotIn("The Water Crystal, at last", again)

    def test_questioning_the_king_costs_the_seal_and_is_remembered(self):
        self.assertTrue(self.holds("item_commander_seal"))
        self._question_the_king()
        self.assertFalse(self.holds("item_commander_seal"))
        self.assertIs(True, self.player.flags.get("questioned_king"))
        self.assertIn("The King's Package", self.quest_states())
        self.assertTrue(self.holds("package_of_the_king"), "a courier run hands you its package")
        self.assertEqual("varenholt:courtyard", self.where(), "the guards march you out")
        self.at("varenholt", "throne_room")
        self.assertNotIn("slaughter", self.say("talk king"), "the choice cannot be made twice")

    def test_defying_the_king_gets_you_marched_out_and_the_arrival_is_read_last(self):
        self.at("varenholt", "throne_room")
        self.say("talk king")
        said = self.say("reply 2")
        self.assertEqual("varenholt:courtyard", self.where())
        self.assertIn("march you out", said)
        self.assertLess(said.index("march you out"), said.upper().index("CASTLE COURTYARD"),
                        "the guards first, and then where you now are")

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

    def test_the_court_falls_silent_the_first_time_you_come_back_in(self):
        self.at("varenholt", "courtyard")
        self.assertIn("The banners hang motionless", self.say("go north"))
        self.say("go south")
        self.assertNotIn("The banners hang motionless", self.say("go north"))

    def test_the_fog_ambush_springs_once_for_the_whole_world(self):
        self.at("road", "fogreach_mouth")
        first = self.say("go in")
        self.assertIn("something small and red grins", first)
        imps = [n for n in self.npcs("cave_imp") if n.obj_id == "imp_ambush"]
        self.assertEqual(1, len(imps))
        self.assertEqual(("fogreach", "entry"), (imps[0].current_region_id, imps[0].current_room_id))
        self.say("go out")
        again = self.say("go in")
        self.assertNotIn("grins", again)
        self.assertEqual(1, len([n for n in self.npcs("cave_imp") if n.obj_id == "imp_ambush"]), "no second imp")

    def test_the_fog_drake_unravelling_starts_a_scene(self):
        self.world.spawn_npc("fog_drake", "fogreach", "fog_hollow", instance_id="drake_probe")
        printed = self.kill("fog_drake", "drake")
        self.assertIn("comes apart into long grey ribbons", printed)
        self.assertIs(True, self.player.flags.get("drake_slain"))

    def _into_the_hollow(self):
        apply_effects({"give_rewards": {"xp": 250}}, {"player": self.player, "world": self.world})
        self.player.health = self.player.max_health
        self.at("fogreach", "fog_gallery")
        self.player.flags["exit_warned:fogreach:fog_gallery:south"] = True
        self._kessa_joins()
        self.say("go south")
        self._let_scenes_play(16)
        return self.npcs("fog_drake")[0]

    def test_the_fog_drake_alternates_between_solid_and_mist_and_kessa_says_so(self):
        from engine.npcs import phases

        drake = self._into_the_hollow()
        self.assertEqual(["solid", "mist"], [p["name"] for p in phases.phases_of(drake)])
        told = []
        seen = set()
        for _ in range(60):
            self.world.clock.advance(1.0)
            told += [str(e["payload"]) for e in self.server.tick(self.sid) + self.server._flush_background_batch(self.sid) if e["type"] == "text"]
            seen.add(phases.is_untouchable(drake))
        text = _MARKUP.sub("", chr(10).join(told))
        self.assertEqual({True, False}, seen, "it is sometimes touchable and sometimes not")
        self.assertIn("thins into mist", text)
        self.assertIn("scales harden", text)
        self.assertIn("Captain Kessa shouts", text, "and Kessa reads the fight aloud")

    def test_swinging_at_the_mist_costs_health_and_waiting_for_it_to_harden_does_not(self):
        from engine.npcs import phases

        drake = self._into_the_hollow()
        for _ in range(40):   # to its mist
            if phases.is_untouchable(drake):
                break
            self._let_scenes_play(1)
        self.assertTrue(phases.is_untouchable(drake))
        health, drake_health = self.player.health, drake.health
        said = self.say("attack drake")
        self.assertIn("passes through the mist", said)
        self.assertLess(self.player.health, health, "the drake's breath answers the blow")
        self.assertEqual(drake_health, drake.health, "and the blow did nothing")

    def test_the_fog_drake_is_beaten_by_striking_only_while_it_is_solid(self):
        from engine.npcs import phases

        drake = self._into_the_hollow()
        for _ in range(240):
            self._let_scenes_play(1)
            if not drake.is_alive or not self.player.is_alive:
                break
            if self.player.health < 0.4 * self.player.max_health:
                self.say("use potion")
            if not phases.is_untouchable(drake):
                self.say("attack drake")
        self.assertTrue(self.player.is_alive, "the hero survives a fight fought sensibly")
        self.assertFalse(drake.is_alive, "and the drake falls")
        self.assertIs(True, self.player.flags.get("drake_slain"))

    def test_the_cave_warns_three_times_and_each_warning_stops_the_first_try_south(self):
        for room, after, spoken in (("crystal_pool", "narrow_ledge", "turn back"), ("narrow_ledge", "fog_gallery", "Go back"),
                                    ("fog_gallery", "fog_hollow", "last chance to turn back")):
            self.at("fogreach", room)
            first = self.say("go south")
            self.assertEqual("fogreach:" + room, self.where(), "the first try is stopped: " + room)
            self.assertNotIn(spoken, first, "and the warning is told slowly, not at once")
            self.assertIn(spoken, self._let_scenes_play_told(20))
            self.say("go south")
            self.assertEqual("fogreach:" + after, self.where(), "the second goes through: " + room)
            if after == "fog_hollow":
                continue   # the hollow's own scene holds the player; there is no second visit
            self.at("fogreach", room)
            self.say("go south")
            self.assertEqual("fogreach:" + after, self.where(), "and is never warned again: " + room)

    def test_the_cave_has_treasure_worth_a_detour(self):
        for room, item in (("guano_nook", "item_traveller_cache"), ("crystal_alcove", "item_iron_chest_fogreach"),
                           ("echo_niche", "item_dead_scout_pack")):
            found = self.world.get_region("fogreach").get_room(room)
            self.assertTrue(any(i.obj_id == item for i in found.items), (room, item))

    def test_the_hollow_closes_behind_you_and_the_fog_becomes_the_drake(self):
        self.at("fogreach", "fog_gallery")
        self.player.flags["exit_warned:fogreach:fog_gallery:south"] = True   # the warning has its own test
        self.assertEqual([], self.npcs("fog_drake"))
        self.say("go south")
        self.assertEqual("fogreach:fog_hollow", self.where())
        self._let_scenes_play(20)
        drake = self.npcs("fog_drake")
        self.assertEqual(1, len(drake))
        self.assertEqual(("fogreach", "fog_hollow"), (drake[0].current_region_id, drake[0].current_room_id))
        hollow = self.world.get_region("fogreach").get_room("fog_hollow")
        self.assertNotIn("north", hollow.exits, "the way back is gone")
        self.assertNotIn("down", hollow.exits, "and the way on is not open yet")
        self.say("go north")
        self.assertEqual("fogreach:fog_hollow", self.where(), "locked in with it")

    def test_the_drake_dying_opens_the_way_down_to_the_village(self):
        self.at("fogreach", "fog_gallery")
        self.player.flags["exit_warned:fogreach:fog_gallery:south"] = True
        self.say("go south")
        self._let_scenes_play(20)
        self.kill("fog_drake", "drake")
        self._let_scenes_play(20)
        hollow = self.world.get_region("fogreach").get_room("fog_hollow")
        self.assertEqual("hazevale:valley_path", hollow.exits.get("down"))
        self.assertIn("north", hollow.exits)
        self.say("go down")
        self.assertEqual("hazevale:valley_path", self.where())

    def test_the_castle_gate_stays_shut_until_kessa_rides_with_you(self):
        self.at("varenholt", "castle_gate")
        refused = self.say("go south")
        self.assertEqual("varenholt:castle_gate", self.where())
        self.assertIn("Not alone, captain", refused)
        self.assertIn("Captain Kessa goes with you", refused)
        self.at("varenholt", "throne_room")
        self._question_the_king()   # either answer: the king has given his orders
        self.at("varenholt", "castle_gate")
        self.assertIn("Not alone, captain", self.say("go south"), "the king alone is not enough")
        self.assertEqual("varenholt:castle_gate", self.where())
        self.player.flags["kessa_joined"] = True
        self.assertIn("Not alone, captain", self.say("go south"), "having once agreed is not the same as being beside you")
        self._kessa_joins()
        self.say("go south")
        self.assertEqual("road:castle_road", self.where())

    def test_the_way_out_of_the_castle_runs_the_same_way_both_ways(self):
        self.at("varenholt", "courtyard")
        self.player.flags["king_ordered"] = True
        self._kessa_joins()
        self.say("go south")
        self.assertEqual("varenholt:castle_gate", self.where(), "the courtyard leads south to the gate")
        self.say("go south")
        self.assertEqual("road:castle_road", self.where(), "the gate leads on south to the road")
        self.say("go north")
        self.assertEqual("varenholt:castle_gate", self.where(), "and the road leads back north to the gate")
        self.say("go north")
        self.assertEqual("varenholt:courtyard", self.where(), "and the gate back north to the courtyard")

    def test_the_chancellor_cannot_be_unmasked_at_the_start(self):
        """Early on the king is the only way into the story, and a fiend loose in his hall could end it."""
        self.at("varenholt", "throne_room")
        said = self.say("talk chancellor")
        self.assertNotIn("Your smile does not reach your eyes", said)
        self.say("reply 1")
        self.assertEqual(1, len(self.npcs("chancellor")))
        self.assertEqual([], self.npcs("chancellor_fiend"))

    def test_after_the_drake_the_guards_let_you_back_into_the_throne_room(self):
        self._question_the_king()
        self.assertIn("guards", self.say("go north"))
        self.assertEqual("varenholt:courtyard", self.where())
        self.player.flags["drake_slain"] = True
        self.say("go north")
        self.assertEqual("varenholt:throne_room", self.where())

    def test_the_chancellor_unmasks_into_a_fiend(self):
        self.at("varenholt", "throne_room")
        self.player.flags["drake_slain"] = True   # the story has reached the point where it can happen
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
        self.player.flags["drake_slain"] = True
        self.say("talk chancellor")
        self.say("reply 1")
        self.kill("chancellor_fiend", "thing")
        self.assertEqual([], self.npcs("chancellor_fiend"))
        self.tick(400)
        self.assertEqual([], self.npcs("chancellor_fiend"), "a fiend that was killed is not brought back")
        self.assertEqual([], self.npcs("chancellor"), "and the chancellor never returns")

    def test_the_inn_is_a_room_you_go_in_to_not_a_direction_on_the_compass(self):
        self.at("hazevale", "village_square")
        self.assertIn("in", self.world.get_current_room(self.player).exits)
        self.say("go in")
        self.assertEqual("hazevale:inn", self.where())
        self.assertEqual(1, len(self.npcs("innkeeper")))
        self.assertEqual(("hazevale", "inn"), (self.npcs("innkeeper")[0].current_region_id, self.npcs("innkeeper")[0].current_room_id))
        self.say("go out")
        self.assertEqual("hazevale:village_square", self.where())

    def test_the_mayor_has_small_talk_for_someone_with_no_errand(self):
        self.at("hazevale", "village_square")
        self.assertIn("Travellers are rare", self.say("talk mayor"))

    def test_the_mayor_asks_for_the_package_of_someone_sent_with_it(self):
        self._question_the_king()   # either answer: the king puts the package in your hands
        self.at("hazevale", "village_square")
        said = self.say("talk mayor")
        self.assertIn("A messenger from the king?", said)
        self.assertIn("give sealed package to mayor", said, "and says how to hand it over")

    STARTER_MONSTERS = ("goblin_scout", "road_wolf", "cave_bat", "cave_imp", "thorn_wolf", "dune_jackal", "storm_wyvern", "thunderhawk")

    def _hits(self, attacker, defender, power, count=150):
        from engine.core.combat_system import CombatSystem

        results = []
        saved = defender.health
        for _ in range(count):
            defender.health = 10 ** 6
            results.append(defender.take_damage(CombatSystem.calculate_physical_damage(attacker, defender, power), "physical"))
        defender.health = saved
        return results

    def test_every_starter_enemy_hurts_the_hero_and_kessa_a_little_with_every_hit_that_lands(self):
        kessa = self.npcs("captain_kessa")[0]
        for template in self.STARTER_MONSTERS:
            monster = NPCFactory.create_npc_from_template(template, self.world, instance_id="probe_" + template)
            for victim, name in ((self.player, "the hero"), (kessa, "Kessa")):
                taken = self._hits(monster, victim, monster.attack_power)
                self.assertGreaterEqual(min(taken), 1, "%s never does nothing to %s" % (template, name))
                self.assertLess(sum(taken) / len(taken), 12, "and only a little: %s to %s" % (template, name))

    def test_nobody_one_shots_a_starter_enemy_not_the_hero_with_his_blade_or_gloom_wave_and_not_kessa(self):
        kessa = self.npcs("captain_kessa")[0]
        wave = self.world.spells["gloom_wave"] if hasattr(self.world, "spells") else None
        wave_damage = 40
        for template in self.STARTER_MONSTERS:
            monster = NPCFactory.create_npc_from_template(template, self.world, instance_id="probe_" + template)
            blade = max(self._hits(self.player, monster, self.player.get_attack_power()))
            spear = max(self._hits(kessa, monster, kessa.attack_power))
            for blow, who in ((blade, "the blade"), (spear, "Kessa's spear"), (wave_damage, "Gloom Wave")):
                self.assertLess(blow, monster.max_health, "%s must not kill a %s in one go (%d of %d)" % (who, template, blow, monster.max_health))

    def test_kessa_carries_potions_of_her_own(self):
        kessa = self.npcs("captain_kessa")[0]
        carried = sum(slot.quantity for slot in kessa.inventory.slots if slot.item and slot.item.obj_id == "item_potion")
        self.assertGreaterEqual(carried, 2)

    def test_what_the_player_says_is_coloured_apart_from_what_everyone_else_says(self):
        self.say("talk king")
        raw = chr(10).join(str(e["payload"]) for e in self.server.execute_command(self.sid, "reply 3"))
        self.assertIn('[[BLUE]]"Tell me again what the package is."[[/]]', raw, "the player's words are blue (the NPCs' are green)")

    def test_every_quoted_line_in_the_shrine_scenes_is_coloured_by_who_speaks(self):
        scenes = json.loads((REPO_ROOT / "content_sets" / "ff4_slice" / "data" / "scenes" / "hazevale.json").read_text(encoding="utf-8"))
        for scene_id in ("kessa_deduces", "colossus_quake", "wake_in_the_wood", "reach_the_inn"):
            for beat in scenes[scene_id]["beats"]:
                text = beat.get("text", "")
                uncoloured = re.sub(r"\[\[(GREEN|BLUE)\]\].*?\[\[/\]\]", "", text)   # speech that has its colour is taken out
                self.assertNotIn('"', uncoloured, "a quotation with no colour: " + text[:80])

    def test_the_inn_charges_for_a_room_and_restores_the_traveller(self):
        self.at("hazevale", "inn")
        magic = self.player.runtime_state.magic
        self.player.runtime_state.gold = 50
        self.player.health, magic.mana = 1, 0
        self.say("talk innkeeper")
        said = self.say("reply 1")
        self.assertEqual(20, self.player.runtime_state.gold)
        self.assertEqual(self.player.max_health, self.player.health)
        self.assertEqual(magic.max_mana, magic.mana)
        self.assertIn("sleep", said)

    def _companions(self):
        from engine.npcs import companions

        return [n.template_id for n in companions.companions_of(self.world, self.player)]

    def test_kessa_sends_you_to_bed_and_waits_for_dawn(self):
        self.say("talk king")
        self.say("reply 1")
        self.at("varenholt", "barracks")
        said = self.say("talk kessa")
        self.assertIn("Did you speak to him", said)
        self.assertIn("leave at dawn", self.say("reply 1"))
        self.assertTrue(self.player.flags.get("kessa_briefed"))
        again = self.say("talk kessa")
        self.assertIn("Sleep first", again, "she does not ask you again, or say anything else yet")
        self.assertEqual([], self._companions())

    def test_the_night_in_your_quarters_brings_dawn_and_kessa_to_the_gate(self):
        self.player.flags["kessa_briefed"] = True
        self.player.flags["king_ordered"] = True
        self.at("varenholt", "barracks")
        self.say("go north")
        self.assertEqual("varenholt:quarters", self.where())
        for _ in range(40):   # the night is told over a few seconds
            self.world.clock.advance(1.0)
            self.server.tick(self.sid)
        self.assertTrue(self.player.flags.get("rested_at_castle"))
        self.assertEqual(6, self.server.time_manager.hour, "the night has passed: it is six in the morning")
        kessa = self.npcs("captain_kessa")[0]
        self.assertEqual(("varenholt", "castle_gate"), (kessa.current_region_id, kessa.current_room_id), "and she is at the gate")
        self.at("varenholt", "castle_gate")
        said = self.say("talk kessa")
        self.assertIn("Are you ready", said)
        self.assertIn("Let's go, Kessa", said)
        self.say("reply 1")
        self.assertEqual(["captain_kessa"], self._companions())
        self.assertIs(True, self.player.flags.get("kessa_joined"))
        self.say("go south")
        self.assertEqual("road:castle_road", self.where(), "and the gate opens to the two of them")

    def test_the_night_is_only_for_someone_who_has_been_told_to_rest(self):
        self.at("varenholt", "barracks")
        self.say("go north")
        for _ in range(10):
            self.world.clock.advance(1.0)
            self.server.tick(self.sid)
        self.assertFalse(self.player.flags.get("rested_at_castle"), "the quarters are only a room until Kessa has spoken")

    def test_kessa_and_ryn_can_join_and_the_inn_heals_the_whole_party(self):
        self.player.flags["rested_at_castle"] = True
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")   # "Let's go, Kessa."
        self.assertEqual(["captain_kessa"], self._companions())
        ryn = self.npcs("ryn")[0]
        ryn.current_region_id, ryn.current_room_id = self.player.current_region_id, self.player.current_room_id
        apply_effects({"recruit": "ryn"}, {"player": self.player, "world": self.world})
        self.assertEqual(["captain_kessa", "ryn"], sorted(self._companions()), "the party of three has room for both")
        self.at("hazevale", "inn")
        self.player.runtime_state.gold = 50
        for npc in self.world.npcs.values():
            if npc.template_id in ("captain_kessa", "ryn"):
                npc.current_region_id, npc.current_room_id = "hazevale", "inn"
                npc.health = 1
        self.player.health = 1
        self.say("talk innkeeper")
        self.say("reply 1")
        for npc in self.world.npcs.values():
            if npc.template_id in ("captain_kessa", "ryn"):
                self.assertEqual(npc.max_health, npc.health, npc.template_id)
        self.assertEqual(self.player.max_health, self.player.health)

    def test_kessa_can_be_sent_back_to_hold_the_square(self):
        self.player.flags["rested_at_castle"] = True
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")
        self.say("talk kessa")
        self.say("reply 1")   # "Hold here, Kessa."
        self.assertEqual([], self._companions())

    def test_away_from_the_castle_kessa_just_answers_and_offers_no_reply(self):
        self.player.flags["rested_at_castle"] = True
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")
        self.at("road", "castle_road")
        kessa = self.npcs("captain_kessa")[0]
        kessa.current_region_id, kessa.current_room_id = "road", "castle_road"
        said = self.say("talk kessa")
        self.assertIn("I am right behind you", said)
        self.assertNotIn("reply <number>", said, "nothing to answer: no lone 'Nothing. Lead on.'")
        self.assertEqual(["captain_kessa"], self._companions(), "and she is still with you")

    def test_a_party_of_three_stops_at_three(self):
        from engine.npcs import companions

        self.assertEqual(3, companions.max_companions(self.world))

    def test_the_inn_does_not_offer_a_room_to_someone_who_cannot_pay(self):
        self.at("hazevale", "inn")
        self.player.runtime_state.gold = 5
        self.player.health = 1
        offered = self.say("talk innkeeper")
        self.assertNotIn("take the room", offered, "the paid choice is not shown to someone who cannot pay")
        self.assertIn("Not tonight", offered)
        self.say("reply 1")   # all that is left to say is "Not tonight."
        self.assertEqual(5, self.player.runtime_state.gold)
        self.assertLess(self.player.health, self.player.max_health // 2, "not rested (a tick of ordinary healing is not a night's sleep)")

    def test_delivering_the_package_burns_the_village(self):
        self._question_the_king()
        self.at("hazevale", "village_square")
        self.assertEqual(1, len(self.npcs("mayor_of_hazevale")))
        self.assertIn("Quest Complete", self.say("give sealed package to mayor"))
        self.assertEqual(1, len(self.npcs("mayor_of_hazevale")), "the fire takes a few told moments to start")
        self._let_scenes_play(60)
        self.assertEqual([], self.npcs("mayor_of_hazevale"), "and the mayor is not there when it is over")
        self.assertEqual("hazevale_ruin:village_square", self.where(), "you run from the fire, and stop in what it left")
        self.assertIs(True, self.player.flags.get("village_burned"))

    def _in_the_ashes(self):
        self.player.flags["village_burned"] = True
        self.at("hazevale_ruin", "shrine")
        self._kessa_joins()

    def test_ryn_tells_what_became_of_her_mother_and_kessa_works_out_the_king_s_purpose(self):
        self._in_the_ashes()
        self.assertIn("Why would you do that", self.say("talk ryn"))
        self.say("reply 1")
        told = self._let_scenes_play_told(70)
        self.assertIn("The king needed Hazevale gone", told)
        self.assertIn("That means her", told, "she would have the girl killed too")
        self.assertIn("Deserters, then", told, "and is brought round")
        self.assertIs(True, self.player.flags.get("kessa_relented"))

    def _let_scenes_play_told(self, seconds):
        heard = []
        for _ in range(seconds):
            self.world.clock.advance(1.0)
            heard += [str(e["payload"]) for e in self.server.tick(self.sid) + self.server._flush_background_batch(self.sid)
                      if e["type"] == "text"]
        return _MARKUP.sub("", chr(10).join(heard))

    def test_ryn_has_to_be_asked_three_times_and_then_she_calls_the_colossus(self):
        self._in_the_ashes()
        self.say("talk ryn")
        self.say("reply 1")
        self._let_scenes_play(70)
        for expected in ("What do you want", "Go away", "I am going to sing"):
            self.assertIn(expected, self.say("talk ryn"))
            self.assertIsNone(self.player.flags.get("_scene.colossus_quake"))
            self.say("reply 1")
        self.assertIn("_scene.colossus_quake", self.player.flags)
        told = self._let_scenes_play_told(90)
        self.assertIn("A Quake rolls out from the shrine", told)
        self.assertEqual("thornwood:clearing", self.where(), "the mountain comes down and you wake elsewhere")
        self.assertEqual([], self.npcs("colossus_minion"), "the colossus does not stay")

    def test_after_the_quake_kessa_is_gone_and_ryn_is_carried_asleep(self):
        self._in_the_ashes()
        self.player.flags.update({"ryn_told": True, "kessa_relented": True, "ryn_resisted_once": True, "ryn_resisted_twice": True})
        self.say("talk ryn")
        self.say("reply 1")
        told = self._let_scenes_play_told(120)
        self.assertNotIn("stays behind", told, "the quake scene does not announce Kessa's going")
        self.assertEqual([], [c for c in self._companions() if c == "captain_kessa"], "Kessa is nowhere to be found")
        self.assertEqual([], self.npcs("captain_kessa"), "she is not in the world at all, and nothing said that she stayed behind")
        self.assertEqual(["ryn"], self._companions(), "a party of one and the girl in your arms")
        self.assertEqual(("thornwood", "clearing"), (self.player.respawn_region_id, self.player.respawn_room_id),
                         "dying out here does not send the hero back to the first room of the story")
        self.assertIn("Mother", self.say("talk ryn"), "she is asleep, and says nothing but that")

    def _ryn_asleep_in_the_inn(self):
        apply_effects({"give_rewards": {"xp": 900}}, {"player": self.player, "world": self.world})
        self.player.health = self.player.max_health
        ryn = self.npcs("ryn")[0]
        ryn.current_region_id, ryn.current_room_id = "dunhallow", "inn"
        self.player.flags.update({"ryn_carried": True, "reached_the_inn": True})
        self.at("dunhallow", "inn")

    def test_the_kings_guards_come_for_ryn_and_the_hero_will_not_give_her_up(self):
        self._ryn_asleep_in_the_inn()
        self.world.scene_runner.play(self.player, "guards_arrive")
        told = self._let_scenes_play_told(50)
        self.assertIn("The king wants the girl", told)
        self.assertIn("She stays with me", told, "the hero refuses")
        self.assertEqual(1, len(self.npcs("pursuit_sergeant")))
        self.assertEqual(2, len(self.npcs("castle_pursuer")))
        self.assertIs(True, self.player.flags.get("guards_fight"))
        self.assertEqual([], self.npcs("ryn_young"), "and Ryn sleeps on in the back room")

    def test_the_fight_with_the_guards_is_the_ordinary_kind_and_is_won_with_a_sensible_hero(self):
        self._ryn_asleep_in_the_inn()
        self.world.scene_runner.play(self.player, "guards_arrive")
        self._let_scenes_play(40)
        for _ in range(120):
            alive = self.npcs("pursuit_sergeant") + self.npcs("castle_pursuer")
            if not alive or not self.player.is_alive:
                break
            if self.player.health < 0.4 * self.player.max_health:
                self.say("use potion")
            self.say("cast gloom wave") if self.player.health > 0.5 * self.player.max_health else None
            self.say("attack " + alive[0].name)
            self._let_scenes_play(1)
        self.assertTrue(self.player.is_alive, "a hero who uses what he has beats three guards")
        self.assertEqual([], self.npcs("pursuit_sergeant") + self.npcs("castle_pursuer"))

    def test_after_the_guards_ryn_wakes_thanks_the_hero_and_joins_and_the_innkeeper_mentions_a_woman(self):
        self._ryn_asleep_in_the_inn()
        self.world.scene_runner.play(self.player, "guards_arrive")
        self._let_scenes_play(40)
        for template, name in (("pursuit_sergeant", "havel"), ("castle_pursuer", "guard"), ("castle_pursuer", "guard")):
            if self.npcs(template):
                self.kill(template, name)
        told = self._let_scenes_play_told(80)
        self.assertIn("You stood in front of them", told)
        self.assertIn("nowhere left to go", told, "she joins partly because there is nowhere else")
        self.assertEqual(["ryn_young"], self._companions())
        self.assertEqual([], self.npcs("ryn"), "the sleeper is replaced by Ryn awake")
        self.assertIn("blue shutters", told, "and a woman asking for the hero is mentioned")
        self.assertIs(True, self.player.flags.get("rosalind_hint"))

    def _in_dunhallow_after_the_guards(self):
        self.player.flags.update({"ryn_carried": True, "reached_the_inn": True, "guards_beaten": True, "rosalind_hint": True})
        self.world.spawn_npc("rosalind_sick", "dunhallow", "sickroom", instance_id="rosalind_in_bed")

    def test_the_village_is_a_real_one_with_houses_shops_and_folk(self):
        region = self.world.get_region("dunhallow")
        rooms = set(region.rooms)
        self.assertTrue({"square", "inn", "market_street", "general_store", "armorer", "date_grove", "south_lane", "orrins_house",
                         "sickroom", "potters_house", "widows_cottage"} <= rooms)
        folk = {n.template_id for n in self.world.npcs.values() if n.current_region_id == "dunhallow"}
        self.assertTrue({"water_carrier", "spice_seller", "date_picker", "lizard_child", "potter_ilse", "widow_tamsin", "pell_trader",
                         "brannoch_smith", "maren", "desert_innkeeper"} <= folk)

    def test_the_shops_sell_useful_things_and_the_prices_are_real(self):
        self.at("dunhallow", "general_store")
        self.player.runtime_state.gold = 500
        self.say("trade pell")
        self.assertIn("salve", self.say("list"))
        self.say("buy salve")
        self.assertTrue(self.holds("item_salve"))
        self.assertLess(self.player.runtime_state.gold, 500)
        self.say("stoptrade")
        self.at("dunhallow", "armorer")
        self.say("trade brannoch")
        wares = self.say("list")
        for ware in ("brass cap", "dune boots", "sun amulet", "buckler", "ash staff"):
            self.assertIn(ware, wares)
        self.assertNotIn("1 gil", wares, "nothing is given away")

    def test_old_gear_is_lying_about_for_those_who_look(self):
        self.at("dunhallow", "potters_house")
        self.say("open potter's trunk")
        self.say("get all from potter's trunk")
        self.assertTrue(self.holds("item_old_buckler"))
        self.at("dunhallow", "widows_cottage")
        self.say("open widow's chest")
        self.say("get all from widow's chest")
        self.assertTrue(self.holds("item_sun_circlet"))
        self.assertTrue(self.holds("item_traveller_boots"))

    def test_the_back_room_shows_rosalind_sick_and_says_what_will_cure_her(self):
        self._in_dunhallow_after_the_guards()
        self.at("dunhallow", "orrins_house")
        self.say("go north")
        told = self._let_scenes_play_told(60)
        self.assertIn("Rosalind.", told)
        self.assertIn("salt fever", told)
        self.assertIn("mirage pearl", told)
        self.assertIs(True, self.player.flags.get("pearl_quest"))
        self.assertIn("pearl", self.say("talk orrin") + self.say("reply 2"), "Orrin tells where it comes from")
        self.assertIs(True, self.player.flags.get("pearl_known"))

    def test_the_cutscene_is_told_only_the_first_time(self):
        self._in_dunhallow_after_the_guards()
        self.at("dunhallow", "orrins_house")
        self.say("go north")
        self._let_scenes_play(60)
        self.say("go south")
        self.say("go north")
        self.assertNotIn("Rosalind.", self._let_scenes_play_told(10))

    def test_bringing_the_pearl_cures_her(self):
        self._in_dunhallow_after_the_guards()
        self.at("dunhallow", "sickroom")
        self.give("item_mirage_pearl")
        self.say("talk orrin")
        said = self.say("reply 1")   # "Give Orrin the mirage pearl."
        self.assertFalse(self.holds("item_mirage_pearl"), "the pearl is used")
        self.assertIs(True, self.player.flags.get("rosalind_cured"))
        self.assertIn("You look terrible", self._let_scenes_play_told(40))
        self.assertIn("sitting up", self.say("talk rosalind"))

    def test_the_guards_scene_sends_rosalind_to_the_village_and_off_the_castle_chapel(self):
        self._ryn_asleep_in_the_inn()
        self.world.scene_runner.play(self.player, "guards_arrive")
        self._let_scenes_play(40)
        for template, name in (("pursuit_sergeant", "havel"), ("castle_pursuer", "guard"), ("castle_pursuer", "guard")):
            if self.npcs(template):
                self.kill(template, name)
        self._let_scenes_play(80)
        self.assertEqual([], self.npcs("rosalind"), "she has left the castle")
        sick = self.npcs("rosalind_sick")
        self.assertEqual(1, len(sick))
        self.assertEqual(("dunhallow", "sickroom"), (sick[0].current_region_id, sick[0].current_room_id))

    def _level_up_to_the_caverns(self):
        apply_effects({"give_rewards": {"xp": 2300}}, {"player": self.player, "world": self.world})   # about where the story has got the hero
        self.player.health = self.player.max_health

    def _join(self, template, region, room):
        npc = self.npcs(template)[0] if self.npcs(template) else self.world.spawn_npc(template, region, room)[0]
        npc.current_region_id, npc.current_room_id = region, room
        self.at(region, room)   # a companion is recruited from the room the player stands in
        apply_effects({"recruit": template}, {"player": self.player, "world": self.world})
        return npc

    def test_the_far_corner_of_the_desert_leads_down_to_the_brineway(self):
        self.at("saltreach", "dry_wash")
        for step in ("south", "east", "south", "east", "down"):
            self.say("go " + step)
        self.assertEqual("brineway:mouth", self.where())

    def test_the_desert_has_its_own_monsters_and_a_chest_worth_the_walk(self):
        found = {n.template_id for n in self.world.npcs.values() if n.current_region_id == "saltreach"}
        self.assertTrue({"salt_scorpion", "dune_jackal"} <= found)
        ridge = self.world.get_region("saltreach").get_room("bleached_ridge")
        self.assertTrue(any(i.obj_id == "item_ridge_chest" for i in ridge.items))

    def test_belaric_is_met_at_the_foot_of_the_sinkhole_and_joins_the_party(self):
        self.at("brineway", "mouth")
        self.world.scene_runner.play(self.player, "meet_belaric")
        told = self._let_scenes_play_told(60)
        self.assertIn("Are you lost, or only stupid?", told)
        self.assertIn("I was a sage at its court", told)
        self.assertIn("Fair?", told)
        self.assertEqual(["belaric"], self._companions())
        self.assertIs(True, self.player.flags.get("belaric_joined"))

    def test_the_midpoint_is_a_dry_hall_where_the_party_camps_and_belaric_tells_his_story(self):
        self._join("belaric", "brineway", "dry_hall")
        ryn = self._join("ryn_young", "brineway", "dry_hall")
        self.assertNotIn("lightning", ryn.usable_spells)
        self.player.flags["belaric_joined"] = True
        self.at("brineway", "tidewalk")
        self.say("go east")
        told = self._let_scenes_play_told(60)
        self.assertIn("The Dry Hall", told)
        self.assertIn("(talk belaric)", told)
        self.assertIs(True, self.player.flags.get("camp_night"))
        self.assertEqual(21, self.server.time_manager.hour, "it is night")
        said = self.say("talk belaric")
        self.assertIn("looking at me like a man with questions", said)
        why = self.say("reply 2")
        self.assertIn("Mirelle", why)
        self.assertIn("bard", why)
        self.assertIn("Lucan", why)
        self.say("reply 1")
        self.assertIn("Brinecoil", self.say("reply 1") and self.say("reply 3"), "he says what waits at the end")
        self.say("reply 1")
        self.say("reply 5")
        self.assertIs(True, self.player.flags.get("camp_done"))
        self._let_scenes_play(40)
        self.assertEqual(6, self.server.time_manager.hour, "and the night passes")
        self.assertIn("lightning", ryn.usable_spells, "and Belaric has taught Ryn the lightning he favours")

    def test_the_caverns_do_not_hold_the_pearl_they_lead_to_the_castle_that_knows_how_to_get_one(self):
        region = self.world.get_region("brineway")
        for room_id, room in region.rooms.items():
            self.assertFalse(any(i.obj_id == "item_mirage_pearl" for i in room.items), room_id)
        grotto = region.get_room("nacre_grotto")
        self.assertTrue(any(i.obj_id == "item_grotto_cache" for i in grotto.items), "the grotto is a treasure room, guarded by crabs")
        self.assertEqual(2, len([n for n in self.world.npcs.values() if n.current_room_id == "nacre_grotto" and n.template_id == "cavern_crab"]))
        told = self.say("talk orrin") if False else ""
        self.assertNotIn("Brineway", json.dumps(json.loads((REPO_ROOT / "content_sets" / "ff4_slice" / "data" / "dialogue" / "orrin_talk.json").read_text(encoding="utf-8"))["nodes"]["pearl"]),
                         "the village says the royal house of Ashmere knows, not that the pearl is here")

    def test_the_caverns_have_treasure_and_the_loop_and_side_rooms_a_dungeon_needs(self):
        region = self.world.get_region("brineway")
        self.assertGreaterEqual(len(region.rooms), 14)
        for room, item in (("eel_pool", "item_eel_chest"), ("sunken_vault", "item_vault_chest")):
            self.assertTrue(any(i.obj_id == item for i in region.get_room(room).items), (room, item))
        hall = region.get_room("hall_of_drips")
        self.assertEqual({"west", "north", "east", "south"}, set(hall.exits), "four ways on from the first hall")

    def test_the_brine_gate_warns_once_and_then_the_gallery_closes_behind_you(self):
        self._level_up_to_the_caverns()
        self.at("brineway", "brine_gate")
        self.say("go east")
        self.assertEqual("brineway:brine_gate", self.where(), "the first try is stopped")
        self.assertIn("That is the door", self._let_scenes_play_told(15))
        self.say("go east")
        self.assertEqual("brineway:brine_hollow", self.where())
        self._let_scenes_play(20)
        self.assertEqual(1, len(self.npcs("brinecoil")))
        self.assertNotIn("west", self.world.get_region("brineway").get_room("brine_hollow").exits, "no way back")

    def test_the_brinecoil_is_eight_legs_and_a_head_all_weak_to_lightning(self):
        for template in ("brinecoil", "brinecoil_leg"):
            npc = NPCFactory.create_npc_from_template(template, self.world, instance_id="probe_" + template)
            self.assertLess(npc.get_resistance("air"), 0, template + " is weak to lightning")
        leg = NPCFactory.create_npc_from_template("brinecoil_leg", self.world, instance_id="probe_leg")
        head = NPCFactory.create_npc_from_template("brinecoil", self.world, instance_id="probe_head")
        self.assertLess(leg.max_health * 4, head.max_health * 2 + 1, "a leg is a fraction of the head")
        self.assertLess(leg.attack_power, head.attack_power, "and hits for less")
        self.assertNotIn("phases", head.properties, "the head no longer surfaces and sinks: the legs are the fight")

    def test_the_brinecoil_rises_with_eight_legs_that_fight_on_their_own_and_a_head(self):
        self._level_up_to_the_caverns()
        self.at("brineway", "brine_gate")
        self.player.flags["exit_warned:brineway:brine_gate:east"] = True
        self.say("go east")
        self._let_scenes_play(25)
        self.assertEqual(8, len(self.npcs("brinecoil_leg")))
        self.assertEqual(1, len(self.npcs("brinecoil")))
        legs_in_the_fight = [n for n in self.npcs("brinecoil_leg") if n.in_combat]
        self.assertGreater(len(legs_in_the_fight), 4, "each leg attacks on its own")

    def test_the_brinecoil_is_beaten_legs_first_and_the_far_shore_opens(self):
        self._level_up_to_the_caverns()
        self.at("brineway", "brine_gate")
        self._join("belaric", "brineway", "brine_gate")
        ryn = self._join("ryn_young", "brineway", "brine_gate")
        apply_effects({"teach_companion": {"npc": "ryn_young", "spell": "lightning"}}, {"player": self.player, "world": self.world})
        self.assertIn("lightning", ryn.usable_spells)
        self.player.flags["exit_warned:brineway:brine_gate:east"] = True
        self.say("go east")
        self._let_scenes_play(17)   # the scene, and not a moment more: the legs do not wait for the hero
        head = self.npcs("brinecoil")[0]
        legs_dead_first = None
        for tick in range(300):
            self._let_scenes_play(1)
            if not head.is_alive or not self.player.is_alive:
                break
            if self.player.health < 0.4 * self.player.max_health:
                self.say("use potion")
            legs = self.npcs("brinecoil_leg")
            if legs_dead_first is None and not legs:
                legs_dead_first = head.is_alive
            if legs and tick % 7 == 0 and self.player.health > 0.45 * self.player.max_health:
                self.say("cast gloom wave")
            self.say("attack leg" if legs else "attack coil")
        self.assertTrue(self.player.is_alive, "a hero who burns the legs first and has his friends' lightning survives")
        self.assertFalse(head.is_alive)
        self.assertTrue(legs_dead_first, "the legs fell while the head still lived")
        self.assertEqual([], self.npcs("brinecoil_leg"), "and none is left standing when the head falls")
        self._let_scenes_play(15)
        self.assertIs(True, self.player.flags.get("brineway_cleared"))
        hollow = self.world.get_region("brineway").get_room("brine_hollow")
        self.assertEqual("far_shore", hollow.exits.get("up"))
        self.say("go up")
        self.assertEqual("brineway:far_shore", self.where())

    # -- Ashmere ----------------------------------------------------------------------------------------------------------------
    def test_ashmere_is_a_castle_still_under_attack_with_defenders_and_a_music_hall_and_a_boathouse(self):
        region = self.world.get_region("ashmere")
        self.assertTrue({"road", "gate", "courtyard", "great_hall", "infirmary", "music_hall", "throne_room", "boathouse"} <= set(region.rooms))
        present = {n.template_id for n in self.world.npcs.values() if n.current_region_id == "ashmere"}
        self.assertTrue({"red_fleet_besieger", "red_fleet_lancer", "ashmere_guard", "king_osric", "healer_ansa", "harp_seller", "lucan_prince", "mirelle"} <= present)
        self.at("brineway", "far_shore")
        self.say("go east")
        self.assertEqual("ashmere:road", self.where(), "the caverns lead to the castle")

    def test_the_throne_room_scene_belaric_strikes_the_prince_mirelle_dies_and_belaric_leaves_for_revenge(self):
        self._join("belaric", "ashmere", "courtyard")
        self.player.flags["belaric_joined"] = True
        self.say("go up")
        told = self._let_scenes_play_told(160)
        for line in ("I am Lucan of Ashmere", "each weaker than the last", "Father... stop. Please. Stop.", "I am not angry now",
                     "The Red Fleet. Its master is a man called Varkos", "I will find him", "Do not follow me, boy"):
            self.assertIn(line, told)
        self.assertIs(True, self.player.flags.get("mirelle_dead"))
        self.assertEqual([], self.npcs("mirelle"))
        self.assertEqual(1, len(self.npcs("mirelle_fallen")))
        self.assertEqual([], self.npcs("belaric"), "he has gone after Varkos")
        self.assertEqual([], [c for c in self._companions() if c == "belaric"])
        self.assertIn("(talk mirelle)", told)

    def test_the_scene_is_not_told_twice(self):
        self.player.flags.update({"belaric_joined": True, "mirelle_dead": True})
        self.at("ashmere", "courtyard")
        self.say("go up")
        self.assertNotIn("Father...", self._let_scenes_play_told(30))

    def test_a_last_goodbye_to_mirelle_and_then_the_prince_joins_as_a_bard(self):
        self.player.flags.update({"belaric_joined": True, "mirelle_dead": True})
        self.world.remove_npcs("mirelle")
        self.world.spawn_npc("mirelle_fallen", "ashmere", "throne_room", instance_id="mirelle_in_the_hall")
        self.at("ashmere", "throne_room")
        self.assertIn("say goodbye", self.say("talk lucan"), "he asks to say goodbye first")
        self.say("talk mirelle")
        said = self.say("reply 2")
        self.assertNotIn("speaks", said, "what happens at her side is told, not said")
        self.assertIs(True, self.player.flags.get("farewell_said"))
        self.say("talk lucan")
        self.say("reply 1")
        self.assertEqual(["lucan_prince"], self._companions())
        lucan = self.npcs("lucan_prince")[0]
        self.assertEqual({"lullaby", "discord"}, set(lucan.usable_spells), "his harp carries two songs")
        self.assertIs(True, lucan.properties.get("hides_when_hurt"))

    def test_the_music_hall_sells_harps_with_songs_attached(self):
        self.at("ashmere", "music_hall")
        self.player.runtime_state.gold = 1000
        self.say("trade ilvane")
        wares = self.say("list")
        for harp in ("oak harp", "silver harp", "war harp"):
            self.assertIn(harp, wares)
        self.say("buy silver harp")
        self.assertTrue(self.holds("item_silver_harp"))
        self.say("stoptrade")
        self.at("ashmere", "throne_room")
        lucan = self.npcs("lucan_prince")[0]
        self.player.flags.update({"farewell_said": True, "mirelle_dead": True})
        self.say("talk lucan")
        self.say("reply 1")
        self.say("equip silver harp on lucan")
        self.assertIn("hush", lucan.usable_spells, "the silver harp gives him the song of silence")

    def test_the_king_lends_the_skimmer_only_once_his_son_is_with_the_party_and_the_boathouse_is_shut_without_it(self):
        self.at("ashmere", "boathouse")
        self.assertIn("king's to lend", self.say("go north"))
        self.assertEqual("ashmere:boathouse", self.where())
        self.at("ashmere", "great_hall")
        self.assertNotIn("skimmer", self.say("talk osric"), "he says nothing of it before")
        self.player.flags["lucan_joined"] = True
        self.say("talk osric")
        self.say("reply 1")
        self.assertIs(True, self.player.flags.get("skimmer_granted"))
        self.at("ashmere", "boathouse")
        self.say("go north")
        self.assertEqual("sandsea:drift_a", self.where())
        self.assertIn("pour across", self._let_scenes_play_told(20), "the first crossing is told")

    def test_the_skimmer_crosses_the_sand_sea_to_the_glass_dunes_and_down_to_the_pit(self):
        self.player.flags["skimmer_granted"] = True
        self.at("sandsea", "drift_a")
        self.say("go west")
        self.say("go west")
        self.assertEqual("saltreach:glass_dunes", self.where(), "the shortcut home to Dunhallow's side of the desert")
        self.say("go east")
        self.assertEqual("sandsea:drift_b", self.where())
        self.at("sandsea", "drift_a")
        self.say("go north")
        self.say("go down")
        self.assertEqual("sandmaw_pit:rim", self.where())

    def test_the_glass_dunes_do_not_open_onto_the_sand_sea_on_foot(self):
        self.at("saltreach", "glass_dunes")
        self.assertIn("king's to lend", self.say("go east"))
        self.assertEqual("saltreach:glass_dunes", self.where())

    def test_the_pit_has_a_chest_a_warning_and_the_sandmaw_at_the_bottom_with_the_pearl_unfound(self):
        self.assertGreaterEqual(len(self.world.get_region("sandmaw_pit").rooms), 6)
        nest = self.world.get_region("sandmaw_pit").get_room("nest")
        self.assertEqual("warning", nest.properties["exit_requirements"]["east"]["type"])
        self.assertFalse(self.holds("item_mirage_pearl"))
        self.assertEqual(0, len(self.npcs("sandmaw")), "it sleeps until the maw is entered")

    def test_the_sandmaw_is_beaten_by_striking_only_when_it_emerges_and_gives_up_the_pearl(self):
        from engine.npcs import phases

        self._level_up_to_the_caverns()
        self.at("sandmaw_pit", "maw")
        self.world.remove_npcs("sand_grub")
        self._join("lucan_prince", "sandmaw_pit", "nest")
        ryn = self._join("ryn_young", "sandmaw_pit", "nest")
        apply_effects({"teach_companion": {"npc": "ryn_young", "spell": "lightning"}}, {"player": self.player, "world": self.world})
        self.player.flags["exit_warned:sandmaw_pit:nest:east"] = True
        self.say("go east")
        self._let_scenes_play(16)
        boss = self.npcs("sandmaw")[0]
        self.assertEqual({"emerged", "burrowed"}, {p["name"] for p in phases.phases_of(boss)})
        self.assertNotIn("west", self.world.get_region("sandmaw_pit").get_room("maw").exits, "no way out until it is done")
        for tick in range(300):
            self._let_scenes_play(1)
            if not boss.is_alive or not self.player.is_alive:
                break
            if self.player.health < 0.4 * self.player.max_health:
                self.say("use potion")
            if not phases.is_untouchable(boss):
                if tick % 7 == 0 and self.player.health > 0.45 * self.player.max_health:
                    self.say("cast gloom wave")
                self.say("attack sandmaw")
        self.assertTrue(self.player.is_alive)
        self.assertFalse(boss.is_alive)
        self._let_scenes_play(25)
        self.assertTrue(self.holds("item_mirage_pearl"), "the pearl is found where it fell")
        self.assertIs(True, self.player.flags.get("pearl_found"))
        self.assertIn("west", self.world.get_region("sandmaw_pit").get_room("maw").exits, "and the way back opens")

    def test_the_pearl_from_the_pit_cures_rosalind_in_dunhallow(self):
        self.player.flags.update({"ryn_carried": True, "reached_the_inn": True, "guards_beaten": True, "rosalind_hint": True})
        self.world.spawn_npc("rosalind_sick", "dunhallow", "sickroom", instance_id="rosalind_in_bed")
        self.give("item_mirage_pearl")
        self.at("dunhallow", "sickroom")
        self.say("talk orrin")
        self.say("reply 1")
        self.assertIs(True, self.player.flags.get("rosalind_cured"))

    def test_ryn_is_a_passenger_no_enemy_can_touch(self):
        ryn = self.world.npc_templates["ryn"]["properties"]
        self.assertIs(True, ryn.get("untargetable"))
        self.assertIs(True, ryn.get("pacifist"), "she is carried, not fighting: she cannot attack or be attacked")

    def test_the_wood_leads_to_a_desert_village_and_its_inn_ends_the_slice(self):
        self.player.flags["ryn_carried"] = True
        self.at("thornwood", "clearing")
        ryn = self.npcs("ryn")[0]
        ryn.current_region_id, ryn.current_room_id = "thornwood", "clearing"
        apply_effects({"recruit": "ryn"}, {"player": self.player, "world": self.world})
        for monster in ("thorn_wolf", "dune_jackal"):
            self.world.remove_npcs(monster)   # the walk is what is tested here, not the wolves
        for step in ("east", "east", "east", "east", "east", "east", "east", "north"):
            self.say("go " + step)
        self.assertEqual("dunhallow:inn", self.where())
        told = self._let_scenes_play_told(30)
        self.assertIn("Lay her down", told)
        self.assertIs(True, self.player.flags.get("reached_the_inn"))
        self.assertEqual([], self._companions(), "Ryn is left to sleep at the inn")

    def test_the_colossus_the_calling_summons_shakes_every_enemy_in_the_room(self):
        self._question_the_king()
        self.at("hazevale", "village_square")
        magic = self.player.runtime_state.magic
        magic.known_spells.add("call_colossus")
        magic.mana = magic.max_mana = 100
        self.assertIn("no enemies", self.say("cast call colossus"), "a colossus answers a fight, not an empty room")
        self.assertEqual([], self.npcs("colossus_minion"))
        foes = []
        for index in range(2):
            foe = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id="quake_target_%d" % index)
            foe.current_region_id, foe.current_room_id = "hazevale", "village_square"
            foe.health = foe.max_health = 500
            self.world.add_npc(foe)
            foes.append(foe)
        said = self.say("cast call colossus")
        self.assertIn("quake", said)
        colossus = self.npcs("colossus_minion")
        self.assertEqual(1, len(colossus), "one colossus, however many enemies it shakes")
        self.assertTrue(all(foe.health < 500 for foe in foes), "the quake reaches every enemy in the room")
        for _ in range(12):   # and it is gone again almost at once
            self.world.clock.advance(1.0)
            self.tick()
            if not self.npcs("colossus_minion"):
                break
        self.assertEqual([], self.npcs("colossus_minion"))

        self.assertIn("Lightsworn", self.say("title lightsworn"), "the class-change stand-in can be claimed")


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
        skip_the_ff4_opening(first.world, hero)   # past the scenes, where nobody can be talked to first
        hero.flags["drake_slain"] = True
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

    def test_a_sealed_boss_door_is_still_sealed_after_a_restart_and_a_death_reopens_it(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = "mossroot", "mossy_gallery"
        hero.inventory.add_item(ItemFactory.create_item_from_template("item_key_mossroot", first.world))
        self._say(first, sid, "go west")
        self.assertNotIn("east", first.world.get_region("mossroot").get_room("boss_hall").exits)
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Restarter", "another-id")
        hall = second.world.get_region("mossroot").get_room("boss_hall")
        self.assertNotIn("east", hall.exits, "sealed, and it stays that way: the room's change is in the snapshot")
        wyrm = next(n for n in second.world.npcs.values() if n.template_id == "horned_wyrm")
        wyrm.take_damage(10 ** 6, "physical")   # a death nothing called die() for
        for _ in range(30):
            second.tick(sid2)
        self.assertIn("east", hall.exits, "the world tick found the death, and the trigger reopened the door")

    def test_the_fog_ambush_does_not_spring_again_after_a_restart(self):
        db = self._db()
        first = self._boot("ff4_slice", db)
        sid, _ = self._join(first, "Caelan", "transport-1")
        hero = first.get_player_for_session(sid)
        skip_the_ff4_opening(first.world, hero, place=("road", "fogreach_mouth"))
        self.assertIn("grins", self._say(first, sid, "go in"))
        first.shutdown()

        second = self._boot("ff4_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Caelan", "another-id")
        again = second.get_player_for_session(sid2)
        self.assertTrue(second.world.world_state.get("triggers", {}).get("fog_ambush"), "the latch is in the world's own state")
        again.current_region_id, again.current_room_id = "road", "fogreach_mouth"
        self._say(second, sid2, "go in")
        imps = [n for n in second.world.npcs.values() if n.obj_id == "imp_ambush" and n.is_alive]
        self.assertEqual(1, len(imps), "the imp from the first run is still the only one")

    def test_a_bombed_wall_is_still_open_after_a_restart(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.current_region_id, hero.current_room_id = "drowned_vault", "bomb_chamber"
        magic = hero.runtime_state.magic
        magic.known_spells.add("bomb")
        magic.mana = magic.max_mana = 100
        self.assertIn("bursts", self._say(first, sid, "cast bomb on here"))
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Restarter", "another-id")
        again = second.get_player_for_session(sid2)
        self.assertEqual("bomb_chamber", again.current_room_id)
        self._say(second, sid2, "go north")
        self.assertEqual("key_niche", again.current_room_id, "the wall is still down: the room's change is in the snapshot")

    def test_a_spent_key_and_its_open_door_survive_a_restart(self):
        db = self._db()
        first = self._boot("zelda_slice", db)
        sid, _ = self._join(first, "Restarter", "transport-1")
        hero = first.get_player_for_session(sid)
        hero.inventory.add_item(ItemFactory.create_item_from_template("item_small_key", first.world))
        hero.current_region_id, hero.current_room_id = "mossroot", "mossy_gallery"
        self._say(first, sid, "go east")
        self.assertEqual("key_chamber", hero.current_room_id)
        first.shutdown()

        second = self._boot("zelda_slice", db)
        self.addCleanup(second.shutdown)
        sid2, _ = self._join(second, "Restarter", "another-id")
        again = second.get_player_for_session(sid2)
        self.assertFalse(self._holds(again, "item_small_key"), "the key stays spent")
        again.current_region_id, again.current_room_id = "mossroot", "mossy_gallery"
        self._say(second, sid2, "go east")
        self.assertEqual("key_chamber", again.current_room_id, "the door is still open: the memory is a flag, not a rebuilt room")

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

    def test_ff4_keeps_the_choice_the_quest_and_a_friend_who_rides_with_you(self):
        db = self._db()
        first = self._boot("ff4_slice", db)
        sid, _ = self._join(first, "Caelan", "transport-1")
        hero = first.get_player_for_session(sid)
        skip_the_ff4_opening(first.world, hero)
        self._say(first, sid, "talk king")
        self._say(first, sid, "reply 2")
        hero.current_region_id, hero.current_room_id = "varenholt", "barracks"
        self._say(first, sid, "talk kessa")
        self._say(first, sid, "reply 1")
        hero.flags["rested_at_castle"] = True
        hero.current_region_id, hero.current_room_id = "varenholt", "barracks"
        self._say(first, sid, "talk kessa")
        self._say(first, sid, "reply 1")   # she rides with you
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
        self.assertIs(True, again.flags.get("kessa_joined"))
        from engine.npcs import companions

        self.assertEqual(["captain_kessa"], [n.template_id for n in companions.companions_of(second.world, again)], "and the friend who rode with him still does")

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
