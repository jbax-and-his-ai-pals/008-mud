# tests/singles/test_interaction_info_command.py
"""Coverage for engine/commands/interaction/info.py's `collection` command.

It used to answer a bare `collection` with "Usage: collection
<collection_id>", an id nothing shows a player. Now a bare `collection`
lists every collection by name with progress, and a name (whole or part)
finds one; the id still works for testers."""

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

    def test_no_args_lists_collections_by_name(self):
        result = self.game.process_command("collection")
        self.assertIn("Rare Bugs: 0/1 turned in", result)
        self.assertNotIn("collection_id", result)

    def test_a_name_finds_the_collection(self):
        self.assertIn("Golden Beetle", self.game.process_command("collection rare bugs"))
        self.assertIn("Golden Beetle", self.game.process_command("collection rare"))

    def test_an_unknown_name_lists_what_there_is(self):
        result = self.game.process_command("collection dragons")
        self.assertIn("No collection called 'dragons'", result)
        self.assertIn("Rare Bugs", result)

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
