# tests/singles/test_social_contract.py
"""`ruleset.social`: the ladder a relationship climbs, declared or not.

`orbital_salvage` shipped without this section, so it silently rendered the
engine's defaults -- fantasy's tier names and a 15% discount nobody in that set
had chosen. That is the failure this file exists for, and it has two halves:

* **The section is checked now, where it never was.** A `tier` instead of `tiers`,
  a `min` that is a string, a gift category the engine does not score, a threshold
  repeated, or a ladder with no bottom rung all fall back to engine defaults
  silently today; each is an error here, because the author's belief that they
  configured something is the thing being protected.
* **The second theme says it out loud.** Orbital's ladder is its own words, its
  own numbers, and sized so the loop it actually has can reach the top.

The engine's *defaults* are legitimately fantasy-shaped -- they are what a set
that declares nothing gets -- so the defaults are not the bug. Rendering them for
a set whose author never saw them is.
"""

import json
import tempfile
import unittest
from pathlib import Path

from engine.server.content_set import _validate_social_rules
from engine.server.headless_server import HeadlessServer
from engine.social.relationships import (
    has_ladder,
    relationship_discount,
    relationship_tier,
    relationship_tiers,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
ORBITAL_SALVAGE = REPO_ROOT / "content_sets" / "orbital_salvage"
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
NIGHT_SHIFT = REPO_ROOT / "content_sets" / "night_shift"
MODERN_CAPSULE = REPO_ROOT / "content_sets" / "modern_capsule"


def _issues(social, required: bool = True):
    issues: list = []
    _validate_social_rules({"social": social}, issues, Path("ruleset.json"))
    return [issue.message for issue in issues]


class TestTheSectionIsValidated(unittest.TestCase):
    """Every silent fallback this section had, named."""

    def test_a_well_formed_section_reports_nothing(self):
        self.assertEqual([], _issues({
            "gift_values": {"ordinary": 1, "crafted": 5},
            "gift_tag_values": {"gem": 1},
            "tiers": [
                {"min": 60, "label": "Close Friend", "vendor_discount": 0.15},
                {"min": 0, "label": "Stranger", "vendor_discount": 0.0},
            ],
        }))

    def test_the_shipped_sets_are_well_formed(self):
        for content_set in (FANTASY_FRONTIER, ORBITAL_SALVAGE):
            with self.subTest(content_set=content_set.name):
                ruleset = json.loads((content_set / "rules" / "ruleset.json").read_text(encoding="utf-8"))
                issues: list = []
                _validate_social_rules(ruleset, issues, content_set / "rules" / "ruleset.json")
                self.assertEqual([], [i.message for i in issues])

    def test_an_unknown_key_is_reported_rather_than_ignored(self):
        """`tier` instead of `tiers` is the typo that made this check worth writing."""
        messages = _issues({"tier": [{"min": 0, "label": "Nobody"}]})
        self.assertTrue(any("social.tier is not a field the engine reads" in m for m in messages), messages)
        self.assertTrue(any("gift_tag_values, gift_values, tiers" in m for m in messages), messages)

    def test_an_underscore_key_is_an_authoring_comment_not_a_field(self):
        self.assertEqual([], _issues({"_comment": "why", "tiers": [{"min": 0, "label": "Nobody"}]}))

    def test_a_gift_category_the_engine_never_scores_is_reported(self):
        messages = _issues({"gift_values": {"ordinary": 1, "shiny": 3}})
        self.assertTrue(any("social.gift_values.shiny is not a gift category" in m for m in messages), messages)

    def test_gift_values_must_be_numbers(self):
        self.assertTrue(any("must be a number" in m for m in _issues({"gift_values": {"crafted": "lots"}})))
        self.assertTrue(any("must be a number" in m for m in _issues({"gift_values": {"crafted": True}})))
        self.assertEqual([], _issues({"gift_values": {"ordinary": 1, "disliked_item": -3}}))

    def test_gift_tag_values_map_a_tag_to_a_number(self):
        self.assertTrue(any("must map an item tag to a number" in m
                            for m in _issues({"gift_tag_values": {"gem": "plenty"}})))
        self.assertEqual([], _issues({"gift_tag_values": {"gem": 1, "scrap": -1}}))

    def test_tiers_must_be_a_list_of_objects(self):
        self.assertTrue(any("social.tiers must be a list" in m for m in _issues({"tiers": {"min": 0}})))
        self.assertTrue(any("tiers[1] must be an object" in m
                            for m in _issues({"tiers": [{"min": 0, "label": "A"}, "b"]})))

    def test_a_threshold_must_be_a_whole_number_of_points(self):
        for bad in ("60", 2.5, -1, True, None):
            with self.subTest(min=bad):
                messages = _issues({"tiers": [{"min": bad, "label": "A"}]})
                self.assertTrue(any("min must be a whole number" in m for m in messages), messages)

    def test_two_tiers_cannot_share_a_threshold(self):
        """One of them is unreachable, and which one is decided by sort order."""
        messages = _issues({"tiers": [
            {"min": 10, "label": "Friend"},
            {"min": 10, "label": "Also Friend"},
        ]})
        self.assertTrue(any("repeats 10" in m and "never be reached" in m for m in messages), messages)

    def test_a_tier_must_have_a_name_a_player_reads(self):
        for bad in ("", "   ", 7, None):
            with self.subTest(label=bad):
                messages = _issues({"tiers": [{"min": 0, "label": bad}]})
                self.assertTrue(any("label must be the name a player reads" in m for m in messages), messages)

    def test_a_discount_above_what_the_engine_honours_is_reported(self):
        """`relationship_discount` clamps at 0.95; a bigger number is quietly reduced."""
        messages = _issues({"tiers": [{"min": 0, "label": "A", "vendor_discount": 1.0}]})
        self.assertTrue(any("above the 0.95" in m for m in messages), messages)
        self.assertTrue(any("zero or more" in m
                            for m in _issues({"tiers": [{"min": 0, "label": "A", "vendor_discount": -0.5}]})))

    def test_a_ladder_with_no_bottom_rung_is_reported(self):
        """Every score under the lowest threshold would wear the engine's own label."""
        messages = _issues({"tiers": [{"min": 10, "label": "Known"}]})
        self.assertTrue(any("no tier at or below zero" in m for m in messages), messages)

    def test_social_must_be_an_object(self):
        self.assertTrue(any("social must be an object" in m for m in _issues(["tiers"])))

    def test_a_set_with_no_social_section_is_left_alone(self):
        issues: list = []
        _validate_social_rules({}, issues, Path("ruleset.json"))
        self.assertEqual([], [i.message for i in issues])

    def test_a_set_with_npcs_and_no_section_is_told_what_it_gives_up(self):
        """The warning that makes running without a ladder a choice.

        Scoped to sets that have an NPC at all: with nobody to have a relationship
        with, there is nothing to declare and a warning would be noise.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "npcs").mkdir()
            (root / "npcs" / "people.json").write_text("{}", encoding="utf-8")

            empty: list = []
            _validate_social_rules({}, empty, root / "ruleset.json", root, ["inventory"])
            self.assertEqual(1, len(empty), [i.message for i in empty])
            self.assertEqual("warning", empty[0].severity)
            self.assertIn("no bond surface", empty[0].message)
            self.assertIn("no vendor discount applies", empty[0].message)

            declared: list = []
            _validate_social_rules(
                {"social": {"tiers": [{"min": 0, "label": "Nobody"}]}},
                declared, root / "ruleset.json", root, ["social"],
            )
            self.assertEqual([], [i.message for i in declared])

    def test_a_set_with_no_npcs_gets_no_warning(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / "items").mkdir()
            issues: list = []
            _validate_social_rules({}, issues, root / "ruleset.json", root, [])
            self.assertEqual([], [i.message for i in issues])


class TestTheSecondThemeDeclaresIt(unittest.TestCase):
    """Orbital's ladder, in orbital's words, reachable in orbital's loop."""

    def setUp(self) -> None:
        self.server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(ORBITAL_SALVAGE),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(self.server.shutdown)
        self.world = self.server.world

    def test_the_top_tier_is_this_sets_own_word(self):
        self.assertEqual("Unvetted", relationship_tier(0, self.world))
        self.assertEqual("Known", relationship_tier(3, self.world))
        self.assertEqual("Trusted", relationship_tier(9, self.world))
        self.assertEqual("Crew", relationship_tier(18, self.world))
        self.assertNotIn("Close Friend", relationship_tier(100, self.world))

    def test_the_discounts_are_the_ones_it_declared(self):
        self.assertEqual(0.0, relationship_discount(0, self.world))
        self.assertEqual(0.05, relationship_discount(3, self.world))
        self.assertEqual(0.10, relationship_discount(9, self.world))
        self.assertEqual(0.15, relationship_discount(18, self.world))

    def test_the_ladder_is_reachable_by_the_loop_the_set_has(self):
        """A gate nobody can pass is a gate that does not exist.

        Measured against the set's own numbers rather than asserted: Ivo's salvage
        orders pay `relationship_amount`, and a patch kit the salvager crafted
        themselves is a `gift_values.crafted` gift. Whichever route a player takes,
        the top of the ladder has to be a handful of either -- that is the scale a
        four-room slice can carry.
        """
        from engine.social.relationships import relationship_rules

        top = max(
            tier["min"] for tier in relationship_rules(self.world)["tiers"]
        )
        crafted = int(relationship_rules(self.world).get("gift_values", {}).get("crafted", 0))
        self.assertGreater(crafted, 0, "a crafted gift has to be worth something")
        self.assertLessEqual(top, crafted * 4, "four crafted gifts should not fall short of the top")

        crew = json.loads((ORBITAL_SALVAGE / "data" / "npcs" / "crew.json").read_text(encoding="utf-8"))
        orders = crew["foreman_ivo"]["properties"]["buy_orders"]
        best_order = max(int(order.get("relationship_amount", 0)) for order in orders)
        self.assertGreater(best_order, 0, "the set's orders are one of the two routes")
        self.assertLessEqual(top, best_order * 6, "and six of the best order should reach the top")

    def test_a_fantasy_set_still_gets_its_own_ladder(self):
        """The two sets disagree, which is the point of the section existing."""
        fantasy = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(fantasy.shutdown)
        self.assertEqual("Close Friend", relationship_tier(60, fantasy.world))
        self.assertEqual("Stranger", relationship_tier(0, fantasy.world))
        self.assertEqual("Unvetted", relationship_tier(0, self.world))


class TestALadderIsRequired(unittest.TestCase):
    """No section means no bond surface -- not the engine's fantasy-shaped one.

    Before this, a set that never mentioned relationships rendered "Close Friend"
    and quietly took up to 15% off its own vendors' prices. A default that moves
    prices is not a default; it is a rule nobody declared.
    """

    def _server(self, content_set: Path) -> HeadlessServer:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(content_set),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        return server

    def test_a_set_with_no_ladder_has_no_tiers_and_no_discount(self):
        world = self._server(MODERN_CAPSULE).world
        self.assertEqual([], relationship_tiers(world))
        self.assertFalse(has_ladder(world))
        self.assertEqual("", relationship_tier(100, world))
        self.assertEqual(0.0, relationship_discount(100, world))

    def test_the_three_sets_that_declare_it_disagree_with_each_other(self):
        labels = {}
        for content_set in (FANTASY_FRONTIER, ORBITAL_SALVAGE, NIGHT_SHIFT):
            world = self._server(content_set).world
            labels[content_set.name] = relationship_tier(10_000, world)
            self.assertTrue(has_ladder(world), content_set.name)
        self.assertEqual(3, len(set(labels.values())), labels)
        self.assertNotIn("Close Friend", [labels["orbital_salvage"], labels["night_shift"]])

    def test_the_vendor_price_moves_by_exactly_the_declared_tier(self):
        """The discount is the set's number, applied at the set's threshold.

        Both sets that have a vendor *and* a ladder, because a discount that only
        works in the set it was written for is not a contract.
        """
        from engine.commands.mercantile import _get_price_multiplier
        from engine.social.relationships import relationship_key

        for content_set, vendor_id, top, top_discount, mid, mid_discount in (
            (ORBITAL_SALVAGE, "foreman_ivo", 18, 0.15, 9, 0.10),
            (NIGHT_SHIFT, "dana", 12, 0.12, 5, 0.07),
        ):
            with self.subTest(content_set=content_set.name):
                server = self._server(content_set)
                session = server.create_session(player_id="visitor")
                server.execute_command(session.session_id, "char create Visitor")
                player = server.get_player_for_session(session.session_id)
                vendor = next(npc for npc in server.world.npcs.values() if npc.template_id == vendor_id)

                player.npc_relationships[relationship_key(vendor)] = 0
                stranger = _get_price_multiplier(vendor, player)
                player.npc_relationships[relationship_key(vendor)] = top
                self.assertAlmostEqual(
                    stranger * (1.0 - top_discount), _get_price_multiplier(vendor, player), places=6,
                    msg="the top tier's declared discount",
                )
                player.npc_relationships[relationship_key(vendor)] = mid
                self.assertAlmostEqual(
                    stranger * (1.0 - mid_discount), _get_price_multiplier(vendor, player), places=6,
                    msg="and the middle tier's",
                )

    def test_a_set_without_a_ladder_never_discounts_its_vendor(self):
        from engine.commands.mercantile import _get_price_multiplier

        server = self._server(MODERN_CAPSULE)
        session = server.create_session(player_id="visitor")
        server.execute_command(session.session_id, "char create Avery")
        player = server.get_player_for_session(session.session_id)

        class _Vendor:
            properties: dict = {}
            obj_id = "counter"

        from engine.social.relationships import relationship_key
        player.npc_relationships[relationship_key(_Vendor())] = 100
        self.assertEqual(_get_price_multiplier(_Vendor(), player), _get_price_multiplier(_Vendor(), None))


class TestTheSurfaceAndTheLadderAreOneDecision(unittest.TestCase):
    def _issues(self, social, capabilities):
        issues: list = []
        _validate_social_rules(
            {"social": social} if social is not None else {},
            issues, Path("ruleset.json"), None, capabilities,
        )
        return [(i.severity, i.message) for i in issues]

    def test_presenting_the_surface_without_a_ladder_is_reported(self):
        """A warning, not an error: a scaffolded set inherits capabilities first.

        The engine degrades honestly -- the commands say this game tracks no bonds
        -- so this is a state to be told about rather than a world to refuse.
        """
        found = self._issues(None, ["inventory", "social"])
        self.assertTrue(any(sev == "warning" and "no `social` section" in msg for sev, msg in found), found)
        self.assertFalse(any(sev == "error" for sev, _ in found), found)

    def test_declaring_a_ladder_nobody_can_see_is_an_error(self):
        """The inverse is a declaration the engine ignores, so it is not a warning."""
        found = self._issues({"tiers": [{"min": 0, "label": "Nobody"}]}, ["inventory"])
        self.assertTrue(any(sev == "error" and "not the `social` capability" in msg for sev, msg in found), found)

    def test_capability_and_ladder_together_report_nothing(self):
        self.assertEqual([], self._issues({"tiers": [{"min": 0, "label": "Nobody"}]}, ["social"]))

    def test_the_commands_say_so_when_there_is_no_ladder(self):
        """Whatever the manifest claims, a set with no ladder tracks no bonds."""
        from engine.commands.interaction.use_give import relationship_handler, relationships_handler

        class _NoLadder:
            def ruleset_section(self, name):
                return {}

        context = {"world": _NoLadder(), "player": object()}
        self.assertIn("does not track bonds", relationship_handler(["Ivo"], context))
        self.assertIn("does not track bonds", relationships_handler([], context))

    def test_the_command_surface_is_gated_on_the_capability(self):
        """A set that presents no ladder does not offer a command that prints one."""
        def run(content_set: Path, command: str) -> str:
            server = HeadlessServer(
                db_path=":memory:",
                content_set_path=str(content_set),
                deterministic_test_mode=True,
                default_presentation_mode="player",
            )
            self.addCleanup(server.shutdown)
            session = server.create_session(player_id="visitor")
            server.execute_command(session.session_id, "char create Visitor")
            events = server.execute_command(session.session_id, command)
            return "\n".join(str(e.get("payload")) for e in events if e.get("type") == "text")

        self.assertIn("does not include the 'social' system", run(MODERN_CAPSULE, "relationships"))
        self.assertIn("does not include the 'social' system", run(MODERN_CAPSULE, "relationship someone"))
        self.assertNotIn("does not include", run(ORBITAL_SALVAGE, "relationships"))

    def test_a_gift_still_changes_hands_where_there_is_no_ladder(self):
        """The interaction is general; only the *bond* needs declaring."""
        from engine.items.item_factory import ItemFactory

        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(MODERN_CAPSULE),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        session = server.create_session(player_id="visitor")
        server.execute_command(session.session_id, "char create Avery")
        player = server.get_player_for_session(session.session_id)

        friend = next((npc for npc in server.world.npcs.values() if npc.friendly), None)
        self.assertIsNotNone(friend, "the slice has a friendly NPC to hand something to")
        # This set declares no starting kit, so the gift comes from its own item list.
        gift = ItemFactory.create_item_from_template("paper_cup", server.world)
        self.assertIsNotNone(gift, "the slice has something to give")
        added, message = player.inventory.add_item(gift, 1)
        self.assertTrue(added, message)

        text = "\n".join(
            str(e.get("payload"))
            for e in server.execute_command(session.session_id, "give paper cup to %s" % friend.template_id)
            if e.get("type") == "text"
        )
        self.assertIn("You give", text, "handing something over still works")
        self.assertNotIn("Relationship:", text, "and no bond is claimed for it")
        self.assertEqual({}, player.npc_relationships)


class TestWhatAPlayerSees(unittest.TestCase):
    def test_the_relationship_command_prints_the_sets_own_tier(self):
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(ORBITAL_SALVAGE),
            deterministic_test_mode=True,
            default_presentation_mode="player",
        )
        self.addCleanup(server.shutdown)
        session = server.create_session(player_id="salvager")
        server.execute_command(session.session_id, "char create Vess")
        events = server.execute_command(session.session_id, "relationship Ivo")
        text = "\n".join(str(e.get("payload")) for e in events if e.get("type") == "text")
        self.assertIn("Unvetted", text)
        self.assertNotIn("Stranger", text)


if __name__ == "__main__":
    unittest.main()
