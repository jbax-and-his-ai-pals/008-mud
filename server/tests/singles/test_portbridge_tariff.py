# tests/singles/test_portbridge_tariff.py
"""Coverage for the Portbridge tariff: a flat 10% penalty on buying from
and selling to Portbridge's vendors, gated live on whether the player
has completed the portbridge_smugglers campaign (any ending) -- not a
timed modifier like the existing economy_impact property, which expires
on its own regardless of quest state."""

from tests.fixtures import GameTestBase
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory


class TestPortbridgeTariff(GameTestBase):
    def setUp(self):
        super().setUp()
        self.vendor = NPCFactory.create_npc_from_template("portbridge_fisherman", self.world)
        self.world.add_npc(self.vendor)
        self.vendor.current_region_id = self.player.current_region_id
        self.vendor.current_room_id = self.player.current_room_id
        self.player.trading_with = self.vendor.obj_id
        self.player.runtime_state.gold = 1000

    def test_buy_price_is_inflated_while_campaign_incomplete(self):
        listing = self.game.process_command("list")
        self.assertIn("Portbridge Tariff in Effect", listing)

        before = self.game.process_command("buy fishing net")
        self.assertIn("You buy", before)
        untariffed_price = int(self.world.item_templates["item_fishing_net"]["value"] * 2.0)
        tariffed_price = int(self.world.item_templates["item_fishing_net"]["value"] * 2.0 * 1.10)
        self.assertIn(f"for {tariffed_price}", before)
        self.assertNotEqual(untariffed_price, tariffed_price)

    def test_sell_price_is_reduced_while_campaign_incomplete(self):
        # item_fresh_fish is a Consumable, which portbridge_fisherman's
        # buys_item_types doesn't include -- use item_fishing_net (an
        # "Item", which it does buy) so the sale itself isn't rejected.
        net = ItemFactory.create_item_from_template("item_fishing_net", self.world)
        self.player.inventory.add_item(net)
        result = self.game.process_command("sell fishing net")
        expected = max(0, int(net.value * 0.4 * 0.90))
        self.assertIn(f"for {expected}", result)

    def test_prices_normalize_once_campaign_completed(self):
        self.player.runtime_state.quests.completed_campaigns["portbridge_smugglers"] = {"outcome": "SMUGGLING_BUSTED"}

        listing = self.game.process_command("list")
        self.assertNotIn("Portbridge Tariff in Effect", listing)

        result = self.game.process_command("buy fishing net")
        normal_price = int(self.world.item_templates["item_fishing_net"]["value"] * 2.0)
        self.assertIn(f"for {normal_price}", result)

    def test_vendor_without_tariff_property_is_unaffected(self):
        merchant = NPCFactory.create_npc_from_template("merchant", self.world)
        self.world.add_npc(merchant)
        merchant.current_region_id = self.player.current_region_id
        merchant.current_room_id = self.player.current_room_id
        self.player.trading_with = merchant.obj_id
        listing = self.game.process_command("list")
        self.assertNotIn("Tariff", listing)


class TestSmugglerLeaderExemptFromTariff(GameTestBase):
    def test_fence_payout_is_flat_regardless_of_tariff_property(self):
        vendor = NPCFactory.create_npc_from_template("smuggler_leader", self.world)
        self.world.add_npc(vendor)
        vendor.current_region_id = self.player.current_region_id
        vendor.current_room_id = self.player.current_room_id
        self.player.trading_with = vendor.obj_id
        self.assertNotIn("tariff", vendor.properties)

        from engine.social.relationships import relationship_key
        self.player.npc_relationships[relationship_key(vendor)] = 20
        bundle = ItemFactory.create_item_from_template("item_contraband_bundle", self.world)
        self.player.inventory.add_item(bundle)
        result = self.game.process_command("fulfill contraband_run")
        self.assertIn("for 35 gold", result)
