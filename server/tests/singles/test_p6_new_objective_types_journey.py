"""Live journeys for the four objective types P6 added to the engine.

`test_p6_new_objective_types.py` drives each type through the engine directly.
That proves the mechanic, not the content: an objective type with no authored
quest is a mechanic no player can reach, and four of the five P6 types had none
until these quests. Every test here starts at the quest board, accepts what a
player can see, and finishes the quest the way a player would -- no objective
dicts are hand-built, and nothing is injected into quest state.

The world tick assertion is `QuestManager.check_quest_completion`, which is the
same call `World.update` makes for every connected player each tick
(`world.py`): the passive types (relationship, discover_n) are meant to notice a
condition becoming true while the player is off doing something else.
"""

import re
import unittest

from engine.core.advancement import ledger_entries_of_kind
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER
from tests.journey_runner import GotoDirective

DELIVERY_PACKAGE = "quest_package_generic"

_MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def _plain_text(text: str) -> str:
    """The text a player reads, without the client's colour markup."""
    return _MARKUP.sub("", text)


class TestObjectiveTypeContentJourneys(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.session = self.server.create_session(player_id="objective_type_journeys")
        self.server.execute_command(self.session.session_id, "char create Rowan")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    # -- helpers -------------------------------------------------------------

    def command(self, text: str) -> str:
        return "\n".join(
            str(event.get("payload", ""))
            for event in self.server.execute_command(self.session.session_id, text)
            if event.get("type") == "text"
        )

    def walk_to(self, region_id: str, room_id: str, limit: int = 80) -> None:
        directive = GotoDirective()
        command = "__goto__:%s:%s" % (region_id, room_id)
        for _ in range(limit):
            direction = directive.next_direction(command, self.server, self.session.session_id)
            if direction == "":
                return
            self.command(direction)
        self.fail("could not reach %s:%s" % (region_id, room_id))

    def accept_from_the_board(self, title: str) -> str:
        """Take the notice a player can see, by the number the board printed.

        Read through the markup the client renders: the number a player types is
        the one in the listing, which in player mode is *not* the board index
        (gated notices are hidden rather than shown greyed out).
        """
        listing = _plain_text(self.command("look board"))
        number = None
        for line in listing.splitlines():
            stripped = line.strip()
            if not stripped.startswith("[") or "]" not in stripped:
                continue
            index, _, label = stripped[1:].partition("]")
            if label.strip() == title:
                number = index.strip()
                break
        self.assertIsNotNone(number, "the board does not offer %r:\n%s" % (title, listing))
        return self.command("accept quest %s" % number)

    def active_quest(self, template_id: str) -> dict:
        for quest_id, quest in self.player.runtime_state.quests.active.items():
            if quest.get("template_id") == template_id or quest_id.startswith(template_id + "_"):
                return quest
        self.fail("%s is not active (active: %s)" % (
            template_id, [q.get("template_id") for q in self.player.runtime_state.quests.active.values()]))

    def world_tick(self) -> None:
        """The passive objective check the world runs for every player."""
        self.server.world.quest_manager.check_quest_completion(self.player)

    def place(self, region_id: str, room_id: str) -> None:
        self.player.current_region_id = region_id
        self.player.current_room_id = room_id

    def _crafted_gift(self, item_id: str):
        item = ItemFactory.create_item_from_template(item_id, self.server.world)
        self.assertIsNotNone(item, item_id)
        item.properties["crafted_by_player"] = True
        self.player.inventory.add_item(item)
        return item

    # -- relationship --------------------------------------------------------

    def test_earning_the_hermits_trust_completes_the_elder_errand(self) -> None:
        accepted = self.accept_from_the_board("The Hermit of the Deep Wood")
        self.assertIn("Quest Accepted", accepted)
        quest = self.active_quest("quest_hermit_of_the_deep_wood")
        self.assertEqual("relationship", quest["stages"][0]["objective"]["type"])

        self.walk_to("forest", "ancient_oak")
        bryn = self.server.world.find_npc_in_room_for_player("bryn", self.player)
        self.assertIsNotNone(bryn, "Old Bryn should be living at the ancient oak")
        self.assertIn("visitors", self.command("talk Old Bryn"))

        # One crafted gift is worth five ordinary ones, which is what makes the
        # quest a first lesson in how the valley remembers people.
        self._crafted_gift("item_leather_cap")
        given = self.command("give leather cap to Old Bryn")
        self.assertIn("Relationship: +5", given)
        self.assertEqual(5, self.player.npc_relationships["forest_hermit"])
        self.assertEqual("active", quest["state"], "trust alone is not the turn-in")

        self.world_tick()
        self.assertEqual("ready_to_complete", quest["state"])

        self.walk_to("town", "town_square")
        done = self.command("talk Elder Thorne complete")
        self.assertIn("Quest Complete", done)
        self.assertIn("still cursing the village", done)
        self.assertNotIn(quest, self.player.runtime_state.quests.active.values())

    def test_the_hermit_quest_stays_open_while_he_is_still_a_stranger(self) -> None:
        """A gift to somebody else must not stand in for the hermit's trust."""
        self.accept_from_the_board("The Hermit of the Deep Wood")
        quest = self.active_quest("quest_hermit_of_the_deep_wood")

        self.place("town", "blacksmith_interior")
        self._crafted_gift("item_leather_cap")
        self.command("give leather cap to Grenda")
        self.world_tick()

        self.assertEqual("active", quest["state"])
        self.assertNotIn("forest_hermit", self.player.npc_relationships)
        self.assertEqual(5, self.player.npc_relationships["blacksmith"])

    # -- discover_n ----------------------------------------------------------

    def test_the_curators_catalogue_fills_from_the_field_journal(self) -> None:
        accepted = self.accept_from_the_board("A Catalogue of the Valley")
        self.assertIn("Quest Accepted", accepted)
        quest = self.active_quest("quest_catalogue_of_the_valley")
        objective = quest["stages"][0]["objective"]
        self.assertEqual("discover_n", objective["type"])
        required = int(objective["required_count"])

        recorded = ledger_entries_of_kind(self.player, "item")
        needed = max(0, required - recorded)
        self.world_tick()
        if needed:
            self.assertEqual("active", quest["state"], "the quest completed early")

        # Six things a traveller would actually pick up on the way out of town.
        for item_id in (
            "item_wild_herbs",
            "item_softwood",
            "item_river_clay",
            "item_iron_ingot",
            "item_ale",
            "item_glass_vial",
        )[:needed]:
            item = ItemFactory.create_item_from_template(item_id, self.server.world)
            self.assertIsNotNone(item, item_id)
            self.server.world.add_item_to_room(
                self.player.current_region_id, self.player.current_room_id, item
            )
            self.assertIn("You pick up", self.command("get %s" % item.name))

        self.assertGreaterEqual(ledger_entries_of_kind(self.player, "item"), required)
        self.world_tick()
        self.assertEqual("ready_to_complete", quest["state"])

        self.walk_to("town", "museum_interior")
        done = self.command("talk Curator Vane complete")
        self.assertIn("Quest Complete", done)

    # -- craft_quality -------------------------------------------------------

    def _brew_one_barrel(self) -> str:
        """One successful brew, retried the way a brewer retries a spoiled batch.

        `craft` rolls against the recipe's difficulty (12 here), and a failed
        attempt keeps the materials, so a run that stopped at the first bad roll
        would be testing the dice rather than the quest.
        """
        for _ in range(30):
            if self.player.inventory.count_item("item_ale_wort") < 4:
                wort = ItemFactory.create_item_from_template("item_ale_wort", self.server.world)
                self.player.inventory.add_item(wort, 4)
            result = self.command("craft ferment house ale")
            if "Successfully" in result:
                return result
        self.fail("the house ale never came out")

    def test_the_house_brew_needs_a_fine_barrel_not_merely_an_early_one(self) -> None:
        """Eight barrels is where this recipe's ladder reaches `fine`, so the
        quest cannot be satisfied by the first two that come out sound."""
        accepted = self.accept_from_the_board("The House Brew")
        self.assertIn("Quest Accepted", accepted)
        quest = self.active_quest("quest_house_brew")

        self.walk_to("town", "tavern_kitchen")
        self.assertIn("drying rack", self.command("look").lower())

        for craft_number in range(1, 9):
            result = self._brew_one_barrel()
            self.assertIn("Craft quality", result)
            self.assertEqual(craft_number, self.player.recipe_craft_counts["ferment_house_ale"])
            if craft_number < 8:
                self.assertEqual(
                    "active", quest["state"],
                    "barrel %d was good enough to satisfy a fine request" % craft_number,
                )
            else:
                self.assertIn("Fine", result)
            # A barrel weighs fifty: a real brewer sells or cellars each one
            # before laying down the next, and so does this run.
            self.assertEqual(1, self.player.inventory.remove_item("item_barrel_ale", 1)[1])

        self.assertEqual(8, self.player.recipe_craft_counts["ferment_house_ale"])
        self.assertEqual("ready_to_complete", quest["state"])

        self.walk_to("town", "tavern_main_floor")
        done = self.command("talk Barlin complete")
        self.assertIn("Quest Complete", done)
        self.assertIn("Same colour, same nose", done)

    # -- deliver_multi -------------------------------------------------------

    def test_two_sealed_packets_completes_only_at_the_second_recipient(self) -> None:
        accepted = self.accept_from_the_board("Two Sealed Packets")
        self.assertIn("You received the packages", accepted)
        quest = self.active_quest("quest_upcountry_packets")
        recipients = quest["stages"][0]["objective"]["recipients"]
        self.assertEqual(2, len(recipients))
        self.assertEqual(2, self.player.inventory.count_item(DELIVERY_PACKAGE))

        self.walk_to("portbridge", "sailors_rest_inn_common")
        first = self.command("give sealed packet to Nell")
        self.assertIn("1/2 delivered", first)
        self.assertIn("Mara Vale", first)
        self.assertEqual("active", quest["state"])
        self.assertEqual(1, self.player.inventory.count_item(DELIVERY_PACKAGE))

        self.walk_to("frostpeak_outpost", "mining_lodge")
        second = self.command("give sealed packet to Mara")
        self.assertIn("Quest Complete", second)
        self.assertIn("carried up the pass by hand", second)
        self.assertEqual(0, self.player.inventory.count_item(DELIVERY_PACKAGE))
        self.assertNotIn(quest, self.player.runtime_state.quests.active.values())

    def test_the_board_serves_the_outposts_and_not_only_the_home_towns(self) -> None:
        """One shared board, five places to read it: a player who has walked to
        Frostpeak, Sunscorch or Aurelia can take work without walking back."""
        for region_id, room_id in (
            ("frostpeak_outpost", "mining_lodge"),
            ("sunscorch_caravanserai", "wayfarers_rest"),
            ("aurelia_city", "guild_square"),
        ):
            self.place(region_id, room_id)
            listing = _plain_text(self.command("look board"))
            self.assertIn("Quest Board", listing, "%s:%s has no board" % (region_id, room_id))
            self.assertIn("Two Sealed Packets", listing)

    def test_a_packet_cannot_be_gifted_away_to_a_bystander(self) -> None:
        """A quest item is not the player's to give: the vendor path already
        refuses to buy one, and a courier who handed a packet to the blacksmith
        would otherwise be left with a delivery that can never be finished."""
        self.accept_from_the_board("Two Sealed Packets")
        quest = self.active_quest("quest_upcountry_packets")

        self.walk_to("town", "blacksmith_interior")
        result = self.command("give sealed packet to Grenda")

        self.assertIn("isn't something you can part with", result)
        self.assertEqual(2, self.player.inventory.count_item(DELIVERY_PACKAGE))
        self.assertEqual("active", quest["state"])
        self.assertEqual([], quest["stages"][0]["objective"].get("delivered_to", []))


if __name__ == "__main__":
    unittest.main()
