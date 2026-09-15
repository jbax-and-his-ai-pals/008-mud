"""Tripwire: engine text I/O must pin an encoding.

On Windows the locale default is cp1252, so a UTF-8 content file opened without
`encoding="utf-8"` silently mojibakes every apostrophe and accent. The engine
read `npcs/villagers.json` that way, so a player saw

    Curator Vane entrusts you with an archive finder\u00e2\u20ac\u2122s stipend.

for a file whose bytes were a perfectly good U+2019. Nothing raises, nothing
logs -- the world's prose is just quietly wrong, which is the worst way for a
bug to behave in a game made of prose.

This test parses the engine's own source and fails on any text-mode `open()`,
`Path.read_text()`, or `Path.write_text()` that does not say which encoding it
means. Binary modes are exempt. Parsing rather than pattern-matching is
deliberate: the word "open" appears in prose all over this codebase, and a
tripwire that cries wolf gets switched off.
"""

import ast
import pathlib
import unittest


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[3]
ENGINE_ROOT = REPOSITORY_ROOT / "server" / "engine"

# The builtin, and the two pathlib methods that touch a file's text. `open` is
# matched as a bare name only: this engine has plenty of its own `open()`
# methods -- a chest opens, a door opens -- and none of them read a file.
BUILTIN_TEXT_IO = {"open"}
METHOD_TEXT_IO = {"read_text", "write_text"}


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name) and func.id in BUILTIN_TEXT_IO:
        return func.id
    if isinstance(func, ast.Attribute) and func.attr in METHOD_TEXT_IO:
        return func.attr
    return ""


def _literal(node: ast.AST | None) -> object:
    return node.value if isinstance(node, ast.Constant) else None


def _is_binary_open(node: ast.Call) -> bool:
    """`open(path, "rb")` reads bytes; it has no encoding to declare."""
    candidates = [arg for arg in node.args[1:2]]
    candidates += [kw.value for kw in node.keywords if kw.arg == "mode"]
    for candidate in candidates:
        mode = _literal(candidate)
        if isinstance(mode, str):
            return "b" in mode
    return False


def unpinned_text_io(path: pathlib.Path) -> list[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _call_name(node)
        if not name:
            continue
        if any(keyword.arg == "encoding" for keyword in node.keywords):
            continue
        if name == "open" and _is_binary_open(node):
            continue
        offenders.append("%s:%d: %s(...)" % (path.relative_to(REPOSITORY_ROOT), node.lineno, name))
    return offenders


class TestEncodingHygiene(unittest.TestCase):
    def test_engine_text_io_pins_an_encoding(self) -> None:
        offenders: list[str] = []
        for path in sorted(ENGINE_ROOT.rglob("*.py")):
            offenders.extend(unpinned_text_io(path))

        self.assertEqual(
            [],
            offenders,
            "Engine text I/O must pass encoding='utf-8' (Windows defaults to "
            "cp1252 and silently mojibakes content):\n  " + "\n  ".join(offenders),
        )


if __name__ == "__main__":
    unittest.main()
