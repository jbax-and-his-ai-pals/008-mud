# tests/singles/test_container_class_direct.py
"""Coverage for engine/items/container.py exercised directly against the
Container class rather than through game commands: constructor content
hydration edge cases, examine()/list_contents() formatting, open/close,
toggle_lock's exact-id/fuzzy-name matching, pick_lock, magic_interact,
can_add/add_item/find_item_by_name/remove_item, and to_dict/from_dict
round-tripping -- most of which the existing command-driven container tests
never exercise at this direct, unit level."""

from tests.fixtures import GameTestBase
from engine.items.container import Container
from engine.items.item import Item
from engine.items.item_factory import ItemFactory


class TestConstructorHydration(GameTestBase):
    def test_stackable_kwarg_is_silently_dropped(self):
        # Container always forces stackable=False; passing it explicitly
        # would otherwise collide with the super().__init__ call.
        c = Container(obj_id="c1", name="Box", stackable=True)
        self.assertFalse(c.stackable)

    def test_contents_as_item_instances_are_kept_as_is(self):
        item = Item(obj_id="raw_item", name="Raw Item", description="x")
        c = Container(obj_id="c2", name="Box", contents=[item])
        self.assertIn(item, c.properties["contains"])

    def test_contents_as_dict_refs_are_hydrated_via_factory(self):
        c = Container(
            obj_id="c3", name="Box",
            contents=[{"item_id": "item_starter_dagger"}],
            world=self.world,
        )
        self.assertEqual(1, len(c.properties["contains"]))
        self.assertTrue(all(isinstance(i, Item) for i in c.properties["contains"]))

    def test_dict_ref_without_world_context_is_skipped_with_warning(self):
        c = Container(obj_id="c4", name="Box", contents=[{"item_id": "item_starter_dagger"}])
        self.assertEqual([], c.properties["contains"])

    def test_dict_ref_with_unknown_item_id_is_skipped(self):
        c = Container(
            obj_id="c5", name="Box",
            contents=[{"item_id": "not_a_real_item_template"}],
            world=self.world,
        )
        self.assertEqual([], c.properties["contains"])

    def test_contains_kwarg_used_when_contents_arg_absent(self):
        c = Container(obj_id="c6", name="Box", contains=[{"item_id": "item_starter_dagger"}], world=self.world)
        self.assertEqual(1, len(c.properties["contains"]))

    def test_malformed_entry_neither_item_nor_dict_ref_is_skipped(self):
        c = Container(obj_id="c7", name="Box", contents=["not_an_item_or_dict", 42, {"no_item_id_key": True}])
        self.assertEqual([], c.properties["contains"])


class TestExamine(GameTestBase):
    def test_locked_closed_container(self):
        c = Container(obj_id="ex1", name="Chest", locked=True, is_open=False)
        result = c.examine()
        self.assertIn("Locked", result)
        # contents_desc is computed as "It's locked." but the Contents section
        # is only appended when unlocked+open, so it never actually appears.
        self.assertNotIn("Contents:", result)

    def test_unlocked_closed_container(self):
        c = Container(obj_id="ex2", name="Chest", locked=False, is_open=False)
        result = c.examine()
        self.assertIn("Unlocked", result)
        self.assertIn("Closed", result)
        self.assertNotIn("Contents:", result)

    def test_unlocked_open_container_shows_contents(self):
        item = Item(obj_id="ex_item", name="Trinket", description="x", weight=1.0)
        c = Container(obj_id="ex3", name="Chest", locked=False, is_open=True, contents=[item])
        result = c.examine()
        self.assertIn("Open", result)
        self.assertIn("Contents:", result)
        self.assertIn("Trinket", result)

    def test_capacity_and_weight_shown(self):
        item = Item(obj_id="ex_item2", name="Rock", description="x", weight=3.0)
        c = Container(obj_id="ex4", name="Sack", capacity=10.0, is_open=True, contents=[item])
        result = c.examine()
        self.assertIn("3.0 / 10.0", result)


class TestListContents(GameTestBase):
    def test_empty_container_reports_empty(self):
        c = Container(obj_id="lc1", name="Box")
        self.assertEqual("  (Empty)", c.list_contents())

    def test_non_item_entries_are_skipped(self):
        c = Container(obj_id="lc2", name="Box")
        c.properties["contains"] = ["not_an_item", 42, None]
        # The early-return "(Empty)" check only looks at the raw list's
        # truthiness, not whether any entry is a real Item -- so a list of
        # junk entries silently produces an empty content-lines string.
        self.assertEqual("", c.list_contents())

    def test_stackable_items_are_grouped_with_count(self):
        c = Container(obj_id="lc3", name="Box")
        item_a = Item(obj_id="stackable_coin", name="Coin", description="x", stackable=True)
        item_b = Item(obj_id="stackable_coin", name="Coin", description="x", stackable=True)
        c.properties["contains"] = [item_a, item_b]
        result = c.list_contents()
        self.assertIn("Coin (x2)", result)

    def test_non_stackable_items_are_listed_individually(self):
        c = Container(obj_id="lc4", name="Box")
        sword_a = Item(obj_id="unique_sword", name="Sword", description="x", stackable=False)
        sword_b = Item(obj_id="unique_sword", name="Sword", description="x", stackable=False)
        c.properties["contains"] = [sword_a, sword_b]
        result = c.list_contents()
        self.assertEqual(2, result.count("Sword"))
        self.assertNotIn("(x2)", result)

    def test_single_stackable_item_has_no_count_suffix(self):
        c = Container(obj_id="lc5", name="Box")
        item = Item(obj_id="lone_coin", name="Coin", description="x", stackable=True)
        c.properties["contains"] = [item]
        result = c.list_contents()
        self.assertEqual("  - Coin", result)


class TestOpenClose(GameTestBase):
    def test_open_locked_container_fails(self):
        c = Container(obj_id="oc1", name="Chest", locked=True)
        result = c.open()
        self.assertIn("locked", result)
        self.assertFalse(c.properties["is_open"])

    def test_open_already_open_container_reports_so(self):
        c = Container(obj_id="oc2", name="Chest", is_open=True)
        result = c.open()
        self.assertIn("already open", result)

    def test_open_succeeds_and_lists_contents(self):
        item = Item(obj_id="oc_item", name="Gem", description="x")
        c = Container(obj_id="oc3", name="Chest", contents=[item])
        result = c.open()
        self.assertTrue(c.properties["is_open"])
        self.assertIn("Gem", result)

    def test_close_already_closed_container_reports_so(self):
        c = Container(obj_id="cc1", name="Chest", is_open=False)
        result = c.close()
        self.assertIn("already closed", result)

    def test_close_succeeds(self):
        c = Container(obj_id="cc2", name="Chest", is_open=True)
        result = c.close()
        self.assertFalse(c.properties["is_open"])
        self.assertIn("close", result)


class TestToggleLock(GameTestBase):
    def test_no_key_returns_false(self):
        c = Container(obj_id="tl1", name="Chest")
        self.assertFalse(c.toggle_lock(None))

    def test_exact_container_key_id_match_unlocks(self):
        c = Container(obj_id="tl2", name="Chest", key_id="the_right_key", locked=True)
        key = Item(obj_id="the_right_key", name="Key", description="x")
        self.assertTrue(c.toggle_lock(key))
        self.assertFalse(c.properties["locked"])

    def test_key_target_id_match_unlocks(self):
        c = Container(obj_id="tl3", name="Chest", locked=True)
        key = Item(obj_id="some_key", name="Key", description="x")
        key.properties["target_id"] = "tl3"
        self.assertTrue(c.toggle_lock(key))

    def test_fuzzy_name_inclusion_match_unlocks(self):
        c = Container(obj_id="tl4", name="Iron Strongbox", locked=True)
        key = Item(obj_id="fuzzy_key1", name="Strongbox", description="x")
        self.assertTrue(c.toggle_lock(key))

    def test_fuzzy_name_key_suffix_stripped_match_unlocks(self):
        c = Container(obj_id="tl5", name="Iron Strongbox", locked=True)
        key = Item(obj_id="fuzzy_key2", name="Iron Key", description="x")
        self.assertTrue(c.toggle_lock(key))

    def test_wrong_key_with_container_key_id_set_skips_fuzzy_match(self):
        # container_key_id is set, so the fuzzy-match branch (which only
        # applies when neither container_key_id nor key_target_id exist)
        # is never even attempted -- exact mismatch is the final word.
        c = Container(obj_id="tl6b", name="Chest", key_id="the_real_key", locked=True)
        key = Item(obj_id="wrong_key_id", name="Chest Key", description="x")  # would fuzzy-match by name
        self.assertFalse(c.toggle_lock(key))
        self.assertTrue(c.properties["locked"])

    def test_no_match_returns_false(self):
        c = Container(obj_id="tl6", name="Chest", locked=True)
        key = Item(obj_id="wrong_key", name="Completely Unrelated", description="x")
        self.assertFalse(c.toggle_lock(key))
        self.assertTrue(c.properties["locked"])

    def test_locking_forces_container_closed(self):
        c = Container(obj_id="tl7", name="Chest", key_id="lockkey1", locked=False, is_open=True)
        key = Item(obj_id="lockkey1", name="Key", description="x")
        self.assertTrue(c.toggle_lock(key))
        self.assertTrue(c.properties["locked"])
        self.assertFalse(c.properties["is_open"])


class TestPickLock(GameTestBase):
    def test_already_unlocked_reports_so(self):
        c = Container(obj_id="pl1", name="Chest", locked=False)
        ok, msg = c.pick_lock(self.player)
        self.assertFalse(ok)
        self.assertIn("already unlocked", msg)

    def test_locked_container_gets_unlocked(self):
        c = Container(obj_id="pl2", name="Chest", locked=True)
        ok, msg = c.pick_lock(self.player)
        self.assertTrue(ok)
        self.assertFalse(c.properties["locked"])


class TestMagicInteract(GameTestBase):
    def test_unlock_already_unlocked_fails(self):
        c = Container(obj_id="mi1", name="Chest", locked=False)
        ok, msg = c.magic_interact("unlock")
        self.assertFalse(ok)
        self.assertIn("not locked", msg)

    def test_unlock_locked_container_succeeds(self):
        c = Container(obj_id="mi2", name="Chest", locked=True)
        ok, msg = c.magic_interact("unlock")
        self.assertTrue(ok)
        self.assertFalse(c.properties["locked"])

    def test_lock_already_locked_fails(self):
        c = Container(obj_id="mi3", name="Chest", locked=True)
        ok, msg = c.magic_interact("lock")
        self.assertFalse(ok)
        self.assertIn("already locked", msg)

    def test_lock_unlocked_container_succeeds_and_closes_it(self):
        c = Container(obj_id="mi4", name="Chest", locked=False, is_open=True)
        ok, msg = c.magic_interact("lock")
        self.assertTrue(ok)
        self.assertTrue(c.properties["locked"])
        self.assertFalse(c.properties["is_open"])

    def test_unrecognized_interaction_has_no_effect(self):
        c = Container(obj_id="mi5", name="Chest")
        ok, msg = c.magic_interact("dance")
        self.assertFalse(ok)
        self.assertIn("no effect", msg)


class TestCanAddAndAddItem(GameTestBase):
    def test_cannot_add_self(self):
        c = Container(obj_id="ca1", name="Chest", is_open=True)
        ok, msg = c.can_add(c)
        self.assertFalse(ok)
        self.assertIn("inside itself", msg)

    def test_closed_container_rejects_add(self):
        c = Container(obj_id="ca2", name="Chest", is_open=False)
        item = Item(obj_id="ca_item", name="Gem", description="x", weight=1.0)
        ok, msg = c.can_add(item)
        self.assertFalse(ok)
        self.assertIn("closed", msg)

    def test_over_capacity_rejects_add(self):
        c = Container(obj_id="ca3", name="Chest", is_open=True, capacity=1.0)
        item = Item(obj_id="ca_item2", name="Boulder", description="x", weight=5.0)
        ok, msg = c.can_add(item)
        self.assertFalse(ok)
        self.assertIn("too full", msg)

    def test_valid_add_succeeds(self):
        c = Container(obj_id="ca4", name="Chest", is_open=True, capacity=10.0)
        item = Item(obj_id="ca_item3", name="Gem", description="x", weight=1.0)
        self.assertTrue(c.add_item(item))
        self.assertIn(item, c.properties["contains"])

    def test_add_item_respects_can_add_failure(self):
        c = Container(obj_id="ca5", name="Chest", is_open=False)
        item = Item(obj_id="ca_item4", name="Gem", description="x", weight=1.0)
        self.assertFalse(c.add_item(item))


class TestFindItemByName(GameTestBase):
    def test_finds_case_insensitive_partial_match(self):
        c = Container(obj_id="fi1", name="Chest")
        item = Item(obj_id="fi_item", name="Golden Ring", description="x")
        c.properties["contains"] = [item]
        self.assertIs(item, c.find_item_by_name("golden"))

    def test_no_match_returns_none(self):
        c = Container(obj_id="fi2", name="Chest")
        self.assertIsNone(c.find_item_by_name("anything"))

    def test_skips_non_matching_items_before_finding_match(self):
        c = Container(obj_id="fi4", name="Chest")
        decoy = Item(obj_id="fi_decoy", name="Rusty Nail", description="x")
        target = Item(obj_id="fi_target", name="Golden Ring", description="x")
        c.properties["contains"] = [decoy, target]
        self.assertIs(target, c.find_item_by_name("golden"))

    def test_non_item_entries_are_skipped(self):
        c = Container(obj_id="fi3", name="Chest")
        c.properties["contains"] = ["not_an_item"]
        self.assertIsNone(c.find_item_by_name("anything"))


class TestRemoveItem(GameTestBase):
    def test_closed_container_rejects_removal(self):
        c = Container(obj_id="ri1", name="Chest", is_open=False)
        item = Item(obj_id="ri_item", name="Gem", description="x")
        c.properties["contains"] = [item]
        self.assertFalse(c.remove_item(item))

    def test_removes_exact_instance(self):
        c = Container(obj_id="ri2", name="Chest", is_open=True)
        item = Item(obj_id="ri_item2", name="Gem", description="x")
        c.properties["contains"] = [item]
        self.assertTrue(c.remove_item(item))
        self.assertEqual([], c.properties["contains"])

    def test_removes_by_matching_obj_id_when_instance_not_found(self):
        c = Container(obj_id="ri3", name="Chest", is_open=True)
        original = Item(obj_id="ri_shared_id", name="Gem", description="x")
        duplicate_reference = Item(obj_id="ri_shared_id", name="Gem", description="x")
        c.properties["contains"] = [original]
        # duplicate_reference is a different object instance but shares obj_id.
        self.assertTrue(c.remove_item(duplicate_reference))
        self.assertEqual([], c.properties["contains"])

    def test_item_not_present_at_all_returns_false(self):
        c = Container(obj_id="ri4", name="Chest", is_open=True)
        item = Item(obj_id="ri_item3", name="Gem", description="x")
        self.assertFalse(c.remove_item(item))

    def test_removes_matching_obj_id_after_scanning_past_non_matches(self):
        c = Container(obj_id="ri5", name="Chest", is_open=True)
        decoy = Item(obj_id="ri_decoy", name="Decoy", description="x")
        original = Item(obj_id="ri_shared_id2", name="Gem", description="x")
        duplicate_reference = Item(obj_id="ri_shared_id2", name="Gem", description="x")
        c.properties["contains"] = [decoy, original]
        self.assertTrue(c.remove_item(duplicate_reference))
        self.assertEqual([decoy], c.properties["contains"])


class TestToDictFromDict(GameTestBase):
    def test_to_dict_serializes_contents_and_state(self):
        item = ItemFactory.create_item_from_template("item_starter_dagger", self.world)
        c = Container(obj_id="td1", name="Chest", locked=True, is_open=False, contents=[item])
        data = c.to_dict(self.world)
        self.assertEqual(True, data["properties"]["locked"])
        self.assertEqual(False, data["properties"]["is_open"])
        self.assertEqual(1, len(data["properties"]["contains"]))

    def test_to_dict_skips_non_item_entries(self):
        c = Container(obj_id="td6", name="Chest")
        c.properties["contains"] = ["not_an_item"]
        data = c.to_dict(self.world)
        self.assertEqual([], data["properties"]["contains"])

    def test_to_dict_skips_items_with_no_serializable_reference(self):
        from unittest.mock import patch
        c = Container(obj_id="td7", name="Chest")
        item = Item(obj_id="td7_item", name="Something", description="x")
        c.properties["contains"] = [item]
        with patch("engine.items.container._serialize_item_reference", return_value=None):
            data = c.to_dict(self.world)
        self.assertEqual([], data["properties"]["contains"])

    def test_from_dict_without_world_returns_none(self):
        self.assertIsNone(Container.from_dict({"name": "Chest"}, None))

    def test_from_dict_round_trips_contents(self):
        item = ItemFactory.create_item_from_template("item_starter_dagger", self.world)
        original = Container(obj_id="td2", name="Chest", locked=True, contents=[item])
        data = original.to_dict(self.world)
        rebuilt = Container.from_dict(data, self.world)
        self.assertIsNotNone(rebuilt)
        self.assertTrue(rebuilt.properties["locked"])
        self.assertEqual(1, len(rebuilt.properties["contains"]))

    def test_from_dict_with_non_list_contains_warns_and_yields_empty(self):
        data = {"obj_id": "td3", "name": "Chest", "properties": {"contains": "not_a_list"}}
        rebuilt = Container.from_dict(data, self.world)
        self.assertEqual([], rebuilt.properties["contains"])

    def test_from_dict_skips_malformed_refs_but_loads_valid_ones(self):
        data = {
            "obj_id": "td8", "name": "Chest",
            "properties": {"contains": [None, "not_a_dict", {"no_item_id": True}, {"item_id": "item_starter_dagger"}]},
        }
        rebuilt = Container.from_dict(data, self.world)
        self.assertEqual(1, len(rebuilt.properties["contains"]))

    def test_from_dict_skips_unknown_item_id_refs(self):
        data = {
            "obj_id": "td4", "name": "Chest",
            "properties": {"contains": [{"item_id": "not_a_real_item_template"}]},
        }
        rebuilt = Container.from_dict(data, self.world)
        self.assertEqual([], rebuilt.properties["contains"])

    def test_from_dict_applies_defaults_when_properties_missing(self):
        data = {"obj_id": "td5", "name": "Bare Chest"}
        rebuilt = Container.from_dict(data, self.world)
        self.assertIsNotNone(rebuilt)
        self.assertEqual(50.0, rebuilt.properties["capacity"])
        self.assertFalse(rebuilt.properties["locked"])
        self.assertIsNone(rebuilt.properties["key_id"])
        self.assertFalse(rebuilt.properties["is_open"])


if __name__ == "__main__":
    import unittest
    unittest.main()
