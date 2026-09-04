import argparse
import json

from engine.server import HeadlessServer


def main() -> None:
    parser = argparse.ArgumentParser(description="Headless MUD server spike")
    parser.add_argument("--save", "-s", default="server_save.json", help="Save file name")
    parser.add_argument("--content-set", default=None, help="Content-set directory or manifest path")
    args = parser.parse_args()

    server = HeadlessServer(save_file=args.save, content_set_path=args.content_set)
    session = server.create_session()
    print(json.dumps({"type": "info", "payload": f"session={session.session_id}"}))

    # Simple stdin command loop for local smoke usage.
    while True:
        try:
            text = input("> ").strip()
        except EOFError:
            break
        if not text:
            continue
        if text.lower() in {"quit", "exit"}:
            break
        for event in server.execute_command(session.session_id, text):
            print(json.dumps(event))


if __name__ == "__main__":
    main()
