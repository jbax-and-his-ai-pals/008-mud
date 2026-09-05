# tests/singles/test_player_persistence_full.py
"""Coverage for engine/player/persistence.py's Player.from_dict: the
missing-gameplay-aspect guard, the malformed-skills-structure guard, the
stat-modifier loop's non-matching-effect skip, equipment restoration
(valid item, unknown slot, missing item_id, factory failure), the
no-conversation-history branch, and the no-normalize-callable branch."""

import unittest

from tests.fixtures import GameTestBase
from engine.player.core import Player


def _base_payload(world, **overrides):
    payload = {
        "name": "Test Player", "id": "test_player_persist",
        "gameplay": {
            "magic": {}, "combat": {}, "economy": {},
            "progression": {"skills": {}},
            "quests": {},
        },
        "current_location": {"region_id": world.content_set.start_region_id, "room_id": world.content_set.start_room_id},
    }
    payload.update(overrides)
    return payload


class TestFromDictGuards(GameTestBase):
    def test_missing_gameplay_raises(self):
        payload = _base_payload(self.world)
        del payload["gameplay"]
        with self.assertRaises(ValueError):
            Player.from_dict(payload, self.world)

    def test_non_dict_gameplay_raises(self):
        payload = _base_payload(self.world, gameplay="not a dict")
        with self.assertRaises(ValueError):
            Player.from_dict(payload, self.world)

    def test_non_dict_skills_raises(self):
        payload = _base_payload(self.world)
        payload["gameplay"]["progression"]["skills"] = "not a dict"
        with self.assertRaises(ValueError):
            Player.from_dict(payload, self.world)

    def test_unstructured_skill_value_raises(self):
        payload = _base_payload(self.world)
        payload["gameplay"]["progression"]["skills"] = {"crafting": "not structured"}
        with self.assertRaises(ValueError):
            Player.from_dict(payload, self.world)


class TestFromDictStatModifiers(GameTestBase):
    def test_loop_skips_non_stat_mod_effects_before_applying_one(self):
        payload = _base_payload(self.world)
        payload["effects"] = [
            {"name": "Regular Effect", "type": "dot"},
            {"name": "Strength Buff", "type": "stat_mod", "modifiers": {"strength": 5}},
        ]
        player = Player.from_dict(payload, self.world)
        self.assertEqual(player.stat_modifiers.get("strength"), 5)


class TestFromDictEquipment(GameTestBase):
    def test_unknown_slot_is_skipped(self):
        payload = _base_payload(self.world)
        payload["equipment"] = {"totally_bogus_slot_xyz": {"item_id": "item_iron_sword"}}
        player = Player.from_dict(payload, self.world)
        self.assertNotIn("totally_bogus_slot_xyz", player.equipment)

    def test_missing_item_id_is_skipped(self):
        payload = _base_payload(self.world)
        payload["equipment"] = {"main_hand": {"no_item_id_here": True}}
        player = Player.from_dict(payload, self.world)
        self.assertIsNone(player.equipment.get("main_hand"))

    def test_valid_item_ref_is_restored(self):
        payload = _base_payload(self.world)
        payload["equipment"] = {"main_hand": {"item_id": "item_iron_sword"}}
        player = Player.from_dict(payload, self.world)
        self.assertIsNotNone(player.equipment.get("main_hand"))

    def test_factory_failure_is_skipped_with_warning(self):
        import io
        from contextlib import redirect_stdout
        payload = _base_payload(self.world)
        payload["equipment"] = {"main_hand": {"item_id": "totally_bogus_item_template_xyz"}}
        buf = io.StringIO()
        with redirect_stdout(buf):
            player = Player.from_dict(payload, self.world)
        self.assertIsNone(player.equipment.get("main_hand"))
        self.assertIn("Failed to load equipped item", buf.getvalue())


class TestFromDictConversationAndNormalize(GameTestBase):
    def test_missing_conversation_history_keeps_default(self):
        payload = _base_payload(self.world)
        self.assertNotIn("conversation_history", payload)
        player = Player.from_dict(payload, self.world)
        self.assertIsNotNone(player.conversation)

    def test_missing_normalize_callable_is_skipped(self):
        payload = _base_payload(self.world)
        original = self.world.apply_content_player_defaults
        self.world.apply_content_player_defaults = None
        try:
            player = Player.from_dict(payload, self.world)
        finally:
            self.world.apply_content_player_defaults = original
        self.assertIsNotNone(player)


if __name__ == "__main__":
    unittest.main()
