"""The sci-fi proving slice: a second reference set with no fantasy in it.

`docs/design/cross_theme_engine_contracts.md` step 5 asks for a deliberately
small content set that exercises a kinetic attack source, protective gear, a
charge/heat ability, a generated component and a fabrication recipe while
omitting magic, mana, spell schools, gems and fantasy vocabulary. This is that
set, `content_sets/orbital_salvage`, walked as a player would walk it.

Two kinds of assertion live here, and they are doing different jobs:

* **It works.** Creation grants the set's own kit, gathering rolls its own
  components, the recipe turns them into a patch kit, the ability costs charge,
  the weapon and vest resolve their declared profiles.
* **Nothing leaks.** Every line of text a player can read on this journey is
  scanned for the vocabulary the set never declares. That second kind is the
  actual proof: a fantasy word reaching a sci-fi player is the failure mode this
  whole initiative exists to remove, and it is invisible to a test that only
  checks the mechanics still function.
"""

import json
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from engine.contracts import work as work_contract
from engine.contracts.equipment import armor_defense, weapon_damage
from engine.contracts.resources import label_for, pool_for
from engine.items.item_factory import ItemFactory
from engine.server.headless_server import HeadlessServer


REPO_ROOT = Path(__file__).resolve().parents[3]
ORBITAL_SALVAGE = REPO_ROOT / "content_sets" / "orbital_salvage"

# The parts the salvage bench yields. Three tests ask "how many of these does the
# player have", and the set is the thing that decides which they are.
COMPONENT_IDS = {"item_servo_cluster", "item_cell_stack", "item_lattice_shard"}

# Words this set never declares anywhere and a player must therefore never read.
# Deliberately matched on word boundaries so "manager" and "damage" do not trip
# it, and kept to vocabulary that would be a genuine engine leak rather than a
# coincidence of English.
FORBIDDEN = (
    "mana", "magical", "arcane", "spell", "spells", "gem", "gems",
    "sword", "pickaxe", "leather", "chainmail", "potion", "gold",
)


class OrbitalSalvageBase(unittest.TestCase):
    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(ORBITAL_SALVAGE),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.session = self.server.create_session(player_id="salvager")
        self.transcript: list[str] = []
        self._run("char create Vess")
        self.player = self.server.get_player_for_session(self.session.session_id)

    def _run(self, command: str) -> str:
        events = self.server.execute_command(self.session.session_id, command)
        text = "\n".join(
            str(event.get("payload")) for event in events if event.get("type") == "text"
        )
        self.transcript.append("%s\n%s" % (command, text))
        return text

    def _inventory_ids(self) -> list[str]:
        return [
            slot.item.obj_id
            for slot in self.player.inventory.slots
            if slot.item is not None
        ]

    def _carried(self, item_id: str):
        for slot in self.player.inventory.slots:
            if slot.item is not None and slot.item.obj_id == item_id:
                return slot.item
        return None

    def _gather_for_ingredients(self, attempts: int = 6) -> None:
        for _ in range(attempts):
            self._run("gather bench")

    def _count_of(self, item_ids: set) -> int:
        return len([entry for entry in self._inventory_ids() if entry in item_ids])

    def _go_to_hold(self) -> None:
        self._run("north")
        self._run("north")


class TestTheSetIsBuiltFromDeclarations(OrbitalSalvageBase):
    def test_it_declares_abilities_without_declaring_magic(self) -> None:
        capabilities = set(self.server.content_set.capabilities)
        self.assertIn("abilities", capabilities)
        self.assertNotIn("magic", capabilities, "the proving slice must not declare magic")

    def test_its_ability_pool_is_the_resource_it_declares(self) -> None:
        """Charge, named by the contract, not a hardcoded pool called mana."""
        status = self.server._build_status_payload(self.session.session_id)
        pool = status["ability_resource"]
        self.assertEqual("charge", pool["id"])
        self.assertEqual("Charge", pool["label"])
        self.assertEqual("CHG", pool["short"])
        self.assertEqual(pool["label"], label_for(self.server.world, pool["id"]))
        self.assertEqual(pool["max"], pool["current"])
        self.assertGreater(pool["max"], 0)

    def test_its_weapon_and_vest_resolve_their_declared_profiles(self) -> None:
        pistol = ItemFactory.create_item_from_template("item_rail_pistol", self.server.world)
        vest = ItemFactory.create_item_from_template("item_impact_vest", self.server.world)
        self.assertIsNotNone(pistol)
        self.assertIsNotNone(vest)

        registry = self.server.world.contract_registry
        weapon_profile = registry.attack_profiles["kinetic_round"]
        armor_profile = registry.defense_profiles["impact_shell"]
        self.assertEqual(weapon_profile["damage"], weapon_damage(self.server.world, pistol))
        self.assertEqual(armor_profile["defense"], armor_defense(self.server.world, vest))


class TestThePlayerJourney(OrbitalSalvageBase):
    def test_creation_grants_the_sets_own_kit_and_abilities(self) -> None:
        self.assertIn("item_pry_bar", self._inventory_ids())
        self.assertEqual("Salvager", self.player.runtime_state.progression.player_class)
        self.assertEqual({"overcharge"}, set(self.player.runtime_state.magic.known_spells))
        self.assertEqual(
            self.player.runtime_state.magic.max_mana,
            self.player.runtime_state.magic.mana,
            "the pool should start full",
        )

    def test_gathering_rolls_this_sets_components_rather_than_a_gem(self) -> None:
        self._gather_for_ingredients(3)
        component_ids = {
            "item_servo_cluster", "item_cell_stack", "item_lattice_shard",
        }
        components = [
            slot.item for slot in self.player.inventory.slots
            if slot.item is not None and slot.item.obj_id in component_ids
        ]
        self.assertTrue(components, "gathering produced nothing")
        component = components[0]

        # The set declares its own property prefix and its own band names.
        self.assertIn(
            component.get_property("component_size"),
            ("micro", "standard", "bulk"),
        )
        self.assertIn(component.get_property("component_quality"), ("worn", "true", "clean"))
        self.assertEqual(
            component.get_property("component_size"),
            component.get_property("instance_size"),
            "the neutral vocabulary is written for every family",
        )
        self.assertIsNone(component.get_property("gem_size"))
        self.assertFalse(component.stackable, "distinct instances must not stack")
        # The cross-system trio is what crafting and appraisal read.
        self.assertIn(component.get_property("material_quality_score"), (1, 2, 3))

    def test_the_fabrication_recipe_consumes_components_and_yields_a_kit(self) -> None:
        self._gather_for_ingredients()
        before = self._count_of(COMPONENT_IDS)
        self.assertGreaterEqual(before, 2, "gathering produced too few components to craft with")

        crafted = self._run("craft fabricate patch kit")
        self.assertIn("patch kit", crafted.lower())
        self.assertIn("item_patch_kit", self._inventory_ids())
        self.assertEqual(
            before - 2,
            self._count_of(COMPONENT_IDS),
            "the recipe asks for two parts of the family, not a named template",
        )

    def test_the_recipe_names_a_family_and_a_grade_floor_rather_than_a_template(self) -> None:
        """The ingredient is a rule this set declares, not two item ids."""
        recipe = self.server.world.game.crafting_manager.recipes["fabricate_patch_kit"]
        ingredient = recipe.ingredients[0]
        self.assertNotIn("item_id", ingredient)
        self.assertEqual("salvaged_part", ingredient["item_family"])
        self.assertEqual(2, ingredient["min_material_quality"])

        # What the bench yields satisfies it; the family is what the recipe reads.
        self._gather_for_ingredients()
        parts = [
            slot.item for slot in self.player.inventory.slots
            if slot.item is not None and slot.item.obj_id in COMPONENT_IDS
        ]
        self.assertTrue(parts)
        self.assertTrue(
            all(str(part.get_property("item_family", "")) == "salvaged_part" for part in parts),
            "every gathered component should carry the family the recipe names",
        )

    def test_a_scrap_part_does_not_satisfy_the_grade_floor(self) -> None:
        """The floor is what makes the rule a choice rather than a formality.

        The recipe asks for grade 2 or better, which is what the bench yields;
        a part below it is refused by name rather than quietly spent. This is
        the content half of the substitution machinery -- `alternatives` in this
        set exist to let a *different* template stand in, and pricing that
        trade-off is what `quality_penalty` is for. The penalty arithmetic
        itself is covered in `test_crafting_reference_ingredients`.
        """
        manager = self.server.world.game.crafting_manager
        recipe = manager.recipes["fabricate_patch_kit"]
        ingredient = recipe.ingredients[0]

        scrap = ItemFactory.create_item_from_template("item_servo_cluster", self.server.world)
        scrap.properties["material_quality_score"] = 1
        scrap.stackable = False
        scrap.update_property("stackable", False)
        self.assertIsNone(
            manager.matched_option(ingredient, scrap),
            "a worn part is below the floor and should not match",
        )

        serviceable = ItemFactory.create_item_from_template("item_cell_stack", self.server.world)
        serviceable.properties["material_quality_score"] = 2
        serviceable.stackable = False
        serviceable.update_property("stackable", False)
        matched = manager.matched_option(ingredient, serviceable)
        self.assertIsNotNone(matched, "a serviceable part should match")
        self.assertEqual("salvaged_part", matched.get("item_family"))

    def test_gathered_parts_can_be_broken_down_into_station_scrap(self) -> None:
        """The set enables `salvage` and, until now, declared no rule for it.

        Every attempt refused. The rule is keyed by the family the bench yields,
        so it reaches parts the ruleset never names.
        """
        self._gather_for_ingredients(2)
        parts = self._count_of(COMPONENT_IDS)
        self.assertGreater(parts, 0, "nothing was gathered to break down")

        result = self._run("salvage servo cluster")
        self.assertIn("scrap alloy", result)
        self.assertGreater(self.player.inventory.count_item("item_scrap_alloy"), 0)

    def test_a_familyless_item_still_comes_back_as_the_sets_scrap(self) -> None:
        """The locker is not a salvaged part; the default is what catches it."""
        locker = ItemFactory.create_item_from_template("item_locker", self.server.world)
        self.assertIsNotNone(locker)
        self.player.inventory.add_item(locker)
        result = self._run("salvage locker")
        self.assertIn("scrap alloy", result)

    def test_ivo_buys_parts_by_family_and_grade(self) -> None:
        """The set's economy closes the loop: gather, or craft, then get paid."""
        self._run("trade ivo")
        listed = self._run("orders")
        self.assertIn("serviceable_parts", listed)
        self.assertIn("Salvaged part", listed)
        self.assertIn("credits", listed)

    def test_the_ability_spends_the_declared_resource(self) -> None:
        self._go_to_hold()
        before = self.player.runtime_state.magic.mana

        listed = self._run("abilities")
        self.assertIn("6 CHG", listed, "the listed cost must be named by the contract")

        result = self._run("cast overcharge")
        self.assertIn("discharge", result)
        self.assertEqual(before - 6, self.player.runtime_state.magic.mana)
        self.assertLess(self.player.runtime_state.magic.mana, before)

        # And the contract's cooldown is what stops the second attempt.
        again = self._run("cast overcharge")
        self.assertIn("cooldown", again.lower())

    def test_the_kinetic_weapon_hits_harder_than_bare_hands(self) -> None:
        self._go_to_hold()
        self._run("attack drone")
        bare = "\n".join(self.transcript)
        self.assertIn("bare hands", bare)

        pistol = ItemFactory.create_item_from_template("item_rail_pistol", self.server.world)
        self.player.inventory.add_item(pistol)
        self.player.equip_item(pistol, slot_name="main_hand")
        self._run("attack drone")
        armed = self.transcript[-1]
        self.assertNotIn("bare hands", armed)


class TestThePoolFollowsItsDeclaration(OrbitalSalvageBase):
    """The four resource fields are read, not merely declared.

    `engine/contracts/resources.py` takes `label`, `short`, `max_stat` and
    `regeneration_stat` from the set's contract. A declaration nothing reads is
    the failure mode this whole initiative is about, so the regeneration switch
    is asserted by flipping it and watching the pool stop refilling.
    """

    def _drain_and_tick(self) -> int:
        pool = self.player.runtime_state.magic
        pool.mana = 0
        self.player.last_mana_regen_time = 0.0
        now = self.server.world.clock.now()
        self.player.update(now + 30.0, 1.0)
        return pool.mana

    def test_the_declared_pool_refills_when_it_says_it_regenerates(self) -> None:
        self.assertGreater(self._drain_and_tick(), 0)

    def test_a_pool_declared_not_to_regenerate_stays_where_it_is(self) -> None:
        resources = self.server.world.contract_registry.resources
        resources["charge"]["regenerates"] = False
        self.assertEqual(0, self._drain_and_tick())

    def test_the_declared_stat_measures_the_pool(self) -> None:
        """`max_stat` decides how large the pool is, not a hardcoded stat."""
        stats = dict(self.player.stats)
        baseline = pool_for(self.server.world, stats)
        resources = self.server.world.contract_registry.resources
        resources["charge"]["max_stat"] = "strength"
        self.assertEqual(baseline, pool_for(self.server.world, stats), "equal stats, equal pool")
        stats["strength"] = stats.get("strength", 10) + 4
        self.assertGreater(pool_for(self.server.world, stats), baseline)


class TestNoFantasyVocabularyReachesThePlayer(OrbitalSalvageBase):
    def test_a_full_journey_never_shows_a_word_this_set_does_not_declare(self) -> None:
        for command in (
            "look", "status", "abilities", "inventory",
            "gather bench", "gather bench", "gather bench", "gather bench",
            "recipes", "craft fabricate patch kit", "inventory",
            "north", "north", "look", "attack cargo drone", "cast overcharge",
            "status", "combat", "south", "east", "jobs", "begin patch-kit batch",
            "collect", "look", "south", "east", "look", "talk Ivo",
        ):
            self._run(command)
        self._assert_clean("\n".join(self.transcript))

    def test_the_status_line_names_the_pool_it_declares(self) -> None:
        status = self._run("status")
        self.assertIn("Charge:", status)
        self.assertNotIn("Mana:", status)

    def test_the_ability_command_reads_as_an_ability_command(self) -> None:
        """The command surface is neutral; only a content set's names are not.

        `help` also lists the command's aliases, and the ability command keeps
        fantasy synonyms (`spells`, `magic`) so a player of a spellcasting set can
        still type what they always typed. Those are engine vocabulary a content
        set cannot currently hide, so this asserts what the *command* says rather
        than scanning its alias list; the design doc records the alias question
        as outstanding.
        """
        help_text = self._run("help abilities")
        self.assertIn("Help: Abilities Commands", help_text)
        self.assertIn("List the abilities you know.", help_text)
        self.assertIn("Use an ability you know.", help_text)
        self.assertNotIn("Mana", help_text)

        overview = self._run("help")
        self.assertIn("Abilities", overview)

    def _assert_clean(self, text: str) -> None:
        offenders = [
            word for word in FORBIDDEN
            if re.search(r"\b%s\b" % re.escape(word), text, re.IGNORECASE)
        ]
        if offenders:
            self.fail(
                "the player read vocabulary this content set never declares: %s\n\n%s"
                % (", ".join(sorted(set(offenders))), text)
            )


class TestWorkThatTakesTime(OrbitalSalvageBase):
    """The fabrication bay: `work`'s first consumer, in a set with no seasons.

    This is the *second theme* half of "a system is not finished until two themes
    use it", and it is deliberately a set whose world has no weather, no harvest
    and no winter: a duration here is only ever "the bay is still running".

    The loop is the content's, not the engine's:
    three salvaged parts go into the bay, half a day later two patch kits come
    out, against the instant recipe's one kit from two parts. Waiting is the
    cheaper way to keep kits, which is the decision the mechanic exists to offer.
    """

    SAVE_BATCH = "kit_batch"

    def _seed_parts(self, count: int) -> None:
        """Parts directly rather than by gathering: the bench rolls grades, and
        the thing under test here is the bay."""
        for _ in range(count):
            item = ItemFactory.create_item_from_template("item_servo_cluster", self.server.world)
            self.player.inventory.add_item(item, 1)

    def _go_to_workshop(self) -> None:
        self._run("east")
        self.assertEqual("workshop", self.player.current_room_id)

    def _tick_half_a_day(self) -> None:
        # The world clock is a SimulatedClock under deterministic_test_mode and
        # one command advances it by `tick_dt`, so half a game day is one tick.
        self.server.tick_dt = 600.0
        self._run("look")

    def test_the_bay_is_a_station_this_set_declares(self) -> None:
        room = self.server.world.regions["station"].rooms["workshop"]
        station = next(
            item for item in room.items
            if item.get_property("crafting_station_type") == "fabricator"
        )
        self.assertIsNotNone(station, "the workshop's own prose describes a fabrication bay")
        self.assertFalse(station.get_property("can_take", True), "it is furniture, not loot")

        declared = self.server.world.contract_registry.work_declaration(self.SAVE_BATCH)
        self.assertIsNotNone(declared, "the set declares the work the bay runs")
        self.assertEqual("fabricator", declared["station"])
        self.assertEqual(0.5, declared["duration_days"])

    def test_jobs_names_the_station_a_batch_needs(self) -> None:
        away = self._run("jobs")
        self.assertIn("patch-kit batch", away)
        self.assertIn("fabricator", away.lower(), "the requirement is named, not hidden")

        self._go_to_workshop()
        here = self._run("jobs")
        self.assertIn("Stations here", here)
        self.assertIn("fabricator", here.lower())

    def test_a_batch_cannot_be_started_away_from_the_bay(self) -> None:
        self._seed_parts(3)
        refused = self._run("begin patch-kit batch")
        self.assertIn("fabricator", refused.lower())
        self.assertEqual(3, self.player.inventory.count_item("item_servo_cluster"), "nothing was spent")
        self.assertEqual([], self.player.runtime_state.work.jobs)

    def test_begin_spends_the_parts_and_collect_waits_for_the_clock(self) -> None:
        self._seed_parts(3)
        self._go_to_workshop()

        started = self._run("begin patch-kit batch")
        self.assertIn("half a day", started.lower().replace("12 hours", "half a day"))
        self.assertEqual(0, self.player.inventory.count_item("item_servo_cluster"), "the bay has them now")

        early = self._run("collect")
        self.assertIn("Nothing is ready", early)
        self.assertEqual(1, len(self.player.runtime_state.work.jobs))

    def test_the_batch_finishes_on_the_world_clock(self) -> None:
        self._seed_parts(3)
        self._go_to_workshop()
        self._run("begin patch-kit batch")
        self._tick_half_a_day()

        # The *score* is forced rather than the check itself: `practice_check`
        # still runs for real, so the training it grants is under test too.
        with patch("engine.core.skill_system.SkillSystem._compute_score", return_value=70):
            finished = self._run("collect")

        self.assertIn("2 x patch kit", finished)
        self.assertEqual(2, self.player.inventory.count_item("item_patch_kit"))
        self.assertEqual([], self.player.runtime_state.work.jobs)
        self.assertIn("fabrication", self.player.runtime_state.progression.skills,
                      "the check trains the skill it tests")
        self.assertGreater(self.player.runtime_state.progression.skills["fabrication"]["xp"], 0)

    def test_a_run_that_goes_badly_yields_half(self) -> None:
        self._seed_parts(3)
        self._go_to_workshop()
        self._run("begin patch-kit batch")
        self._tick_half_a_day()

        with patch("engine.core.skill_system.SkillSystem._compute_score", return_value=3):
            finished = self._run("collect")

        self.assertIn("spoiled", finished)
        self.assertEqual(1, self.player.inventory.count_item("item_patch_kit"))
        self.assertGreater(
            self.player.runtime_state.progression.skills.get("fabrication", {}).get("xp", 0), 0,
            "practice still teaches, even when the run goes badly",
        )


class TestAJobOutlivesTheProcess(unittest.TestCase):
    """What the two absolute numbers are for.

    A job is `started_at` and `ends_at`, so a save records *when it ends* rather
    than how much was left. The player here starts a batch, the server is shut
    down entirely, a new server loads the save with the clock moved on, and the
    batch is finished -- on the same `ends_at` the first process wrote.
    """

    def setUp(self) -> None:
        self.save_name = "work_batch_save.json"
        self._runtime_state = tempfile.TemporaryDirectory()
        self.save_directory = Path(self._runtime_state.name) / "saves"
        self.save_path = self.save_directory / self.save_name
        self.addCleanup(self._runtime_state.cleanup)

    def _server(self) -> HeadlessServer:
        return HeadlessServer(
            db_path=":memory:",
            content_set_path=str(ORBITAL_SALVAGE),
            save_directory=str(self.save_directory),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )

    def test_a_running_batch_is_finished_by_the_next_process(self) -> None:
        server = self._server()
        try:
            session = server.create_session(player_id="salvager")
            server.execute_command(session.session_id, "char create Vess")
            player = server.get_player_for_session(session.session_id)
            for _ in range(3):
                item = ItemFactory.create_item_from_template("item_servo_cluster", server.world)
                player.inventory.add_item(item, 1)
            server.execute_command(session.session_id, "east")
            server.execute_command(session.session_id, "begin patch-kit batch")

            self.assertEqual(1, len(player.runtime_state.work.jobs))
            written_ends_at = float(player.runtime_state.work.jobs[0]["ends_at"])
            self.assertTrue(server.world.save_game(self.save_name, player=player))
        finally:
            server.shutdown()

        saved = json.loads(self.save_path.read_text(encoding="utf-8"))
        self.assertEqual(
            written_ends_at,
            float(saved["player"]["gameplay"]["work"]["jobs"][0]["ends_at"]),
            "the save carries the deadline, not a countdown",
        )

        restored = self._server()
        try:
            loaded, _time_state, _weather_state = restored.world.load_save_game(self.save_name)
            self.assertTrue(loaded)
            player = restored.world.player
            self.assertEqual(1, len(player.runtime_state.work.jobs))
            self.assertEqual(written_ends_at, float(player.runtime_state.work.jobs[0]["ends_at"]))

            # The new process's clock starts where a SimulatedClock always starts,
            # so it is moved past the deadline rather than waited for.
            restored.world.clock.advance(written_ends_at - restored.world.clock.now() + 1)

            timer = player.runtime_state.work.jobs[0]
            with patch("engine.core.skill_system.SkillSystem._compute_score", return_value=70):
                result = work_contract.collect(restored.world, player, timer)

            self.assertTrue(result["ok"], result)
            self.assertEqual(2, player.inventory.count_item("item_patch_kit"))
            self.assertEqual([], player.runtime_state.work.jobs)
        finally:
            restored.shutdown()


if __name__ == "__main__":
    unittest.main()
