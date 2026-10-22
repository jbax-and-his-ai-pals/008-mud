# tests/singles/test_dq_toolkit.py
"""What a short, old-style game needs of the engine: worn-gear conditions, zones that switch off, creatures called by a tune, an item that
casts an ability, gear that mends with every step, and a game that can really end."""

import unittest

from engine import conditions
from engine.items.consumable import Consumable
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.server.headless_server import HeadlessServer

from tests.fixtures import STORY_FIXTURE
from tests.singles.test_encounters import _game, _hostile_template, _rooms


def _wear(server, player):
    """Put the fixture's dark armour on the player and return it."""
    from engine.items.item_factory import ItemFactory

    armour = ItemFactory.create_item_from_template("item_dark_armor", server.world)
    assert armour is not None
    player.equipment["body"] = armour
    return armour


class TestWornGear(unittest.TestCase):
    def test_equipped_is_true_only_for_what_is_worn(self):
        _server, player = _game(self)
        _server, player = _server, player
        worn = _wear(_server, player)
        self.assertTrue(conditions.evaluate({"kind": "equipped", "item_id": worn.obj_id}, player).satisfied)
        self.assertFalse(conditions.evaluate({"kind": "equipped", "item_id": "item_other"}, player).satisfied)
        slot = next(name for name, item in player.equipment.items() if item is worn)
        player.equipment[slot] = None
        self.assertFalse(conditions.evaluate({"kind": "equipped", "item_id": worn.obj_id}, player).satisfied, "carried is not worn")


class TestZonesSwitchOff(unittest.TestCase):
    def test_a_zone_with_a_condition_is_live_only_while_it_holds(self):
        server, player = _game(self)
        region_id, _here, other = _rooms(server, player)
        server.world.encounters.add("quiet", {"region": region_id, "monsters": [_hostile_template(server)], "chance": 1,
                                              "when": {"not": {"kind": "flag", "flag": "won"}}})
        player.flags["won"] = True
        server.world._arrive(player, region_id, other, region_id)
        self.assertFalse([n for n in server.world.npcs.values() if n.properties.get("encounter")], "after the victory the world is quiet")
        player.flags.pop("won")
        server.world._arrive(player, region_id, _here, region_id)
        server.world._arrive(player, region_id, other, region_id)
        self.assertTrue([n for n in server.world.npcs.values() if n.properties.get("encounter") and n.is_alive])


class TestCallingACreature(unittest.TestCase):
    def test_the_effect_brings_one_whatever_the_chance(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        region_id, _here, _other = _rooms(server, player)
        server.world.encounters.add("tune", {"region": region_id, "monsters": [_hostile_template(server)], "chance": 0})
        report = apply_effects({"call_encounter": "tune"}, {"player": player, "world": server.world})
        self.assertTrue(report.applied, report.failed)
        self.assertTrue([n for n in server.world.npcs.values() if n.properties.get("encounter") == "tune"])

    def test_here_means_the_zone_of_the_room(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        region_id, here, _other = _rooms(server, player)
        server.world.encounters.add("local", {"region": region_id, "rooms": [here], "monsters": [_hostile_template(server)], "chance": 0})
        report = apply_effects({"call_encounter": "here"}, {"player": player, "world": server.world})
        self.assertTrue(report.applied, report.failed)
        self.assertTrue([n for n in server.world.npcs.values() if n.properties.get("encounter") == "local"])

    def test_an_unknown_zone_is_a_failure_not_a_crash(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        report = apply_effects({"call_encounter": "nowhere"}, {"player": player, "world": server.world})
        self.assertTrue(report.failed)


class TestAnItemThatCastsAnAbility(unittest.TestCase):
    def test_a_flute_puts_the_target_to_sleep_and_a_missing_target_costs_nothing(self):
        server, player = _game(self)
        SPELL_REGISTRY["t_flute_song"] = Spell("t_flute_song", "Flute Song", "d", effects=[
            {"type": "apply_effect", "effect_data": {"type": "status", "name": "Slumber", "tags": ["sleep"], "base_duration": 300}}],
            mana_cost=0, target_type="enemy", cast_message="You play a slow tune.")
        self.addCleanup(SPELL_REGISTRY.pop, "t_flute_song", None)
        region_id, here, _other = _rooms(server, player)
        server.world.remove_npcs("goblin_scout")
        foe, _status = server.world.spawn_npc(_hostile_template(server), region_id, here, "sleeper")
        flute = Consumable(obj_id="item_flute", name="flute", uses=1, effect_type="cast", spell="t_flute_song", reusable=True)
        said = flute.use(player)
        self.assertIn("needs a target", said)
        flute.use(player, target=foe)
        self.assertTrue(foe.has_effect_tag("sleep"))


class TestGearThatMends(unittest.TestCase):
    def test_each_step_heals_by_what_is_worn(self):
        server, player = _game(self)
        region_id, here, other = _rooms(server, player)
        worn = _wear(server, player)
        worn.properties["heal_per_step"] = 3
        player.health = player.max_health - 10
        server.world._arrive(player, region_id, other, region_id)
        self.assertEqual(player.max_health - 7, player.health)
        server.world._arrive(player, region_id, other, region_id)
        self.assertEqual(player.max_health - 7, player.health, "standing still mends nothing")


class TestAPermanentGainInDefense(unittest.TestCase):
    def test_raise_defense_adds_to_the_defense_that_is_kept(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        before = player.get_defense()
        report = apply_effects({"raise": {"defense": 2}}, {"player": player, "world": server.world})
        self.assertTrue(report.applied, report.failed)
        self.assertEqual(before + 2, player.get_defense())
        self.assertEqual(player.runtime_state.combat.defense, player.to_dict(server.world)["gameplay"]["combat"]["defense"], "and it is what the save keeps")

    def test_a_nonsense_gain_is_refused(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        self.assertTrue(apply_effects({"raise": {"defense": 0}}, {"player": player, "world": server.world}).failed)


class TestTakingWhatIsWorn(unittest.TestCase):
    def test_take_item_takes_a_worn_item_even_a_cursed_one(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        worn = _wear(server, player)
        worn.properties["cursed"] = True
        player.inventory.remove_item(worn.obj_id, 99)   # the fixture's hero also carries a spare
        report = apply_effects({"take_item": worn.obj_id}, {"player": player, "world": server.world})
        self.assertTrue(report.applied, report.failed)
        self.assertIsNone(player.equipment["body"])

    def test_it_still_fails_when_it_is_neither_carried_nor_worn(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        self.assertTrue(apply_effects({"take_item": "item_nothing"}, {"player": player, "world": server.world}).failed)


class TestTheGameCanEnd(unittest.TestCase):
    def test_game_over_kills_the_character_and_respawn_refuses(self):
        from engine.dialogue.effects import apply_effects

        server, player = _game(self)
        report = apply_effects({"game_over": "Darkness takes you."}, {"player": player, "world": server.world})
        self.assertFalse(player.is_alive)
        self.assertIn("Darkness takes you.", report.message())
        from engine.commands.system import respawn_handler

        said = respawn_handler([], {"player": player, "world": server.world})
        self.assertIn("adventure is over", said)
        self.assertFalse(player.is_alive)


if __name__ == "__main__":
    unittest.main()
