import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path
import time
from unittest.mock import patch

from engine.core.clock import SimulatedClock
from engine.magic.spell_registry import get_spell
from engine.server.headless_server import HeadlessServer
from engine.player import Player
from engine.server.content_set import ContentSetIssue, GameContract, _validate_ambient_loot_references, _validate_collection_references, _validate_crafting_quality_contracts, _validate_discovery_references, _validate_item_extension_data, _validate_region_hazard_coverage, _validate_region_level_bands, _validate_resource_node_yields, _validate_ruleset_references, _validate_vendor_orders, load_content_set
from poc_server import JsonLineMudServer
from poc_ws_server import JsonWebSocketMudServer


REPO_ROOT = Path(__file__).resolve().parents[3]
FANTASY_FRONTIER = REPO_ROOT / "content_sets" / "fantasy_frontier"
MODERN_CAPSULE = REPO_ROOT / "content_sets" / "modern_capsule"


class TestContentSetRuntime(unittest.TestCase):
    def test_authored_board_relationship_gates_are_validated(self) -> None:
        issues: list[ContentSetIssue] = []
        _validate_ruleset_references(
            FANTASY_FRONTIER / "data",
            {"quest_generation": {"authored_board_templates": [
                {
                    "template_id": "quest_wildflower_commission",
                    "relationship_min": "ten",
                    "repeatable": {"delay_seconds": 0, "unavailable_text": ""},
                }
            ]}},
            issues,
            FANTASY_FRONTIER / "rules.json",
        )
        messages = [issue.message for issue in issues]
        self.assertTrue(any("relationship_min must be an integer from 0 to 100" in message for message in messages))
        self.assertTrue(any("repeatable.delay_seconds must be a positive number" in message for message in messages))
        self.assertTrue(any("repeatable.unavailable_text must be a non-empty string" in message for message in messages))

    def test_required_region_level_bands_and_spawn_ranges_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            regions = content_root / "regions"
            regions.mkdir()
            (regions / "missing.json").write_text(
                json.dumps({"region_id": "missing", "rooms": {}}), encoding="utf-8"
            )
            (regions / "misaligned.json").write_text(json.dumps({
                "region_id": "misaligned",
                "properties": {"level_band": {"min": 3, "max": 5}},
                "spawner": {"level_range": [2, 6]},
                "rooms": {},
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_region_level_bands(content_root, issues, required=True)

        messages = [issue.message for issue in issues]
        self.assertTrue(any("requires properties.level_band" in message for message in messages))
        self.assertTrue(any("spawner.level_range must stay inside" in message for message in messages))

    def test_required_region_hazard_coverage_and_schema_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            regions = content_root / "regions"
            combat = content_root / "combat"
            regions.mkdir()
            combat.mkdir()
            (combat / "elements.json").write_text(json.dumps({
                "hazards": {"mapping": {"cold": "ice", "heat": "fire"}},
            }), encoding="utf-8")
            (regions / "bad_hazard.json").write_text(json.dumps({
                "region_id": "bad_hazard",
                "rooms": {
                    "room": {
                        "properties": {
                            "hazard_type": "lightning",
                            "hazard_damage": 0,
                            "hazard_tick_interval": "often",
                        },
                    },
                },
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_region_hazard_coverage(content_root, issues, required=True)

        messages = [issue.message for issue in issues]
        self.assertTrue(any("uses unknown hazard_type 'lightning'" in message for message in messages))
        self.assertTrue(any("hazard 'cold'" in message for message in messages))
        self.assertTrue(any("hazard 'heat'" in message for message in messages))

    def test_hazard_timing_and_damage_must_be_positive_numbers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            regions = content_root / "regions"
            combat = content_root / "combat"
            regions.mkdir()
            combat.mkdir()
            (combat / "elements.json").write_text(json.dumps({
                "hazards": {"mapping": {"cold": "ice"}},
            }), encoding="utf-8")
            (regions / "invalid_values.json").write_text(json.dumps({
                "region_id": "invalid_values",
                "rooms": {
                    "room": {
                        "properties": {
                            "hazard_type": "cold",
                            "hazard_damage": 0,
                            "hazard_tick_interval": True,
                        },
                    },
                },
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_region_hazard_coverage(content_root, issues)

        messages = [issue.message for issue in issues]
        self.assertTrue(any("hazard_damage must be a positive number" in message for message in messages))
        self.assertTrue(any("hazard_tick_interval must be a positive number" in message for message in messages))

    def test_ambient_loot_references_are_validated(self) -> None:
        issues: list[ContentSetIssue] = []
        _validate_ambient_loot_references(
            FANTASY_FRONTIER / "data",
            {"loot": {"ambient_pools": [{
                "chance": 1.5,
                "npc_tags_any": "living",
                "entries": [{"item_id": "item_missing_gem", "weight": 0}],
            }]}},
            issues,
            FANTASY_FRONTIER / "rules.json",
        )
        messages = [issue.message for issue in issues]
        self.assertTrue(any("chance must be a number from 0 to 1" in message for message in messages))
        self.assertTrue(any("npc_tags_any must be an array" in message for message in messages))
        self.assertTrue(any("missing item template" in message for message in messages))
        self.assertTrue(any("weight must be a positive number" in message for message in messages))

    def test_collection_references_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            (content_root / "items").mkdir()
            (content_root / "items" / "items.json").write_text(json.dumps({"item_real": {}}), encoding="utf-8")
            (content_root / "collections.json").write_text(
                json.dumps({"gem_ledger": {"items": ["item_missing_gem", "item_missing_gem"], "rewards": []}}),
                encoding="utf-8",
            )
            issues: list[ContentSetIssue] = []
            _validate_collection_references(content_root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("must not contain duplicates" in message for message in messages))
        self.assertTrue(any("missing item template" in message for message in messages))
        self.assertTrue(any("rewards must be an object" in message for message in messages))

    def test_resource_node_yield_and_material_grade_contracts_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            (content_root / "items").mkdir()
            (content_root / "items" / "resources.json").write_text(json.dumps({
                "item_real": {},
                "node_bad": {"type": "ResourceNode", "properties": {
                    "resource_item_id": "item_missing",
                    "material_quality": {"id": "", "label": "", "score": 0},
                    "yield_table": [{"item_id": "item_missing", "chance": 2, "material_quality": "bad"}],
                    "substitute_resource_ids": "item_real",
                }},
                "node_bad_substitute": {"type": "ResourceNode", "properties": {
                    "resource_item_id": "item_real",
                    "substitute_resource_ids": ["item_missing_substitute"],
                }},
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_resource_node_yields(content_root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("resource_item_id references a missing item template" in message for message in messages))
        self.assertTrue(any("material_quality.id must be a non-empty string" in message for message in messages))
        self.assertTrue(any("chance must be a number from 0 to 1" in message for message in messages))
        self.assertTrue(any("material_quality must be an object" in message for message in messages))
        self.assertTrue(any("substitute_resource_ids must be an array" in message for message in messages))
        self.assertTrue(any("substitute_resource_ids references a missing item template" in message for message in messages))

    def test_crafting_quality_contributor_contract_is_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            (content_root / "items").mkdir(); (content_root / "crafting").mkdir()
            (content_root / "items" / "items.json").write_text(
                json.dumps({"item_real": {}}), encoding="utf-8",
            )
            (content_root / "crafting" / "recipes.json").write_text(json.dumps({
                "bad": {
                    "ingredients": [{
                        "item_id": "item_missing", "quality_contributes": "yes",
                        "alternatives": [{"item_id": "item_missing_alt", "quality_penalty": -1}],
                    }],
                    "quality_tiers": [{"min_crafts": 1, "min_material_quality": 2}],
                },
                "bad_alternatives_shape": {
                    "ingredients": [{"item_id": "item_real", "alternatives": "not_a_list"}],
                },
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_crafting_quality_contracts(content_root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("missing item template" in message for message in messages))
        self.assertTrue(any("quality_contributes must be a boolean" in message for message in messages))
        self.assertTrue(any("has no quality-contributing ingredient" in message for message in messages))
        self.assertTrue(any("alternatives[0].item_id references a missing item template" in message for message in messages))
        self.assertTrue(any("alternatives[0].quality_penalty must be a non-negative integer" in message for message in messages))
        self.assertTrue(any("alternatives must be an array" in message for message in messages))

    def test_attachment_extensions_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            (content_root / "items").mkdir()
            (content_root / "items" / "items.json").write_text(json.dumps({
                "item_host": {"properties": {"attachment_slots": ["ornament", "ornament"]}},
                "item_token": {"properties": {"attachment": {
                    "slot": "",
                    "modifiers": {"attack": "one", "stats": {"strength": "two"}},
                }}},
                "item_effect": {"properties": {"effect_type": "apply_effect", "effect_data": {
                    "name": "", "type": "stat_mod", "base_duration": 0,
                    "modifiers": {"": "many"},
                }}},
                "item_cleanse": {"properties": {"effect_type": "cleanse", "effect_tags": []}},
                "item_flask": {"properties": {"effect_type": "target_damage", "damage_amount": 0, "damage_type": ""}},
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_item_extension_data(content_root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("attachment_slots must not contain duplicates" in message for message in messages))
        self.assertTrue(any("attachment.slot must be a non-empty string" in message for message in messages))
        self.assertTrue(any("attachment.modifiers.attack must be a number" in message for message in messages))
        self.assertTrue(any("attachment.modifiers.stats must map stat names to numbers" in message for message in messages))
        self.assertTrue(any("effect_data.name must be a non-empty string" in message for message in messages))
        self.assertTrue(any("effect_data.base_duration must be a positive number" in message for message in messages))
        self.assertTrue(any("effect_data.modifiers must map stat names to numbers" in message for message in messages))
        self.assertTrue(any("effect_tags must be a non-empty array of tags" in message for message in messages))
        self.assertTrue(any("damage_amount must be a positive number" in message for message in messages))
        self.assertTrue(any("damage_type must be a non-empty string" in message for message in messages))

    def test_discovery_references_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            (content_root / "items").mkdir()
            (content_root / "items" / "items.json").write_text(json.dumps({"item_real": {}}), encoding="utf-8")
            (content_root / "discoveries.json").write_text(json.dumps({
                "bad_entry": {"name": "", "item_ids": ["item_missing", "item_missing"], "item_tags": []},
                "no_trigger": {"name": "No Trigger", "item_ids": [], "item_tags": []},
            }), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_discovery_references(content_root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("name must be a non-empty string" in message for message in messages))
        self.assertTrue(any("must not contain duplicates" in message for message in messages))
        self.assertTrue(any("missing item template" in message for message in messages))
        self.assertTrue(any("requires at least one" in message for message in messages))

    def test_vendor_orders_are_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            content_root = Path(temp_dir)
            (content_root / "items").mkdir(); (content_root / "npcs").mkdir()
            (content_root / "items" / "items.json").write_text(json.dumps({"item_real": {}}), encoding="utf-8")
            (content_root / "npcs" / "npcs.json").write_text(json.dumps({"trader": {"properties": {"buy_orders": [
                {"id": "bad", "item_id": "item_missing", "quantity": 0, "reward_gold": -1},
                {"id": "bad", "item_id": "item_real", "quantity": 1, "reward_gold": 1, "repeatable": "yes"},
            ]}}}), encoding="utf-8")
            issues: list[ContentSetIssue] = []
            _validate_vendor_orders(content_root, issues)
        messages = [issue.message for issue in issues]
        self.assertTrue(any("ids must be unique" in message for message in messages))
        self.assertTrue(any("missing item template" in message for message in messages))
        self.assertTrue(any("quantity must be" in message for message in messages))
        self.assertTrue(any("repeatable must be a boolean" in message for message in messages))

    def test_headless_server_requires_a_content_set(self) -> None:
        with self.assertRaisesRegex(ValueError, "content_set_path is required"):
            HeadlessServer(db_path=":memory:")

    def test_headless_server_boots_selected_content_set(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            self.assertIsNotNone(server.content_set)
            assert server.content_set is not None
            self.assertEqual("fantasy_frontier", server.content_set.content_set_id)
            self.assertEqual(FANTASY_FRONTIER / "data", Path(server.content_root))
            self.assertEqual(0, server.world.definition_load_stats["spell_registry"]["overwrites"])
            self.assertEqual(0, server.world.definition_load_stats["item_templates"]["invalid_missing_required"])
            self.assertEqual(2, server.world.definition_load_stats["item_templates"]["metadata_files_skipped"])
            session = server.create_session()
            server.execute_command(session.session_id, "char create ContentTester")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("town", player.current_region_id)
            self.assertEqual("town_square", player.current_room_id)
            # P4: a background owns the whole starting kit -- stats, gear,
            # spells, skills, recipes. With no background named at creation the
            # content set's declared default applies (fantasy_frontier sets
            # `_default: wanderer`), so these are the wanderer's item counts
            # rather than the ruleset's old generic starter kit. A content set
            # that defines no backgrounds still falls back to
            # `player_defaults.starting_inventory`.
            self.assertEqual("wanderer", player.background_id)
            # The wanderer's kit is authored, not generated: dagger in the
            # pack, two potions and a knife beside it. Nothing is granted
            # twice. Weapons ship *carried*, not equipped -- the first-ten-
            # minutes contract is that `inventory` shows what you own.
            self.assertIsNone(player.equipment["main_hand"])
            self.assertEqual(1, player.inventory.count_item("item_starter_dagger"))
            self.assertEqual(2, player.inventory.count_item("item_healing_potion_small"))
            self.assertEqual(1, player.inventory.count_item("item_foraging_knife"))
        finally:
            server.shutdown()

    def test_initial_population_waits_for_its_movement_cooldown(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
            clock=SimulatedClock(1234.5),
        )
        try:
            self.assertTrue(server.world.npcs)
            npc_movement_times = [npc.last_moved for npc in server.world.npcs.values()]
            self.assertTrue(all(value >= 1234.5 for value in npc_movement_times))
            self.assertTrue(any(value > 1234.5 for value in npc_movement_times))
        finally:
            server.shutdown()

    def test_first_world_tick_primes_initial_npc_cooldowns_from_simulation_start(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            server.world.clock.set(4321.0)
            server.world.update()
            self.assertTrue(server.world._simulation_has_started)
            self.assertTrue(all(npc.last_moved >= 4321.0 for npc in server.world.npcs.values()))
        finally:
            server.shutdown()
    def test_content_root_is_not_a_runtime_override(self) -> None:
        with self.assertRaises(TypeError):
            HeadlessServer(
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                content_root=str(REPO_ROOT / "server" / "data_fixtures"),
            )

    def test_fantasy_frontier_opening_journey(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="opening_journey_player")
            creation_events = server.execute_command(session.session_id, "char create Rowan")
            # P4: the creation line now names the background the character
            # began with, so a player can see what they got.
            created_line = next(
                (str(event["payload"]) for event in creation_events
                 if "Character created" in str(event["payload"])),
                "",
            )
            self.assertTrue(created_line.startswith("Character created: Rowan"), created_line)
            self.assertIn("Wanderer", created_line)
            self.assertIn("Welcome to Riverside", "\n".join(str(event["payload"]) for event in creation_events))
            self.assertIn("Elder Thorne", "\n".join(str(event["payload"]) for event in creation_events))
            self.assertIn("talk Elder Thorne", "\n".join(str(event["payload"]) for event in creation_events))
            self.assertIn("equip rusty dagger", "\n".join(str(event["payload"]) for event in creation_events))
            self.assertIn("Choose a first path", "\n".join(str(event["payload"]) for event in creation_events))
            self.assertIn("Talia", "\n".join(str(event["payload"]) for event in creation_events))

            look_events = server.execute_command(session.session_id, "look")
            self.assertIn("Town Square", "\n".join(str(event["payload"]) for event in look_events))

            nearby_events = server.execute_command(session.session_id, "nearby")
            self.assertIn("Elder Thorne", "\n".join(str(event["payload"]) for event in nearby_events))

            server.execute_command(session.session_id, "north")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("town", player.current_region_id)
            self.assertEqual("north_gate_road", player.current_room_id)
        finally:
            server.shutdown()

    def test_fantasy_frontier_merchant_schedule_targets_real_market_room(self) -> None:
        """Schedule slots resolve to a playable content location, not an alias."""
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            merchant = next(npc for npc in server.world.npcs.values() if npc.template_id == "merchant")
            work_entry = merchant.schedule["9"]

            self.assertEqual("town", work_entry["region_id"])
            self.assertEqual("market_square", work_entry["room_id"])
            self.assertIsNotNone(server.world.get_region(work_entry["region_id"]).get_room(work_entry["room_id"]))
        finally:
            server.shutdown()

    def test_forest_edge_authors_a_low_risk_stationary_encounter(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            rat = server.world.get_npc("forest_edge_lone_giant_rat")
            self.assertIsNotNone(rat)
            self.assertEqual("forest", rat.current_region_id)
            self.assertEqual("forest_edge", rat.current_room_id)
            self.assertEqual("stationary", rat.behavior_type)
            self.assertEqual(8, rat.health)
        finally:
            server.shutdown()
    def test_fantasy_frontier_hazards_are_runtime_active(self) -> None:
        """Every authored hazard resolves through the content-defined mapping."""
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(FANTASY_FRONTIER),
            deterministic_test_mode=True,
        )
        try:
            session = server.create_session(player_id="hazard_player")
            server.execute_command(session.session_id, "char create HazardTester")
            player = server.get_player_for_session(session.session_id)
            expected_hazards = {
                "extreme_heat": ("obsidian_trial", "inner_sanctum", 6, "intense heat"),
                "extreme_cold": ("mountains", "ice_cave_chamber", 5, "biting cold"),
                "poison_gas": ("caves", "mine_lower_level", 6, "toxic fumes"),
                "electrified_floor": ("coastal_path", "shipwreck_debris", 6, "Sparks"),
                "unholy_aura": ("ruins", "ritual_chamber", 4, "oppressive darkness"),
                "quicksand": ("swamp", "quicksand_pit", 4, "sucking mud"),
            }

            for hazard_type, (region_id, room_id, damage, flavor) in expected_hazards.items():
                with self.subTest(hazard_type=hazard_type):
                    room = server.world.get_region(region_id).get_room(room_id)
                    starting_health = player.health
                    message = room.apply_hazards(player, time.time())

                    self.assertEqual(hazard_type, room.get_property("hazard_type"))
                    self.assertEqual(damage, room.get_property("hazard_damage"))
                    self.assertLess(player.health, starting_health)
                    self.assertIn(flavor, message)
        finally:
            server.shutdown()
    def test_modern_capsule_is_a_playable_non_fantasy_slice(self) -> None:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(MODERN_CAPSULE),
            deterministic_test_mode=True,
        )
        try:
            self.assertIsNone(server.world.quest_manager)
            self.assertIsNone(server.world.campaign_manager)
            self.assertIsNone(server.crafting_manager)
            self.assertFalse(server.world.definition_load_stats["spell_registry"]["enabled"])

            session = server.create_session(player_id="modern_capsule_player")
            created = server.execute_command(session.session_id, "char create Avery")
            created_text = "\n".join(str(event["payload"]) for event in created)
            self.assertIn("A Connection Across Town", created_text)
            self.assertIn("Maya Chen", created_text)
            status_events = [event for event in created if event["type"] == "status"]
            self.assertEqual(1, len(status_events))
            self.assertNotIn("mana", status_events[0]["payload"])
            self.assertNotIn("level", status_events[0]["payload"])
            self.assertNotIn("experience", status_events[0]["payload"])
            player = server.get_player_for_session(session.session_id)
            self.assertIsNone(player.runtime_state.magic)
            self.assertIsNone(player.runtime_state.combat)
            self.assertIsNone(player.runtime_state.progression)
            self.assertIsNone(player.runtime_state.gold)
            self.assertIsNone(player.runtime_state.quests)
            self.assertEqual(0, player.inventory.get_total_weight())
            status_text = "\n".join(str(event["payload"]) for event in server.execute_command(session.session_id, "status"))
            self.assertNotIn("Attack:", status_text)
            self.assertNotIn("Defense:", status_text)
            self.assertNotIn("Class:", status_text)
            self.assertNotIn("Level:", status_text)
            self.assertNotIn("Stats:", status_text)
            self.assertNotIn("Gold:", status_text)
            help_text = "\n".join(str(event["payload"]) for event in server.execute_command(session.session_id, "help"))
            self.assertNotIn("skills", help_text)
            self.assertNotIn("trade", help_text)
            self.assertNotIn("journal", help_text)
            self.assertNotIn("accept quest", help_text)
            skills_events = server.execute_command(session.session_id, "skills")
            self.assertIn("does not include the 'progression' system", "\n".join(str(event["payload"]) for event in skills_events))
            combat_events = server.execute_command(session.session_id, "attack maya")
            self.assertIn("does not include the 'combat' system", "\n".join(str(event["payload"]) for event in combat_events))
            quest_events = server.execute_command(session.session_id, "accept quest 1")
            self.assertIn("does not include the 'quests' system", "\n".join(str(event["payload"]) for event in quest_events))

            conversation = server.execute_command(session.session_id, "talk maya")
            self.assertIn("Morning.", "\n".join(str(event["payload"]) for event in conversation))
            server.execute_command(session.session_id, "east")
            player = server.get_player_for_session(session.session_id)
            self.assertEqual("midtown", player.current_region_id)
            self.assertEqual("corner_cafe", player.current_room_id)
        finally:
            server.shutdown()

    def test_mixed_contracts_compose_only_their_declared_player_aspects(self) -> None:
        """Exercise optional systems independently rather than as a fantasy bundle."""
        modern_definition, modern_issues = load_content_set(MODERN_CAPSULE)
        fantasy_definition, fantasy_issues = load_content_set(FANTASY_FRONTIER)
        self.assertIsNotNone(modern_definition, modern_issues)
        self.assertIsNotNone(fantasy_definition, fantasy_issues)
        assert modern_definition is not None
        assert fantasy_definition is not None

        combat_contract = GameContract(
            progression_model="level_based",
            systems=tuple(sorted({
                "inventory": True, "dialogue": True, "combat": True, "magic": False,
                "crafting": False, "quests": False, "progression": True, "economy": False,
            }.items())),
            status_fields=("name", "health", "level", "experience"),
            ui_sections=("log", "nearby", "status", "inventory"),
        )
        combat_definition = replace(
            modern_definition,
            content_set_id="combat_without_magic",
            capabilities=("inventory", "dialogue", "combat"),
            game_contract=combat_contract,
        )
        with patch("engine.server.headless_server.load_content_set", return_value=(combat_definition, [])):
            combat_server = HeadlessServer(
                db_path=":memory:",
                content_set_path=str(MODERN_CAPSULE),
                deterministic_test_mode=True,
            )
        try:
            combat_session = combat_server.create_session(player_id="combat_only_player")
            combat_server.execute_command(combat_session.session_id, "char create Casey")
            combat_player = combat_server.get_player_for_session(combat_session.session_id)
            self.assertIsNotNone(combat_player.runtime_state.combat)
            self.assertIsNone(combat_player.runtime_state.magic)
            self.assertIsNotNone(combat_player.runtime_state.progression)
            self.assertIsNone(combat_player.runtime_state.gold)
            self.assertIsNone(combat_player.runtime_state.quests)
            combat_target = next(iter(combat_server.world.npcs.values()))
            combat_player.enter_combat(combat_target)
            self.assertTrue(combat_player.runtime_state.combat.in_combat)
            combat_player.exit_combat(combat_target)
            attack_result = combat_player.attack(combat_target, combat_server.world)
            self.assertIn("message", attack_result)
            leveled_up, _message = combat_player.gain_experience(1000)
            self.assertTrue(leveled_up)
            combat_player.die()
            self.assertFalse(combat_player.is_alive)
            combat_player.respawn()
            self.assertTrue(combat_player.is_alive)
            combat_server.execute_command(combat_session.session_id, "status")
            combat_server.tick(combat_session.session_id)
        finally:
            combat_server.shutdown()

        magic_contract = GameContract(
            progression_model="none",
            systems=tuple(sorted({
                "inventory": True, "dialogue": True, "combat": False, "magic": True,
                "crafting": False, "quests": False, "progression": False, "economy": False,
            }.items())),
            status_fields=("name", "health", "mana"),
            ui_sections=("log", "nearby", "status", "inventory"),
        )
        magic_definition = replace(
            fantasy_definition,
            content_set_id="magic_without_progression",
            capabilities=("inventory", "dialogue", "magic"),
            game_contract=magic_contract,
        )
        with patch("engine.server.headless_server.load_content_set", return_value=(magic_definition, [])):
            magic_server = HeadlessServer(
                db_path=":memory:",
                content_set_path=str(FANTASY_FRONTIER),
                deterministic_test_mode=True,
            )
        try:
            magic_session = magic_server.create_session(player_id="magic_only_player")
            # P4: the content set's default background (wanderer) starts with no
            # spells on purpose -- magic is learned in play from scrolls and
            # teachers, not handed out with the bedroll. This test is about
            # contract composition, so it names a background that does know one.
            magic_server.execute_command(magic_session.session_id, "char create Morgan as acolyte")
            magic_player = magic_server.get_player_for_session(magic_session.session_id)
            self.assertIsNotNone(magic_player.runtime_state.magic)
            self.assertIsNone(magic_player.runtime_state.combat)
            self.assertIsNone(magic_player.runtime_state.progression)
            self.assertIsNone(magic_player.runtime_state.gold)
            self.assertIsNone(magic_player.runtime_state.quests)
            status_text = "\n".join(
                str(event["payload"])
                for event in magic_server.execute_command(magic_session.session_id, "status")
            )
            self.assertIn("Mana:", status_text)
            self.assertNotIn("Level:", status_text)
            minor_heal = get_spell("minor_heal")
            self.assertIsNotNone(minor_heal)
            cast_result = magic_player.cast_spell(minor_heal, magic_player, time.time(), magic_server.world)
            self.assertTrue(cast_result["success"])
            saved_player = magic_player.to_dict(magic_server.world)
            self.assertEqual({"magic"}, set(saved_player["gameplay"]))
            restored_player = Player.from_dict(saved_player, magic_server.world)
            self.assertIsNotNone(restored_player.runtime_state.magic)
            self.assertIsNone(restored_player.runtime_state.progression)
        finally:
            magic_server.shutdown()

    def test_tcp_effective_settings_identify_content_set(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(FANTASY_FRONTIER),
        )
        try:
            content_set = app.effective_settings()["content_set"]
            self.assertEqual("fantasy_frontier", content_set["id"])
            self.assertEqual("town_square", content_set["start"]["room_id"])
        finally:
            app.shutdown()

    def test_transport_profile_presets_are_scoped_to_the_content_set(self) -> None:
        fantasy = JsonLineMudServer(
            "127.0.0.1", 0, "test_save.json", content_set_path=str(FANTASY_FRONTIER)
        )
        modern = JsonLineMudServer(
            "127.0.0.1", 0, "test_save.json", content_set_path=str(MODERN_CAPSULE)
        )
        try:
            self.assertIn("static_world", fantasy._list_profile_presets())
            self.assertEqual([], modern._list_profile_presets())
        finally:
            fantasy.shutdown()
            modern.shutdown()
    def test_modern_policy_publishes_non_fantasy_game_contract(self) -> None:
        app = JsonLineMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(MODERN_CAPSULE),
        )
        try:
            contract = app.build_server_policy_payload()["content_set"]["game_contract"]
            self.assertFalse(contract["systems"]["magic"])
            self.assertFalse(contract["systems"]["combat"])
            self.assertFalse(contract["systems"]["progression"])
            self.assertNotIn("mana", contract["status_fields"])
            self.assertNotIn("quests", contract["ui_sections"])
            self.assertIn("inventory", contract["ui_sections"])
        finally:
            app.shutdown()

    def test_websocket_policy_identifies_content_set(self) -> None:
        app = JsonWebSocketMudServer(
            "127.0.0.1",
            0,
            "test_save.json",
            content_set_path=str(FANTASY_FRONTIER),
        )
        try:
            content_set = app.core.build_server_policy_payload()["content_set"]
            self.assertEqual("fantasy_frontier", content_set["id"])
            self.assertEqual("town", content_set["start"]["region_id"])
        finally:
            app.shutdown()


if __name__ == "__main__":
    unittest.main()
