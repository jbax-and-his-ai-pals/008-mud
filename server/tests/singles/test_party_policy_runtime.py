import unittest
from unittest.mock import patch

from engine.commands.gambling import _play_dice_high_roll
from engine.commands.mercantile import sell_handler
from engine.items.item_factory import ItemFactory
from engine.magic.spell import Spell
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestPartyPolicyRuntime(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.server.feature_profile.world_mode = "co_op_party"
        self.server.feature_profile.raw = {
            "party": {
                "shared_quest_policy": "mirror_all",
                "shared_rewards_policy": "split",
                "loot_policy": "round_robin",
            }
        }

        self.leader = self.server.create_session(player_id="party_leader")
        self.member = self.server.create_session(player_id="party_member")
        self.server.mark_session_connected(self.leader.session_id)
        self.server.mark_session_connected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, "char create Leader")
        self.server.execute_command(self.member.session_id, "char create Member")
        self.server.execute_command(self.leader.session_id, "party invite Member")
        self.server.execute_command(self.member.session_id, "party join")

        board_region, board_room = self.server.world.quest_manager.config["quest_board_locations"][0].split(":", 1)
        for player in (self.server.get_player_for_session(self.leader.session_id), self.server.get_player_for_session(self.member.session_id)):
            player.current_region_id = board_region
            player.current_room_id = board_room

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text_payloads(self, events: list[dict]) -> list[str]:
        return [str(event.get("payload", "")) for event in events if event.get("type") == "text"]

    def test_mirror_all_acceptance_and_split_completion_rewards(self) -> None:
        self.server.world.quest_board = [
            {
                "instance_id": "party_board_quest",
                "title": "Shared Duty",
                "state": "available",
                "giver_instance_id": "quest_board",
                "current_stage_index": 0,
                "stages": [
                    {
                        "description": "Report back.",
                        "turn_in_id": "quest_board",
                        "objective": {"type": "talk"},
                    }
                ],
                "rewards": {"xp": 10, "gold": 9},
            }
        ]

        self.server.execute_command(self.leader.session_id, "accept quest 1")

        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        assert leader_player.runtime_state.quests is not None
        assert member_player.runtime_state.quests is not None
        self.assertEqual(1, len(leader_player.runtime_state.quests.active))
        self.assertEqual(1, len(member_player.runtime_state.quests.active))

        leader_quest_id = next(iter(leader_player.runtime_state.quests.active))
        member_quest_id = next(iter(member_player.runtime_state.quests.active))
        self.assertNotEqual(leader_quest_id, member_quest_id)
        self.assertEqual(
            leader_player.runtime_state.quests.active[leader_quest_id]["party_shared_root_id"],
            member_player.runtime_state.quests.active[member_quest_id]["party_shared_root_id"],
        )

        reward_message = self.server.world.quest_manager.complete_quest(leader_player, leader_quest_id)
        self.assertIn("Leader +5 XP", reward_message)
        self.assertIn("Member +5 XP", reward_message)
        self.assertIn("Leader +5 Gold", reward_message)
        self.assertIn("Member +4 Gold", reward_message)

        self.assertEqual({}, leader_player.runtime_state.quests.active)
        self.assertEqual({}, member_player.runtime_state.quests.active)
        self.assertEqual(1, len(leader_player.runtime_state.quests.completed))
        self.assertEqual(1, len(member_player.runtime_state.quests.completed))
        assert leader_player.runtime_state.progression is not None
        assert member_player.runtime_state.progression is not None
        self.assertEqual(5, leader_player.runtime_state.progression.experience)
        self.assertEqual(5, member_player.runtime_state.progression.experience)
        self.assertEqual(5, leader_player.runtime_state.gold)
        self.assertEqual(4, member_player.runtime_state.gold)

    def test_direct_start_quest_mirrors_without_command_path(self) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        self.server.world.quest_manager.quest_templates["unit_test_party_story"] = {
            "title": "Shared Story",
            "stages": [
                {
                    "description": "Talk to the board.",
                    "turn_in_id": "quest_board",
                    "objective": {"type": "talk"},
                }
            ],
            "rewards": {"xp": 6, "gold": 4},
        }

        started = self.server.world.quest_manager.start_quest("unit_test_party_story", leader_player)
        self.assertTrue(started)
        assert leader_player.runtime_state.quests is not None
        assert member_player.runtime_state.quests is not None
        self.assertEqual(1, len(leader_player.runtime_state.quests.active))
        self.assertEqual(1, len(member_player.runtime_state.quests.active))
        leader_quest = next(iter(leader_player.runtime_state.quests.active.values()))
        member_quest = next(iter(member_player.runtime_state.quests.active.values()))
        self.assertEqual(
            leader_quest["party_shared_root_id"],
            member_quest["party_shared_root_id"],
        )

    def test_collection_rewards_use_party_split_policy(self) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        self.server.collection_manager.collections = {
            "museum_set": {
                "name": "Museum Set",
                "items": ["artifact_token"],
                "rewards": {"xp": 8, "gold": 7},
            }
        }
        leader_player.collections_progress["museum_set"] = ["artifact_token"]
        self.assertFalse(leader_player.collections_completed.get("museum_set", False))

        messages: list[str] = []
        self.server.collection_manager._check_completion(leader_player, "museum_set", messages)

        self.assertTrue(leader_player.collections_completed["museum_set"])
        self.assertTrue(any("Leader +4 XP" in msg for msg in messages))
        self.assertTrue(any("Member +4 XP" in msg for msg in messages))
        self.assertTrue(any("Leader +4 Gold" in msg for msg in messages))
        self.assertTrue(any("Member +3 Gold" in msg for msg in messages))
        assert leader_player.runtime_state.progression is not None
        assert member_player.runtime_state.progression is not None
        self.assertEqual(4, leader_player.runtime_state.progression.experience)
        self.assertEqual(4, member_player.runtime_state.progression.experience)
        self.assertEqual(4, leader_player.runtime_state.gold)
        self.assertEqual(3, member_player.runtime_state.gold)

    def test_round_robin_loot_routes_room_items_across_party(self) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)

        item_a = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        item_b = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        self.assertIsNotNone(item_a)
        self.assertIsNotNone(item_b)
        self.server.world.add_item_to_room(leader_player.current_region_id, leader_player.current_room_id, item_a)
        self.server.world.add_item_to_room(leader_player.current_region_id, leader_player.current_room_id, item_b)

        take_name = item_a.name.lower()
        self.server.execute_command(self.leader.session_id, f"take {take_name}")
        self.server.execute_command(self.leader.session_id, f"take {take_name}")

        self.assertEqual(1, leader_player.inventory.count_item(item_a.obj_id))
        self.assertEqual(1, member_player.inventory.count_item(item_b.obj_id))

    def test_round_robin_cursor_survives_disconnect_and_reconnect(self) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)

        item_a = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        item_b = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        item_c = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        self.assertIsNotNone(item_a)
        self.assertIsNotNone(item_b)
        self.assertIsNotNone(item_c)
        if item_a is None or item_b is None or item_c is None:
            return

        for item in (item_a, item_b, item_c):
            self.server.world.add_item_to_room(leader_player.current_region_id, leader_player.current_room_id, item)

        take_name = item_a.name.lower()
        self.server.execute_command(self.leader.session_id, f"take {take_name}")
        self.server.mark_session_disconnected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, f"take {take_name}")
        self.server.mark_session_connected(self.member.session_id)
        self.server.execute_command(self.leader.session_id, f"take {take_name}")

        self.assertEqual(2, leader_player.inventory.count_item(item_a.obj_id))
        self.assertEqual(1, member_player.inventory.count_item(item_a.obj_id))

    def test_vendor_sale_uses_party_split_policy(self) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        leader_player.runtime_state.gold = 0
        member_player.runtime_state.gold = 0
        leader_player.current_region_id = "town"
        leader_player.current_room_id = "town_square"
        member_player.current_region_id = "town"
        member_player.current_room_id = "town_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "town_square"

        gem = ItemFactory.create_item_from_template("item_ruby", self.server.world)
        self.assertIsNotNone(gem)
        if gem is None:
            return
        leader_player.inventory.add_item(gem)

        merchant = NPCFactory.create_npc_from_template("merchant", self.server.world)
        self.assertIsNotNone(merchant)
        if merchant is None:
            return
        self.server.world.add_npc(merchant)
        merchant.current_region_id = "town"
        merchant.current_room_id = "town_square"
        buy_types = merchant.properties.get("buys_item_types", [])
        if "Gem" not in buy_types:
            buy_types.append("Gem")
        merchant.properties["buys_item_types"] = buy_types
        # This test spawns the "merchant" template as a generic stand-in
        # vendor and expects the global default sell rate, not the
        # merchant's own (deliberately lower) general-store rate.
        merchant.properties["sell_rate_multiplier"] = 0.4
        leader_player.trading_with = merchant.obj_id

        result = sell_handler(["ruby"], {"world": self.server.world, "player": leader_player})

        self.assertIn("you sell 1 ruby", result.lower())
        self.assertIn("leader +60 gold", result.lower())
        self.assertIn("member +60 gold", result.lower())
        self.assertEqual(60, leader_player.runtime_state.gold)
        self.assertEqual(60, member_player.runtime_state.gold)
        self.assertEqual(0, leader_player.inventory.count_item(gem.obj_id))

    @patch("engine.commands.gambling.random.randint", side_effect=[90, 10])
    def test_gambling_profit_shares_only_profit_not_stake(self, _mock_randint) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        leader_player.runtime_state.gold = 100
        member_player.runtime_state.gold = 0
        leader_player.current_region_id = "casino"
        leader_player.current_room_id = "dice_parlor"
        member_player.current_region_id = "casino"
        member_player.current_room_id = "dice_parlor"
        self.server.world.current_region_id = "casino"
        self.server.world.current_room_id = "dice_parlor"

        dealer = NPCFactory.create_npc_from_template("dice_dealer", self.server.world)
        self.assertIsNotNone(dealer)
        if dealer is None:
            return
        self.server.world.add_npc(dealer)
        dealer.current_region_id = "casino"
        dealer.current_room_id = "dice_parlor"

        result = _play_dice_high_roll(leader_player, dealer, 10)

        self.assertIn("you win", result.lower())
        self.assertIn("leader +5 gold", result.lower())
        self.assertIn("member +5 gold", result.lower())
        self.assertEqual(105, leader_player.runtime_state.gold)
        self.assertEqual(5, member_player.runtime_state.gold)

    @patch("engine.player.combat.calculate_xp_gain", return_value=8)
    @patch("engine.player.combat.random.randint", return_value=5)
    @patch("engine.player.combat.random.random", return_value=0.0)
    def test_melee_kill_rewards_use_party_split_policy(self, _mock_random, _mock_randint, _mock_xp) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        assert leader_player.runtime_state.progression is not None
        assert member_player.runtime_state.progression is not None
        leader_player.runtime_state.progression.experience = 0
        member_player.runtime_state.progression.experience = 0
        leader_player.runtime_state.gold = 0
        member_player.runtime_state.gold = 0

        target = NPCFactory.create_npc_from_template("goblin", self.server.world)
        self.assertIsNotNone(target)
        if target is None:
            return
        self.server.world.add_npc(target)
        target.current_region_id = leader_player.current_region_id
        target.current_room_id = leader_player.current_room_id
        target.health = 1
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}

        with patch(
            "engine.player.combat.CombatSystem.execute_attack",
            return_value={"message": "Hit!", "is_hit": True, "target_defeated": True},
        ):
            result = leader_player.attack(target, self.server.world)

        self.assertIn("rewards:", result["message"].lower())
        self.assertIn("leader +4 xp", result["message"].lower())
        self.assertIn("member +4 xp", result["message"].lower())
        self.assertIn("leader +3 gold", result["message"].lower())
        self.assertIn("member +2 gold", result["message"].lower())
        self.assertEqual(4, leader_player.runtime_state.progression.experience)
        self.assertEqual(4, member_player.runtime_state.progression.experience)
        self.assertEqual(3, leader_player.runtime_state.gold)
        self.assertEqual(2, member_player.runtime_state.gold)

    @patch("engine.player.magic.calculate_xp_gain", return_value=6)
    @patch("engine.player.magic.random.randint", return_value=5)
    @patch("engine.player.magic.random.random", return_value=0.0)
    def test_spell_kill_rewards_use_party_split_policy(self, _mock_random, _mock_randint, _mock_xp) -> None:
        leader_player = self.server.get_player_for_session(self.leader.session_id)
        member_player = self.server.get_player_for_session(self.member.session_id)
        assert leader_player.runtime_state.progression is not None
        assert member_player.runtime_state.progression is not None
        assert leader_player.runtime_state.magic is not None
        leader_player.runtime_state.progression.experience = 0
        member_player.runtime_state.progression.experience = 0
        leader_player.runtime_state.gold = 0
        member_player.runtime_state.gold = 0
        leader_player.runtime_state.magic.mana = 100

        target = NPCFactory.create_npc_from_template("goblin", self.server.world)
        self.assertIsNotNone(target)
        if target is None:
            return
        self.server.world.add_npc(target)
        target.current_region_id = leader_player.current_region_id
        target.current_room_id = leader_player.current_room_id
        target.health = 1
        target.loot_table = {"gold_value": {"chance": 1.0, "quantity": [5, 5]}}

        spell = Spell(
            spell_id="unit_test_party_blast",
            name="Party Blast",
            description="Finishes a target.",
            mana_cost=0,
            cooldown=0.0,
            effects=[{"type": "damage", "value": 50}],
            target_type="enemy",
            level_required=1,
        )
        leader_player.runtime_state.magic.known_spells.add(spell.spell_id)

        result = leader_player.cast_spell(spell, target, 0.0, self.server.world)

        self.assertTrue(result["success"])
        self.assertEqual(3, leader_player.runtime_state.progression.experience)
        self.assertEqual(3, member_player.runtime_state.progression.experience)
        self.assertEqual(3, leader_player.runtime_state.gold)
        self.assertEqual(2, member_player.runtime_state.gold)


if __name__ == "__main__":
    unittest.main()
