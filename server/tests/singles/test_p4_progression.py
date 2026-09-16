# tests/singles/test_p4_progression.py
"""P4 progression spine: the advancement ledger, titles, backgrounds, curve.

The model this replaces: XP came from kills and quests, the curve was hardcoded
at x1.5 and uncapped, identity was a class chosen once and unreachable from the
server, and several skill checks tested skills no player could raise.
"""

import unittest

from engine.conditions import evaluate, explain, KNOWN_KINDS
from engine.core.advancement import (
    DEFAULT_CURVE_MULTIPLIER,
    KIND_CREATURE,
    KIND_ITEM,
    KIND_LANDMARK,
    KIND_REGION,
    KNOWN_ENTRY_KINDS,
    AdvancementManager,
    entry_key,
    parse_entry_key,
)
from engine.core.backgrounds import BackgroundManager
from engine.core.titles import Title, TitleManager
from tests.fixtures import GameTestBase, make_test_server


class _FakeWorld:
    """Minimal world for manager unit tests: no server, no game."""

    def __init__(self, ruleset=None, content_root=None):
        self._ruleset = ruleset or {}
        self.content_root = content_root
        self.item_templates = {}

    def ruleset_section(self, name):
        # Mirrors World.ruleset_section: the named section within the ruleset,
        # not the whole ruleset. Returning the latter made every manager read an
        # empty config and silently author no rules at all.
        section = self._ruleset.get(name, {})
        return section if isinstance(section, dict) else {}


class TestCurve(unittest.TestCase):
    def test_default_multiplier_is_the_gentler_one(self):
        """x1.5 needed hundreds of regions to reach level 15 (WORLD_DESIGN 3.1)."""
        self.assertEqual(DEFAULT_CURVE_MULTIPLIER, 1.25)

    def test_curve_comes_from_content(self):
        world = _FakeWorld({"advancement": {"curve": {"base": 100, "multiplier": 1.25}}})
        manager = AdvancementManager(world)
        self.assertEqual(manager.xp_for_next_level(1), 100)
        self.assertEqual(manager.xp_for_next_level(2), 125)
        self.assertEqual(manager.xp_for_next_level(3), 156)

    def test_curve_is_tunable_without_a_code_change(self):
        gentle = AdvancementManager(_FakeWorld({"advancement": {"curve": {"base": 100, "multiplier": 1.2}}}))
        steep = AdvancementManager(_FakeWorld({"advancement": {"curve": {"base": 100, "multiplier": 1.5}}}))
        self.assertLess(gentle.xp_for_next_level(10), steep.xp_for_next_level(10))

    def test_cumulative_progress_matches_the_step_costs(self):
        manager = AdvancementManager(_FakeWorld({"advancement": {"curve": {"base": 100, "multiplier": 1.25}}}))
        total = 0
        for level in range(1, 8):
            self.assertEqual(manager.xp_to_reach_level(level), total)
            total += manager.xp_for_next_level(level)

    def test_bad_curve_values_are_reported_and_ignored(self):
        world = _FakeWorld({"advancement": {"curve": {"base": -5, "multiplier": 0.5}}})
        manager = AdvancementManager(world)
        self.assertEqual(manager.curve_base, 100)
        self.assertEqual(manager.curve_multiplier, DEFAULT_CURVE_MULTIPLIER)
        self.assertEqual(len(manager.issues), 2)


class TestLedger(unittest.TestCase):
    def _manager(self, grants=None, player=None):
        world = _FakeWorld({"advancement": {"curve": {"base": 100, "multiplier": 1.25},
                                            "grants": grants or []}})
        manager = AdvancementManager(world)
        return manager, player

    def test_first_time_pays_and_repeat_pays_nothing(self):
        player = _Player()
        manager, _ = self._manager(
            [{"id": "r", "match": {"kind": KIND_REGION}, "xp": 50}], player
        )
        player.world = manager.world
        manager.world.server = _ServerWith(manager)

        first = manager.record(player, KIND_REGION, "forest", payload={"region_id": "forest"})
        second = manager.record(player, KIND_REGION, "forest", payload={"region_id": "forest"})

        self.assertTrue(first.recorded)
        self.assertEqual(first.xp, 50)
        # The award reached the player, not just the ledger.
        self.assertEqual(player.runtime_state.progression.experience, 50)
        self.assertFalse(second.recorded)
        self.assertEqual(second.xp, 0)
        self.assertEqual(player.runtime_state.progression.experience, 50)

    def test_entries_are_recorded_even_when_no_rule_matches(self):
        """The journal should show where you have been, paid or not."""
        manager, _ = self._manager([])
        player = _Player()
        result = manager.record(player, KIND_REGION, "swamp", payload={"region_id": "swamp"})
        self.assertTrue(result.recorded)
        self.assertEqual(result.xp, 0)
        self.assertTrue(manager.has_entry(player, entry_key(KIND_REGION, "swamp")))

    def test_seed_records_without_paying_and_blocks_a_later_award(self):
        """Where you spawned is history, not an achievement.

        The starting region is seeded so the journal shows it and a later
        arrival cannot pay for it -- paying it handed every new character 90 of
        the 100 XP their first level costs before they had done anything.
        """
        player = _Player()
        manager, _ = self._manager(
            [{"id": "r", "match": {"kind": KIND_REGION}, "xp": 90}], player
        )
        player.world = manager.world
        manager.world.server = _ServerWith(manager)

        seeded = manager.seed(player, KIND_REGION, "town")
        again = manager.seed(player, KIND_REGION, "town")
        paid = manager.record(player, KIND_REGION, "town", payload={"region_id": "town"})

        self.assertTrue(seeded)
        self.assertFalse(again, "seeding twice should report nothing new")
        self.assertTrue(manager.has_entry(player, entry_key(KIND_REGION, "town")))
        self.assertFalse(paid.recorded)
        self.assertEqual(paid.xp, 0)
        self.assertEqual(player.runtime_state.progression.experience, 0)

    def test_entry_key_round_trips(self):
        kind, identifier = parse_entry_key(entry_key(KIND_ITEM, "item_rat_tail"))
        self.assertEqual(kind, KIND_ITEM)
        self.assertEqual(identifier, "item_rat_tail")

    def test_matching_can_narrow_by_item_type(self):
        manager, _ = self._manager([
            {"id": "gem", "match": {"kind": "item", "item_type": "Gem"}, "xp": 15},
        ])
        player = _Player()
        gem = manager.record(player, KIND_ITEM, "item_ruby", payload={"item_type": "Gem"})
        rock = manager.record(player, KIND_ITEM, "item_shiny_rock", payload={"item_type": "Junk"})
        self.assertEqual(gem.xp, 15)
        self.assertEqual(rock.xp, 0)

    def test_malformed_rule_is_reported_and_skipped(self):
        manager, _ = self._manager([
            {"id": "no_match_block", "xp": 10},
            {"id": "bad_xp", "match": {"kind": KIND_REGION}, "xp": "lots"},
            {"id": "unknown_kind", "match": {"kind": "not_a_kind"}, "xp": 10},
        ])
        self.assertEqual(len(manager.issues), 3)
        self.assertEqual(manager.grants, [])


    def test_legacy_discoveries_are_ingested_once(self):
        manager, _ = self._manager([])
        player = _Player()
        player.discoveries = {"rose_quartz": {"item_id": "item_rose_quartz"}}
        added = manager.ingest_legacy_discoveries(player)
        again = manager.ingest_legacy_discoveries(player)
        self.assertEqual(added, 1)
        self.assertEqual(again, 0)
        self.assertTrue(manager.has_entry(player, entry_key("discovery", "rose_quartz")))


class TestShippedAdvancementContent(GameTestBase):
    """The shipped content set's own advancement table must load cleanly.

    This is the guard that matters most: a rule whose `match.kind` does not
    match an engine entry kind is *rejected*, so a typo between the ruleset and
    the engine would silently pay nothing for that activity. Loading the real
    world is the only way to catch that.
    """

    def test_shipped_ruleset_loads_with_no_issues(self):
        manager = self.world.server.advancement_manager
        self.assertEqual(manager.issues, [], "advancement content has problems")

    def test_shipped_ruleset_uses_the_gentler_curve(self):
        manager = self.world.server.advancement_manager
        self.assertEqual(manager.curve_multiplier, 1.25)
        self.assertEqual(manager.curve_base, 100)

    def test_every_grant_rule_reaches_a_real_entry_kind(self):
        manager = self.world.server.advancement_manager
        self.assertTrue(manager.grants, "no grant rules loaded at all")
        kinds = {kind for rule in manager.grants for kind in rule.kinds}
        self.assertTrue(kinds, "no rules declared a kind")
        for kind in kinds:
            self.assertIn(kind, KNOWN_ENTRY_KINDS, "rule declares unknown kind %r" % kind)

    def test_every_kind_can_actually_be_earned(self):
        """Each granted kind must have something in the engine that records it.

        Guards against authoring XP for an activity nothing ever reports --
        which would look live in the ruleset and pay nothing in play.
        """
        manager = self.world.server.advancement_manager
        granted_kinds = {kind for rule in manager.grants for kind in rule.kinds}
        # Recorded by, respectively: change_room (region, landmark),
        # dispatch_event (creature), take (item), crafting (recipe),
        # learn_spell (spell), talk (npc), relationship tiers, quest
        # completion, collection completion, DiscoveryManager (discovery).
        recorded_by_engine = {
            KIND_REGION, KIND_LANDMARK, KIND_CREATURE, KIND_ITEM, "recipe",
            "spell", "npc", "relationship", "quest", "collection", "discovery",
        }
        self.assertTrue(
            granted_kinds <= recorded_by_engine,
            "granted but never recorded: %s" % (granted_kinds - recorded_by_engine),
        )

    def test_a_freshly_created_character_starts_at_zero_experience(self):
        """The end-to-end version of the seed rule, on the real server.

        Everything a character *begins* with -- the region they spawn in, and
        the recipes and spells in their background's kit -- is recorded in the
        journal but pays nothing. Paying it meant a wanderer started with 50 XP
        from two recipes nobody had taught them, on top of 90 for the town they
        spawned in: a whole first level for existing.

        Every background is checked, not just the default: the wandering kit
        was fine while the acolyte's spell quietly paid 30.
        """
        server = make_test_server()
        try:
            session = server.create_session(player_id="fresh_character")
            server.execute_command(session.session_id, "char create Rowan")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual(0, player.total_experience())
            self.assertTrue(server.advancement_manager.has_entry(player, entry_key(KIND_REGION, "town")))
        finally:
            server.shutdown()

        for background in ("wanderer", "labourer", "apprentice", "acolyte", "pedlar", "poacher"):
            with self.subTest(background=background):
                server = make_test_server()
                try:
                    session = server.create_session(player_id="fresh_%s" % background)
                    server.execute_command(
                        session.session_id, "char create Rowan as %s" % background
                    )
                    player = server.get_player_for_session(session.session_id)
                    self.assertEqual(background, player.background_id)
                    self.assertEqual(
                        0, player.total_experience(),
                        "background '%s' pays advancement XP for its own "
                        "starting kit" % background,
                    )
                finally:
                    server.shutdown()


class TestConditions(unittest.TestCase):
    def test_empty_condition_is_satisfied(self):
        self.assertTrue(evaluate(None, _Player()))
        self.assertTrue(evaluate({}, _Player()))

    def test_all_and_any_and_not(self):
        player = _Player()
        player.runtime_state.progression.level = 5
        self.assertTrue(evaluate({"all": [{"kind": "level_at_least", "value": 3}]}, player))
        self.assertFalse(evaluate({"all": [{"kind": "level_at_least", "value": 9}]}, player))
        self.assertTrue(evaluate({"any": [{"kind": "level_at_least", "value": 9},
                                           {"kind": "level_at_least", "value": 3}]}, player))
        self.assertTrue(evaluate({"not": {"kind": "level_at_least", "value": 9}}, player))
        self.assertFalse(evaluate({"not": {"kind": "level_at_least", "value": 3}}, player))

    def test_unknown_kind_fails_closed(self):
        """A content typo must not silently open a gate."""
        result = evaluate({"kind": "lvle_at_least", "value": 1}, _Player())
        self.assertFalse(result.satisfied)
        self.assertIn("lvle_at_least", result.unknown_kinds)

    def test_level_condition_reads_progression(self):
        player = _Player()
        player.runtime_state.progression.level = 7
        self.assertTrue(evaluate({"kind": "level_at_least", "value": 7}, player))
        self.assertFalse(evaluate({"kind": "level_at_least", "value": 8}, player))

    def test_spell_condition_reads_known_spells(self):
        player = _Player()
        player.runtime_state.magic.known_spells = {"minor_heal"}
        self.assertTrue(evaluate({"kind": "spell_known", "spell_id": "minor_heal"}, player))
        self.assertFalse(evaluate({"kind": "spell_known", "spell_id": "fireball"}, player))

    def test_flag_condition(self):
        player = _Player()
        self.assertFalse(evaluate({"kind": "flag", "flag": "met_king"}, player))
        player.flags = {"met_king": True}
        self.assertTrue(evaluate({"kind": "flag", "flag": "met_king"}, player))

    def test_every_known_kind_is_evaluable_without_raising(self):
        """A kind listed as known must actually be handled."""
        for kind in sorted(KNOWN_KINDS):
            with self.subTest(kind=kind):
                result = evaluate({"kind": kind}, _Player())
                self.assertNotIn(kind, result.unknown_kinds)

    def test_explain_names_the_missing_requirement(self):
        player = _Player()
        text = explain({"kind": "level_at_least", "value": 5}, player)
        self.assertIn("level", text.lower())

    def test_malformed_condition_node_is_refused(self):
        self.assertFalse(evaluate("just a string", _Player()).satisfied)


class TestTitles(unittest.TestCase):
    def _manager(self, titles):
        world = _FakeWorld(content_root=None)
        manager = TitleManager.__new__(TitleManager)
        manager.world = world
        manager.content_root = None
        manager.issues = []
        manager.titles = titles
        return manager

    def test_title_without_condition_is_available_to_everyone(self):
        manager = self._manager({"free": Title("free", "Free")})
        player = _Player()
        self.assertTrue(manager.has_earned("free", player))

    def test_title_requires_its_conditions(self):
        manager = self._manager({
            "veteran": Title("veteran", "Veteran",
                             condition={"kind": "level_at_least", "value": 5}),
        })
        player = _Player()
        self.assertFalse(manager.has_earned("veteran", player))
        player.runtime_state.progression.level = 5
        self.assertTrue(manager.has_earned("veteran", player))

    def test_requirements_combine_with_condition(self):
        manager = self._manager({
            "healer": Title("healer", "Healer",
                            condition={"kind": "level_at_least", "value": 2},
                            requirements=[{"kind": "spell_known", "spell_id": "minor_heal"}]),
        })
        player = _Player()
        player.runtime_state.progression.level = 5
        self.assertFalse(manager.has_earned("healer", player), "requirement was ignored")
        player.runtime_state.magic.known_spells = {"minor_heal"}
        self.assertTrue(manager.has_earned("healer", player))

    def test_sync_grants_then_revokes(self):
        """A falling-out should cost you the name."""
        manager = self._manager({
            "ally": Title("ally", "Ally", condition={"kind": "flag", "flag": "sworn"}),
        })
        player = _Player()
        player.flags = {"sworn": True}
        self.assertEqual(manager.sync(player), ["ally"])
        self.assertIn("ally", player.earned_titles)

        player.flags = {}
        self.assertEqual(manager.sync(player), [])
        self.assertNotIn("ally", player.earned_titles)

    def test_revoking_a_worn_title_clears_it(self):
        manager = self._manager({
            "ally": Title("ally", "Ally", condition={"kind": "flag", "flag": "sworn"}),
        })
        player = _Player()
        player.flags = {"sworn": True}
        manager.sync(player)
        player.active_title = "ally"
        player.flags = {}
        manager.sync(player)
        self.assertEqual(player.active_title, "")

    def test_cannot_wear_an_unearned_title(self):
        manager = self._manager({
            "ally": Title("ally", "Ally", condition={"kind": "flag", "flag": "sworn"}),
        })
        player = _Player()
        result = manager.set_active(player, "ally")
        self.assertIn("cannot claim", result.lower())

    def test_wearing_and_clearing_a_title(self):
        manager = self._manager({"free": Title("free", "Free")})
        player = _Player()
        self.assertIn("now known as", manager.set_active(player, "free").lower())
        self.assertEqual(player.active_title, "free")
        manager.set_active(player, "none")
        self.assertEqual(player.active_title, "")

    def test_title_is_mechanically_inert(self):
        """Wearing a title must not change any statistic."""
        manager = self._manager({"free": Title("free", "Free")})
        player = _Player()
        before = (dict(player.stats), player.max_health,
                  set(player.runtime_state.magic.known_spells))
        manager.set_active(player, "free")
        after = (dict(player.stats), player.max_health,
                 set(player.runtime_state.magic.known_spells))
        self.assertEqual(before, after)

    def test_earned_title_identifies_its_conferring_place(self):
        manager = self._manager({
            "hand": Title("hand", "Hand", guild_name="The Workward", guild_place="town:forge"),
        })
        player = _Player()
        manager.sync(player)
        status = manager.status(player)
        self.assertIn("The Workward", status)
        self.assertIn("town, forge", status)


class TestBackgrounds(unittest.TestCase):
    def test_real_content_loads_every_background(self):
        manager = BackgroundManager(_FakeWorld(
            content_root=r"C:\jbax-and-his-ai-pals\008-mud\content_sets\fantasy_frontier\data"
        ))
        self.assertEqual(manager.issues, [])
        ids = [b.background_id for b in manager.available()]
        for expected in ("wanderer", "labourer", "apprentice", "acolyte", "pedlar", "poacher"):
            self.assertIn(expected, ids)

    def test_authoring_comment_keys_are_skipped(self):
        manager = BackgroundManager(_FakeWorld(
            content_root=r"C:\jbax-and-his-ai-pals\008-mud\content_sets\fantasy_frontier\data"
        ))
        self.assertFalse([b for b in manager.backgrounds if b.startswith("_")])

    def test_resolves_by_id_and_display_name(self):
        manager = BackgroundManager(_FakeWorld(
            content_root=r"C:\jbax-and-his-ai-pals\008-mud\content_sets\fantasy_frontier\data"
        ))
        self.assertIsNotNone(manager.resolve("wanderer"))
        self.assertIsNotNone(manager.resolve("Wanderer"))
        self.assertIsNotNone(manager.resolve("pedlar"))
        self.assertIsNone(manager.resolve("necromancer"))

    def test_missing_content_falls_back_to_adventurer(self):
        manager = BackgroundManager(_FakeWorld(content_root=None))
        self.assertEqual(manager.default_background().name, "Adventurer")

    def test_no_background_grants_exclusive_content(self):
        """A background must not lock anything; it only decides where you start.

        Only the six core attributes are range-checked. `spell_power` and
        `magic_resist` are derived capability stats on a different scale, and a
        labourer having no spell power is a flavour choice, not a locked door --
        nothing stops that character learning magic later.
        """
        core_stats = ("strength", "dexterity", "constitution",
                      "agility", "intelligence", "wisdom")
        manager = BackgroundManager(_FakeWorld(
            content_root=r"C:\jbax-and-his-ai-pals\008-mud\content_sets\fantasy_frontier\data"
        ))
        for background in manager.available():
            with self.subTest(background=background.background_id):
                for stat in core_stats:
                    value = background.stats.get(stat)
                    self.assertIsNotNone(value, "%s is missing %s" % (background.background_id, stat))
                    self.assertLessEqual(
                        value, 16,
                        "%s.%s is a class in disguise" % (background.background_id, stat),
                    )
                    self.assertGreaterEqual(
                        value, 6,
                        "%s.%s is punitive" % (background.background_id, stat),
                    )

    def test_no_background_is_gated_behind_another(self):
        """Every background is offered to every new character."""
        manager = BackgroundManager(_FakeWorld(
            content_root=r"C:\jbax-and-his-ai-pals\008-mud\content_sets\fantasy_frontier\data"
        ))
        available = {b.background_id for b in manager.available()}
        self.assertEqual(len(available), len(manager.backgrounds),
                         "some backgrounds are unreachable")
        for background in manager.available():
            self.assertFalse(
                getattr(background, "requires", None),
                "%s requires something, so it is not a free starting choice" % background.background_id,
            )


class _ServerWith:
    def __init__(self, advancement_manager):
        self.advancement_manager = advancement_manager


class _Progress:
    def __init__(self):
        self.level = 1
        self.experience = 0
        self.experience_to_level = 100
        self.skills = {}
        self.player_class = ""


class _Magic:
    def __init__(self):
        self.known_spells = set()
        self.cooldowns = {}
        self.max_mana = 50
        self.mana = 50


class _Quests:
    def __init__(self):
        self.active = {}
        self.completed = {}
        self.archived = {}


class _Runtime:
    def __init__(self):
        self.progression = _Progress()
        self.magic = _Magic()
        self.quests = _Quests()
        self.gold = 0
        self.combat = None


class _Player:
    """A player with just enough surface for these units."""

    def __init__(self):
        self.obj_id = "p"
        self.name = "Tester"
        self.world = None
        self.runtime_state = _Runtime()
        self.stats = {"strength": 10, "dexterity": 10, "intelligence": 10,
                      "wisdom": 10, "constitution": 10, "agility": 10}
        self.max_health = 100
        self.health = 100
        self.discoveries = {}
        self.advancement_entries = set()
        self.earned_titles = set()
        self.active_title = ""
        self.background_id = ""
        self.flags = {}
        self.npc_relationships = {}
        self.inventory = _Inventory()
        self.known_recipe_ids = set()

    def gain_experience(self, amount):
        self.runtime_state.progression.experience += amount
        return False, ""

    def get_skill_level(self, skill):
        data = self.runtime_state.progression.skills.get(skill)
        return int(data.get("level", 0)) if isinstance(data, dict) else 0


class _Inventory:
    def count_item(self, item_id):
        return 0


if __name__ == "__main__":
    unittest.main()
