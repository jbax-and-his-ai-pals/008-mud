# tests/singles/test_companion_fall_and_support.py
"""A companion struck down falls instead of dying (`falls_when_defeated`), can be revived, and a companion that knows
a healing or reviving spell tends the party on its own.

The fallen: alive at 0 health, out of the fight, untouchable and unhealable, until a `revive` (the spell effect, a
`revive` consumable, an inn's `restore` with `companions: true`) or, some time after the fighting stops, by itself.
Without the property a companion dies as it always did.
"""

import unittest

from engine.items.consumable import Consumable
from engine.magic.spell import Spell
from engine.magic.spell_registry import SPELL_REGISTRY
from engine.npcs import companions
from engine.npcs.ai import specialized
from engine.npcs.npc_factory import NPCFactory
from engine.server.headless_server import HeadlessServer
from tests.fixtures import STORY_FIXTURE

ROOM = ("hazevale", "village_square")


class _Party(unittest.TestCase):
    def setUp(self):
        self.server = HeadlessServer(db_path=":memory:", content_set_path=str(STORY_FIXTURE), deterministic_test_mode=True,
                                     default_presentation_mode="player")
        self.addCleanup(self.server.shutdown)
        self.sid = self.server.create_session(player_id="hero").session_id
        self.server.execute_command(self.sid, "char create Aldric")
        self.player = self.server.get_player_for_session(self.sid)
        self.world = self.server.world
        self.player.current_region_id, self.player.current_room_id = ROOM
        self.addCleanup(SPELL_REGISTRY.pop, "test_raise", None)
        SPELL_REGISTRY["test_raise"] = Spell(
            "test_raise", "Raise", "Brings a fallen friend up.", effects=[{"type": "revive", "value": 50}],
            mana_cost=5, cooldown=1.0, target_type="friendly")

    def companion(self, instance_id, falls=True, spells=()):
        npc = NPCFactory.create_npc_from_template("ryn", self.world, instance_id=instance_id)
        npc.current_region_id, npc.current_room_id = ROOM
        if falls:
            npc.properties["falls_when_defeated"] = True
        self.world.add_npc(npc)
        companions.recruit(self.world, self.player, npc)
        npc.usable_spells = list(spells)
        npc.max_mana = npc.mana = 100
        npc.combat_cooldown = 3.0
        npc.last_combat_action = 0
        self.world.pending_player_notices.clear()
        return npc


class TestTheFall(_Party):
    def test_a_lethal_blow_puts_the_companion_down_not_dead(self):
        ryn = self.companion("ryn_a")
        ryn.take_damage(10 ** 6, "physical")
        self.assertTrue(ryn.is_alive)
        self.assertEqual(0, ryn.health)
        self.assertTrue(companions.is_fallen(ryn))
        self.assertTrue(any("falls" in text for _, text in self.world.pending_player_notices))

    def test_without_the_property_a_companion_dies_as_before(self):
        ryn = self.companion("ryn_b", falls=False)
        ryn.take_damage(10 ** 6, "physical")
        self.assertFalse(ryn.is_alive)

    def test_the_fallen_cannot_be_hurt_healed_or_picked_as_a_target(self):
        from engine.npcs.combat import is_untargetable

        ryn = self.companion("ryn_c")
        ryn.take_damage(10 ** 6, "physical")
        self.assertEqual(0, ryn.take_damage(50, "physical"))
        self.assertEqual(0, ryn.heal(50), "a healing draught does not raise the dead")
        self.assertTrue(is_untargetable(ryn))

    def test_enemies_stop_fighting_the_one_on_the_ground(self):
        ryn = self.companion("ryn_d")
        goblin = NPCFactory.create_npc_from_template("goblin_scout", self.world, instance_id="goblin_d")
        goblin.current_region_id, goblin.current_room_id = ROOM
        self.world.add_npc(goblin)
        goblin.combat_targets.add(ryn)
        goblin.combat_target = ryn
        ryn.take_damage(10 ** 6, "physical")
        self.assertNotIn(ryn, goblin.combat_targets)

    def test_it_gets_up_by_itself_once_it_has_been_quiet_for_a_while(self):
        ryn = self.companion("ryn_e")
        ryn.take_damage(10 ** 6, "physical")
        now = float(self.world.clock.now())
        self.assertIsNone(companions.fallen_step(ryn, self.world, now + 10, self.player))
        self.assertTrue(companions.is_fallen(ryn))
        told = companions.fallen_step(ryn, self.world, now + companions.FALLEN_RECOVERY_SECONDS + 1, self.player)
        self.assertIn("gets slowly to their feet", told)
        self.assertFalse(companions.is_fallen(ryn))
        self.assertGreaterEqual(ryn.health, 1)

    def test_it_does_not_get_up_while_the_fight_goes_on(self):
        ryn = self.companion("ryn_f")
        ryn.take_damage(10 ** 6, "physical")
        self.player.runtime_state.combat.in_combat = True
        now = float(self.world.clock.now())
        companions.fallen_step(ryn, self.world, now + 1000, self.player)
        self.assertTrue(companions.is_fallen(ryn))


class TestRevival(_Party):
    def test_a_revive_item_stands_a_companion_up(self):
        ryn = self.companion("ryn_g")
        ryn.take_damage(10 ** 6, "physical")
        salve = Consumable(obj_id="phoenix", name="phoenix feather", effect_type="revive", effect_value=40)
        said = salve.use(self.player, target=ryn)
        self.assertIn("rises", said)
        self.assertFalse(companions.is_fallen(ryn))
        self.assertEqual(int(ryn.max_health * 0.4), ryn.health)
        spare = Consumable(obj_id="phoenix_spare", name="phoenix feather", effect_type="revive", effect_value=40)
        self.assertIn("is not down", spare.use(self.player, target=ryn), "and it is not wasted on someone who is standing")
        self.assertEqual(1, spare.get_property("uses"), "unspent")

    def test_a_revive_item_says_whom_it_is_for_when_used_alone(self):
        salve = Consumable(obj_id="phoenix2", name="phoenix feather", effect_type="revive", effect_value=40)
        self.assertIn("fallen companion", salve.use(self.player))
        self.assertEqual(1, salve.get_property("uses"))

    def test_the_revive_spell_effect(self):
        from engine.magic.effects import apply_spell_effect

        ryn, healer = self.companion("ryn_h"), self.companion("healer_h")
        ryn.take_damage(10 ** 6, "physical")
        _, text = apply_spell_effect(healer, ryn, SPELL_REGISTRY["test_raise"], None)
        self.assertIn("back to their feet", text)
        self.assertEqual(int(ryn.max_health * 0.5), ryn.health)
        _, again = apply_spell_effect(healer, ryn, SPELL_REGISTRY["test_raise"], None)
        self.assertIn("no need of reviving", again)

    def test_a_heal_spell_on_the_fallen_says_to_revive_first(self):
        from engine.magic.effects import apply_spell_effect
        from engine.magic.spell_registry import get_spell

        ryn, healer = self.companion("ryn_i"), self.companion("healer_i")
        ryn.take_damage(10 ** 6, "physical")
        _, text = apply_spell_effect(healer, ryn, get_spell("cure"), None)
        self.assertIn("must be revived first", text)
        self.assertTrue(companions.is_fallen(ryn))

    def test_an_inns_restore_brings_the_fallen_up_and_mends_them(self):
        from engine.dialogue.effects import apply_effects

        ryn = self.companion("ryn_j")
        ryn.take_damage(10 ** 6, "physical")
        apply_effects({"restore": {"resource": "health", "amount": "full", "companions": True}}, {"player": self.player, "world": self.world})
        self.assertFalse(companions.is_fallen(ryn))
        self.assertEqual(ryn.max_health, ryn.health)


class TestTheSupport(_Party):
    def test_a_companion_with_a_heal_mends_the_most_hurt_member_of_the_party(self):
        healer = self.companion("healer_k", spells=["cure"])
        hurt = self.companion("ryn_k", falls=False)
        hurt.health = int(hurt.max_health * 0.2)
        told = specialized.perform_companion_support(healer, self.world, 1000.0, self.player)
        self.assertIsNotNone(told)
        self.assertGreater(hurt.health, int(hurt.max_health * 0.2))

    def test_it_leaves_the_healthy_alone(self):
        healer = self.companion("healer_l", spells=["cure"])
        self.assertIsNone(specialized.perform_companion_support(healer, self.world, 1000.0, self.player))

    def test_it_stands_the_fallen_up_before_it_mends_anyone(self):
        healer = self.companion("healer_m", spells=["cure", "test_raise"])
        down = self.companion("ryn_m")
        hurt = self.companion("ryn_n", falls=False)
        hurt.health = int(hurt.max_health * 0.1)
        down.take_damage(10 ** 6, "physical")
        specialized.perform_companion_support(healer, self.world, 1000.0, self.player)
        self.assertFalse(companions.is_fallen(down), "the fallen first")
        self.assertEqual(int(hurt.max_health * 0.1), hurt.health, "and the hurt wait their turn")

    def test_it_keeps_the_rhythm_of_any_other_action(self):
        healer = self.companion("healer_o", spells=["cure"])
        hurt = self.companion("ryn_o", falls=False)
        hurt.health = int(hurt.max_health * 0.1)
        self.assertIsNotNone(specialized.perform_companion_support(healer, self.world, 1000.0, self.player))
        hurt.health = int(hurt.max_health * 0.1)
        self.assertIsNone(specialized.perform_companion_support(healer, self.world, 1001.0, self.player), "not twice in one beat")

    def test_it_will_not_cast_silenced(self):
        healer = self.companion("healer_p", spells=["cure"])
        hurt = self.companion("ryn_p", falls=False)
        hurt.health = 1
        healer.apply_effect({"type": "status", "name": "Silenced", "tags": ["silence"], "base_duration": 30}, 1000.0)
        self.assertIsNone(specialized.perform_companion_support(healer, self.world, 1000.0, self.player))


class TestTheValidator(unittest.TestCase):
    def test_falls_when_defeated_must_be_a_bool(self):
        import json
        import shutil
        import tempfile
        from pathlib import Path

        from engine.server import content_set

        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        pkg = tmp / "story_fixture"
        shutil.copytree(STORY_FIXTURE, pkg)
        path = pkg / "data" / "npcs" / "people.json"
        people = json.loads(path.read_text(encoding="utf-8"))
        people["ryn"].setdefault("properties", {})["falls_when_defeated"] = "yes"
        path.write_text(json.dumps(people), encoding="utf-8")
        errors = [i.message for i in content_set.validate_content_set(pkg) if i.severity == "error"]
        self.assertTrue([m for m in errors if "falls_when_defeated must be true or false" in m], errors)


if __name__ == "__main__":
    unittest.main()
