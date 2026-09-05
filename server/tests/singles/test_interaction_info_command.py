# tests/singles/test_interaction_info_command.py
"""Coverage for engine/commands/interaction/info.py's `collection` command:
the missing-args usage error and the happy path that delegates to
CollectionManager.get_collection_status."""

from tests.fixtures import GameTestBase


class TestCollectionCommand(GameTestBase):

    def setUp(self):
        super().setUp()
        self.game.collection_manager.collections["bugs"] = {
            "name": "Rare Bugs",
            "items": ["beetle"],
            "rewards": {"gold": 10},
        }
        self.world.item_templates["beetle"] = {
            "type": "Junk", "name": "Golden Beetle", "value": 1,
            "properties": {"collection_id": "bugs"},
        }

    def test_no_args_returns_usage_error(self):
        result = self.game.process_command("collection")
        self.assertIn("Usage: collection", result)

    def test_with_id_delegates_to_collection_manager(self):
        result = self.game.process_command("collection bugs")
        self.assertIn("Golden Beetle", result)

    def test_alias_col_works(self):
        result = self.game.process_command("col bugs")
        self.assertIn("Golden Beetle", result)

    def test_id_is_lowercased(self):
        result = self.game.process_command("collection BUGS")
        self.assertIn("Golden Beetle", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
