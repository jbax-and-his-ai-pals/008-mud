# tests/singles/test_observation_commands.py
"""Coverage for engine/commands/interaction/observation.py: look's
'in'/'inside'/'at' parsing branches (including their "what?" guards),
inventory-alias delegation, quest-board-alias delegation (and its fallback
when 'look board' isn't registered), the player/NPC/room-item/inventory/
equipment search priority chain, container inside-lookup (open/locked/
closed), the Player-target health-tier description, and examine/read's
guard clauses and delegation to look_handler.

Note: look_handler's final `return f"You see {target.name}."` fallback is
left untested as unreachable -- every search path that can assign `target`
(the other-player loop, find_npc_in_room_for_player,
find_item_in_room_for_player, inventory.find_item_by_name, the equipment
loop) only ever produces a Player, an NPC, or an Item, and all three are
handled by the preceding isinstance branches."""

from tests.fixtures import GameTestBase
from engine.commands.interaction.observation import look_handler, examine_handler, read_handler
from engine.commands.command_system import registered_commands
from engine.items.container import Container
from engine.items.item import Item
from engine.npcs.npc_factory import NPCFactory
from engine.player.core import Player


class TestLookHandlerGuards(GameTestBase):
    def test_no_player_reports_error(self):
        result = look_handler([], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)

    def test_no_args_looks_around_room(self):
        result = look_handler([], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)


class TestLookInParsing(GameTestBase):
    def test_look_in_with_no_target_prompts(self):
        result = self.game.process_command("look in")
        self.assertIn("Look in what?", result)

    def test_look_inside_with_no_target_prompts(self):
        result = self.game.process_command("look inside")
        self.assertIn("Look inside what?", result)

    def test_look_at_with_no_target_prompts(self):
        result = self.game.process_command("look at")
        self.assertIn("Look at what?", result)

    def test_look_inside_with_target_finds_container(self):
        container = Container(obj_id="obs_inside_target", name="Crate", is_open=True)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = self.game.process_command("look inside crate")
        self.assertIn("Inside the Crate", result)

    def test_look_at_with_target_finds_item(self):
        item = Item(obj_id="obs_at_target", name="Statue", description="A stone statue.")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        result = self.game.process_command("look at statue")
        self.assertIn("A stone statue.", result)

    def test_look_in_inventory_delegates_to_inventory_handler(self):
        result = self.game.process_command("look in inventory")
        self.assertIn("INVENTORY", result)

    def test_look_in_backpack_delegates_to_inventory_handler(self):
        result = self.game.process_command("look in backpack")
        self.assertIn("INVENTORY", result)


class TestLookQuestBoard(GameTestBase):
    def test_look_board_delegates_when_registered(self):
        # "look board" is itself a distinct registered command, so going
        # through process_command resolves it directly without ever
        # reaching look_handler's own QUEST_BOARD_ALIASES branch. Call the
        # handler directly with args=["board"] to exercise that branch.
        result = look_handler(["board"], {"world": self.world, "player": self.player})
        self.assertIsNotNone(result)

    def test_look_board_falls_back_when_not_registered(self):
        saved = {}
        for alias in ("look board", "board", "quest board", "notice board"):
            if alias in registered_commands:
                saved[alias] = registered_commands.pop(alias)
        try:
            original_quest_manager = self.world.quest_manager
            self.world.quest_manager = None
            try:
                result = look_handler(["board"], {"world": self.world, "player": self.player})
            finally:
                self.world.quest_manager = original_quest_manager
        finally:
            registered_commands.update(saved)
        self.assertIn("quest system seems to be unavailable", result)

    def test_falls_through_to_search_when_board_unregistered_but_quest_manager_present(self):
        saved = {}
        for alias in ("look board", "board", "quest board", "notice board"):
            if alias in registered_commands:
                saved[alias] = registered_commands.pop(alias)
        try:
            # quest_manager is present (untouched), so the "unavailable"
            # early-return is skipped and execution falls into the normal
            # player/NPC/item search chain, which finds nothing named "board".
            result = look_handler(["board"], {"world": self.world, "player": self.player})
        finally:
            registered_commands.update(saved)
        self.assertIn("don't see", result)


class TestLookTargetSearchPriority(GameTestBase):
    def test_skips_non_matching_players_before_finding_match(self):
        decoy = Player("Decoy Person", obj_id="obs_decoy_player", world=self.world)
        decoy.world = self.world
        decoy.current_region_id = self.player.current_region_id
        decoy.current_room_id = self.player.current_room_id
        self.world.players[decoy.obj_id] = decoy

        target = Player("Findable Hero", obj_id="obs_findable_player", world=self.world)
        target.world = self.world
        target.current_region_id = self.player.current_region_id
        target.current_room_id = self.player.current_room_id
        self.world.players[target.obj_id] = target

        result = self.game.process_command("look findable hero")
        self.assertIn("Findable Hero", result)

    def test_finds_another_player_in_same_room(self):
        other = Player("Other Hero", obj_id="obs_other_player", world=self.world)
        other.world = self.world
        other.current_region_id = self.player.current_region_id
        other.current_room_id = self.player.current_room_id
        self.world.players[other.obj_id] = other
        result = self.game.process_command("look other hero")
        self.assertIn("Other Hero", result)

    def test_finds_npc_in_room(self):
        npc = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="obs_elder")
        npc.current_region_id = self.player.current_region_id
        npc.current_room_id = self.player.current_room_id
        self.world.add_npc(npc)
        result = self.game.process_command(f"look {npc.name}")
        self.assertIsNotNone(result)

    def test_finds_room_item(self):
        item = Item(obj_id="obs_room_item", name="Shiny Coin", description="x")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        result = self.game.process_command("look shiny coin")
        self.assertIn("Shiny Coin", result)

    def test_finds_inventory_item(self):
        item = Item(obj_id="obs_inv_item", name="Lucky Charm", description="A charm.")
        self.player.inventory.add_item(item)
        result = self.game.process_command("look lucky charm")
        self.assertIn("A charm.", result)

    def test_finds_equipped_item(self):
        from engine.items.weapon import Weapon
        weapon = Weapon(obj_id="obs_equip_item", name="Glowing Blade", description="It glows.")
        self.player.equipment["main_hand"] = weapon
        result = self.game.process_command("look glowing blade")
        self.assertIn("It glows.", result)

    def test_no_match_reports_not_here(self):
        result = self.game.process_command("look absolutely_nothing_matches_this_xyz")
        self.assertIn("don't see", result)


class TestLookInsideContainer(GameTestBase):
    def test_look_inside_open_container_lists_contents(self):
        item = Item(obj_id="obs_c_item", name="Gem", description="x")
        container = Container(obj_id="obs_open_chest", name="Open Chest", is_open=True, contents=[item])
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = self.game.process_command("look in open chest")
        self.assertIn("Inside the Open Chest", result)
        self.assertIn("Gem", result)

    def test_look_inside_closed_container_reports_closed(self):
        container = Container(obj_id="obs_closed_chest", name="Closed Chest", is_open=False, locked=False)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = self.game.process_command("look in closed chest")
        self.assertIn("closed", result)

    def test_look_inside_locked_container_reports_locked(self):
        container = Container(obj_id="obs_locked_chest", name="Locked Chest", is_open=False, locked=True)
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, container)
        result = self.game.process_command("look in locked chest")
        self.assertIn("locked", result)

    def test_look_inside_non_container_reports_error(self):
        item = Item(obj_id="obs_not_container", name="Plain Rock", description="x")
        self.world.add_item_to_room(self.player.current_region_id, self.player.current_room_id, item)
        result = self.game.process_command("look in plain rock")
        self.assertIn("not a container", result)


class TestLookAtPlayerHealthTiers(GameTestBase):
    def _other_player(self):
        other = Player("Wounded Hero", obj_id="obs_wounded_player", world=self.world)
        other.world = self.world
        other.current_region_id = self.player.current_region_id
        other.current_room_id = self.player.current_room_id
        self.world.players[other.obj_id] = other
        return other

    def test_excellent_health_description(self):
        other = self._other_player()
        other.health = other.max_health
        result = self.game.process_command("look wounded hero")
        self.assertIn("excellent health", result)

    def test_banged_up_description(self):
        other = self._other_player()
        other.health = int(other.max_health * 0.6)
        result = self.game.process_command("look wounded hero")
        self.assertIn("banged up", result)

    def test_badly_wounded_description(self):
        other = self._other_player()
        other.health = int(other.max_health * 0.3)
        result = self.game.process_command("look wounded hero")
        self.assertIn("badly wounded", result)

    def test_barely_clinging_to_life_description(self):
        other = self._other_player()
        other.health = 1
        other.max_health = 100
        result = self.game.process_command("look wounded hero")
        self.assertIn("barely clinging to life", result)

    def test_zero_max_health_does_not_crash(self):
        other = self._other_player()
        other.max_health = 0
        other.health = 0
        result = self.game.process_command("look wounded hero")  # must not raise
        self.assertIsNotNone(result)


class TestExamineHandler(GameTestBase):
    def test_no_player_reports_error(self):
        result = examine_handler(["thing"], {"world": self.world, "player": None})
        self.assertIn("must start or load a game", result)

    def test_no_args_prompts(self):
        result = examine_handler([], {"world": self.world, "player": self.player})
        self.assertIn("What do you want to examine", result)

    def test_delegates_to_look_handler(self):
        item = Item(obj_id="exam_item", name="Curious Orb", description="It hums.")
        self.player.inventory.add_item(item)
        result = self.game.process_command("examine curious orb")
        self.assertIn("It hums.", result)


class TestReadHandler(GameTestBase):
    def test_no_args_prompts(self):
        result = read_handler([], {"world": self.world, "player": self.player})
        self.assertIn("What do you want to read", result)

    def test_delegates_to_look_handler(self):
        item = Item(obj_id="read_item", name="Old Scroll", description="Ancient runes.")
        self.player.inventory.add_item(item)
        result = self.game.process_command("read old scroll")
        self.assertIn("Ancient runes.", result)


if __name__ == "__main__":
    import unittest
    unittest.main()
