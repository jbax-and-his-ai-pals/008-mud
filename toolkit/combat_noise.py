"""How noisy is a fight? Play one and count the lines the player is shown.

    python toolkit/combat_noise.py ff4_slice ashmere "go east" "go east"
    python toolkit/combat_noise.py ff4_slice pit --verbosity brief

Starts a debug session, jumps to a checkpoint, plays the given moves, then fights every hostile in the room
(the player strikes the nearest one) for up to `--seconds` of game time. The report is lines per ten seconds
(a line is a paragraph of text the player reads) and how many of them were combat. It is a measuring stick for
pacing and for the combat-detail setting, not a test of the story.
"""

import argparse
import os
import re
import sys
from pathlib import Path

os.environ.setdefault("MUD_LOG_LEVEL", "ERROR")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

from engine.server.headless_server import HeadlessServer  # noqa: E402
from engine.world import factions  # noqa: E402

MARKUP = re.compile(r"\[\[[^\]]*\]\]")
COMBAT = re.compile(r"\b(attacks?|hits?|misses|but misses|deals?|casts?|strikes?|defeated|falls|slain|dies|damage)\b", re.I)


def paragraphs(events):
    lines = []
    for event in events:
        if event["type"] == "text":
            text = MARKUP.sub("", str(event["payload"]))
            lines += [part.strip() for part in text.split("\n") if part.strip()]
    return lines


def play(content_set, checkpoint, moves, seconds, verbosity):
    server = HeadlessServer(db_path=":memory:", content_set_path=str(ROOT / "content_sets" / content_set),
                            deterministic_test_mode=True, default_presentation_mode="test")
    sid = server.create_session(player_id="noise").session_id
    server.execute_command(sid, "char create Hero")
    world, player = server.world, server.get_player_for_session(sid)
    server.execute_command(sid, "checkpoint " + checkpoint)
    if verbosity:
        server.execute_command(sid, "combat " + verbosity)

    def step():
        world.clock.advance(1.0)
        return paragraphs(server.tick(sid) + server._flush_background_batch(sid))

    for _ in range(5):
        step()
    for move in moves:
        server.execute_command(sid, move)
        for _ in range(3):
            step()

    per_second = []
    for _ in range(seconds):
        hostiles = factions.hostiles_in(world, player.current_region_id, player.current_room_id)
        if not hostiles or not player.is_alive:
            break
        if player.health < 0.4 * player.max_health:
            heard = paragraphs(server.execute_command(sid, "use potion"))
        elif player.can_attack(float(world.clock.now())):   # a player waits for the blow to be ready
            heard = paragraphs(server.execute_command(sid, "attack " + hostiles[0].name))
        else:
            heard = []
        per_second.append(heard + step())
    return per_second, [(npc.name, npc.health) for npc in factions.hostiles_in(world, player.current_region_id, player.current_room_id)]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("content_set")
    parser.add_argument("checkpoint")
    parser.add_argument("moves", nargs="*")
    parser.add_argument("--seconds", type=int, default=120)
    parser.add_argument("--verbosity", default="")
    parser.add_argument("--show", action="store_true", help="print what the player read")
    args = parser.parse_args()
    seconds, left = play(args.content_set, args.checkpoint, args.moves, args.seconds, args.verbosity)
    total = sum(len(lines) for lines in seconds)
    combat = sum(1 for lines in seconds for line in lines if COMBAT.search(line))
    print("fought %d s, %d lines (%d about combat), %d enemies left" % (len(seconds), total, combat, len(left)))
    for start in range(0, len(seconds), 10):
        window = seconds[start:start + 10]
        print("  %3d-%3d s  %3d lines" % (start, start + len(window), sum(len(lines) for lines in window)))
    if total and seconds:
        print("average %.2f lines a second, busiest ten seconds %d lines" % (
            total / len(seconds), max(sum(len(lines) for lines in seconds[i:i + 10]) for i in range(0, len(seconds), 10))))
    if args.show:
        for index, lines in enumerate(seconds):
            for line in lines:
                print("%3d| %s" % (index, line))


if __name__ == "__main__":
    main()
