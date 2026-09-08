"""Regression coverage for the deterministic long-form journey foundation."""

import json
import tempfile
import unittest
from pathlib import Path

from tests.fixtures import make_test_server
from tests.journey_runner import (
    CommandSequencePolicy,
    FantasyFrontierCombatRoutePolicy,
    FantasyFrontierFirstHourPolicy,
    FantasyFrontierFirstSessionPolicy,
    FantasyFrontierOpportunityPolicy,
    FantasyFrontierPremiumMaterialPolicy,
    FantasyFrontierSystemSweepPolicy,
    JourneyRunner,
    LocationVisitedOutcome,
    MultiJourneyRunner,
    SessionReconnectFault,
    SimulatedCombatCadenceHook,
    commands_from_trace,
    fantasy_frontier_first_hour_outcome_checks,
    fantasy_frontier_combat_route_outcome_checks,
    fantasy_frontier_premium_material_outcome_checks,
    fantasy_frontier_opportunity_route_outcome_checks,
    minimize_failing_commands,
)


class TestJourneyRunner(unittest.TestCase):
    def test_seeded_explorer_records_a_replayable_journey(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(server, seed=47, action_interval_s=5.0).run(duration_s=120.0)
            self.assertTrue(report.passed, report.invariant_errors)
            self.assertEqual(24, len(report.steps))
            self.assertEqual(120.0, report.simulated_duration_s)
            self.assertEqual("look", report.steps[0].command)
            self.assertTrue(any(step.command in {"north", "south", "east", "west"} for step in report.steps))
            self.assertTrue(all(step.location is not None for step in report.steps))
        finally:
            server.shutdown()

    def test_trace_export_is_json_and_captures_seed(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(server, seed=9).run(duration_s=10.0)
            with tempfile.TemporaryDirectory() as directory:
                trace_path = Path(directory) / "journey.json"
                report.write_json(trace_path)
                payload = json.loads(trace_path.read_text(encoding="utf-8"))
            self.assertEqual(9, payload["seed"])
            self.assertEqual(2, payload["step_count"])
            self.assertIn("steps", payload)
        finally:
            server.shutdown()

    def test_guided_first_session_reaches_quest_combat_and_vendor_commands(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=22,
                policy=FantasyFrontierFirstSessionPolicy(),
            ).run(duration_s=120.0)
            self.assertTrue(report.passed, report.invariant_errors)
            commands = [step.command for step in report.steps]
            for expected in ("accept quest 1", "attack giant rat", "cast minor heal", "trade talia"):
                self.assertIn(expected, commands)
        finally:
            server.shutdown()

    def test_system_sweep_reaches_crafting_gifting_and_relationship_commands(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(server, seed=23, policy=FantasyFrontierSystemSweepPolicy()).run(duration_s=180.0)
            self.assertTrue(report.passed, report.invariant_errors)
            commands = [step.command for step in report.steps]
            for expected in ("look board", "accept quest 1", "recipes all", "gather herb bed", "craft tie_wildflower_posy", "give wildflower posy to Elder Thorne", "relationship Elder Thorne"):
                self.assertIn(expected, commands)
        finally:
            server.shutdown()

    def test_first_hour_route_proves_its_authored_outcomes(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=24,
                policy=FantasyFrontierFirstHourPolicy(),
                outcome_checks=fantasy_frontier_first_hour_outcome_checks(),
            ).run(duration_s=200.0)
            self.assertTrue(report.passed, report.outcome_errors)
            self.assertEqual([], report.outcome_errors)
        finally:
            server.shutdown()

    def test_low_risk_combat_route_resolves_an_authored_encounter(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=26,
                policy=FantasyFrontierCombatRoutePolicy(),
                hooks=[SimulatedCombatCadenceHook()],
                outcome_checks=fantasy_frontier_combat_route_outcome_checks(),
            ).run(duration_s=90.0)
            self.assertTrue(report.passed, report.outcome_errors)
            self.assertIn("attack lone giant rat", [step.command for step in report.steps])
        finally:
            server.shutdown()

    def test_premium_material_route_proves_quality_aware_trade_and_delivery(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=27,
                policy=FantasyFrontierPremiumMaterialPolicy(),
                outcome_checks=fantasy_frontier_premium_material_outcome_checks(),
            ).run(duration_s=220.0)
            self.assertTrue(report.passed, report.outcome_errors)
            self.assertEqual([], report.outcome_errors)
            self.assertIn("fulfill river_fine_token", [step.command for step in report.steps])
        finally:
            server.shutdown()

    def test_opportunity_route_selects_social_economy_and_crafting_outlets(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=28,
                policy=FantasyFrontierOpportunityPolicy(),
                outcome_checks=fantasy_frontier_opportunity_route_outcome_checks(),
            ).run(duration_s=400.0)
            self.assertTrue(report.passed, report.outcome_errors)
            self.assertEqual([], report.outcome_errors)
        finally:
            server.shutdown()

    def test_outcome_checks_turn_an_unmet_route_goal_into_a_failed_report(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=25,
                policy=CommandSequencePolicy(["look"]),
                outcome_checks=[LocationVisitedOutcome("forest", "forest_edge", label="exploration route")],
            ).run(duration_s=5.0)
            self.assertFalse(report.passed)
            self.assertEqual(["exploration route: never reached forest/forest_edge"], report.outcome_errors)
        finally:
            server.shutdown()

    def test_trace_commands_replay_on_a_fresh_server(self) -> None:
        source_server = make_test_server()
        try:
            source = JourneyRunner(source_server, seed=71).run(duration_s=30.0)
            commands = commands_from_trace(source)
        finally:
            source_server.shutdown()

        replay_server = make_test_server()
        try:
            replay = JourneyRunner(replay_server, seed=71).run_commands(commands)
            self.assertTrue(replay.passed, replay.invariant_errors)
            self.assertEqual(commands, commands_from_trace(replay))
        finally:
            replay_server.shutdown()

    def test_minimizer_removes_irrelevant_commands(self) -> None:
        commands = ["look", "north", "inventory", "trigger", "south", "status"]
        minimized = minimize_failing_commands(commands, lambda trial: "trigger" in trial)
        self.assertEqual(["trigger"], minimized)

    def test_session_reconnect_fault_is_recorded_and_keeps_journey_valid(self) -> None:
        server = make_test_server()
        try:
            report = JourneyRunner(
                server,
                seed=33,
                hooks=[SessionReconnectFault([1, 3])],
            ).run(duration_s=25.0)
            self.assertTrue(report.passed, report.invariant_errors)
            self.assertEqual(["session_disconnect_resume"], report.steps[1].faults)
            self.assertEqual(["session_disconnect_resume"], report.steps[3].faults)
        finally:
            server.shutdown()

    def test_multi_agent_runner_interleaves_players_in_one_world(self) -> None:
        server = make_test_server()
        try:
            report = MultiJourneyRunner(server, seed=88, agent_count=2).run(duration_s=30.0)
            self.assertTrue(report.passed, report.invariant_errors)
            self.assertEqual({"agent_1", "agent_2"}, set(report.agents))
            self.assertEqual(6, len(report.agents["agent_1"]))
            self.assertEqual(6, len(report.agents["agent_2"]))
            self.assertEqual(2, len(server.world.players))
        finally:
            server.shutdown()

    def test_multi_agent_runner_accepts_distinct_agent_policies(self) -> None:
        server = make_test_server()
        try:
            report = MultiJourneyRunner(
                server,
                seed=89,
                agent_count=2,
                agent_policy_factories=[
                    lambda: CommandSequencePolicy(["look", "status"]),
                    lambda: CommandSequencePolicy(["inventory", "nearby"]),
                ],
            ).run(duration_s=10.0)
            self.assertTrue(report.passed, report.invariant_errors)
            self.assertEqual(["look", "status"], [step.command for step in report.agents["agent_1"]])
            self.assertEqual(["inventory", "nearby"], [step.command for step in report.agents["agent_2"]])
        finally:
            server.shutdown()

    def test_multi_agent_runner_applies_reconnect_fault_to_each_agent(self) -> None:
        server = make_test_server()
        try:
            report = MultiJourneyRunner(
                server,
                seed=99,
                agent_count=2,
                hooks=[SessionReconnectFault([1])],
            ).run(duration_s=15.0)
            self.assertTrue(report.passed, report.invariant_errors)
            self.assertEqual(["session_disconnect_resume"], report.agents["agent_1"][1].faults)
            self.assertEqual(["session_disconnect_resume"], report.agents["agent_2"][1].faults)
        finally:
            server.shutdown()
