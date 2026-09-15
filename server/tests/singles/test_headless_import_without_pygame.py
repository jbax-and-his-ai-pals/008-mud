"""Tripwire: the headless server and command registry must import without
pygame installed.

`engine/utils/text_formatter.py` did `import pygame` at module scope for the
sake of four type annotations (plus one real runtime use inside `render()`,
the one method that actually touches a live pygame surface and so can only
ever be called by client code that already has pygame). That module is
imported transitively by `engine/utils/utils.py`, which `engine/items/
container.py` and `engine/server/headless_server.py` both import directly --
so a genuinely headless environment without pygame installed could not even
construct a `HeadlessServer`, and `engine/commands/__init__.py`'s loader
(which logs an ImportError and moves on rather than failing loudly) silently
dropped inventory, locksmithing, magic, mercantile, quest, crafting,
gathering, interaction, and debug from the command registry with no visible
error to a player or operator.

Two checks: a fast, precise AST scan of the one file this actually came from
(so a regression there fails immediately with a clear message), and a
subprocess probe that proves the real import chain works with pygame
genuinely unavailable -- run in a fresh interpreter rather than by patching
`sys.modules` in-process, since this test suite's own process has already
imported the real pygame and polluting that for every other test would be
worse than what it is trying to catch.
"""

import ast
import pathlib
import subprocess
import sys
import unittest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
SERVER_ROOT = REPOSITORY_ROOT / "server"
TEXT_FORMATTER = SERVER_ROOT / "engine" / "utils" / "text_formatter.py"


def module_scope_pygame_import(path: pathlib.Path) -> bool:
    """True if `path` imports pygame anywhere but inside `if TYPE_CHECKING:`."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.If):
            test = node.test
            guarded = isinstance(test, ast.Name) and test.id == "TYPE_CHECKING"
            if guarded:
                continue
        elif not isinstance(node, (ast.Import, ast.ImportFrom)):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Import) and any(alias.name == "pygame" for alias in sub.names):
                return True
            if isinstance(sub, ast.ImportFrom) and sub.module == "pygame":
                return True
    return False


class TestTextFormatterHasNoModuleScopePygameImport(unittest.TestCase):
    def test_pygame_is_only_imported_under_type_checking_or_inside_a_function(self) -> None:
        self.assertFalse(
            module_scope_pygame_import(TEXT_FORMATTER),
            f"{TEXT_FORMATTER} must not import pygame at module scope -- it is "
            "imported transitively by headless/server code that never touches "
            "pygame. Guard it with `if TYPE_CHECKING:` (annotations) or a local "
            "`import pygame` inside the one function that needs it at runtime.",
        )


class TestHeadlessImportWithoutPygame(unittest.TestCase):
    def test_headless_server_and_full_command_registry_import_without_pygame(self) -> None:
        probe = (
            "import sys\n"
            "sys.modules['pygame'] = None\n"
            f"sys.path.insert(0, {str(SERVER_ROOT)!r})\n"
            "import engine.server.headless_server\n"
            "import engine.commands\n"
            "print('IMPORT_OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", probe],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("IMPORT_OK", result.stdout)
        self.assertNotIn("FAILED to load", result.stderr + result.stdout)


if __name__ == "__main__":
    unittest.main()
