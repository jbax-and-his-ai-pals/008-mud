# tests/singles/test_vendor_order_references.py
"""A buy order asks for an item the way everything else does.

An order used to name one template. It may now name a *family* or a
*capability*, with a material-grade floor -- the same reference a recipe
ingredient uses, resolved by the same rule (`engine/items/references.py`) -- so
a vendor who will take "two parts of grade 2 or better" does not need the author
to list every part in the set, and does not need editing when a new one is added.

The first class below walks the shipped sci-fi set, because that is where an
order actually names a family. The second uses the fantasy set's merchant with
orders written in the test, for the shapes the shipped content does not happen
to use yet.
"""
import unittest
from pathlib import Path

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
ORBITAL_SALVAGE = REPO_ROOT / "content_sets" / "orbital_salvage"


class OrbitalVendorTest(unittest.TestCase):
    """Ivo's orders, which name the set's own family."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(ORBITAL_SALVAGE),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="salvager")
        self._run("char create Vess")
        self.world = self.server.world
        self.player = self.server.get_player_for_session(self.session.session_id)
        # The instance id, not the template id: Ivo is placed in the dock ring.
        self.vendor = next(
            npc for npc in self.world.npcs.values() if npc.obj_id == "ivo_dock"
        )
        self.player.trading_with = self.vendor.obj_id

    def _run(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        return "\n".join(
            str(event.get("payload")) for event in events if event.get("type") == "text"
        )

    def give(self, item_id: str, material_quality_score: int = 0):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.assertIsNotNone(item, "template %r produced no item" % item_id)
        # What the bench would have rolled onto it.
        item.properties["material_quality_score"] = material_quality_score
        item.stackable = False
        item.update_property("stackable", False)
        self.player.inventory.add_item(item)
        return item

    def test_an_order_is_listed_by_what_it_wants_not_by_a_template_name(self):
        listed = self._run("orders")
        self.assertIn("serviceable_parts", listed)
        self.assertIn("2 x Salvaged part", listed)
        self.assertIn("material quality 2+", listed)

    def test_each_order_carries_its_own_grade_floor(self):
        self.assertIn("material quality 3+", self._run("orders"))

    def test_a_part_below_the_floor_is_refused_by_name(self):
        self.give("item_servo_cluster", material_quality_score=1)
        self.give("item_cell_stack", material_quality_score=1)
        result = self._run("fulfill serviceable_parts")
        self.assertIn("Salvaged part", result)
        self.assertIn("material grade 2 or better", result)
        self.assertEqual(
            2,
            self.player.inventory.count_item("item_servo_cluster")
            + self.player.inventory.count_item("item_cell_stack"),
        )

    def test_parts_at_the_floor_fill_the_order(self):
        self.give("item_servo_cluster", material_quality_score=2)
        self.give("item_cell_stack", material_quality_score=2)
        result = self._run("fulfill serviceable_parts")
        self.assertIn("Order fulfilled", result)
        self.assertEqual(0, self.player.inventory.count_item("item_servo_cluster"))
        self.assertEqual(0, self.player.inventory.count_item("item_cell_stack"))

    def test_the_order_takes_any_member_of_the_family_it_never_named(self):
        self.give("item_lattice_shard", material_quality_score=3)
        result = self._run("fulfill clean_part")
        self.assertIn("Order fulfilled", result)
        self.assertEqual(0, self.player.inventory.count_item("item_lattice_shard"))

    def test_an_item_outside_the_family_is_not_counted(self):
        self.give("item_patch_kit", material_quality_score=5)
        result = self._run("fulfill clean_part")
        self.assertIn("Salvaged part", result)
        self.assertEqual(1, self.player.inventory.count_item("item_patch_kit"))

    def test_the_delivery_says_what_grade_was_accepted(self):
        self.give("item_lattice_shard", material_quality_score=3)
        self.assertIn("material grade 3", self._run("fulfill clean_part"))

    def test_the_reward_is_the_sets_own_currency(self):
        self.give("item_servo_cluster", material_quality_score=3)
        self.give("item_cell_stack", material_quality_score=3)
        result = self._run("fulfill serviceable_parts")
        self.assertIn("credits", result)
        self.assertNotIn("gold", result)

    def test_a_fresh_player_cannot_fill_the_order_yet(self):
        """The order is a reason to go and work the bench, not a free payout."""
        self.assertIn("Salvaged part", self._run("fulfill serviceable_parts"))


class TestOrderReferenceShapes(GameTestBase):
    """Capability, crafted-only and the two material-quality spellings."""

    def setUp(self):
        super().setUp()
        self.vendor = NPCFactory.create_npc_from_template("merchant", self.world)
        self.world.add_npc(self.vendor)
        self.vendor.current_region_id = self.player.current_region_id
        self.vendor.current_room_id = self.player.current_room_id
        self.player.trading_with = self.vendor.obj_id

    def set_orders(self, orders):
        self.vendor.properties["buy_orders"] = orders

    def give(self, item_id: str, material_quality_score: int = 0, crafted: bool = False):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.assertIsNotNone(item)
        item.properties["material_quality_score"] = material_quality_score
        if crafted:
            item.properties["crafted_by_player"] = True
        item.stackable = False
        item.update_property("stackable", False)
        self.player.inventory.add_item(item)
        return item

    def test_a_capability_order_accepts_a_family_that_declares_it(self):
        self.set_orders([{
            "id": "any_material", "capability": "crafting_input", "quantity": 1,
            "reward_gold": 10, "repeatable": True,
        }])
        self.give("item_iron_ingot")
        self.assertIn("Order fulfilled", self.game.process_command("fulfill any_material"))

    def test_a_capability_order_refuses_a_family_that_does_not(self):
        self.set_orders([{
            "id": "any_material", "capability": "crafting_input", "quantity": 1,
            "reward_gold": 10, "repeatable": True,
        }])
        self.give("item_iron_sword")
        result = self.game.process_command("fulfill any_material")
        self.assertIn("crafting input", result)
        self.assertEqual(1, self.player.inventory.count_item("item_iron_sword"))

    def test_the_short_material_quality_spelling_is_honoured(self):
        """Content may author either spelling; both mean the same floor."""
        self.set_orders([{
            "id": "fine_only", "item_id": "item_iron_ingot", "quantity": 1,
            "reward_gold": 10, "min_material_quality": 2, "repeatable": True,
        }])
        self.give("item_iron_ingot", material_quality_score=1)
        self.assertIn("material grade 2 or better", self.game.process_command("fulfill fine_only"))

    def test_the_older_quality_spelling_still_works(self):
        self.set_orders([{
            "id": "fine_only", "item_id": "item_iron_ingot", "quantity": 1,
            "reward_gold": 10, "min_material_quality_score": 2, "repeatable": True,
        }])
        item = self.give("item_iron_ingot", material_quality_score=2)
        self.assertEqual(2, item.get_property("material_quality_score"))
        self.assertIn("Order fulfilled", self.game.process_command("fulfill fine_only"))

    def test_a_crafted_only_order_says_so_when_the_item_was_not_made_by_you(self):
        self.set_orders([{
            "id": "commission", "item_id": "item_iron_ingot", "quantity": 1,
            "reward_gold": 10, "crafted_only": True,
        }])
        self.give("item_iron_ingot", crafted=False)
        result = self.game.process_command("fulfill commission")
        self.assertIn("made by you", result)
        self.assertEqual(1, self.player.inventory.count_item("item_iron_ingot"))

    def test_a_crafted_only_order_accepts_one_you_made(self):
        self.set_orders([{
            "id": "commission", "item_id": "item_iron_ingot", "quantity": 1,
            "reward_gold": 10, "crafted_only": True,
        }])
        self.give("item_iron_ingot", crafted=True)
        self.assertIn("Order fulfilled", self.game.process_command("fulfill commission"))

    def test_a_crafted_only_family_order_needs_both_conditions(self):
        self.set_orders([{
            "id": "commission", "item_family": "material", "quantity": 1,
            "reward_gold": 10, "crafted_only": True, "repeatable": True,
        }])
        self.give("item_iron_ingot", crafted=False)
        self.assertIn("made by you", self.game.process_command("fulfill commission"))

        self.give("item_iron_ingot", crafted=True)
        self.assertIn("Order fulfilled", self.game.process_command("fulfill commission"))

    def test_an_order_naming_nothing_can_never_be_filled(self):
        self.set_orders([{
            "id": "mystery", "quantity": 1, "reward_gold": 10,
        }])
        self.give("item_iron_ingot")
        result = self.game.process_command("fulfill mystery")
        self.assertIn("something", result.lower())
        self.assertEqual(1, self.player.inventory.count_item("item_iron_ingot"))


if __name__ == "__main__":
    unittest.main()
