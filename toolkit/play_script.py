#!/usr/bin/env python3
"""Play a content set from a script and print what the player would read.

    python toolkit/play_script.py ff4_slice "wait 30" "take crystal" "waitq 45" "fight storm_wyvern,thunderhawk" where
    python toolkit/play_script.py ff4_slice --name Aldric --file route.txt

A step is a game command ("talk king", "reply 2") or one of:

    wait N          let N simulated seconds pass (scenes, fights and the clock run); print what was told
    waitq N         the same, silently
    fight A,B       attack whichever of these templates are alive until none are, silently
    where           print the region:room the player is in
    flags           print the player's story flags
    items           print the inventory

The character is created first (default name "Hero"). Colour markup is stripped. This is the harness the opening and
the story were checked with; the unit tests drive the same server, this one shows the text.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MUD_LOG_LEVEL", "WARNING")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
sys.path.insert(0, str(REPO_ROOT / "server"))

from engine.server.headless_server import HeadlessServer  # noqa: E402

MARKUP = re.compile(r"\[\[[^\]]*\]\]")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("content_set", help="a content set id (under content_sets/) or a path")
    parser.add_argument("steps", nargs="*")
    parser.add_argument("--file", help="read steps from a file, one per line (# starts a comment)")
    parser.add_argument("--name", default="Hero", help="the character's name")
    parser.add_argument("--debug", action="store_true", help="a test session: the debug commands (checkpoint, scene, level, tp...) are available")
    args = parser.parse_args()

    steps = list(args.steps)
    if args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                steps.append(line)

    path = Path(args.content_set)
    if not path.exists():
        path = REPO_ROOT / "content_sets" / args.content_set
    server = HeadlessServer(db_path=":memory:", content_set_path=str(path), deterministic_test_mode=True,
                            default_presentation_mode="test" if args.debug else "player")
    sid = server.create_session(player_id="p").session_id

    def show(text: str) -> None:
        text = MARKUP.sub("", text).strip()
        if text:
            print("  " + text.replace("\n", "\n  "))

    def texts(events) -> str:
        return "\n".join(str(event["payload"]) for event in events if event["type"] == "text")

    def command(text: str) -> None:
        print(">>", text)
        show(texts(server.execute_command(sid, text)))

    def wait(seconds: int, quiet: bool) -> None:
        for _ in range(seconds):
            server.world.clock.advance(1.0)
            told = texts(server.tick(sid) + server._flush_background_batch(sid))
            if told.strip() and not quiet:
                show(told)

    command("char create %s" % args.name)
    player = server.get_player_for_session(sid)
    for step in steps:
        word, _, rest = step.partition(" ")
        if word in ("wait", "waitq") and rest.strip().isdigit():
            print(">>", step)
            wait(int(rest), quiet=word == "waitq")
        elif word == "fight" and rest.strip():
            print(">>", step)
            names = {name.strip() for name in rest.split(",")}
            for _ in range(120):
                alive = [npc for npc in server.world.npcs.values() if npc.template_id in names and npc.is_alive]
                if not alive:
                    break
                server.execute_command(sid, "attack " + alive[0].name)
                wait(4, quiet=True)
        elif step == "where":
            print("-- at %s:%s  health %s/%s" % (player.current_region_id, player.current_room_id, player.health, player.max_health))
        elif step == "flags":
            print("-- flags:", {key: value for key, value in player.flags.items() if not key.startswith("_")})
        elif step == "items":
            print("-- items:", sorted(item.obj_id if hasattr(item, "obj_id") else str(item) for item in player.inventory.items.values()) if hasattr(player.inventory, "items") else player.inventory)
        else:
            command(step)
    return 0


if __name__ == "__main__":
    sys.exit(main())
