"""End-to-end coverage for the authored early gather -> craft -> gift route."""

from pathlib import Path
import unittest
from unittest.mock import patch

from engine.items.resource_node import ResourceNode
from engine.items.item_factory import ItemFactory
from engine.player import Player
from engine.server.content_set import load_content_set
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"


class TestFantasyGatheringRoute(unittest.TestCase):
    def test_content_declares_gathering_and_the_first_hour_route_is_playable(self) -> None:
        definition, issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(definition, issues)
        assert definition is not None
        self.assertTrue(definition.game_contract.system_enabled("gathering"))

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="gathering_route_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual(1, player.inventory.count_item("item_foraging_knife"))

            garden = server.world.get_region("town").get_room("community_garden")
            self.assertTrue(any(isinstance(item, ResourceNode) for item in garden.items))

            server.execute_command(session.session_id, "west")
            server.execute_command(session.session_id, "south")
            surveyed = server.execute_command(session.session_id, "survey")
            survey_text = "\n".join(str(event["payload"]) for event in surveyed)
            self.assertIn("Resource Survey", survey_text)
            self.assertIn("herb bed: 6/6 (ready)", survey_text)
            self.assertIn("tool: foraging knife", survey_text)
            first = server.execute_command(session.session_id, "gather herb bed")
            second = server.execute_command(session.session_id, "gather herb bed")
            gathered_text = "\n".join(str(event["payload"]) for event in first + second)
            self.assertIn("gather wild herbs", gathered_text.lower())

            crafted = server.execute_command(session.session_id, "craft tie_wildflower_posy")
            self.assertIn("Successfully", "\n".join(str(event["payload"]) for event in crafted))
            posy = player.inventory.find_item_by_name("wildflower posy")
            self.assertIsNotNone(posy)
            self.assertTrue(posy.get_property("crafted_by_player"))

            server.execute_command(session.session_id, "north")
            server.execute_command(session.session_id, "east")
            gifted = server.execute_command(session.session_id, "give wildflower posy to Elder Thorne")
            gifted_text = "\n".join(str(event["payload"]) for event in gifted)
            self.assertIn("Relationship: +5", gifted_text)
        finally:
            server.shutdown()

    def test_authored_crafting_commission_requires_a_player_made_delivery(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="commission_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("quest_wildflower_commission", server.world.quest_board[0]["template_id"])

            accepted = server.execute_command(session.session_id, "accept quest 1")
            self.assertIn("Quest Accepted", "\n".join(str(event["payload"]) for event in accepted))
            self.assertEqual(0, player.inventory.count_item("item_wildflower_posy"))

            server.execute_command(session.session_id, "west")
            server.execute_command(session.session_id, "south")
            server.execute_command(session.session_id, "gather herb bed")
            server.execute_command(session.session_id, "gather herb bed")
            server.execute_command(session.session_id, "craft tie_wildflower_posy")
            server.execute_command(session.session_id, "north")
            server.execute_command(session.session_id, "east")

            completed = server.execute_command(session.session_id, "give wildflower posy to Elder Thorne")
            completed_text = "\n".join(str(event["payload"]) for event in completed)
            self.assertIn("Quest Complete", completed_text)
            self.assertIn("25 XP", completed_text)
            self.assertIn("12 Gold", completed_text)
            self.assertEqual(10, player.npc_relationships["village_elder"])

            board = server.execute_command(session.session_id, "look board")
            board_text = "\n".join(str(event["payload"]) for event in board)
            self.assertIn("A Riverside Welcome", board_text)
            self.assertIn("Trust: 10/10", board_text)
            self.assertNotIn("Trust: 10/10 (locked)", board_text)
        finally:
            server.shutdown()

    def test_foothills_gem_loop_requires_a_pick_and_makes_a_talisman(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="gem_route_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)

            for direction in ("east", "east", "east", "east", "east", "north"):
                server.execute_command(session.session_id, direction)
            self.assertEqual(("foothills", "rocky_outcrop"), (player.current_region_id, player.current_room_id))

            outcrop = server.world.get_region("foothills").get_room("rocky_outcrop")
            self.assertTrue(any(item.obj_id == "node_rose_quartz_seam" for item in outcrop.items))
            without_pick = server.execute_command(session.session_id, "mine rose quartz seam")
            self.assertIn("pickaxe", "\n".join(str(event["payload"]) for event in without_pick))

            pick = ItemFactory.create_item_from_template("item_prospector_pick", server.world)
            leather = ItemFactory.create_item_from_template("item_leather_strip", server.world)
            self.assertIsNotNone(pick)
            self.assertIsNotNone(leather)
            player.inventory.add_item(pick)
            player.inventory.add_item(leather)

            gathered = server.execute_command(session.session_id, "mine rose quartz seam")
            gathered_text = "\n".join(str(event["payload"]) for event in gathered)
            self.assertIn("gather rose quartz", gathered_text.lower())
            self.assertIn("Riverside Gem Ledger", gathered_text)
            self.assertIn("Rose Quartz Prospect", gathered_text)
            self.assertEqual({"fieldcraft_basics", "rose_quartz"}, set(player.discoveries))
            self.assertEqual([], player.collections_progress["riverside_gem_ledger"])
            crafted = server.execute_command(session.session_id, "craft string_rose_quartz_talisman")
            self.assertIn("Successfully", "\n".join(str(event["payload"]) for event in crafted))
            talisman = player.inventory.find_item_by_name("rose quartz talisman")
            self.assertIsNotNone(talisman)
            self.assertTrue(talisman.get_property("crafted_by_player"))
        finally:
            server.shutdown()

    def test_fine_gathered_materials_raise_their_authored_craft_quality(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="quality_clay_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            player.current_region_id = "forest"
            player.current_room_id = "stream_crossing"

            survey = server.execute_command(session.session_id, "survey")
            self.assertIn("material quality: Fine", "\n".join(str(event["payload"]) for event in survey))
            gathered = server.execute_command(session.session_id, "gather river clay bank")
            gathered += server.execute_command(session.session_id, "gather river clay bank")
            self.assertIn("Fine quality", "\n".join(str(event["payload"]) for event in gathered))
            clay = [slot.item for slot in player.inventory.slots if slot.item and slot.item.obj_id == "item_river_clay"]
            self.assertEqual(2, len(clay))
            self.assertTrue(all(item.get_property("material_quality_score") == 2 for item in clay))

            crafted = server.execute_command(session.session_id, "craft press_river_token")
            crafted_text = "\n".join(str(event["payload"]) for event in crafted)
            token = player.inventory.find_item_by_name("river-clay token")
            self.assertIn("Craft quality: River Fine.", crafted_text)
            self.assertEqual("river_fine", token.get_property("craft_quality"))
            self.assertEqual(2, token.get_property("material_quality_score"))
        finally:
            server.shutdown()

    def test_rare_yield_grade_overrides_a_node_regional_grade_and_keeps_source(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="rare_grade_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            player.current_region_id = "foothills"
            player.current_room_id = "rocky_outcrop"
            player.inventory.add_item(ItemFactory.create_item_from_template("item_prospector_pick", server.world))

            surveyed = server.execute_command(session.session_id, "survey")
            self.assertIn("Rough Foothill", "\n".join(str(event["payload"]) for event in surveyed))
            with patch("engine.items.resource_node.random.random", return_value=0.0):
                gathered = server.execute_command(session.session_id, "gather rose quartz seam")
            gathered_text = "\n".join(str(event["payload"]) for event in gathered)
            quartz = player.inventory.find_item_by_name("rose quartz")
            self.assertIn("Pristine Foothill quality", gathered_text)
            self.assertEqual("foothill_pristine", quartz.get_property("material_quality"))
            self.assertEqual(3, quartz.get_property("material_quality_score"))
            self.assertEqual("rose quartz seam", quartz.get_property("material_source_label"))
            self.assertFalse(quartz.stackable)
            appraisal = server.execute_command(session.session_id, "appraise rose quartz")
            appraisal_text = "\n".join(str(event["payload"]) for event in appraisal)
            self.assertIn("Material grade: Pristine Foothill (score 3)", appraisal_text)
            self.assertIn("Gathered from: rose quartz seam", appraisal_text)
        finally:
            server.shutdown()

    def test_gem_ledger_static_membership_can_be_donated_to_the_museum(self) -> None:
        """A collection list works without bespoke gem properties in engine code."""
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="gem_donation_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            rose_quartz = ItemFactory.create_item_from_template("item_rose_quartz", server.world)
            self.assertIsNotNone(rose_quartz)
            player.inventory.add_item(rose_quartz)

            server.execute_command(session.session_id, "southeast")
            server.execute_command(session.session_id, "in")
            donated = server.execute_command(session.session_id, "turnin")
            donated_text = "\n".join(str(event["payload"]) for event in donated)

            self.assertIn("Donated rose quartz", donated_text)
            self.assertEqual(0, player.inventory.count_item("item_rose_quartz"))
            self.assertEqual(["item_rose_quartz"], player.collections_progress["riverside_gem_ledger"])
        finally:
            server.shutdown()

    def test_gem_can_be_appraised_then_refined_at_a_content_authored_station(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="gem_refinement_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            rose_quartz = ItemFactory.create_item_from_template("item_rose_quartz", server.world)
            self.assertIsNotNone(rose_quartz)
            player.inventory.add_item(rose_quartz)

            appraised = server.execute_command(session.session_id, "appraise rose quartz")
            appraisal_text = "\n".join(str(event["payload"]) for event in appraised)
            self.assertIn("rough specimen", appraisal_text)
            self.assertIn("cuttable", appraisal_text)

            server.execute_command(session.session_id, "southeast")
            server.execute_command(session.session_id, "in")
            crafted = server.execute_command(session.session_id, "craft facet_rose_quartz")
            crafted_text = "\n".join(str(event["payload"]) for event in crafted)
            self.assertIn("Successfully crafted", crafted_text)
            self.assertIn("Lapidary Work", crafted_text)
            faceted = player.inventory.find_item_by_name("faceted rose quartz")
            self.assertIsNotNone(faceted)
            self.assertTrue(faceted.get_property("crafted_by_player"))
            self.assertIn("lapidary_work", player.discoveries)

            refined = server.execute_command(session.session_id, "appraise faceted rose quartz")
            self.assertIn("lapidary work", "\n".join(str(event["payload"]) for event in refined))
        finally:
            server.shutdown()

    def test_refined_gem_commission_uses_the_social_gate_and_crafted_delivery(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="gem_commission_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            curator = next(npc for npc in server.world.npcs.values() if npc.template_id == "curator")
            locked_board = server.execute_command(session.session_id, "look board")
            locked_board_text = "\n".join(str(event["payload"]) for event in locked_board)
            self.assertIn("A Light for the Museum", locked_board_text)
            self.assertIn("Trust: 0/5 (locked)", locked_board_text)
            player.npc_relationships["curator"] = 5
            board_index = next(
                index + 1
                for index, quest in enumerate(server.world.quest_board)
                if quest.get("template_id") == "quest_museum_showcase_commission"
            )
            accepted = server.execute_command(session.session_id, f"accept quest {board_index}")
            self.assertIn("Quest Accepted", "\n".join(str(event["payload"]) for event in accepted))

            player.current_region_id = "town"
            player.current_room_id = "museum_interior"
            gem = ItemFactory.create_item_from_template("item_faceted_rose_quartz", server.world)
            self.assertIsNotNone(gem)
            gem.properties["crafted_by_player"] = True
            player.inventory.add_item(gem)
            delivered = server.execute_command(session.session_id, "give faceted rose quartz to Curator Vane")
            delivered_text = "\n".join(str(event["payload"]) for event in delivered)

            self.assertIn("Quest Complete", delivered_text)
            self.assertIn("50 XP", delivered_text)
            self.assertIn("28 Gold", delivered_text)
            self.assertEqual(13, player.npc_relationships["curator"])
            self.assertEqual(curator.current_room_id, player.current_room_id)
        finally:
            server.shutdown()

    def test_museum_commission_allows_a_sourced_display_specimen_alternative(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="museum_alternative_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            player.npc_relationships["curator"] = 5
            board_index = next(
                index + 1 for index, quest in enumerate(server.world.quest_board)
                if quest.get("template_id") == "quest_museum_showcase_commission"
            )
            server.execute_command(session.session_id, f"accept quest {board_index}")
            journal = server.execute_command(session.session_id, "journal")
            journal_text = "\n".join(str(event["payload"]) for event in journal)
            self.assertIn("player-faceted rose quartz", journal_text)
            self.assertIn("amethyst specimen", journal_text)

            player.current_region_id = "town"
            player.current_room_id = "museum_interior"
            amethyst = ItemFactory.create_item_from_template("item_amethyst", server.world)
            self.assertIsNotNone(amethyst)
            player.inventory.add_item(amethyst)
            delivered = server.execute_command(session.session_id, "give amethyst to Curator Vane")
            self.assertIn("Quest Complete", "\n".join(str(event["payload"]) for event in delivered))
            self.assertEqual(0, player.inventory.count_item("item_amethyst"))
        finally:
            server.shutdown()

    def test_merchant_buy_orders_support_repeatable_gathering_and_one_time_crafts(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="buy_order_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            player.current_region_id = "town"
            player.current_room_id = "market_square"
            server.execute_command(session.session_id, "trade Talia")
            orders = server.execute_command(session.session_id, "orders")
            order_text = "\n".join(str(event["payload"]) for event in orders)
            self.assertIn("river_clay", order_text)
            self.assertIn("riverside_charm", order_text)

            clay = ItemFactory.create_item_from_template("item_river_clay", server.world)
            self.assertIsNotNone(clay)
            player.inventory.add_item(clay, 4)
            first = server.execute_command(session.session_id, "fulfill river_clay")
            self.assertIn("Order fulfilled", "\n".join(str(event["payload"]) for event in first))
            self.assertEqual(12, player.runtime_state.gold)
            second = server.execute_command(session.session_id, "fulfill river_clay")
            self.assertIn("Order fulfilled", "\n".join(str(event["payload"]) for event in second))
            self.assertEqual(24, player.runtime_state.gold)

            charm = ItemFactory.create_item_from_template("item_riverside_charm", server.world)
            self.assertIsNotNone(charm)
            charm.properties["crafted_by_player"] = True
            player.inventory.add_item(charm)
            completed = server.execute_command(session.session_id, "fulfill riverside_charm")
            self.assertIn("Relationship with Talia", "\n".join(str(event["payload"]) for event in completed))
            repeat = server.execute_command(session.session_id, "fulfill riverside_charm")
            self.assertIn("already completed", "\n".join(str(event["payload"]) for event in repeat))

            ordinary_token = ItemFactory.create_item_from_template("item_river_token", server.world)
            self.assertIsNotNone(ordinary_token)
            ordinary_token.properties["crafted_by_player"] = True
            player.inventory.add_item(ordinary_token)
            rejected = server.execute_command(session.session_id, "fulfill river_fine_token")
            self.assertIn("material quality 2", "\n".join(str(event["payload"]) for event in rejected))

            fine_token = ItemFactory.create_item_from_template("item_river_token", server.world)
            self.assertIsNotNone(fine_token)
            fine_token.properties.update({"crafted_by_player": True, "material_quality_score": 2})
            fine_token.stackable = False
            fine_token.update_property("stackable", False)
            player.inventory.add_item(fine_token)
            premium = server.execute_command(session.session_id, "fulfill river_fine_token")
            premium_text = "\n".join(str(event["payload"]) for event in premium)
            self.assertIn("Order fulfilled", premium_text)
            self.assertIn("28 gold", premium_text)

            restored = Player.from_dict(player.to_dict(server.world), server.world)
            self.assertIn("riverside_charm", restored.vendor_orders_completed.get("merchant", []))
            self.assertIn("river_fine_token", restored.vendor_orders_completed.get("merchant", []))
        finally:
            server.shutdown()

    def test_premium_commission_requires_a_quality_bearing_crafted_delivery(self) -> None:
        server = HeadlessServer(
            db_path=":memory:", content_set_path=str(FANTASY_FRONTIER), deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="premium_commission_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            player.npc_relationships["village_elder"] = 10
            board_index = next(
                index + 1 for index, quest in enumerate(server.world.quest_board)
                if quest.get("template_id") == "quest_river_fine_token_commission"
            )
            accepted = server.execute_command(session.session_id, f"accept quest {board_index}")
            self.assertIn("Quest Accepted", "\n".join(str(event["payload"]) for event in accepted))

            ordinary = ItemFactory.create_item_from_template("item_river_token", server.world)
            self.assertIsNotNone(ordinary)
            ordinary.properties["crafted_by_player"] = True
            player.inventory.add_item(ordinary)
            rejected = server.execute_command(session.session_id, "give river-clay token to Elder Thorne")
            self.assertIn("requires material quality 2", "\n".join(str(event["payload"]) for event in rejected))

            fine = ItemFactory.create_item_from_template("item_river_token", server.world)
            self.assertIsNotNone(fine)
            fine.properties.update({"crafted_by_player": True, "material_quality_score": 2})
            fine.stackable = False
            fine.update_property("stackable", False)
            player.inventory.add_item(fine)
            completed = server.execute_command(session.session_id, "give river-clay token to Elder Thorne")
            completed_text = "\n".join(str(event["payload"]) for event in completed)
            self.assertIn("Quest Complete", completed_text)
            self.assertIn("24 Gold", completed_text)
        finally:
            server.shutdown()

    def test_content_authored_attachment_modifies_equipped_combat_and_persists(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="attachment_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            faceted = ItemFactory.create_item_from_template("item_faceted_rose_quartz", server.world)
            self.assertIsNotNone(faceted)
            player.inventory.add_item(faceted)
            server.execute_command(session.session_id, "equip rusty dagger")
            baseline_attack = player.get_attack_power()

            attached = server.execute_command(session.session_id, "attach faceted rose quartz to rusty dagger")
            self.assertIn("install faceted rose quartz", "\n".join(str(event["payload"]) for event in attached))
            inventory = next(event["payload"] for event in attached if event["type"] == "inventory")
            equipped_dagger = next(item for item in inventory["equipped"] if item["item_id"] == "item_starter_dagger")
            self.assertEqual(["faceted rose quartz"], equipped_dagger["attachments"])
            self.assertEqual(baseline_attack + 1, player.get_attack_power())
            self.assertEqual(0, player.inventory.count_item("item_faceted_rose_quartz"))

            detached = server.execute_command(session.session_id, "detach ornament from rusty dagger")
            self.assertIn("remove faceted rose quartz", "\n".join(str(event["payload"]) for event in detached))
            self.assertEqual(baseline_attack, player.get_attack_power())
            self.assertEqual(1, player.inventory.count_item("item_faceted_rose_quartz"))

            server.execute_command(session.session_id, "attach faceted rose quartz to rusty dagger")

            restored = Player.from_dict(player.to_dict(server.world), server.world)
            self.assertIsNotNone(restored)
            assert restored is not None
            self.assertEqual(player.get_attack_power(), restored.get_attack_power())
            dagger = restored.equipment["main_hand"]
            self.assertEqual("item_faceted_rose_quartz", dagger.get_property("attachments")[0]["item_id"])
        finally:
            server.shutdown()

    def test_second_commission_can_be_funded_and_completed_from_the_first(self) -> None:
        """The authored social ladder has a player-facing economic path."""
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="second_commission_player")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)

            server.execute_command(session.session_id, "accept quest 1")
            for command in ("west", "south", "gather herb bed", "gather herb bed", "craft tie_wildflower_posy", "north", "east"):
                server.execute_command(session.session_id, command)
            first_delivery = server.execute_command(session.session_id, "give wildflower posy to Elder Thorne")
            self.assertIn("Quest Complete", "\n".join(str(event["payload"]) for event in first_delivery))
            self.assertEqual(12, player.runtime_state.gold)

            server.execute_command(session.session_id, "accept quest 1")
            for command in ("east", "east"):
                server.execute_command(session.session_id, command)
            server.execute_command(session.session_id, "trade Talia")
            bought = server.execute_command(session.session_id, "buy hand axe")
            self.assertIn("You buy", "\n".join(str(event["payload"]) for event in bought))
            self.assertEqual(0, player.runtime_state.gold)

            for command in ("east", "east", "east", "northwest", "west", "gather fallen bough", "gather fallen bough"):
                server.execute_command(session.session_id, command)
            crafted = server.execute_command(session.session_id, "craft carve_riverside_charm")
            self.assertIn("Successfully", "\n".join(str(event["payload"]) for event in crafted))

            for command in ("east", "southeast", "west", "west", "west", "west", "west"):
                server.execute_command(session.session_id, command)
            completed = server.execute_command(session.session_id, "give carved riverside charm to Elder Thorne")
            self.assertIn("Quest Complete", "\n".join(str(event["payload"]) for event in completed))
            self.assertEqual(20, player.runtime_state.gold)
        finally:
            server.shutdown()


if __name__ == "__main__":
    unittest.main()
