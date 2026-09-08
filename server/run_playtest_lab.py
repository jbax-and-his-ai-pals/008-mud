"""Run seeded headless player journeys as a background-friendly playtest lab."""

from __future__ import annotations

import argparse
from contextlib import nullcontext, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
from typing import Any


SERVER_ROOT = Path(__file__).resolve().parent
REPOSITORY_ROOT = SERVER_ROOT.parent
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

def _run_one(args: argparse.Namespace, seed: int, trace_directory: Path) -> dict[str, Any]:
    stdout_context = nullcontext() if args.verbose else redirect_stdout(io.StringIO())
    stderr_context = nullcontext() if args.verbose else redirect_stderr(io.StringIO())
    with stdout_context, stderr_context:
        return _run_one_quiet(args, seed, trace_directory)


def _run_one_quiet(args: argparse.Namespace, seed: int, trace_directory: Path) -> dict[str, Any]:
    # These imports initialize the command registry, which is intentionally
    # captured for normal background runs so stdout stays JSON-only.
    from engine.server.headless_server import HeadlessServer
    from tests.journey_runner import (
        ExplorerPolicy,
        FantasyFrontierCombatRoutePolicy,
        FantasyFrontierFirstSessionPolicy,
        FantasyFrontierFirstHourPolicy,
        FantasyFrontierOpportunityPolicy,
        FantasyFrontierPremiumMaterialPolicy,
        FantasyFrontierSystemSweepPolicy,
        JourneyRunner,
        MultiJourneyRunner,
        SessionReconnectFault,
        SimulatedCombatCadenceHook,
        fantasy_frontier_combat_route_outcome_checks,
        fantasy_frontier_first_hour_outcome_checks,
        fantasy_frontier_premium_material_outcome_checks,
        fantasy_frontier_opportunity_route_outcome_checks,
    )

    content_set = Path(args.content_set).resolve()
    with tempfile.TemporaryDirectory(prefix="mud_playtest_") as runtime_directory:
        server = HeadlessServer(
            db_path=":memory:",
            content_set_path=str(content_set),
            save_directory=runtime_directory,
            deterministic_test_mode=True,
        )
        try:
            hooks = [SessionReconnectFault(args.reconnect_at)] if args.reconnect_at else []
            policy_types = {
                "explorer": ExplorerPolicy,
                "combat": FantasyFrontierCombatRoutePolicy,
                "guided": FantasyFrontierFirstSessionPolicy,
                "first-hour": FantasyFrontierFirstHourPolicy,
                "opportunity": FantasyFrontierOpportunityPolicy,
                "premium": FantasyFrontierPremiumMaterialPolicy,
                "sweep": FantasyFrontierSystemSweepPolicy,
            }
            selected_policies = args.agent_policy or [args.policy] * args.agents
            if "combat" in selected_policies:
                hooks.append(SimulatedCombatCadenceHook())
            if args.agents > 1:
                report = MultiJourneyRunner(
                    server,
                    seed=seed,
                    agent_count=args.agents,
                    action_interval_s=args.action_interval,
                    policy_factory=policy_types[args.policy],
                    agent_policy_factories=[policy_types[policy_name] for policy_name in selected_policies],
                    hooks=hooks,
                ).run(args.duration)
            else:
                report = JourneyRunner(
                    server,
                    seed=seed,
                    player_name=f"Playtester {seed}",
                    action_interval_s=args.action_interval,
                    policy=policy_types[args.policy](),
                    hooks=hooks,
                    outcome_checks=(
                        fantasy_frontier_first_hour_outcome_checks()
                        if args.policy == "first-hour"
                        else fantasy_frontier_combat_route_outcome_checks()
                        if args.policy == "combat"
                        else fantasy_frontier_premium_material_outcome_checks()
                        if args.policy == "premium"
                        else fantasy_frontier_opportunity_route_outcome_checks()
                        if args.policy == "opportunity"
                        else []
                    ),
                ).run(args.duration)
            summary = {
                "seed": seed,
                "passed": report.passed,
                "steps": sum(len(steps) for steps in report.agents.values()) if args.agents > 1 else len(report.steps),
                "simulated_seconds": args.duration if args.agents > 1 else report.simulated_duration_s,
                "error_event_count": report.error_event_count,
                "gameplay_failure_count": report.gameplay_failure_count,
                "invariant_errors": report.invariant_errors,
                "outcome_errors": getattr(report, "outcome_errors", []),
                "agents": args.agents,
            }
            if args.keep_passing_traces or not report.passed:
                trace_path = trace_directory / f"journey_seed_{seed}.json"
                report.write_json(trace_path)
                summary["trace"] = str(trace_path)
            return summary
        finally:
            server.shutdown()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content-set", default=str(REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"))
    parser.add_argument("--policy", choices=("explorer", "combat", "guided", "first-hour", "opportunity", "premium", "sweep"), default="guided")
    parser.add_argument("--duration", type=float, default=1800.0, help="Simulated seconds per journey.")
    parser.add_argument("--action-interval", type=float, default=5.0, help="Simulated seconds per command.")
    parser.add_argument("--runs", type=int, default=1, help="Journeys per cycle.")
    parser.add_argument("--agents", type=int, default=1, help="Player-like agents sharing each journey world.")
    parser.add_argument("--agent-policy", choices=("explorer", "combat", "guided", "first-hour", "opportunity", "premium", "sweep"), action="append", default=[], help="Per-agent policy; repeat once per shared-world agent.")
    parser.add_argument("--seed", type=int, default=1, help="First seed; later runs increment it.")
    parser.add_argument("--reconnect-at", type=int, nargs="*", default=[], help="Journey steps that inject disconnect/resume.")
    parser.add_argument("--trace-dir", default=str(SERVER_ROOT / "tmp" / "playtest_lab"))
    parser.add_argument("--keep-passing-traces", action="store_true")
    parser.add_argument("--verbose", action="store_true", help="Keep engine diagnostic output instead of JSON-only summaries.")
    parser.add_argument("--repeat", type=int, default=1, help="Cycles to run; 0 repeats forever.")
    parser.add_argument("--sleep-seconds", type=float, default=0.0, help="Pause between cycles.")
    args = parser.parse_args(argv)
    if args.duration <= 0 or args.action_interval <= 0 or args.runs <= 0 or args.agents <= 0 or args.repeat < 0:
        parser.error("duration/action-interval/runs/agents must be positive and repeat cannot be negative")
    if args.agent_policy and (args.agents == 1 or len(args.agent_policy) != args.agents):
        parser.error("--agent-policy requires multiple agents and must appear once for each agent")

    trace_directory = Path(args.trace_dir).resolve()
    trace_directory.mkdir(parents=True, exist_ok=True)
    cycle = 0
    failed = False
    while args.repeat == 0 or cycle < args.repeat:
        summaries = [_run_one(args, args.seed + cycle * args.runs + offset, trace_directory) for offset in range(args.runs)]
        print(json.dumps({"cycle": cycle + 1, "runs": summaries}, sort_keys=True), flush=True)
        failed = failed or any(not summary["passed"] for summary in summaries)
        cycle += 1
        if args.sleep_seconds > 0 and (args.repeat == 0 or cycle < args.repeat):
            time.sleep(args.sleep_seconds)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
