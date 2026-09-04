import argparse
import asyncio
import json


async def read_events(reader: asyncio.StreamReader) -> None:
    while True:
        line = await reader.readline()
        if not line:
            print("Disconnected from server.")
            return
        try:
            event = json.loads(line.decode("utf-8", errors="replace"))
            print(json.dumps(event, indent=2))
        except json.JSONDecodeError:
            print(line.decode("utf-8", errors="replace").rstrip())


async def input_loop(writer: asyncio.StreamWriter) -> None:
    loop = asyncio.get_running_loop()
    while True:
        text = await loop.run_in_executor(None, input, "> ")
        cmd = text.strip()
        if not cmd:
            continue
        if cmd.lower() in {"quit", "exit"}:
            writer.write((json.dumps({"type": "disconnect"}) + "\n").encode("utf-8"))
            await writer.drain()
            return
        envelope = {
            "type": "command",
            "session_id": "client_will_be_ignored",
            "command_text": cmd,
            "client_capabilities": {"rich_text": False},
        }
        writer.write((json.dumps(envelope) + "\n").encode("utf-8"))
        await writer.drain()


async def main_async(host: str, port: int) -> None:
    reader, writer = await asyncio.open_connection(host, port)
    try:
        await asyncio.gather(read_events(reader), input_loop(writer))
    finally:
        writer.close()
        await writer.wait_closed()


def main() -> None:
    parser = argparse.ArgumentParser(description="PoC TCP JSON-line MUD client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    asyncio.run(main_async(args.host, args.port))


if __name__ == "__main__":
    main()

