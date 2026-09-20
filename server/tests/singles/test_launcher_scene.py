# tests/singles/test_launcher_scene.py
"""The launcher, its scene, and the keybindings the client reads at runtime.

Three small web-of-strings contracts that nothing else in either gate covers:

1. `launcher_controller.gd` reaches its nodes with absolute `$` paths. A node
   renamed in `launcher.tscn` is a runtime null, not a load error -- GDScript
   resolves `$Path` when the script runs, so this class of break is invisible
   until someone clicks the button.
2. The launcher writes launch parameters into `Engine` metadata and
   `main_controller.gd` reads them back. The two files agree on key names by
   convention only; a rename on one side silently drops the launch config.
3. `KeybindingsManager.ACTIONS` documents "every entry here must appear in
   keybindings_default.json" in a comment, and `tests/` had no keybindings test
   at all (the named file was 0 bytes).

These read the shipped files as text. That is the same approach
`test_operator_palette_contract.py` uses for `main_controller.gd`, and it is the
only way a Python gate can see GDScript at all.
"""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / "client"
LAUNCHER_SCENE = CLIENT / "scenes" / "launcher.tscn"
LAUNCHER_CONTROLLER = CLIENT / "scripts" / "ui" / "launcher_controller.gd"
MAIN_CONTROLLER = CLIENT / "scripts" / "ui" / "main_controller.gd"
KEYBINDINGS_MANAGER = CLIENT / "scripts" / "ui" / "keybindings_manager.gd"
KEYBINDINGS_DEFAULT = CLIENT / "data" / "keybindings_default.json"

# `@onready var x: T = $A/B/C` -- capture the declared type and the node path.
_ONREADY_NODE = re.compile(r"@onready\s+var\s+\w+\s*:\s*(\w+)\s*=\s*\$([\w/]+)")
_SCENE_NODE = re.compile(
    r'^\[node name="([^"]+)" type="([^"]+)"(?: parent="([^"]*)")?', re.MULTILINE
)


def _scene_paths(text: str) -> dict[str, str]:
    """Map `A/B/C` -> node type for every node declared in a .tscn."""
    nodes: dict[str, str] = {}
    for match in _SCENE_NODE.finditer(text):
        name, node_type, parent = match.group(1), match.group(2), match.group(3) or ""
        path = name if parent in ("", ".") else f"{parent}/{name}"
        nodes[path] = node_type
    return nodes


class TestLauncherControllerResolvesItsNodes(unittest.TestCase):
    """A `$Path` that names no node is a null dereference on the next click."""

    @classmethod
    def setUpClass(cls):
        cls.scene_nodes = _scene_paths(LAUNCHER_SCENE.read_text(encoding="utf-8"))
        cls.controller_text = LAUNCHER_CONTROLLER.read_text(encoding="utf-8")

    def test_the_scene_has_nodes_to_check(self):
        """Guard against the parse silently matching nothing and passing."""
        self.assertGreater(len(self.scene_nodes), 5)

    def test_every_onready_path_exists_in_the_scene(self):
        found = _ONREADY_NODE.findall(self.controller_text)
        self.assertGreater(len(found), 3, "the regex should find the launcher's @onready nodes")
        for node_type, path in found:
            with self.subTest(node=path):
                self.assertIn(path, self.scene_nodes, f"{path} is not a node in launcher.tscn")
                self.assertEqual(
                    node_type, self.scene_nodes[path],
                    f"{path} is a {self.scene_nodes[path]} in the scene, typed {node_type} in the script",
                )

    def test_the_typed_node_declarations_are_statically_typed(self):
        """A statically typed node is what makes a wrong path a visible mistake."""
        untyped = [
            line.strip() for line in self.controller_text.splitlines()
            if "@onready" in line and ":=" in line
        ]
        self.assertEqual([], untyped)


class TestLaunchMetadataIsAgreedOnBothSides(unittest.TestCase):
    """The launcher's writers and main_controller's readers must name the same keys."""

    LAUNCH_KEYS = ("launch_host", "launch_port", "launch_mode", "launch_auto_connect")

    @classmethod
    def setUpClass(cls):
        cls.launcher = LAUNCHER_CONTROLLER.read_text(encoding="utf-8")
        cls.main = MAIN_CONTROLLER.read_text(encoding="utf-8")

    def test_the_launcher_writes_exactly_the_documented_keys(self):
        written = set(re.findall(r'Engine\.set_meta\("([^"]+)"', self.launcher))
        self.assertEqual(set(self.LAUNCH_KEYS), written)

    def test_main_controller_reads_every_key_the_launcher_writes(self):
        read = set(re.findall(r'Engine\.has_meta\("([^"]+)"', self.main))
        for key in self.LAUNCH_KEYS:
            with self.subTest(key=key):
                self.assertIn(key, read, f"main_controller never reads {key}")

    def test_main_controller_consumes_each_key_so_a_restart_is_clean(self):
        """`_apply_launch_config` documents that every key is removed as it is read."""
        for key in self.LAUNCH_KEYS:
            with self.subTest(key=key):
                self.assertIn(f'Engine.remove_meta("{key}")', self.main)

    def test_the_launcher_transitions_to_a_scene_that_exists(self):
        """The target is a `const`, so resolve the constant rather than the literal."""
        constants = dict(re.findall(r'const\s+(\w+)\s*:=\s*"(res://[^"]+)"', self.launcher))
        targets = re.findall(r"change_scene_to_file\(([^)]+)\)", self.launcher)
        self.assertGreater(len(targets), 0, "the launcher should transition somewhere")
        for target in targets:
            resolved = constants.get(target, target).strip('"')
            with self.subTest(target=target):
                self.assertTrue(resolved.startswith("res://"),
                                f"{target} is neither a res:// literal nor a known constant")
                self.assertTrue((CLIENT / resolved.removeprefix("res://")).exists(),
                                f"{resolved} does not exist")

    def test_the_launcher_scene_root_matches_the_script(self):
        """`launcher_controller.gd` extends Control; the root node must match.

        The first line of a .tscn is `[gd_scene ...]`; the root node is the one
        declared with no `parent=`.
        """
        scene = LAUNCHER_SCENE.read_text(encoding="utf-8")
        self.assertIn("extends Control", self.launcher)
        roots = [
            match.group(1) for match in re.finditer(
                r'^\[node name="([^"]+)" type="([^"]+)"\]', scene, re.MULTILINE
            )
        ]
        self.assertEqual(["Launcher"], roots, "exactly one parentless root node is expected")
        self.assertIn('type="Control"', scene)


class TestKeybindingsDefaultsMatchTheManager(unittest.TestCase):
    """`ACTIONS` claims every entry appears in the bundled JSON. Check it."""

    @classmethod
    def setUpClass(cls):
        cls.manager = KEYBINDINGS_MANAGER.read_text(encoding="utf-8")
        cls.defaults = json.loads(KEYBINDINGS_DEFAULT.read_text(encoding="utf-8"))

    def _declared_actions(self) -> list[str]:
        block = re.search(r"const ACTIONS:\s*PackedStringArray\s*=\s*\[(.*?)\]",
                          self.manager, re.DOTALL)
        self.assertIsNotNone(block, "ACTIONS should be a PackedStringArray literal")
        return re.findall(r'"([^"]+)"', block.group(1))

    def test_every_declared_action_is_present_in_the_bundled_defaults(self):
        bundled = set(self.defaults.get("bindings", {}))
        declared = self._declared_actions()
        self.assertGreater(len(declared), 0)
        for action in declared:
            with self.subTest(action=action):
                self.assertIn(action, bundled, f"{action} has no entry in keybindings_default.json")

    def test_the_defaults_declare_nothing_the_manager_would_ignore(self):
        """`_apply_config` skips unknown actions, so a typo there is silently dropped."""
        declared = set(self._declared_actions())
        for action in self.defaults.get("bindings", {}):
            with self.subTest(action=action):
                self.assertIn(action, declared, f"{action} is in the JSON but not in ACTIONS")

    def test_the_config_version_agrees(self):
        declared = re.search(r"const CONFIG_VERSION\s*:=\s*(\d+)", self.manager)
        self.assertIsNotNone(declared)
        self.assertEqual(int(declared.group(1)), self.defaults.get("version"))

    def test_the_key_names_in_the_defaults_are_all_recognised(self):
        """An unrecognised name makes `_apply_config` discard the whole entry."""
        block = re.search(r"const KEY_NAME_MAP:\s*Dictionary\s*=\s*\{(.*?)\n\}",
                          self.manager, re.DOTALL)
        self.assertIsNotNone(block)
        known = set(re.findall(r'"([^"]+)"\s*:', block.group(1)))
        self.assertIn("Up", known, "KEY_NAME_MAP should include the arrow keys")
        for action, entry in self.defaults.get("bindings", {}).items():
            for name in entry.get("keys", []):
                with self.subTest(action=action, key=name):
                    self.assertIn(name, known, f"'{name}' is not in KEY_NAME_MAP")

    def test_every_default_entry_carries_a_description_for_keybind_list(self):
        """`keybind list` prints `[description]`; an empty one prints empty brackets."""
        for action, entry in self.defaults.get("bindings", {}).items():
            with self.subTest(action=action):
                self.assertTrue(str(entry.get("description", "")).strip())


if __name__ == "__main__":
    unittest.main()
