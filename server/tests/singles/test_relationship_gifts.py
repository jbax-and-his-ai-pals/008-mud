import unittest

from engine.social.relationships import relationship_key
from engine.commands.mercantile import _get_price_multiplier, _relationship_allows_stock
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER


class TestRelationshipGifts(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True
        )
        self.session = self.server.create_session()
        self.server.execute_command(self.session.session_id, "char create GiftTester")
        self.player = self.server.get_player_for_session(self.session.session_id)
        self.player.current_region_id = "town"
        self.player.current_room_id = "blacksmith_interior"
        self.blacksmith = self.server.world.find_npc_in_room_for_player("grenda", self.player)
        self.assertIsNotNone(self.blacksmith)

    def tearDown(self) -> None:
        self.server.shutdown()

    def _add_crafted_cap(self) -> None:
        cap = ItemFactory.create_item_from_template("item_leather_cap", self.server.world)
        self.assertIsNotNone(cap)
        cap.properties["crafted_by_player"] = True
        cap.properties["crafted_recipe_id"] = "stitch_leather_cap"
        self.player.inventory.add_item(cap)

    def test_crafted_gift_builds_persistent_personal_relationship(self) -> None:
        self._add_crafted_cap()
        events = self.server.execute_command(self.session.session_id, "give leather cap to grenda")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        key = relationship_key(self.blacksmith)
        self.assertEqual(5, self.player.npc_relationships[key])
        self.assertIn("Relationship: +5", text)
        self.assertIn("handiwork", text)
        snapshot = self.player.to_dict(self.server.world)
        self.assertEqual(5, snapshot["npc_relationships"][key])

    def test_craft_quality_adds_an_authored_gift_bonus(self) -> None:
        self._add_crafted_cap()
        cap = self.player.inventory.find_item_by_name("leather cap")
        cap.properties["gift_quality_bonus"] = 2

        events = self.server.execute_command(self.session.session_id, "give leather cap to grenda")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        self.assertEqual(7, self.player.npc_relationships[relationship_key(self.blacksmith)])
        self.assertIn("quality is immediately apparent", text)

    def test_second_gift_to_same_npc_is_limited_until_a_new_world_day(self) -> None:
        self._add_crafted_cap()
        self.server.execute_command(self.session.session_id, "give leather cap to grenda")
        self._add_crafted_cap()
        events = self.server.execute_command(self.session.session_id, "give leather cap to grenda")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        self.assertIn("another day", text)
        self.assertEqual(1, self.player.inventory.count_item("item_leather_cap"))

    def test_friendship_tiers_lower_vendor_prices(self) -> None:
        base_price = _get_price_multiplier(self.blacksmith, self.player)
        self.player.npc_relationships[relationship_key(self.blacksmith)] = 30
        friend_price = _get_price_multiplier(self.blacksmith, self.player)

        self.assertLess(friend_price, base_price)

    def test_relationship_gated_stock_requires_the_authored_bond_score(self) -> None:
        special_stock = {"item_id": "item_master_lockpick", "relationship_min": 30}
        self.assertFalse(_relationship_allows_stock(self.player, self.blacksmith, special_stock))

        self.player.npc_relationships[relationship_key(self.blacksmith)] = 30
        self.assertTrue(_relationship_allows_stock(self.player, self.blacksmith, special_stock))

    def test_preferred_gift_tags_reward_a_refined_item_and_explain_why(self) -> None:
        self.player.current_room_id = "museum_interior"
        curator = self.server.world.find_npc_in_room_for_player("curator", self.player)
        self.assertIsNotNone(curator)
        gem = ItemFactory.create_item_from_template("item_faceted_rose_quartz", self.server.world)
        self.assertIsNotNone(gem)
        gem.properties["crafted_by_player"] = True
        self.player.inventory.add_item(gem)

        events = self.server.execute_command(self.session.session_id, "give faceted rose quartz to curator")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

        self.assertIn("suits their tastes", text)
        self.assertIn("Relationship: +9", text)
        self.assertEqual(9, self.player.npc_relationships[relationship_key(curator)])

    def test_relationship_milestone_is_awarded_once_and_persists(self) -> None:
        self.player.current_room_id = "museum_interior"
        curator = self.server.world.find_npc_in_room_for_player("curator", self.player)
        self.assertIsNotNone(curator)
        self.player.npc_relationships[relationship_key(curator)] = 9
        gem = ItemFactory.create_item_from_template("item_faceted_rose_quartz", self.server.world)
        self.assertIsNotNone(gem)
        gem.properties["crafted_by_player"] = True
        self.player.inventory.add_item(gem)

        events = self.server.execute_command(self.session.session_id, "give faceted rose quartz to curator")
        text = "\n".join(str(event["payload"]) for event in events if event["type"] == "text")
        self.assertIn("archive finder’s stipend", text)
        self.assertEqual(15, self.player.runtime_state.gold)
        self.assertIn("archive_acquaintance", self.player.relationship_milestones_completed["curator"])

        restored = type(self.player).from_dict(self.player.to_dict(self.server.world), self.server.world)
        self.assertIn("archive_acquaintance", restored.relationship_milestones_completed["curator"])

    def test_relationship_ledger_and_local_detail_explain_next_milestone(self) -> None:
        self.player.current_room_id = "museum_interior"
        curator = self.server.world.find_npc_in_room_for_player("curator", self.player)
        self.assertIsNotNone(curator)
        self.player.npc_relationships[relationship_key(curator)] = 9

        detail = self.server.execute_command(self.session.session_id, "relationship curator")
        self.assertIn("Next milestone: 10/100", "\n".join(str(event["payload"]) for event in detail))
        ledger = self.server.execute_command(self.session.session_id, "relationships")
        ledger_text = "\n".join(str(event["payload"]) for event in ledger)
        self.assertIn("RELATIONSHIPS", ledger_text)
        self.assertIn("Curator Vane", ledger_text)
