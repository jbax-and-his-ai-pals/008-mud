"""A small desktop launcher for the MUD: pick a content set, start a server, open a client.

    .venv/Scripts/python.exe toolkit/launcher.py

Standard library only (tkinter). From it you can:

* see every content set under `content_sets/` with its title, version and whether it
  validates (the same check `run_content_checks.py` uses; run in the background);
* start and stop a server for the selected set (TCP for the Godot client's default, or
  WebSocket), choosing the port, whether debug commands show, a fresh game or a throwaway
  one, and watch its output;
* play it in a terminal window instead (no Godot needed);
* open the Godot client, or the world editor, once you have told it where Godot is.

`--selftest` builds the window, starts a server for one set, checks it accepts a connection,
stops it and exits: a smoke check that the launcher itself works.
"""

from __future__ import annotations

import json
import os
import queue
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTENT_SETS = REPO / "content_sets"
SETTINGS = Path.home() / ".mud_launcher.json"
DEFAULT_PORT = 8765
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "server"))


def load_settings() -> dict:
    try:
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_settings(settings: dict) -> None:
    try:
        SETTINGS.write_text(json.dumps(settings, indent=2), encoding="utf-8")
    except OSError:
        pass


def content_sets() -> list[dict]:
    """Every folder under content_sets/ that has a manifest."""
    found = []
    for folder in sorted(CONTENT_SETS.iterdir()) if CONTENT_SETS.is_dir() else []:
        manifest = folder / "content_set.manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        found.append({
            "id": folder.name, "path": folder,
            "title": str(data.get("title", folder.name)), "version": str(data.get("version", "?")),
        })
    return found


def validate(path: Path) -> str:
    """'valid', or a short count of what is wrong. Never raises."""
    try:
        from toolkit import content_set_validator as validator

        _definition, issues = validator.load_content_set(path)
    except Exception as error:  # noqa: BLE001 - a launcher must not die on one bad set
        return "could not check (%s)" % type(error).__name__
    errors = sum(1 for issue in issues if issue.severity == "error")
    warnings = sum(1 for issue in issues if issue.severity == "warning")
    if errors:
        return "%d error%s" % (errors, "" if errors == 1 else "s")
    return "valid" + (" (%d warning%s)" % (warnings, "" if warnings == 1 else "s") if warnings else "")


def find_godot(saved: str = "") -> str:
    if saved and Path(saved).is_file():
        return saved
    try:
        import run_editor_checks

        return run_editor_checks.find_godot(None)
    except Exception:  # noqa: BLE001
        return ""


def port_open(port: int, host: str = "127.0.0.1") -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return True
    except OSError:
        return False


def server_command(set_path: Path, *, transport: str, port: int, mode: str, fresh: bool, ephemeral: bool) -> list[str]:
    script = "poc_server.py" if transport == "tcp" else "poc_ws_server.py"
    command = [
        sys.executable, "-u", str(REPO / "server" / script),
        "--content-set", str(set_path), "--presentation-mode", mode, "--port", str(port),
    ]
    if fresh:
        command.append("--new-game")
    if ephemeral:
        command.append("--ephemeral")
    return command


def stop_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


class Launcher:
    def __init__(self, root) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk, self.ttk = tk, ttk
        self.root = root
        root.title("MUD Launcher")
        root.geometry("900x640")
        self.settings = load_settings()
        self.sets = content_sets()
        self.process: subprocess.Popen | None = None
        self.lines: "queue.Queue[str]" = queue.Queue()
        self.status: dict[str, str] = {}
        self.results: "queue.Queue[tuple[str, str]]" = queue.Queue()   # worker threads never touch tkinter

        self.transport = tk.StringVar(value=self.settings.get("transport", "tcp"))
        self.port = tk.StringVar(value=str(self.settings.get("port", DEFAULT_PORT)))
        self.mode = tk.StringVar(value=self.settings.get("mode", "player"))
        self.fresh = tk.BooleanVar(value=False)
        self.ephemeral = tk.BooleanVar(value=False)
        self.state = tk.StringVar(value="Server stopped.")

        self._build()
        self._check_sets()
        self._poll()
        root.protocol("WM_DELETE_WINDOW", self._close)

    # -- layout ------------------------------------------------------------------------
    def _build(self) -> None:
        tk, ttk = self.tk, self.ttk
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="Content sets", font=("Segoe UI", 11, "bold")).pack(anchor="w")
        self.tree = ttk.Treeview(top, columns=("title", "version", "status"), show="tree headings", height=7)
        self.tree.heading("#0", text="Set")
        self.tree.heading("title", text="Title")
        self.tree.heading("version", text="Version")
        self.tree.heading("status", text="Check")
        self.tree.column("#0", width=190)
        self.tree.column("title", width=270)
        self.tree.column("version", width=80)
        self.tree.column("status", width=220)
        for entry in self.sets:
            self.tree.insert("", "end", iid=entry["id"], text=entry["id"],
                             values=(entry["title"], entry["version"], "checking..."))
        self.tree.pack(fill="x")
        last = self.settings.get("last_set")
        if last in {e["id"] for e in self.sets}:
            self.tree.selection_set(last)
        elif self.sets:
            self.tree.selection_set(self.sets[0]["id"])
        ttk.Button(top, text="Re-check sets", command=self._check_sets).pack(anchor="e", pady=(4, 0))

        options = ttk.LabelFrame(self.root, text="Server", padding=8)
        options.pack(fill="x", padx=8)
        ttk.Label(options, text="Transport").grid(row=0, column=0, sticky="w")
        ttk.Combobox(options, textvariable=self.transport, values=("tcp", "ws"), width=6, state="readonly").grid(row=0, column=1, padx=6)
        ttk.Label(options, text="Port").grid(row=0, column=2, sticky="w")
        ttk.Entry(options, textvariable=self.port, width=7).grid(row=0, column=3, padx=6)
        ttk.Label(options, text="Commands").grid(row=0, column=4, sticky="w")
        ttk.Combobox(options, textvariable=self.mode, values=("player", "test"), width=7, state="readonly").grid(row=0, column=5, padx=6)
        ttk.Checkbutton(options, text="Start a new game (discard the save)", variable=self.fresh).grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 0))
        ttk.Checkbutton(options, text="Keep nothing (no save)", variable=self.ephemeral).grid(row=1, column=4, columnspan=2, sticky="w", pady=(6, 0))

        buttons = ttk.Frame(self.root, padding=8)
        buttons.pack(fill="x")
        self.start_button = ttk.Button(buttons, text="Start server", command=self.start_server)
        self.start_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop server", command=self.stop_server, state="disabled")
        self.stop_button.pack(side="left", padx=4)
        ttk.Button(buttons, text="Play in a terminal", command=self.play_in_terminal).pack(side="left", padx=12)
        ttk.Button(buttons, text="Open Godot client", command=lambda: self.open_godot("client")).pack(side="left")
        ttk.Button(buttons, text="Open world editor", command=lambda: self.open_godot("mud-world-editor")).pack(side="left", padx=4)
        ttk.Button(buttons, text="Set Godot location...", command=self.pick_godot).pack(side="right")

        ttk.Label(self.root, textvariable=self.state, padding=(8, 0)).pack(anchor="w")
        self.log = tk.Text(self.root, height=16, state="disabled", wrap="none", background="#111", foreground="#ddd")
        self.log.pack(fill="both", expand=True, padx=8, pady=8)

    # -- content sets ------------------------------------------------------------------
    def _check_sets(self) -> None:
        for entry in self.sets:
            self.tree.set(entry["id"], "status", "checking...")

        def work() -> None:
            for entry in self.sets:
                self.results.put((entry["id"], validate(entry["path"])))

        threading.Thread(target=work, daemon=True).start()

    def selected(self) -> dict | None:
        chosen = self.tree.selection()
        return next((e for e in self.sets if chosen and e["id"] == chosen[0]), None)

    # -- server ------------------------------------------------------------------------
    def _port(self) -> int | None:
        try:
            value = int(self.port.get())
        except ValueError:
            return None
        return value if 1 <= value <= 65535 else None

    def start_server(self) -> None:
        entry, port = self.selected(), self._port()
        if entry is None:
            return self._say("Choose a content set first.")
        if port is None:
            return self._say("The port must be a number from 1 to 65535.")
        if self.process is not None and self.process.poll() is None:
            return self._say("A server is already running. Stop it first.")
        if port_open(port):
            return self._say("Port %d is already in use." % port)
        command = server_command(entry["path"], transport=self.transport.get(), port=port, mode=self.mode.get(),
                                 fresh=self.fresh.get(), ephemeral=self.ephemeral.get())
        env = dict(os.environ, PYTHONUNBUFFERED="1", PYGAME_HIDE_SUPPORT_PROMPT="1")
        self.process = subprocess.Popen(command, cwd=str(REPO), env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
        threading.Thread(target=self._pump, args=(self.process,), daemon=True).start()
        self.settings.update(last_set=entry["id"], transport=self.transport.get(), port=port, mode=self.mode.get())
        save_settings(self.settings)
        self.fresh.set(False)   # a new game is asked for once, not on every start
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        self.state.set("Starting %s on port %d..." % (entry["id"], port))
        self._say("$ " + " ".join(command))
        self.root.after(500, lambda: self._wait_ready(port, entry["id"], time.time()))

    def _pump(self, process: subprocess.Popen) -> None:
        assert process.stdout is not None
        for line in process.stdout:
            self.lines.put(line.rstrip("\n"))

    def _wait_ready(self, port: int, set_id: str, started: float) -> None:
        if self.process is None or self.process.poll() is not None:
            return
        if port_open(port):
            self.state.set("Server running: %s on 127.0.0.1:%d (%s). Connect a client to it." % (set_id, port, self.transport.get()))
        elif time.time() - started < 60:
            self.root.after(500, lambda: self._wait_ready(port, set_id, started))
        else:
            self.state.set("The server has not opened its port after 60 seconds; see the log.")

    def stop_server(self) -> None:
        if self.process is not None:
            stop_process(self.process)
        self._server_ended()

    def _server_ended(self) -> None:
        self.process = None
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")
        self.state.set("Server stopped.")

    def play_in_terminal(self) -> None:
        entry = self.selected()
        if entry is None:
            return self._say("Choose a content set first.")
        command = [sys.executable, str(REPO / "server" / "server_main.py"), "--content-set", str(entry["path"])]
        if self.fresh.get():
            command.append("--new-game")
        if self.ephemeral.get():
            command.append("--ephemeral")
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        subprocess.Popen(command, cwd=str(REPO), creationflags=flags)
        self._say("Opened a terminal for %s. Type: char create YourName" % entry["id"])

    # -- godot -------------------------------------------------------------------------
    def pick_godot(self) -> str:
        from tkinter import filedialog

        chosen = filedialog.askopenfilename(title="Godot executable")
        if chosen:
            self.settings["godot"] = chosen
            save_settings(self.settings)
        return chosen

    def open_godot(self, project: str) -> None:
        godot = find_godot(self.settings.get("godot", "")) or self.pick_godot()
        if not godot:
            return self._say("Godot was not found. Use 'Set Godot location...'.")
        subprocess.Popen([godot, "--path", str(REPO / project)], cwd=str(REPO))
        hint = " Connect to 127.0.0.1:%s." % self.port.get() if project == "client" else ""
        self._say("Opened %s in Godot.%s" % (project, hint))

    # -- log ---------------------------------------------------------------------------
    def _say(self, text: str) -> None:
        self.lines.put(text)

    def _poll(self) -> None:
        while True:
            try:
                set_id, verdict = self.results.get_nowait()
            except queue.Empty:
                break
            self.status[set_id] = verdict
            self.tree.set(set_id, "status", verdict)
        drained = False
        while True:
            try:
                line = self.lines.get_nowait()
            except queue.Empty:
                break
            drained = True
            self.log.config(state="normal")
            self.log.insert("end", line + "\n")
            self.log.config(state="disabled")
        if drained:
            self.log.see("end")
        if self.process is not None and self.process.poll() is not None:
            self._say("Server exited with code %s." % self.process.returncode)
            self._server_ended()
        self.root.after(200, self._poll)

    def _close(self) -> None:
        if self.process is not None:
            stop_process(self.process)
        self.root.destroy()


def selftest() -> int:
    import tkinter as tk

    root = tk.Tk()
    app = Launcher(root)
    sets = {entry["id"] for entry in app.sets}
    print("sets:", sorted(sets))
    if "zelda_slice" not in sets:
        print("FAIL zelda_slice missing")
        return 1
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
    app.tree.selection_set("zelda_slice")
    app.port.set(str(free))
    app.ephemeral.set(True)
    app.start_server()
    deadline = time.time() + 90
    ok = False
    while time.time() < deadline:
        root.update()
        if port_open(free):
            ok = True
            break
        time.sleep(0.2)
    print("server accepted a connection:", ok)
    app.stop_server()
    root.update()
    stopped = not port_open(free)
    print("server stopped:", stopped)
    root.destroy()
    return 0 if ok and stopped else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    import tkinter as tk

    root = tk.Tk()
    Launcher(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
