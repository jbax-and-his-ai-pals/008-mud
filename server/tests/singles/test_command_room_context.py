import unittest

from engine.items.container import Container
from engine.items.item_factory import ItemFactory
from engine.npcs.npc import NPC
from engine.server.headless_server import HeadlessServer
from tests.fixtures import FANTASY_FRONTIER
from engine.world.region import Region
from engine.world.room import Room


class TestCommandRoomContext(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(db_path=":memory:", content_set_path=FANTASY_FRONTIER)
        self.session = self.server.create_session(player_id="room_context_player")
        self.server.mark_session_connected(self.session.session_id)
        self.server.execute_command(self.session.session_id, "char create ContextHero")
        self.player = self.server.get_player_for_session(self.session.session_id)
        assert self.player is not None

    def tearDown(self) -> None:
        self.server.shutdown()

    def _text_payloads(self, events: list[dict]) -> list[str]:
        return [str(event.get("payload", "")) for event in events if event.get("type") == "text"]

    def test_trade_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "market_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "town_square"

        events = self.server.execute_command(self.session.session_id, "trade talia")
        payloads = self._text_payloads(events)

        self.assertTrue(any("approach Talia the Merchant to trade" in payload for payload in payloads))

    def test_rules_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "casino"
        self.player.current_room_id = "dice_parlor"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "town_square"

        events = self.server.execute_command(self.session.session_id, "rules")
        payloads = self._text_payloads(events)

        self.assertTrue(any("Game Rules:" in payload for payload in payloads))

    def test_look_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"

        events = self.server.execute_command(self.session.session_id, "look elder")
        payloads = self._text_payloads(events)

        self.assertTrue(any("Elder Thorne" in payload for payload in payloads))

    def test_attack_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"
        goblin = NPC(obj_id="test_goblin_ctx", name="Test Goblin", description="A snarling goblin.", friendly=False)
        goblin.faction = "hostile"
        goblin.current_region_id = "town"
        goblin.current_room_id = "town_square"
        self.server.world.add_npc(goblin)

        events = self.server.execute_command(self.session.session_id, "attack goblin")
        payloads = self._text_payloads(events)

        self.assertFalse(any("No 'goblin' here to attack." in payload for payload in payloads))
        self.assertTrue(any("goblin" in payload.lower() for payload in payloads))

    def test_open_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"
        chest = Container(obj_id="ctx_chest", name="Context Chest", description="A test chest.", is_open=False)
        self.server.world.add_item_to_room("town", "town_square", chest)

        events = self.server.execute_command(self.session.session_id, "open context chest")
        payloads = self._text_payloads(events)

        self.assertTrue(any("You open the Context Chest." in payload for payload in payloads))

    def test_give_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"
        coin = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        self.assertIsNotNone(coin)
        if coin is None:
            return
        self.player.inventory.add_item(coin)
        npc = NPC(obj_id="ctx_friend", name="Context Friend", description="A test recipient.", friendly=True)
        npc.current_region_id = "town"
        npc.current_room_id = "town_square"
        self.server.world.add_npc(npc)

        events = self.server.execute_command(self.session.session_id, "give gold coin to context friend")
        payloads = self._text_payloads(events)

        self.assertTrue(any("You give the" in payload and "Context Friend" in payload for payload in payloads))

    def test_get_from_container_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"
        coin = ItemFactory.create_item_from_template("item_gold_coin", self.server.world)
        self.assertIsNotNone(coin)
        if coin is None:
            return
        chest = Container(
            obj_id="ctx_take_chest",
            name="Context Take Chest",
            description="A test chest.",
            is_open=True,
            contents=[coin],
        )
        self.server.world.add_item_to_room("town", "town_square", chest)

        events = self.server.execute_command(self.session.session_id, "get gold coin from context take chest")
        payloads = self._text_payloads(events)

        self.assertTrue(any("You get the gold coin from the Context Take Chest." in payload for payload in payloads))

    def test_weather_uses_session_player_room_not_global_cursor(self) -> None:
        self.player.current_region_id = "town"
        self.player.current_room_id = "alchemist_interior"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "town_square"

        events = self.server.execute_command(self.session.session_id, "weather")
        payloads = self._text_payloads(events)

        self.assertTrue(any("can't see the weather from inside" in payload for payload in payloads))

    def test_skills_uses_session_player_not_global_player(self) -> None:
        other_session = self.server.create_session(player_id="room_context_other")
        self.server.mark_session_connected(other_session.session_id)
        self.server.execute_command(other_session.session_id, "char create OtherHero")
        other_player = self.server.get_player_for_session(other_session.session_id)
        self.assertIsNotNone(other_player)
        if other_player is None:
            return

        assert self.player.runtime_state.progression is not None
        self.player.runtime_state.progression.skills["alchemy"] = {"level": 2, "xp": 5}
        assert other_player.runtime_state.progression is not None
        other_player.runtime_state.progression.skills["swordsmanship"] = {"level": 4, "xp": 20}
        self.server.world.player = other_player

        events = self.server.execute_command(self.session.session_id, "skills")
        payloads = self._text_payloads(events)

        self.assertTrue(any("Alchemy" in payload for payload in payloads))
        self.assertFalse(any("Swordsmanship" in payload for payload in payloads))

    def test_movement_uses_session_player_room_not_global_cursor(self) -> None:
        region = Region("Context Region", "A region for movement context tests.", obj_id="ctx_region")
        start_room = Room("Start Room", "A simple start room.", obj_id="start")
        north_room = Room("North Room", "A destination room.", obj_id="north_room")
        start_room.exits["north"] = "north_room"
        north_room.exits["south"] = "start"
        region.add_room("start", start_room)
        region.add_room("north_room", north_room)
        self.server.world.add_region("ctx_region", region)

        self.player.current_region_id = "ctx_region"
        self.player.current_room_id = "start"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"

        events = self.server.execute_command(self.session.session_id, "north")
        payloads = self._text_payloads(events)

        self.assertEqual(("ctx_region", "north_room"), (self.player.current_region_id, self.player.current_room_id))
        self.assertTrue(any("NORTH ROOM" in payload for payload in payloads))

    def test_pick_direction_uses_session_player_room_not_global_cursor(self) -> None:
        region = Region("Lock Region", "A region for lockpick tests.", obj_id="lock_region")
        start_room = Room("Lock Start", "A locked test room.", obj_id="lock_start")
        east_room = Room("Lock East", "The room beyond the lock.", obj_id="lock_east")
        start_room.exits["east"] = "lock_east"
        start_room.properties["exit_requirements"] = {
            "east": {"type": "locked", "key_id": "missing_key", "pick_difficulty": 1}
        }
        east_room.exits["west"] = "lock_start"
        region.add_room("lock_start", start_room)
        region.add_room("lock_east", east_room)
        self.server.world.add_region("lock_region", region)

        lockpick = ItemFactory.create_item_from_template("item_lockpick", self.server.world)
        self.assertIsNotNone(lockpick)
        if lockpick is None:
            return
        self.player.inventory.add_item(lockpick)
        self.player.current_region_id = "lock_region"
        self.player.current_room_id = "lock_start"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "market_square"

        events = self.server.execute_command(self.session.session_id, "pick east")
        payloads = self._text_payloads(events)

        self.assertTrue(any("unlock the way east" in payload.lower() for payload in payloads))
        self.assertNotIn("east", start_room.properties.get("exit_requirements", {}))

    def test_recipes_uses_session_player_room_not_global_cursor(self) -> None:
        anvil = ItemFactory.create_item_from_template("item_anvil", self.server.world)
        self.assertIsNotNone(anvil)
        if anvil is None:
            return

        self.player.current_region_id = "town"
        self.player.current_room_id = "blacksmith_interior"
        self.server.world.current_region_id = "town"
        self.server.world.current_room_id = "town_square"
        self.server.world.add_item_to_room("town", "blacksmith_interior", anvil)

        events = self.server.execute_command(self.session.session_id, "recipes")
        payloads = self._text_payloads(events)

        self.assertTrue(any("Nearby Stations:" in payload and "Anvil" in payload for payload in payloads))
