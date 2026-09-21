# tests/singles/test_engine_vocabulary_dump.py
"""The dump the editor's parity check reads, held to its contract.

`toolkit/engine_vocabulary_dump.py` is the one place the editor's copies of the
engine's vocabularies are checked against the engine. Two properties make it
usable at all, and both have broken at least once in this project's history:

1. **One JSON object on stdout, and nothing else.** The editor parses the last
   balanced object in the output, so noise *after* the object is survivable and
   noise *inside* it is not -- but a dump that quietly gains a log line is how a
   consumer ends up parsing whatever it can find. Importing `engine.server`
   executes the headless runtime, which imports the command modules, whose startup
   logging landed on stdout ahead of the JSON. The module is loaded by path now,
   and this asserts the whole of stdout is the object.
2. **Read from the engine, not re-typed.** The manifest block exists so the
   editor's create-set flow can write a manifest the engine accepts. If the dump
   spelled those names out by hand it would be a third copy.

The editor half of the comparison needs Godot and lives in
`mud-world-editor/tests/schema_parity_smoke.gd`; this file is about the source.
"""
import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
DUMP_PATH = REPO_ROOT / "toolkit" / "engine_vocabulary_dump.py"


def _load_dump_module():
    """Loaded by path rather than by adding `toolkit/` to `sys.path`, which would
    change what every other test in the same process can import."""
    spec = importlib.util.spec_from_file_location("engine_vocabulary_dump", DUMP_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


dump_module = _load_dump_module()


def _run_dump() -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(DUMP_PATH)],
        cwd=str(REPO_ROOT), capture_output=True, text=True, errors="replace",
    )


class TestTheDumpIsOneObject(unittest.TestCase):
    def setUp(self):
        self.completed = _run_dump()

    def test_it_succeeds(self):
        self.assertEqual(0, self.completed.returncode, self.completed.stderr[-800:])

    def test_stdout_is_exactly_one_json_object(self):
        """Not "an object somewhere in the output" -- all of it."""
        text = self.completed.stdout
        self.assertTrue(text.strip(), "the dump printed nothing")
        payload = json.loads(text)
        self.assertIsInstance(payload, dict)
        self.assertNotIn("error", payload, payload.get("error", ""))

    def test_the_import_does_not_print_on_the_way_in(self):
        """Loading `engine.server` executes the runtime; its logging must not leak."""
        for noise in ("[INFO ]", "[DEBUG]", "Loading Command Modules"):
            self.assertNotIn(noise, self.completed.stdout, "the dump printed engine logging")

    def test_the_dump_exits_nonzero_and_says_so_when_the_engine_cannot_be_read(self):
        """The failure path is a reported error, not a traceback at the caller."""
        source = DUMP_PATH.read_text(encoding="utf-8")
        self.assertIn('print(json.dumps({"error": str(error)}))', source)
        self.assertIn("return 2", source)


class TestTheManifestBlockReadsTheEngine(unittest.TestCase):
    """The engine owns the manifest's shape; this is what the editor copies."""

    def setUp(self):
        self.manifest = json.loads(_run_dump().stdout)["manifest"]
        self.engine = dump_module._content_set_module()

    def test_it_names_the_engine_constant_for_every_field(self):
        self.assertEqual(self.engine.CONTENT_SET_MANIFEST_NAME, self.manifest["filename"])
        self.assertEqual(self.engine.CONTENT_SET_SCHEMA_VERSION, self.manifest["schema_version"])
        self.assertEqual(self.engine.RUNTIME_API_VERSION, self.manifest["runtime_api_version"])
        self.assertEqual(self.engine._CONTENT_SET_ID_PATTERN.pattern, self.manifest["id_pattern"])

    def test_the_lists_are_the_engines_lists(self):
        for key, attribute in (
            ("required_strings", "REQUIRED_MANIFEST_STRINGS"),
            ("required_paths", "REQUIRED_MANIFEST_PATHS"),
            ("optional_paths", "OPTIONAL_MANIFEST_PATHS"),
            ("required_start_fields", "REQUIRED_START_FIELDS"),
            ("required_data_directories", "_REQUIRED_DATA_DIRECTORIES"),
            ("capabilities", "_CAPABILITY_SYSTEMS"),
        ):
            with self.subTest(key=key):
                self.assertEqual(sorted(getattr(self.engine, attribute)), self.manifest[key])

    def test_the_loader_uses_the_same_constants_it_publishes(self):
        """A constant the loader does not read is a copy waiting to drift."""
        source = (REPO_ROOT / "server" / "engine" / "server" / "content_set.py").read_text(encoding="utf-8")
        for name in ("REQUIRED_MANIFEST_STRINGS", "REQUIRED_MANIFEST_PATHS",
                     "OPTIONAL_MANIFEST_PATHS", "REQUIRED_START_FIELDS"):
            self.assertGreaterEqual(
                source.count(name), 2,
                "%s is declared but the loader does not read it" % name,
            )

    def test_the_options_the_editor_already_used_are_still_present(self):
        """The vocabulary the parity check was built for must not regress."""
        payload = json.loads(_run_dump().stdout)
        self.assertEqual(17, len(payload["condition_kinds"]))
        self.assertEqual(15, len(payload["effect_keys"]))
        self.assertTrue(payload["objective_types"])
        self.assertEqual(4, len(payload["effect_fields"]))

    def test_exit_reciprocals_are_the_engine_mapping(self):
        """The editor must not invent a vertical pair such as climb <-> dive."""
        from engine.utils.utils import DIRECTION_OPPOSITES

        payload = json.loads(_run_dump().stdout)
        self.assertEqual(DIRECTION_OPPOSITES, payload["direction_opposites"])
        self.assertEqual("descend", payload["direction_opposites"]["climb"])
        self.assertEqual("surface", payload["direction_opposites"]["dive"])


if __name__ == "__main__":
    unittest.main()
