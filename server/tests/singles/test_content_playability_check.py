# tests/singles/test_content_playability_check.py
"""The build step that plays the content instead of reading it.

`run_content_checks.py` could prove every content set was *well-formed* and
nothing about whether the game made from it could be played. Two shipped defects
lived in that gap: `orbital_salvage` enabled `salvage` and declared no rule for
any item, so the whole system answered "You cannot salvage the X"; and a
`_comment` at the top of a recipe file aborted the crafting loader, silently
removing every recipe in the file.

These tests are about the check itself -- that it looks at the right things, that
it stays honest about what is not a finding, and that it fails when a set stops
being playable.
"""
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

CONTENT_SETS = ("fantasy_frontier", "modern_capsule", "night_shift", "orbital_salvage")


def _load_tool():
    path = REPO_ROOT / "toolkit" / "content_playability_check.py"
    spec = importlib.util.spec_from_file_location("content_playability_check", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


tool = _load_tool()


class TestTheCheckIsWiredIntoTheBuild(unittest.TestCase):
    def test_run_content_checks_runs_it(self):
        source = (REPO_ROOT / "run_content_checks.py").read_text(encoding="utf-8")
        self.assertIn("content_playability_check.py", source)

    def test_it_knows_about_every_shipped_set(self):
        found = {path.name for path in tool.content_sets()}
        self.assertEqual(set(CONTENT_SETS), found)


class TestThePlanIsDerivedNotGuessed(unittest.TestCase):
    """A plan that names commands by hand goes stale the first time one moves."""

    def _world_and_player(self, content_set: str):
        from engine.server.headless_server import HeadlessServer

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(REPO_ROOT / "content_sets" / content_set),
            deterministic_test_mode=True,
        )
        self.addCleanup(server.shutdown)
        session = server.create_session(player_id="plan")
        server.execute_command(session.session_id, "char create Planner")
        player = server.get_player_for_session(session.session_id)
        return server.world, player

    def test_every_sets_plan_includes_its_declared_systems(self):
        """The plan must be more than the universal commands, or it checks nothing."""
        from engine.commands.command_system import registered_commands

        for content_set in CONTENT_SETS:
            world, player = self._world_and_player(content_set)
            plan = tool.build_plan(
                REPO_ROOT / "content_sets" / content_set, world, player, registered_commands
            )
            self.assertTrue(plan, "%s produced no plan" % content_set)
            beyond_universal = [entry for entry in plan if entry.split()[0] not in tool.UNIVERSAL]
            self.assertTrue(
                beyond_universal,
                "%s's plan is only the universal commands, so it exercises nothing "
                "the set declares: %s" % (content_set, plan),
            )

    def test_a_set_with_crafting_gets_a_craft_command_naming_its_own_recipe(self):
        from engine.commands.command_system import registered_commands

        world, player = self._world_and_player("orbital_salvage")
        plan = tool.build_plan(
            REPO_ROOT / "content_sets" / "orbital_salvage", world, player, registered_commands
        )
        crafts = [entry for entry in plan if entry.startswith("craft ")]
        self.assertTrue(crafts, plan)
        self.assertIn("fabricate_patch_kit", crafts[0])

    def test_a_set_with_gathering_gets_a_gather_command_naming_its_own_node(self):
        from engine.commands.command_system import registered_commands

        world, player = self._world_and_player("orbital_salvage")
        plan = tool.build_plan(
            REPO_ROOT / "content_sets" / "orbital_salvage", world, player, registered_commands
        )
        gathers = [entry for entry in plan if entry.startswith("gather ")]
        self.assertTrue(gathers, plan)
        # The set's own node name, by first word -- `resolve_all` is deliberately
        # loose about the rest, and a two-word query that happens to match
        # nothing would report a working node as broken.
        node_name = str(world.item_templates["node_salvage_bench"]["name"])
        self.assertEqual(tool._first_word(node_name), gathers[0].split(" ", 1)[1])

    def test_a_set_that_declares_nothing_extra_still_gets_the_universal_commands(self):
        from engine.commands.command_system import registered_commands

        world, player = self._world_and_player("modern_capsule")
        plan = tool.build_plan(
            REPO_ROOT / "content_sets" / "modern_capsule", world, player, registered_commands
        )
        for command in tool.UNIVERSAL:
            self.assertIn(command, plan)

    def test_the_plan_is_bounded(self):
        from engine.commands.command_system import registered_commands

        for content_set in CONTENT_SETS:
            world, player = self._world_and_player(content_set)
            plan = tool.build_plan(
                REPO_ROOT / "content_sets" / content_set, world, player, registered_commands
            )
            self.assertLessEqual(len(plan), tool.MAX_COMMANDS)


class TestItDoesNotCryWolf(unittest.TestCase):
    def test_a_command_that_refuses_for_a_good_reason_is_not_a_finding(self):
        """A refusal the engine produced is an answer, not a failure."""
        for set_name in CONTENT_SETS:
            findings = tool.check_one(REPO_ROOT / "content_sets" / set_name)
            messages = [str(finding) for finding in findings]
            for message in messages:
                self.assertNotIn("Unknown command", message)
                self.assertNotIn("Something went wrong running", message)

    def test_every_shipped_set_passes(self):
        """No set fails the build. Warnings are allowed and asserted elsewhere."""
        for set_name in CONTENT_SETS:
            findings = tool.check_one(REPO_ROOT / "content_sets" / set_name)
            fatal = [str(finding) for finding in findings if finding.fatal]
            self.assertEqual([], fatal, set_name)


class TestAnAbilityWithNoRouteToThePlayer(unittest.TestCase):
    """A spell nothing teaches is authored gap, so it warns rather than fails.

    It is still worth reporting: an ability the player can never learn and no
    NPC ever casts is a spell somebody meant to stock a vendor with. The three
    routes that count are all content -- a scroll or tome an item teaches, a
    starting background, and the ruleset's own starting list.
    """

    def _ability_findings(self, set_name: str):
        findings = tool.check_one(REPO_ROOT / "content_sets" / set_name)
        return [finding for finding in findings if finding.command == "abilities"]

    def test_the_shipped_fantasy_set_reports_only_the_three_it_cannot_grant(self):
        """Three abilities, not sixteen.

        The first version of this check read only static `spell_to_learn` and
        reported 16 of 23 abilities as unreachable. `item_scroll_random` carries
        `properties.procedural_type: random_spell_scroll`, which `ItemFactory`
        fills from every spell with `level_required > 0 and mana_cost > 0`
        (`items/item_factory.py:161`) -- so one authored template puts twenty of
        them on a vendor's shelf. Track F caught it.

        What is left is real and smaller: three spells have `mana_cost == 0`, so
        the factory's filter excludes them from every procedural scroll and no
        authored scroll names them either.
        """
        warnings = [f for f in self._ability_findings("fantasy_frontier") if not f.fatal]
        self.assertEqual(1, len(warnings), [str(f) for f in warnings])
        message = warnings[0].message
        self.assertIn("no route to the player", message)
        self.assertIn("3 of 23", message)
        for unreachable in ("bone_shard", "ember_bolt", "zap"):
            self.assertIn(unreachable, message)
        for reachable in ("fireball", "ice_shard", "magic_missile"):
            self.assertNotIn(
                reachable, message,
                "reachable via a named scroll, a background, or the procedural scroll",
            )

    def test_a_procedural_scroll_counts_as_a_route(self):
        """The template that made the old count wrong, named explicitly."""
        taught = self._fantasy_taught()
        self.assertIn("fireball", taught)
        self.assertIn("rolled by", taught["fireball"])
        self.assertEqual(
            "item_scroll_random",
            tool._procedural_spell_route(None, REPO_ROOT / "content_sets" / "fantasy_frontier" / "data"),
        )

    def test_a_set_with_no_procedural_scroll_has_no_procedural_route(self):
        self.assertIsNone(
            tool._procedural_spell_route(None, REPO_ROOT / "content_sets" / "modern_capsule" / "data")
        )

    def test_a_set_that_declares_no_abilities_says_nothing(self):
        """`SPELL_REGISTRY` is process-wide, so the count has to be guarded.

        The check boots every set in one process, which leaves the fantasy set's
        spells registered while a set that declares no abilities is played. That
        read as "23 of 23 have no route" for two sets that have no abilities at
        all.
        """
        self.assertEqual([], self._ability_findings("modern_capsule"))
        self.assertEqual([], self._ability_findings("night_shift"))

    def test_the_warning_does_not_fail_the_build(self):
        self.assertTrue(all(not f.fatal for f in self._ability_findings("fantasy_frontier")))

    def _fantasy_taught(self) -> dict:
        """`_taught_ability_ids` for the fantasy set, from a booted world.

        It read files only until the procedural scroll was handled; that route
        resolves against `SPELL_REGISTRY`, which world construction populates.
        `_world_and_player` returns `(world, player)`, so the registry is the
        thing being relied on here, not the return value.
        """
        helper = TestThePlanIsDerivedNotGuessed()
        helper._world_and_player("fantasy_frontier")  # boots the registry
        return tool._taught_ability_ids(
            None, REPO_ROOT / "content_sets" / "fantasy_frontier"
        )

    def test_it_counts_a_scroll_as_a_route(self):
        from engine.magic.spell_registry import SPELL_REGISTRY

        taught = self._fantasy_taught()
        self.assertIn("raise_skeleton", taught)
        self.assertIn("taught by", taught["raise_skeleton"])
        # And the route is a real one: the spell exists in the registry.
        self.assertIn("raise_skeleton", SPELL_REGISTRY)

    def test_it_counts_a_background_as_a_route(self):
        taught = self._fantasy_taught()
        self.assertIn("magic_missile", taught)
        self.assertEqual("a starting background", taught["magic_missile"])

    def test_an_npc_casting_a_spell_is_not_a_route_for_the_player(self):
        """`usable_spells` says an NPC can cast it, which is not a way to learn it.

        NOTE: this is a weaker assertion than it looks once the procedural route
        exists, because `zap`/`bone_shard`/`ember_bolt` are excluded from
        procedural scrolls by their `mana_cost == 0` rather than by being
        unmentioned. `check_one`'s own count is the load-bearing test; this one
        keeps the roster honest.
        """
        taught = self._fantasy_taught()
        self.assertNotIn("zap", taught)
        self.assertNotIn("ember_bolt", taught)


class TestItCatchesARecipeTheLoaderDropped(unittest.TestCase):
    """The failure this check exists for, reproduced on a copy of a real set."""

    def _copy_set(self, name: str) -> Path:
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        target = scratch / name
        shutil.copytree(REPO_ROOT / "content_sets" / name, target)
        return target

    def test_a_recipe_value_that_is_not_an_object_is_reported(self):
        """Found at boot now, because the validator asks the strict reader.

        The check is the backstop, not the first line: a recipe the loader cannot
        read fails `load_content_set`, so the server refuses to boot and this
        says so. Either way it is a finding rather than a pass.
        """
        target = self._copy_set("orbital_salvage")
        path = target / "data" / "crafting" / "fabrication.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["fabricate_broken"] = "this should have been an object"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

        messages = [str(finding) for finding in tool.check_one(target)]
        self.assertTrue(
            any("fabricate_broken" in message for message in messages),
            messages,
        )
        self.assertTrue(any(finding.fatal for finding in tool.check_one(target)))

    def test_an_authoring_note_is_not_reported_as_a_recipe(self):
        """`_`-prefixed keys are commentary in every loader in the engine."""
        target = self._copy_set("orbital_salvage")
        path = target / "data" / "crafting" / "fabrication.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_comment"] = "a note, not a recipe"
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.assertEqual([], [str(finding) for finding in tool.check_one(target)])

    def test_a_set_that_cannot_boot_is_a_finding_rather_than_a_crash(self):
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        broken = scratch / "broken_set"
        (broken / "data").mkdir(parents=True)
        (broken / "content_set.manifest.json").write_text("{ not json", encoding="utf-8")
        findings = tool.check_one(broken)
        self.assertTrue(findings)
        self.assertTrue(any(finding.command == "boot" for finding in findings), [str(f) for f in findings])


class TestDeclaredRecipes(unittest.TestCase):
    def _scratch_set(self, payload: dict) -> Path:
        scratch = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, scratch, ignore_errors=True)
        crafting = scratch / "data" / "crafting"
        crafting.mkdir(parents=True)
        (crafting / "recipes.json").write_text(json.dumps(payload), encoding="utf-8")
        return scratch

    def test_a_note_is_not_a_declared_recipe(self):
        target = self._scratch_set({"_comment": "note", "make_thing": {"name": "Make Thing"}})
        self.assertEqual({"make_thing"}, tool._declared_recipe_ids(target))

    def test_a_recipe_with_a_broken_value_still_counts_as_declared(self):
        target = self._scratch_set({"make_thing": "not an object"})
        self.assertEqual({"make_thing"}, tool._declared_recipe_ids(target))


if __name__ == "__main__":
    unittest.main()
