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
        self.say("equip dark blade")

    def _question_the_king(self):
        self.say("talk king")
        self.say("reply 2")

    def _let_the_drake_arrive(self):
        """Its arrival is drawn out over a few told moments; let them pass."""
        for _ in range(20):
            self.world.clock.advance(1.0)
            self.server.tick(self.sid)

    def test_the_king_seals_the_package_in_a_scene_before_the_first_quest(self):
        self.say("talk king")
        printed = self.say("reply 1")   # "At once, my king."
        self.assertIn("presses his seal", printed)
        self.assertIn("The King's Package", self.quest_states(), "the cutscene hands straight on to the quest")

    def test_the_kings_first_audience_says_how_to_answer(self):
        self.assertIn("reply <number>", self.say("talk king"))

    def test_a_reply_reads_as_a_transcript_not_a_new_conversation(self):
        opening = self.say("talk king")
        self.assertIn('King Aldous speaks: "The crystals are not yet ours', opening, "an opening reads like every other line")
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
        self.assertIn('King Aldous speaks: "Good. Be quick. The fleet sails at dawn', answered)
        self.assertIn("find her in the barracks before you go", answered, "and he points you at Kessa")
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
        self.assertIn("The crystals are not yet ours", first)
        self.say("reply 4")   # "I will go." agrees, and the guards walk you out
        self.at("varenholt", "throne_room")   # (the door is shut to a player; this puts him back to ask again)
        again = self.say("talk king")
        self.assertNotIn("The crystals are not yet ours", again)
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
        self.assertNotIn("The crystals are not yet ours", again)

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
        # The drake is spawned by its quest stage; here it is put in the square directly.
        self.world.spawn_npc("fog_drake", "mistvale", "village_square", instance_id="drake_probe")
        printed = self.kill("fog_drake", "drake")
        self.assertIn("unravels into grey ribbons", printed)
        self.assertIs(True, self.player.flags.get("drake_slain"))

    def test_the_castle_gate_stays_shut_until_the_king_has_given_orders_and_kessa_has_been_seen(self):
        self.at("varenholt", "castle_gate")
        refused = self.say("go south")
        self.assertEqual("varenholt:castle_gate", self.where())
        self.assertIn("Captain Kessa has been looking for you", refused)
        self.assertIn("Speak with her before you leave", refused)
        self.at("varenholt", "throne_room")
        self._question_the_king()   # either answer: it is that he has spoken that opens the way to Kessa
        self.at("varenholt", "castle_gate")
        self.assertIn("Captain Kessa has been looking for you", self.say("go south"), "the king alone is not enough")
        self.assertEqual("varenholt:castle_gate", self.where())
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")
        self.at("varenholt", "castle_gate")
        self.say("go south")
        self.assertEqual("road:castle_road", self.where())

    def test_the_way_out_of_the_castle_runs_the_same_way_both_ways(self):
        self.at("varenholt", "courtyard")
        self.player.flags["king_ordered"] = True
        self.player.flags["kessa_ahead"] = True
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
        self.at("mistvale", "village_square")
        self.assertIn("in", self.world.get_current_room(self.player).exits)
        self.say("go in")
        self.assertEqual("mistvale:inn", self.where())
        self.assertEqual(1, len(self.npcs("innkeeper")))
        self.assertEqual(("mistvale", "inn"), (self.npcs("innkeeper")[0].current_region_id, self.npcs("innkeeper")[0].current_room_id))
        self.say("go out")
        self.assertEqual("mistvale:village_square", self.where())

    def test_the_mayor_speaks_to_what_has_happened(self):
        self.at("mistvale", "village_square")
        self.assertIn("We have done nothing", self.say("talk mayor"))
        self.player.runtime_state.quests.completed["quest_deliver_package"] = {"template_id": "quest_deliver_package"}
        said = self.say("talk mayor")
        self.assertIn("the moment that package opened it woke", said)
        self.assertIn("find Ryn at the shrine", said, "so that Ryn is a name you know before you are told to report to her")
        self.player.flags["drake_slain"] = True
        said = self.say("talk mayor")
        self.assertIn("It is dead", said)
        self.assertIn("speak with Ryn", said)

    def test_the_inn_charges_for_a_room_and_restores_the_traveller(self):
        self.at("mistvale", "inn")
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

    def test_kessa_waits_for_the_package_to_be_delivered_before_she_will_ride_with_you(self):
        self.player.flags["kessa_ahead"] = True
        kessa = self.npcs("captain_kessa")[0]
        kessa.current_region_id, kessa.current_room_id = "mistvale", "village_square"   # where her ride-ahead would have put her
        self.at("mistvale", "village_square")
        said = self.say("talk kessa")
        self.assertIn("give the mayor the package", said)
        self.assertNotIn("Ride with me", said)
        self.assertNotIn("Did you speak to the king", said, "she knows you have; you are here")
        self.assertEqual([], self._companions())

    def test_once_the_package_is_delivered_kessa_will_ride_with_you(self):
        self.player.flags["kessa_ahead"] = True
        self.player.runtime_state.quests.completed["quest_deliver_package"] = {"template_id": "quest_deliver_package"}
        kessa = self.npcs("captain_kessa")[0]
        kessa.current_region_id, kessa.current_room_id = "mistvale", "village_square"   # where her ride-ahead would have put her
        self.at("mistvale", "village_square")
        said = self.say("talk kessa")
        self.assertIn("What do you need of me", said)
        self.assertIn("Ride with me, Kessa", said)

    def test_kessa_and_ryn_can_join_and_the_inn_heals_the_whole_party(self):
        self.player.flags["kessa_ahead"] = True
        self.player.runtime_state.quests.completed["quest_deliver_package"] = {"template_id": "quest_deliver_package"}
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")   # "Ride with me, Kessa."
        self.assertEqual(["captain_kessa"], self._companions())
        self.player.runtime_state.quests.completed["quest_fog_drake"] = {"template_id": "quest_fog_drake"}
        self.player.flags["ryn_taught"] = True
        ryn = self.npcs("ryn")[0]
        self.at(ryn.current_region_id, ryn.current_room_id)
        self.say("talk ryn")
        self.say("reply 1")   # "The dragon is dead."
        self.say("reply 1")   # "Come with me, Ryn."
        self.assertEqual(["captain_kessa", "ryn"], sorted(self._companions()), "the party of three has room for both")
        self.at("mistvale", "inn")
        self.player.runtime_state.gold = 50
        for npc in self.world.npcs.values():
            if npc.template_id in ("captain_kessa", "ryn"):
                npc.current_region_id, npc.current_room_id = "mistvale", "inn"
                npc.health = 1
        self.player.health = 1
        self.say("talk innkeeper")
        self.say("reply 1")
        for npc in self.world.npcs.values():
            if npc.template_id in ("captain_kessa", "ryn"):
                self.assertEqual(npc.max_health, npc.health, npc.template_id)
        self.assertEqual(self.player.max_health, self.player.health)

    def test_kessa_can_be_sent_back_to_hold_the_square(self):
        self.player.flags["kessa_ahead"] = True
        self.player.runtime_state.quests.completed["quest_deliver_package"] = {"template_id": "quest_deliver_package"}
        self.at("varenholt", "barracks")
        self.say("talk kessa")
        self.say("reply 1")
        self.say("talk kessa")
        self.say("reply 1")   # "Hold the square, Kessa."
        self.assertEqual([], self._companions())

    def test_a_party_of_three_stops_at_three(self):
        from engine.npcs import companions

        self.assertEqual(3, companions.max_companions(self.world))

    def test_the_inn_does_not_offer_a_room_to_someone_who_cannot_pay(self):
        self.at("mistvale", "inn")
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
        self.assertEqual([], self.npcs("fog_drake"), "it does not appear at once: the moment is given time")
        self._let_the_drake_arrive()
        drake = self.npcs("fog_drake")
        self.assertEqual(1, len(drake))
        self.assertEqual(("mistvale", "village_square"), (drake[0].current_region_id, drake[0].current_room_id))

    def test_the_summoner_teaches_the_calling_and_the_titan_arrives(self):
        self._question_the_king()
        self.at("mistvale", "village_square")
        self.say("give sealed package to mayor")
        self._let_the_drake_arrive()
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
        hero.current_region_id, hero.current_room_id = "road", "fogreach_mouth"
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
