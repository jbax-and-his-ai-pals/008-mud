"""What the ledger pays for a find, asked in the set's own vocabulary.

`advancement` item rules used to narrow on the Python class name
(`match.item_type: "Gem"`), and three of `fantasy_frontier`'s five item rules
were therefore dead: `Gem`, `Junk` and `Treasure` are *families* whose class the
engine retired, so an item built from one reports `Item` and only the generic
8-XP material rule could ever match. Gems paid a material's XP, and the ledger's
"A stone worth cataloguing." had never been shown to a player.

The fix is not a bigger if-chain in the engine: it is the family the content set
declared, carried by the instance and matchable by the rule.
"""

import json
import shutil
import unittest
import uuid
from pathlib import Path

from engine.core.advancement import item_payload
from engine.items.item_factory import ITEM_CLASS_MAP, ItemFactory
from engine.server import content_set as cs
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER

REPO_ROOT = Path(__file__).resolve().parents[3]


class TestAnItemCarriesItsDeclaredFamily(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:", content_set_path=FANTASY_FRONTIER, deterministic_test_mode=True
        )
        self.world = self.server.world

    def tearDown(self) -> None:
        self.server.shutdown()

    def _item(self, item_id):
        item = ItemFactory.create_item_from_template(item_id, self.world)
        self.assertIsNotNone(item, item_id)
        return item

    def test_the_instance_reports_the_family_its_template_declared(self) -> None:
        gem = self._item("item_amethyst")

        self.assertEqual("collectible_stone", item_payload(gem)["item_family"])
        # And the class name, which is the engine's and cannot be renamed.
        self.assertEqual("Item", item_payload(gem)["item_type"])

    def test_a_retired_class_name_is_no_longer_what_an_item_reports(self) -> None:
        """The evidence for the three dead rules, pinned so the reason survives."""
        self.assertIs(ITEM_CLASS_MAP["Gem"], ITEM_CLASS_MAP["Item"])
        self.assertIs(ITEM_CLASS_MAP["Junk"], ITEM_CLASS_MAP["Item"])
        self.assertIs(ITEM_CLASS_MAP["Treasure"], ITEM_CLASS_MAP["Item"])

    def test_each_family_pays_what_the_set_says_it_pays(self) -> None:
        server_session = self.server.create_session(player_id="family_rewards")
        self.server.execute_command(server_session.session_id, "char create Ledger Keeper")
        player = self.server.get_player_for_session(server_session.session_id)
        manager = self.world.advancement_manager

        paid = {}
        for item_id in (
            "item_amethyst",              # collectible_stone
            "item_river_clay",            # material
            "item_old_coin",              # treasure
            "item_healing_potion_small",  # consumable
        ):
            result = manager.record(player, "item", item_id, payload=item_payload(self._item(item_id)))
            paid[item_id] = (result.xp, result.messages)

        self.assertEqual(15, paid["item_amethyst"][0], "a gem is not a material")
        self.assertEqual(["A stone worth cataloguing."], paid["item_amethyst"][1])
        self.assertEqual(8, paid["item_river_clay"][0])
        self.assertEqual(10, paid["item_old_coin"][0])
        self.assertEqual(5, paid["item_healing_potion_small"][0])

    def test_the_families_fantasy_pays_for_are_families_its_items_use(self) -> None:
        ruleset = json.loads((Path(FANTASY_FRONTIER) / "rules" / "ruleset.json").read_text(encoding="utf-8"))
        declared = {
            str(grant.get("match", {}).get("item_family", "")).strip()
            for grant in ruleset["advancement"]["grants"]
            if isinstance(grant.get("match"), dict)
        } - {""}
        in_use = set()
        for path in sorted((Path(FANTASY_FRONTIER) / "data" / "items").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            for item in payload.values():
                if isinstance(item, dict) and item.get("item_family"):
                    in_use.add(str(item["item_family"]).strip())

        self.assertTrue(declared)
        self.assertTrue(declared <= in_use, "a grant pays for a family no item has: %s" % (declared - in_use))


class TestADeadItemGrantIsReported(unittest.TestCase):
    def _package(self, match: dict) -> Path:
        root = REPO_ROOT / "tmp" / ("grant_set_%s" % uuid.uuid4().hex)
        package = root / "grant_game"
        data = package / "data"
        for directory in ("regions", "items", "npcs"):
            (data / directory).mkdir(parents=True, exist_ok=True)
        (package / "rules").mkdir(parents=True, exist_ok=True)
        (package / "presentation").mkdir(parents=True, exist_ok=True)
        self.addCleanup(lambda: shutil.rmtree(root, ignore_errors=True))

        (data / "items" / "things.json").write_text(json.dumps({
            "a_stone": {
                "type": "Item", "name": "a stone", "description": "A stone.",
                "weight": 1, "value": 1, "item_family": "collectible_stone",
            }
        }), encoding="utf-8")
        (data / "regions" / "town.json").write_text(json.dumps({
            "region_id": "town",
            "name": "Town",
            "rooms": {"square": {"name": "Square", "description": "A square."}},
        }), encoding="utf-8")
        (package / "rules" / "ruleset.json").write_text(json.dumps({
            "ruleset_id": "grant_core",
            "advancement": {"grants": [{"id": "probe", "match": match, "xp": 5}]},
        }), encoding="utf-8")
        (package / "presentation" / "default.json").write_text("{}", encoding="utf-8")
        (package / cs.CONTENT_SET_MANIFEST_NAME).write_text(json.dumps({
            "id": "grant_game",
            "title": "Grant Game",
            "version": "0.1.0",
            "manifest_schema_version": "1",
            "engine_api_min": "1.0",
            "engine_api_max": "1.0",
            "paths": {
                "content_root": "data",
                "ruleset": "rules/ruleset.json",
                "presentation": "presentation/default.json",
            },
            "start": {"scenario_id": "start", "region_id": "town", "room_id": "square"},
            "capabilities": ["inventory"],
        }), encoding="utf-8")
        return package

    def _messages(self, match: dict) -> list[str]:
        return [i.message for i in cs.validate_content_set(self._package(match))]

    def test_a_retired_class_name_is_an_error_because_it_can_never_match(self) -> None:
        messages = self._messages({"kind": "item", "item_type": "Gem"})

        self.assertTrue(any("can never match" in m and "item_family" in m for m in messages), messages)

    def test_an_unknown_class_name_is_an_error(self) -> None:
        messages = self._messages({"kind": "item", "item_type": "Relic"})

        self.assertTrue(any("not an item class the engine has" in m for m in messages), messages)

    def test_a_family_no_item_declares_is_reported_as_paying_nothing(self) -> None:
        messages = self._messages({"kind": "item", "item_family": "moonstone"})

        self.assertTrue(any("pays nothing" in m for m in messages), messages)

    def test_a_family_items_do_declare_is_accepted(self) -> None:
        messages = self._messages({"kind": "item", "item_family": "collectible_stone"})

        self.assertFalse([m for m in messages if "grant" in m.lower() or "match" in m], messages)


if __name__ == "__main__":
    unittest.main()
