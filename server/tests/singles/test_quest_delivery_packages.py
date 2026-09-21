"""What a delivery hands the player when they accept it.

`deliver` has always built its package here; `deliver_multi` had no way to
obtain its goods at all, so the objective type was unplayable by construction --
`give_handler` matches copies of one template that nothing in the game ever
created. These tests pin both halves of the one rule, plus the two ways it is
allowed to refuse.
"""

import unittest

from engine.core.quests.packages import declared_packages
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER

PACKAGE_TEMPLATE = "quest_package_generic"


class TestDeclaredPackages(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True
        )
        self.world = self.server.world

    def tearDown(self) -> None:
        self.server.shutdown()

    # -- the single delivery -------------------------------------------------

    def test_single_delivery_keeps_its_authored_instance_identity(self) -> None:
        objective = {
            "type": "deliver",
            "item_template_id": PACKAGE_TEMPLATE,
            "item_instance_id": "delivery_ab12",
            "item_to_deliver_name": "sealed orders",
            "item_to_deliver_description": "A folded order for the harbourmaster.",
        }

        packages, problem = declared_packages(self.world, objective)

        self.assertEqual("", problem)
        self.assertEqual(1, len(packages))
        self.assertEqual("delivery_ab12", packages[0].obj_id)
        self.assertEqual("sealed orders", packages[0].name)
        self.assertEqual("A folded order for the harbourmaster.", packages[0].description)

    def test_single_delivery_without_an_instance_id_is_refused(self) -> None:
        objective = {"type": "deliver", "item_template_id": PACKAGE_TEMPLATE}

        packages, problem = declared_packages(self.world, objective)

        self.assertEqual([], packages)
        self.assertIn("incomplete item data", problem)

    def test_crafted_only_delivery_hands_over_nothing(self) -> None:
        """The museum commission's route: the player makes the thing."""
        objective = {
            "type": "deliver",
            "item_template_id": "item_wildflower_posy",
            "crafted_only": True,
            "recipient_template_id": "village_elder",
        }

        packages, problem = declared_packages(self.world, objective)

        self.assertEqual([], packages)
        self.assertEqual("", problem)

    def test_an_unknown_item_template_is_refused_rather_than_guessed(self) -> None:
        objective = {
            "type": "deliver",
            "item_template_id": "item_that_was_never_authored",
            "item_instance_id": "ghost_package",
        }

        packages, problem = declared_packages(self.world, objective)

        self.assertEqual([], packages)
        self.assertIn("no deliverable item", problem)

    # -- the courier run -----------------------------------------------------

    def test_multi_delivery_builds_one_separate_package_per_recipient(self) -> None:
        objective = {
            "type": "deliver_multi",
            "item_template_id": PACKAGE_TEMPLATE,
            "item_to_deliver_name": "sealed packet",
            "recipients": [
                {"template_id": "portbridge_innkeeper", "name": "Nell"},
                {"template_id": "frostpeak_lodgekeeper", "name": "Mara Vale"},
                {"template_id": "merchant", "name": "Talia"},
            ],
        }

        packages, problem = declared_packages(self.world, objective)

        self.assertEqual("", problem)
        self.assertEqual(3, len(packages))
        # The tracking in give_handler matches the *template*, so every package
        # carries it as its id and stays individually removable.
        self.assertEqual({PACKAGE_TEMPLATE}, {package.obj_id for package in packages})
        self.assertEqual(3, len({id(package) for package in packages}))
        self.assertEqual({"sealed packet"}, {package.name for package in packages})

    def test_multi_delivery_without_recipients_is_refused(self) -> None:
        objective = {"type": "deliver_multi", "item_template_id": PACKAGE_TEMPLATE, "recipients": []}

        packages, problem = declared_packages(self.world, objective)

        self.assertEqual([], packages)
        self.assertIn("nobody to deliver to", problem)

    def test_multi_delivery_packages_run_out_at_the_same_count_as_recipients(self) -> None:
        objective = {
            "type": "deliver_multi",
            "item_template_id": PACKAGE_TEMPLATE,
            "recipients": [{"template_id": "merchant"}, {"template_id": "curator"}],
        }

        packages, _ = declared_packages(self.world, objective)

        # Two distinct instances, each removable on its own: handing one over
        # must leave the other in the pack.
        self.assertTrue(self.world.item_templates[PACKAGE_TEMPLATE])
        self.assertEqual(2, len(packages))
        self.assertNotEqual(packages[0], packages[1])

    # -- objectives that are not deliveries ----------------------------------

    def test_a_kill_objective_hands_over_nothing(self) -> None:
        packages, problem = declared_packages(self.world, {"type": "kill", "target_template_id": "wolf"})

        self.assertEqual([], packages)
        self.assertEqual("", problem)

    def test_a_missing_objective_is_not_an_error(self) -> None:
        self.assertEqual(([], ""), declared_packages(self.world, None))


class TestAcceptingADeliveryAtTheBoard(unittest.TestCase):
    """The same rule, reached the way a player reaches it."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=FANTASY_FRONTIER,
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.session = self.server.create_session(player_id="delivery_packages")
        self.server.execute_command(self.session.session_id, "char create Courier")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def tearDown(self) -> None:
        self.server.shutdown()

    def _accept(self, template_id: str) -> str:
        board = self.server.world.quest_board
        index = next(
            i for i, quest in enumerate(board) if str(quest.get("template_id", "")) == template_id
        )
        events = self.server.execute_command(self.session.session_id, "accept quest %d" % (index + 1))
        return "\n".join(str(event.get("payload", "")) for event in events if event.get("type") == "text")

    def _board_holds(self, template_id: str) -> bool:
        return any(
            str(quest.get("template_id", "")) == template_id for quest in self.server.world.quest_board
        )

    def test_accepting_the_courier_run_puts_two_packages_in_the_pack(self) -> None:
        text = self._accept("quest_upcountry_packets")

        self.assertIn("Quest Accepted", text)
        self.assertIn("You received the packages", text)
        self.assertEqual(2, self.player.inventory.count_item(PACKAGE_TEMPLATE))
        # Two units, not one stack of two: a stack could not be handed over one
        # recipient at a time.
        instances = [slot.item for slot in self.player.inventory.slots if slot.item]
        packets = [item for item in instances if item.obj_id == PACKAGE_TEMPLATE]
        self.assertEqual(2, len(packets))

    def test_a_full_pack_refuses_the_job_and_leaves_it_on_the_board(self) -> None:
        self.player.inventory.max_weight = 0.0

        text = self._accept("quest_upcountry_packets")

        self.assertIn("Inventory full", text)
        self.assertEqual(0, self.player.inventory.count_item(PACKAGE_TEMPLATE))
        self.assertTrue(self._board_holds("quest_upcountry_packets"))
        self.assertEqual({}, dict(self.player.runtime_state.quests.active))

    def test_only_the_package_that_did_not_fit_is_given_back(self) -> None:
        """A refused job must not leave the player carrying half of it."""
        self.player.inventory.max_weight = self.player.inventory.get_total_weight() + 1.0

        text = self._accept("quest_upcountry_packets")

        self.assertIn("Inventory full", text)
        self.assertEqual(0, self.player.inventory.count_item(PACKAGE_TEMPLATE))
        self.assertTrue(self._board_holds("quest_upcountry_packets"))

    def test_the_bandit_campaigns_treaty_is_now_a_deliverable_package(self) -> None:
        """The peaceful branch of `bandit_rebellion` could not be accepted at
        all: its deliver objective named no instance id, so the board answered
        "incomplete item data" and the campaign stopped there."""
        quest = self.server.world.quest_manager.quest_templates["quest_deliver_treaty"]

        packages, problem = declared_packages(self.server.world, quest["stages"][0]["objective"])

        self.assertEqual("", problem)
        self.assertEqual(1, len(packages))
        self.assertEqual("Peace Treaty", packages[0].name)
        self.assertEqual("treaty_of_the_valley", packages[0].obj_id)


if __name__ == "__main__":
    unittest.main()
