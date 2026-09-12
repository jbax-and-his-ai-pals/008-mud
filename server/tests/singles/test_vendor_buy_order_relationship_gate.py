# tests/singles/test_vendor_buy_order_relationship_gate.py
"""Coverage for the smuggler-crew follow-up's two small, generically
reusable mercantile fixes: buy_orders can now carry a relationship_min
(mirroring the gate sells_items already had), and a vendor who deals
only in buy orders (no sells_items/stock) is no longer misreported as
having "nothing to sell right now" with the orders hint unreachable."""

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory
from engine.social.relationships import relationship_key


class TestBuyOrderRelationshipGate(GameTestBase):
    def setUp(self):
        super().setUp()
        self.vendor = NPCFactory.create_npc_from_template("smuggler_leader", self.world)
        self.world.add_npc(self.vendor)
        self.vendor.current_region_id = self.player.current_region_id
        self.vendor.current_room_id = self.player.current_room_id
        self.player.trading_with = self.vendor.obj_id
        for _ in range(3):
            bundle = ItemFactory.create_item_from_template("item_contraband_bundle", self.world)
            self.player.inventory.add_item(bundle)

    def test_order_is_locked_below_relationship_threshold(self):
        result = self.game.process_command("orders")
        self.assertIn("Friendship 20/100 required", result)
        self.assertNotIn("repeatable", result)

    def test_fulfill_rejected_below_relationship_threshold(self):
        result = self.game.process_command("fulfill contraband_run")
        self.assertIn("doesn't trust you enough", result)
        self.assertEqual(3, self.player.inventory.count_item("item_contraband_bundle"))

    def test_order_unlocks_and_repeats_above_threshold(self):
        self.player.npc_relationships[relationship_key(self.vendor)] = 20

        listed = self.game.process_command("orders")
        self.assertIn("contraband_run", listed)
        self.assertIn("repeatable", listed)

        first = self.game.process_command("fulfill contraband_run")
        self.assertIn("Order fulfilled", first)
        self.assertEqual(2, self.player.inventory.count_item("item_contraband_bundle"))

        second = self.game.process_command("fulfill contraband_run")
        self.assertIn("Order fulfilled", second)
        self.assertEqual(1, self.player.inventory.count_item("item_contraband_bundle"))


class TestBuyOrdersOnlyVendorDisplay(GameTestBase):
    def setUp(self):
        super().setUp()
        self.vendor = NPCFactory.create_npc_from_template("smuggler_leader", self.world)
        self.world.add_npc(self.vendor)
        self.vendor.current_region_id = self.player.current_region_id
        self.vendor.current_room_id = self.player.current_room_id
        self.player.trading_with = self.vendor.obj_id

    def test_list_mentions_orders_instead_of_nothing_to_sell(self):
        result = self.game.process_command("list")
        self.assertNotIn("has nothing to sell right now", result)
        self.assertIn("deals in buy orders", result)
        self.assertIn("type 'orders'", result)
