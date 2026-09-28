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

import re
import unittest
from pathlib import Path

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer

REPO_ROOT = Path(__file__).resolve().parents[3]
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


if __name__ == "__main__":
    unittest.main()
