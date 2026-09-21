# tests/singles/test_night_shift_crime_loop.py
"""`night_shift`'s crime loop, end to end, in a set with no fantasy nouns.

Track F's F-3: "Sources for `item_shim_card` and `item_master_shim` (2 of 4 items
are unobtainable); 2–3 containers carrying `owned_by_npc`; a locked storeroom; an
`advancement.grants` table so the ledger pays; 2–4 rooms to carry stolen goods to."
Done when "a player can take what is not theirs, be caught, be held and get out".

The loop the content now carries:

    supply room ──(locked door, needs a shim)── storeroom ── wire cage (master shim)
        │  register (Dana's)      tool crib (Priya's: shim cards)
        │
    loading dock ── back alley (a dog) ── end of the alley (Otis, who buys anything)

Two engine seams came out of authoring it, and both are asserted here because
content alone could not have fixed either:

* loot for an owned container was generated at the moment of the *theft*, so
  `steal <item> from <container>` could never name anything -- it is generated on
  first open now, and an authored inventory is left alone;
* `get <item> from <container>` took the same things with no risk at all, which
  made the crime system optional for the only containers it was written for.
"""

import json
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
NIGHT_SHIFT = REPO_ROOT / "content_sets" / "night_shift"

# Patching the *score* rather than the check keeps `practice_check` real, so the
# training it grants is exercised too.
ALWAYS_NOTICED = 0
ALWAYS_UNSEEN = 10_000


class NightShiftBase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(NIGHT_SHIFT),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="attendant")
        self.transcript: list[str] = []
        self._run("char create Wren")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def _run(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        text = "\n".join(str(event.get("payload")) for event in events if event.get("type") == "text")
        self.transcript.append("%s\n%s" % (command, text))
        return text

    def _room(self):
        return self.server.world.get_current_room(self.player)

    def _go(self, direction: str) -> str:
        text = self._run(direction)
        return text

    def _to_supply_room(self) -> None:
        self._run("north")
        self.assertEqual("supply_room", self.player.current_room_id)

    def _to_alley_end(self) -> None:
        self._run("east")
        self._run("east")
        self.assertEqual("alley_end", self.player.current_room_id)

    def _give_skill(self, skill: str, level: int) -> None:
        from engine.core.skill_system import SkillSystem

        SkillSystem._ensure_skill(self.player, skill)["level"] = level


class TestTheSetHasThePieces(NightShiftBase):
    def test_the_two_lockpick_sources_exist(self):
        """F-3: two of the set's four items were unobtainable."""
        items = json.loads((NIGHT_SHIFT / "data" / "items" / "depot_items.json").read_text(encoding="utf-8"))
        crib = items["item_tool_crib"]["properties"]
        cage = items["item_storeroom_cage"]["properties"]
        self.assertIn("item_shim_card", [entry["item_id"] for entry in crib["contains"]])
        self.assertIn("item_master_shim", [entry["item_id"] for entry in cage["contains"]])
        self.assertTrue(cage["locked"], "the master shim is behind a lock, which is the point of it")
        self.assertTrue(cage["owned_by_npc"] and crib["owned_by_npc"], "both belong to somebody")

    def test_the_fence_buys_what_the_depot_sells(self):
        crew = json.loads((NIGHT_SHIFT / "data" / "npcs" / "staff.json").read_text(encoding="utf-8"))
        otis = crew["otis"]["properties"]
        self.assertTrue(otis["is_vendor"])
        self.assertIn("Item", otis["buys_item_types"])
        self.assertIn("Treasure", otis["buys_item_types"])

    def test_the_storeroom_door_is_locked_and_needs_a_pick(self):
        self._to_supply_room()
        refused = self._run("east")
        self.assertIn("locked", refused.lower())
        self.assertEqual("supply_room", self.player.current_room_id, "the door held")

        # And picking it needs the tool the set has two sources for.
        no_pick = self._run("pick east")
        self.assertIn("lockpick", no_pick.lower())
        self.assertEqual("supply_room", self.player.current_room_id)

    def test_the_ledger_and_the_ladder_are_declared(self):
        ruleset = json.loads((NIGHT_SHIFT / "rules" / "ruleset.json").read_text(encoding="utf-8"))
        self.assertTrue(ruleset["advancement"]["grants"], "the ledger has a table to pay from")
        self.assertTrue(ruleset["social"]["tiers"], "and the bonds have a ladder")


class TestTheContainerSeams(NightShiftBase):
    def test_opening_an_owned_container_shows_what_is_inside(self):
        """The seam: contents existed only at the moment of the theft."""
        self._to_supply_room()
        opened = self._run("open tool crib")
        self.assertIn("shim card", opened)
        crib = next(item for item in self._room().items if item.obj_id == "item_tool_crib")
        self.assertTrue(crib.properties.get("loot_generated")
                        or crib.properties.get("contains"))

    def test_an_authored_inventory_is_not_buried_in_household_loot(self):
        """A till is a deliberate inventory, not a roll table."""
        self._to_supply_room()
        self._run("open register")
        register = next(item for item in self._room().items if item.obj_id == "item_register")
        ids = [entry.obj_id for entry in register.properties.get("contains", [])]
        self.assertEqual(["item_energy_drink", "item_energy_drink", "item_lottery_ticket"], ids)

    def test_emptying_an_authored_container_does_not_refill_it(self):
        self._to_supply_room()
        self._run("open tool crib")
        crib = next(item for item in self._room().items if item.obj_id == "item_tool_crib")
        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(True, "", 10)):
            self._run("get all from tool crib")
        self.assertEqual([], crib.properties.get("contains"))
        self._run("close tool crib")
        self._run("open tool crib")
        self.assertEqual([], crib.properties.get("contains"), "authored contents are the contents")


class TestTakingIsTheftWhicheverVerb(NightShiftBase):
    """`get` and `steal` used to disagree about who owns a container."""

    def test_getting_from_an_owned_container_can_be_witnessed(self):
        self._to_supply_room()
        self._run("open register")
        self.player.runtime_state.gold = 1000

        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(False, "", -10)):
            caught = self._run("get energy drink from register")

        self.assertIn("red-handed", caught)
        self.assertGreater(self.player.total_theft_value, 0, "the act was recorded as a crime")
        self.assertEqual(1, self.player.inventory.count_item("item_energy_drink"),
                         "and the item still changed hands")

    def test_getting_from_the_floor_is_not_a_crime(self):
        self._to_supply_room()
        floor_item = ItemFactory.create_item_from_template("item_multitool", self.server.world)
        self.server.world.add_item_to_room(
            self.player.current_region_id, self.player.current_room_id, floor_item
        )
        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(False, "", -10)):
            picked = self._run("get multitool")
        self.assertIn("You pick up", picked)
        self.assertNotIn("red-handed", picked)
        self.assertEqual(0, self.player.total_theft_value)

    def test_a_burglary_with_nobody_around_is_still_a_burglary(self):
        """No witness is not a failure: the owner is simply out."""
        self._to_supply_room()
        for npc in self.server.world.get_npcs_for_player(self.player):
            npc.current_room_id = "back_alley"
        self._run("open tool crib")
        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(False, "", -10)):
            taken = self._run("get shim card from tool crib")
        self.assertIn("You get", taken)
        self.assertNotIn("red-handed", taken)


class TestTheWholeLoop(NightShiftBase):
    def test_stolen_goods_can_be_carried_to_the_fence_and_sold(self):
        """Steal from Dana's shelf, walk it past the dog, and sell it to Otis."""
        self._to_supply_room()
        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(True, "", 10)):
            taken = self._run("steal multitool from Dana")
        self.assertIn("unnoticed", taken)
        self.assertEqual(1, self.player.inventory.count_item("item_multitool"))

        # Carry it out: supply room -> loading dock -> alley (the dog) -> alley end.
        self._run("south")
        self._to_alley_end()
        self.assertIsNotNone(
            next((npc for npc in self.server.world.npcs.values() if npc.template_id == "otis"), None)
        )
        self.player.runtime_state.gold = 0
        self._run("trade Otis")
        sold = self._run("sell multitool")
        self.assertIn("multitool", sold.lower())
        self.assertGreater(self.player.runtime_state.gold, 0, "the fence pays in credits")
        self.assertEqual(0, self.player.inventory.count_item("item_multitool"))

    def test_being_caught_held_and_getting_out(self):
        self._to_supply_room()
        # A pick in hand, taken quietly, is what survives the search.
        self._run("open tool crib")
        self._give_skill("awareness", 20)
        self._give_skill("security", 20)
        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(True, "", 10)):
            self._run("get shim card from tool crib")
        self.assertEqual(1, self.player.inventory.count_item("item_shim_card"))

        self.player.runtime_state.gold = 0
        with patch("engine.core.crime_manager.SkillSystem.attempt_check_with_margin",
                   return_value=(False, "", -10)):
            caught = self._run("steal multitool from Dana")

        self.assertIn("confiscated", caught.lower())
        self.assertIsNotNone(self.player.jailed_until)
        self.assertEqual("holding_room", self.player.current_room_id)
        self.assertEqual(1, self.player.inventory.count_item("item_shim_card"),
                         "a concealed pick survives the search")

        with patch("engine.world.world.SkillSystem.attempt_check_with_margin",
                   return_value=(True, "", 10)):
            escape = self._run("pick north")
        self.assertIn("Click!", escape)
        self._run("north")
        self.assertEqual("loading_dock", self.player.current_room_id)

    def test_the_ledger_pays_for_walking_in(self):
        """F-3: an `advancement.grants` table so the ledger pays."""
        self.assertEqual(0, self.player.runtime_state.progression.experience)
        self._to_supply_room()
        self.assertGreater(self.player.runtime_state.progression.experience, 0,
                           "arriving somewhere new is a recognised activity")
        self.assertTrue(self.player.advancement_entries)


if __name__ == "__main__":
    unittest.main()
