# tests/singles/test_creature_parts.py
"""A creature that comes apart when it dies (`on_death_spawn`), and a body that cannot be hurt while the parts that guard it stand
(`shielded_by`): a great slime that splits, a plant whose mouths must be silenced first."""

import unittest

from engine.core.combat_system import CombatSystem
from engine.npcs import phases

from tests.singles.test_encounters import _game, _hostile_template, _rooms


def _templates(server, **extra):
    server.world.npc_templates["t_big"] = dict(server.world.npc_templates[_hostile_template(server)], name="great slime", properties={
        "respawn_cooldown": 100, "on_death_spawn": {"npc": "t_small", "count": 2, "message": "The {name} comes apart."}})
    server.world.npc_templates["t_small"] = dict(server.world.npc_templates[_hostile_template(server)], name="slime", properties={"respawn_cooldown": 100})
    server.world.npc_templates["t_body"] = dict(server.world.npc_templates[_hostile_template(server)], name="stem", properties={
        "shielded_by": ["t_small"], "shield_text": "{attacker} cannot reach {defender}: the mouths guard it.", **extra})


class TestSplitting(unittest.TestCase):
    def test_a_creature_leaves_what_it_says_in_the_room_it_died_in(self):
        server, player = _game(self)
        _templates(server)
        region_id, here, other = _rooms(server, player)
        big, _status = server.world.spawn_npc("t_big", region_id, here, "big_one")
        big.die(server.world)
        kids = [n for n in server.world.npcs.values() if n.is_alive and n.template_id == "t_small"]
        self.assertEqual(2, len(kids))
        self.assertTrue(all((n.current_region_id, n.current_room_id) == (region_id, here) for n in kids))

    def test_what_it_leaves_is_not_placed_so_it_does_not_come_back(self):
        server, player = _game(self)
        _templates(server)
        region_id, here, other = _rooms(server, player)
        big, _status = server.world.spawn_npc("t_big", region_id, here, "big_one")
        big.die(server.world)
        kid = next(n for n in server.world.npcs.values() if n.is_alive and n.template_id == "t_small")
        self.assertEqual(-1, kid.properties["respawn_cooldown"])
        kid.take_damage(10 ** 5, "physical")
        before = len(server.world.respawn_queue) if hasattr(server.world, "respawn_queue") else 0
        kid.die(server.world)
        self.assertEqual(before, len(server.world.respawn_queue) if hasattr(server.world, "respawn_queue") else 0)

    def test_the_player_is_told(self):
        server, player = _game(self)
        _templates(server)
        region_id, here, other = _rooms(server, player)
        told = []
        server.world.notify_player = lambda p, text: told.append(text)
        big, _status = server.world.spawn_npc("t_big", region_id, here, "big_one")
        big.die(server.world)
        self.assertEqual(["The great slime comes apart."], told)


class TestGuards(unittest.TestCase):
    def test_the_body_is_untouchable_while_a_guard_stands_and_tells_the_attacker_why(self):
        server, player = _game(self)
        _templates(server)
        region_id, here, other = _rooms(server, player)
        body, _status = server.world.spawn_npc("t_body", region_id, here, "the_body")
        mouth, _status = server.world.spawn_npc("t_small", region_id, here, "a_mouth")
        self.assertTrue(phases.is_untouchable(body))
        result = CombatSystem.execute_attack(player, body, 50, always_hit=True)
        self.assertFalse(result["is_hit"] and result["damage"])
        self.assertEqual(body.max_health, body.health)
        self.assertIn("the mouths guard it", result["message"])
        mouth.take_damage(10 ** 5, "physical")
        self.assertFalse(phases.is_untouchable(body), "the guard is down")
        hit = CombatSystem.execute_attack(player, body, 50, always_hit=True)
        self.assertGreater(hit["damage"], 0)

    def test_a_guard_in_another_room_guards_nothing(self):
        server, player = _game(self)
        _templates(server)
        region_id, here, other = _rooms(server, player)
        body, _status = server.world.spawn_npc("t_body", region_id, here, "the_body")
        server.world.spawn_npc("t_small", region_id, other, "far_mouth")
        self.assertFalse(phases.is_untouchable(body))


class TestTheValidator(unittest.TestCase):
    def errors(self, **properties):
        from engine.server.content_set.npcs import _npc_property_errors

        return _npc_property_errors(properties, "NPC 'x'.properties", set())

    def test_well_formed_values_are_accepted(self):
        self.assertEqual([], self.errors(on_death_spawn={"npc": "slime", "count": 2, "message": "It comes apart."}, shielded_by=["mouth"], shield_text="Guarded."))

    def test_a_split_must_name_a_creature_and_a_sane_count(self):
        self.assertTrue(any("on_death_spawn must be an object" in m for m in self.errors(on_death_spawn="slime")))
        self.assertTrue(any("on_death_spawn.count must be a whole number from 1 to 8" in m for m in self.errors(on_death_spawn={"npc": "slime", "count": 20})))
        self.assertTrue(any("on_death_spawn.count" in m for m in self.errors(on_death_spawn={"npc": "slime", "count": 1.5})))
        self.assertTrue(any("on_death_spawn.size is not read" in m for m in self.errors(on_death_spawn={"npc": "slime", "size": 1})))

    def test_guards_are_a_list_of_creature_ids(self):
        self.assertTrue(any("shielded_by must be a non-empty list" in m for m in self.errors(shielded_by="mouth")))
        self.assertTrue(any("shielded_by must be a non-empty list" in m for m in self.errors(shielded_by=[])))
        self.assertTrue(any("shield_text must be text" in m for m in self.errors(shield_text=3)))


if __name__ == "__main__":
    unittest.main()
