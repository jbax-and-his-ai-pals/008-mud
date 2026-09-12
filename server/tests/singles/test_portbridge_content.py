# tests/singles/test_portbridge_content.py
"""Coverage for the Portbridge population pass: NPC placement/roles,
the knowledge-topic-triggered campaign start, and the full
`portbridge_smugglers` campaign branching both ways -- against the real
loaded content, not a synthetic campaign definition (that's what
tests/current/test_campaign_branching.py already covers for the engine
mechanics in isolation)."""

from unittest.mock import patch

from tests.fixtures import GameTestBase
from engine.items.item_factory import ItemFactory


def _portbridge_npc(world, template_id):
    return next(n for n in world.npcs.values() if n.template_id == template_id)


class TestPortbridgePlacement(GameTestBase):
    def test_vendors_are_placed_and_flagged(self):
        for template_id, room_id in [
            ("portbridge_innkeeper", "sailors_rest_inn_common"),
            ("portbridge_fisherman", "fish_market"),
            ("portbridge_shipwright", "shipwright_yard"),
        ]:
            npc = _portbridge_npc(self.world, template_id)
            self.assertTrue(npc.properties.get("is_vendor"), f"{template_id} should be a vendor")
            self.assertEqual(room_id, npc.current_room_id)
            self.assertTrue(npc.properties.get("sells_items"))

    def test_harbourmaster_is_placed_and_not_a_vendor(self):
        voss = _portbridge_npc(self.world, "harbourmaster_voss")
        self.assertEqual("port_authority_office", voss.current_room_id)
        self.assertFalse(voss.properties.get("is_vendor"))

    def test_guards_are_flagged_and_one_patrols(self):
        guards = [n for n in self.world.npcs.values() if n.template_id == "portbridge_guard"]
        self.assertEqual(3, len(guards))
        for guard in guards:
            self.assertTrue(guard.properties.get("is_guard"))
        patrolling = [g for g in guards if g.behavior_type == "patrol"]
        self.assertEqual(1, len(patrolling))
        region = self.world.get_region("portbridge")
        for room_id in patrolling[0].patrol_points:
            self.assertIsNotNone(region.get_room(room_id))

    def test_tunnel_hostiles_are_placed(self):
        thugs = [n for n in self.world.npcs.values() if n.template_id == "smuggler_thug"]
        self.assertEqual(2, len(thugs))
        self.assertEqual({"smugglers_tunnel", "smugglers_crossroads"}, {t.current_room_id for t in thugs})

    def test_tunnel_thugs_can_drop_contraband(self):
        template = self.world.npc_templates["smuggler_thug"]
        self.assertIn("item_contraband_bundle", template["loot_table"])

    def test_smuggler_leader_template_is_a_repeatable_fence(self):
        template = self.world.npc_templates["smuggler_leader"]
        self.assertTrue(template["properties"].get("is_vendor"))
        orders = template["properties"].get("buy_orders", [])
        order = next(o for o in orders if o["id"] == "contraband_run")
        self.assertEqual("item_contraband_bundle", order["item_id"])
        self.assertTrue(order["repeatable"])
        self.assertGreater(order["relationship_min"], 0)


class TestSmugglingCampaignTrigger(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.current_region_id = "portbridge"
        self.player.current_room_id = "port_authority_office"

    def test_hint_topic_does_not_start_the_campaign(self):
        self.game.process_command("ask Voss about smuggling")
        self.assertNotIn("portbridge_smugglers", self.player.runtime_state.quests.active_campaigns)

    def test_investigation_topic_starts_the_campaign(self):
        self.game.process_command("ask Voss about smuggling")
        self.game.process_command("ask Voss about investigate")
        self.assertIn("portbridge_smugglers", self.player.runtime_state.quests.active_campaigns)
        self.assertEqual(
            "investigate_docks",
            self.player.runtime_state.quests.active_campaigns["portbridge_smugglers"]["current_node"],
        )
        self.assertTrue(any(
            k.startswith("quest_investigate_smuggling") for k in self.player.runtime_state.quests.active
        ))

    def test_investigation_topic_is_idempotent_once_active(self):
        self.game.process_command("ask Voss about smuggling")
        self.game.process_command("ask Voss about investigate")
        result = self.game.process_command("ask Voss about investigate")
        self.assertIn("You know what to do", result)
        self.assertEqual(1, len([
            k for k in self.player.runtime_state.quests.active if k.startswith("quest_investigate_smuggling")
        ]))


class _CampaignTestBase(GameTestBase):
    def setUp(self):
        super().setUp()
        self.player.current_region_id = "portbridge"
        self.player.current_room_id = "port_authority_office"
        self.game.process_command("ask Voss about smuggling")
        self.game.process_command("ask Voss about investigate")
        self.player.current_room_id = "underground_cache"
        self.world.quest_manager.handle_room_entry(self.player)
        self.player.current_room_id = "port_authority_office"
        self.game.process_command("talk Voss complete")
        self.player.current_room_id = "underground_cache"
        self.world.quest_manager.handle_room_entry(self.player)

    def _campaign_state(self):
        return self.player.runtime_state.quests.active_campaigns.get("portbridge_smugglers")


class TestSmugglingCampaignPeacefulPath(_CampaignTestBase):
    def test_negotiating_successfully_starts_the_delivery_quest(self):
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            result = self.game.process_command("talk smuggler leader complete")
        self.assertIn("Quest Complete", result)
        self.assertEqual("join_smugglers", self._campaign_state()["current_node"])
        self.assertTrue(any(
            k.startswith("quest_smuggler_delivery") for k in self.player.runtime_state.quests.active
        ))

    def test_delivering_the_cargo_ends_the_campaign_joined(self):
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            self.game.process_command("talk smuggler leader complete")
        cargo = ItemFactory.create_item_from_template("item_dubious_cargo", self.world)
        self.player.inventory.add_item(cargo)
        result = self.game.process_command("give dubious cargo to smuggler leader")
        self.assertIn("Quest Complete", result)
        self.assertIsNone(self._campaign_state())

    def test_delivering_the_cargo_unlocks_the_repeatable_fence_order(self):
        from engine.social.relationships import relationship_key
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            self.game.process_command("talk smuggler leader complete")
        cargo = ItemFactory.create_item_from_template("item_dubious_cargo", self.world)
        self.player.inventory.add_item(cargo)
        self.game.process_command("give dubious cargo to smuggler leader")

        leader = _portbridge_npc(self.world, "smuggler_leader")
        self.assertGreaterEqual(self.player.npc_relationships.get(relationship_key(leader), 0), 20)

        self.game.process_command("trade smuggler leader")
        for _ in range(2):
            bundle = ItemFactory.create_item_from_template("item_contraband_bundle", self.world)
            self.player.inventory.add_item(bundle)
            result = self.game.process_command("fulfill contraband_run")
            self.assertIn("Order fulfilled", result)

    def test_voss_dialogue_reflects_joining_the_smugglers(self):
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(True, "rolled well")):
            self.game.process_command("talk smuggler leader complete")
        cargo = ItemFactory.create_item_from_template("item_dubious_cargo", self.world)
        self.player.inventory.add_item(cargo)
        self.game.process_command("give dubious cargo to smuggler leader")
        self.player.current_room_id = "port_authority_office"
        result = self.game.process_command("ask Voss about smuggling")
        self.assertIn("slipped through my fingers", result)


class TestSmugglingCampaignViolentPath(_CampaignTestBase):
    def test_failing_negotiation_keeps_the_leader_alive_and_hostile(self):
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(False, "rolled poorly")):
            result = self.game.process_command("talk smuggler leader complete")
        self.assertIn("Negotiation FAIL", result)
        leader = _portbridge_npc(self.world, "smuggler_leader")
        self.assertTrue(leader.is_alive)
        self.assertEqual("confront_smugglers", self._campaign_state()["current_node"])

    def test_killing_the_leader_and_reporting_back_ends_the_campaign_busted(self):
        with patch("engine.core.skill_system.SkillSystem.attempt_check", return_value=(False, "rolled poorly")):
            self.game.process_command("talk smuggler leader complete")

        leader = _portbridge_npc(self.world, "smuggler_leader")
        self.player.stats["strength"] = 999
        self.player.runtime_state.combat.attack_power = 999
        # A real hit-chance roll lives in CombatSystem.execute_attack --
        # force every swing to land so this test doesn't depend on
        # leftover global `random` state from whatever ran before it.
        with patch("engine.core.combat_system.random.random", return_value=0.0):
            self.game.process_command("attack smuggler leader")
        self.assertFalse(leader.is_alive)

        self.player.current_room_id = "port_authority_office"
        result = self.game.process_command("talk Voss complete")
        self.assertIn("Quest Complete", result)
        self.assertIsNone(self._campaign_state())

        aftermath = self.game.process_command("ask Voss about smuggling")
        self.assertIn("owes you a debt", aftermath)
