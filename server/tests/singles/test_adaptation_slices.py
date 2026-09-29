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

    # FLIP in item 2.1: a list sets every flag it names.
    def test_limit_set_flag_given_a_list_makes_one_flag(self):
        apply_effects({"set_flag": ["door_open", "guard_alerted"]}, self._context())
        self.assertIn("['door_open', 'guard_alerted']", self.player.flags)
        self.assertNotIn("door_open", self.player.flags)

    # FLIP in item 2.3: `restore` is an effect.
    def test_limit_restore_is_not_an_effect(self):
        report = apply_effects({"restore": "health"}, self._context())
        self.assertTrue(any("restore" in str(entry) for entry in report.unknown), report.summary())

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

    # FLIP in item 1.3: a restarted server gives the character and the world back.
    def test_limit_a_restart_forgets_the_character_and_the_lever(self):
        scratch = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)  # registered first, so it runs last
        db = str(Path(scratch) / "world.sqlite3")

        def boot():
            return HeadlessServer(
                db_path=db,
                content_set_path=str(REPO_ROOT / "content_sets" / self.SET_ID),
                deterministic_test_mode=True,
                default_presentation_mode="player",
            )

        first = boot()
        sid = first.create_session(player_id="restart").session_id
        first.execute_command(sid, "char create Restarter")
        hero = first.get_player_for_session(sid)
        hero.flags["marker"] = True
        hero.current_region_id, hero.current_room_id = "mossroot", "root_hall"
        first.execute_command(sid, "pull loose stone")
        self.assertIn("down", first.world.get_region("mossroot").get_room("root_hall").exits)
        first.shutdown()

        second = boot()
        self.addCleanup(second.shutdown)
        sid = second.create_session(player_id="restart").session_id
        second.execute_command(sid, "char create Restarter")
        again = second.get_player_for_session(sid)
        self.assertEqual({}, again.flags, "a new character, not the one that was saved")
        self.assertNotIn("down", second.world.get_region("mossroot").get_room("root_hall").exits)


if __name__ == "__main__":
    unittest.main()
