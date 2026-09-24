# tests/singles/test_summon_cap_enforcement.py
"""`max_summons` on a summon effect. Nothing read it, so every cast added
another summon; at the cap the oldest living one from that ability is now
dismissed to make room (the cast is already paid for, so it is not refused)."""
import time
from tests.fixtures import GameTestBase
from engine.magic.spell import Spell
from engine.magic.spell_registry import register_spell


class TestSummonCapEnforcement(GameTestBase):

    def setUp(self):
        super().setUp()
        self.summon_spell = Spell(
            spell_id="summon_rat", name="Summon Rat", description="x",
            mana_cost=0, cooldown=0.0, target_type="self", level_required=1,
            effects=[{"type": "summon", "summon_template_id": "giant_rat", "max_summons": 2, "summon_duration": 100}],
        )
        register_spell(self.summon_spell)
        self.player.learn_spell("summon_rat")

    def _cast(self):
        return self.player.cast_spell(self.summon_spell, self.player, time.time(), self.world)

    def _summons(self) -> list:
        assert self.player.runtime_state.magic is not None
        return self.player.runtime_state.magic.summons.get("summon_rat", [])

    def test_casting_at_the_cap_dismisses_the_oldest(self):
        self._cast()
        self._cast()
        first, second = self._summons()

        result = self._cast()

        self.assertEqual(2, len(self._summons()))
        self.assertEqual(second, self._summons()[0])
        self.assertNotIn(first, self._summons())
        self.assertFalse(self.world.get_npc(first).is_alive)
        self.assertIn("fades away", result["message"])

    def test_a_summon_that_already_died_does_not_count(self):
        self._cast()
        self._cast()
        first, _second = self._summons()
        self.world.get_npc(first).is_alive = False

        self._cast()

        self.assertEqual(2, len(self._summons()))
        self.assertNotIn(first, self._summons())

    def test_without_a_cap_summons_accumulate(self):
        self.summon_spell.effects[0].pop("max_summons")
        for _ in range(3):
            self._cast()
        self.assertEqual(3, len(self._summons()))
