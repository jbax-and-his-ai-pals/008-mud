# tests/singles/test_magic_commands.py
"""Coverage for engine/commands/magic.py (cast/spells) target-resolution
branches beyond what test_magic.py's cast-requirements/cooldown tests cover."""

from tests.fixtures import GameTestBase
from engine.commands.magic import cast_handler
from engine.npcs.npc_factory import NPCFactory
from engine.items.item_factory import ItemFactory


class TestCastCommand(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.current_region_id = "town"
        self.player.current_room_id = "town_square"
        self.player.runtime_state.magic.mana = self.player.runtime_state.magic.max_mana

    def test_dead_player_cannot_cast(self):
        # process_command() itself gates dead players before commands not in
        # its allowlist ever dispatch, so cast_handler's own check needs a
        # direct call to reach it.
        self.player.health = 0
        self.player.is_alive = False
        context = {"world": self.world, "player": self.player, "game": self.game}
        result = cast_handler(["magic", "missile"], context)
        self.assertIn("cannot cast spells while dead", result)

    def test_no_args_lists_known_spells(self):
        result = self.game.process_command("cast")
        self.assertIn("SPELLS KNOWN", result)

    def test_unknown_spell_is_reported(self):
        result = self.game.process_command("cast not a real spell")
        self.assertIn("don't know a spell", result)

    def test_item_target_spell_finds_room_item(self):
        self.player.learn_spell("knock")
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.world.add_item_to_room("town", "town_square", item)
        result = self.game.process_command(f"cast knock on {item.name}")
        self.assertNotIn("Invalid target", result)
        self.assertNotIn("don't see", result)

    def test_item_target_spell_requires_a_target_name(self):
        self.player.learn_spell("knock")
        result = self.game.process_command("cast knock")
        self.assertIn("on what item", result)

    def test_item_target_spell_not_found_is_reported(self):
        self.player.learn_spell("knock")
        result = self.game.process_command("cast knock on nonexistent thing")
        self.assertIn("don't see", result)

    def test_item_target_finds_inventory_item(self):
        self.player.learn_spell("knock")
        item = ItemFactory.create_item_from_template("item_iron_sword", self.world)
        self.player.inventory.add_item(item)
        result = self.game.process_command(f"cast knock on {item.name}")
        self.assertNotIn("don't see", result)

    def test_environmental_target(self):
        self.player.learn_spell("chain_lightning")
        result = self.game.process_command("cast chain lightning on room")
        self.assertNotIn("Invalid target", result)

    def test_self_target_spell(self):
        self.player.learn_spell("raise_skeleton")
        result = self.game.process_command("cast raise skeleton")
        self.assertNotIn("Invalid target", result)

    def test_explicit_npc_target_not_found(self):
        result = self.game.process_command("cast minor heal on nobody_here")
        self.assertIn("don't see", result)

    def test_explicit_target_self_by_alias(self):
        result = self.game.process_command("cast minor heal on self")
        self.assertNotIn("Invalid target", result)

    def test_enemy_auto_target_uses_current_combat_target(self):
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world, instance_id="combat_rat")
        rat.current_region_id = "town"
        rat.current_room_id = "town_square"
        self.world.add_npc(rat)
        self.player.enter_combat(rat)
        result = self.game.process_command("cast magic missile")
        self.assertNotIn("Invalid target", result)
        self.assertNotIn("Who do you want", result)

    def test_enemy_auto_target_prefers_current_target_over_other_hostiles(self):
        # With two hostiles present, auto-targeting must hit the one the
        # player is already engaged with (their explicit combat.target),
        # not just any hostile in the room -- a real regression test for
        # the "current target" wiring in Player.attack()/enter_combat().
        engaged_rat = NPCFactory.create_npc_from_template("giant_rat", self.world, instance_id="engaged_rat")
        other_rat = NPCFactory.create_npc_from_template("giant_rat", self.world, instance_id="other_rat")
        engaged_rat.name = "Engaged Rat"
        other_rat.name = "Other Rat"
        for rat in (engaged_rat, other_rat):
            rat.current_region_id = "town"
            rat.current_room_id = "town_square"
            self.world.add_npc(rat)
        self.player.attack(engaged_rat, self.world)
        self.assertIs(engaged_rat, self.player.runtime_state.combat.target)
        result = self.game.process_command("cast magic missile")
        self.assertIn(engaged_rat.name, result)
        self.assertNotIn(other_rat.name, result)

    def test_enemy_auto_target_finds_hostile_in_room(self):
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world, instance_id="auto_rat")
        rat.current_region_id = "town"
        rat.current_room_id = "town_square"
        self.world.add_npc(rat)
        result = self.game.process_command("cast magic missile")
        self.assertNotIn("Invalid target", result)

    def test_enemy_auto_target_with_no_hostiles_present(self):
        self.world.npcs = {}
        result = self.game.process_command("cast magic missile")
        self.assertIn("Who do you want to cast", result)

    def test_all_enemies_target_type_does_not_require_a_target(self):
        self.player.learn_spell("chain_lightning")
        result = self.game.process_command("cast chain lightning")
        self.assertNotIn("Invalid target", result)

    def test_enemy_spell_rejects_friendly_explicit_target(self):
        elder = NPCFactory.create_npc_from_template("village_elder", self.world, instance_id="friendly1")
        elder.current_region_id = "town"
        elder.current_room_id = "town_square"
        self.world.add_npc(elder)
        result = self.game.process_command(f"cast magic missile on {elder.name}")
        self.assertIn("only cast", result)
        self.assertIn("hostile targets", result)

    def test_friendly_spell_rejects_hostile_explicit_target(self):
        rat = NPCFactory.create_npc_from_template("giant_rat", self.world, instance_id="hostile1")
        rat.current_region_id = "town"
        rat.current_room_id = "town_square"
        self.world.add_npc(rat)
        result = self.game.process_command(f"cast minor heal on {rat.name}")
        self.assertIn("only cast", result)
        self.assertIn("friendly targets", result)


class TestSpellsCommand(GameTestBase):
    def test_no_known_spells_is_reported(self):
        self.player.runtime_state.magic.known_spells = set()
        result = self.game.process_command("spells")
        self.assertIn("don't know any spells", result)

    def test_magic_disabled_for_player_is_reported(self):
        self.player.runtime_state.magic = None
        result = self.game.process_command("spells")
        self.assertIn("not enabled", result)

    def test_lists_known_spells_with_mana_cost(self):
        result = self.game.process_command("spells")
        self.assertIn("KNOWN SPELLS", result)
        self.assertIn("MP", result)
        self.assertIn("Mana:", result)

    def test_unknown_spell_lookup_is_reported(self):
        result = self.game.process_command("spells not a real spell")
        self.assertIn("don't know a spell called", result)

    def test_detail_view_for_a_known_spell(self):
        result = self.game.process_command("spells magic missile")
        self.assertIn("MAGIC MISSILE", result)
        self.assertIn("Mana Cost:", result)
        self.assertIn("Cooldown:", result)
        self.assertIn("Target:", result)
        self.assertIn("Effects:", result)

    def test_detail_view_shows_cooldown_status_when_on_cooldown(self):
        spell_id = next(iter(self.player.runtime_state.magic.known_spells))
        import time
        self.player.runtime_state.magic.cooldowns[spell_id] = time.time() + 30
        result = self.game.process_command(f"spells {spell_id.replace('_', ' ')}")
        self.assertIn("On Cooldown", result)
