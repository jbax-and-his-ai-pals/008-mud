"""Map genre coupling in the engine: P9 batch one, item one.

The layering rule (docs/design/cross_theme_engine_contracts.md) says core code may
query a declared capability or a normalized contract, and must not branch on
genre labels such as `spell`, `mana`, `sword`, `gem`, `orc`, or
`science_fiction`. This finds the places that do, and classifies each so the work
of moving behaviour is decided by evidence rather than by reading the whole
engine.

Categories:

  KERNEL          Genre-neutral by nature: dice, persistence, pathfinding. Listed
                  only when a genre word appears in a way that is actually data.
  CAPABILITY      Branching on a *contract* the engine owns (an item family, a
                  damage profile, a capability flag). Fine to keep; the label is
                  the interface, not the genre.
  CONTENT_LEAK    Branching on a genre word that only makes sense for one theme:
                  `type == "Gem"`, `"mana" in spell`, `damage_type == "holy"`.
                  These are what the registry work has to replace.

Writes a markdown report; prints a summary. Read-only.

    python toolkit/genre_coupling_audit.py --report tmp/genre_coupling.md
"""

from __future__ import annotations

import argparse
import ast
import re
from collections import defaultdict
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
ENGINE = REPOSITORY_ROOT / "server" / "engine"
CLIENT = REPOSITORY_ROOT / "client" / "scripts"
EDITOR = REPOSITORY_ROOT / "mud-world-editor" / "scripts"

# Genre vocabulary that must not appear in a core branch. Grouped so the report
# can say *which* theme a leak would privilege.
GENRE_WORDS = {
    "fantasy-magic": ("spell", "mana", "arcane", "cast", "enchant", "rune", "scroll"),
    "fantasy-combat": ("sword", "axe", "dagger", "bow", "armour", "armor", "shield", "melee"),
    "fantasy-creature": ("orc", "goblin", "kobold", "bandit", "dragon", "undead", "beast"),
    "fantasy-material": ("gem", "ore", "ingot", "herb", "potion", "elixir"),
    "sci-fi": ("laser", "plasma", "cyber", "robot", "android", "spaceship", "charge_cell"),
}

# Words that name an engine-owned contract rather than a genre. A branch on one
# of these is a capability query.
CONTRACT_WORDS = (
    "item_family", "generation_profile", "attack_profile", "defense_profile",
    "capability", "capabilities", "system_enabled", "has_capability", "contract",
    "damage_type", "effect_type", "equip_slot", "stackable", "rarity",
)

FILE_SKIP = ("test_", "conftest")


def literal_strings(tree: ast.AST) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.append((node.lineno, node.value))
    return found


def enclosing_function(source_lines: list[str], lineno: int) -> str:
    for index in range(lineno - 1, -1, -1):
        line = source_lines[index]
        if re.match(r"\s*(def|async def) ", line):
            return line.strip().split("(")[0].replace("def ", "")
    return "<module>"


def is_comparison(line: str) -> bool:
    return bool(re.search(r"(==|!=|\.get\(|\.startswith\(|\.endswith\(| in | not in )", line))


def classify(path: Path, line: str, word: str) -> str:
    lowered = line.lower()
    if any(contract in lowered for contract in CONTRACT_WORDS):
        return "CAPABILITY"
    if path.name.startswith(FILE_SKIP):
        return "KERNEL"
    if not is_comparison(line):
        # A genre word in prose, a log line, or a default argument.
        if re.search(r"(f\"|f'|print\(|Logger\.|#)", line):
            return "KERNEL"
    return "CONTENT_LEAK"


def scan(root: Path) -> list[dict]:
    findings: list[dict] = []
    if not root.is_dir():
        return findings
    for path in sorted(root.rglob("*.py")):
        if any(path.name.startswith(prefix) for prefix in FILE_SKIP):
            continue
        source = path.read_text(encoding="utf-8")
        lines = source.splitlines()
        for lineno, text in literal_strings(ast.parse(source)):
            lowered = text.lower()
            for theme, words in GENRE_WORDS.items():
                for word in words:
                    if not re.search(r"(?<![a-z])%s(?![a-z])" % re.escape(word), lowered):
                        continue
                    line = lines[lineno - 1] if 0 < lineno <= len(lines) else ""
                    findings.append({
                        "file": str(path.relative_to(REPOSITORY_ROOT)),
                        "line": lineno,
                        "literal": text[:70],
                        "genre": theme,
                        "word": word,
                        "function": enclosing_function(lines, lineno),
                        "classification": classify(path, line, word),
                    })
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report", default="", help="write a markdown report here")
    args = parser.parse_args()

    engine = scan(ENGINE)
    if not engine:
        print("no findings")
        return 0

    by_class: dict[str, list[dict]] = defaultdict(list)
    for finding in engine:
        by_class[finding["classification"]].append(finding)

    print("engine literal findings: %d" % len(engine))
    for name in ("CONTENT_LEAK", "CAPABILITY", "KERNEL"):
        print("  %-13s %d" % (name, len(by_class.get(name, []))))

    by_file: dict[str, int] = defaultdict(int)
    for finding in by_class.get("CONTENT_LEAK", []):
        by_file[finding["file"]] += 1
    print("\ncontent leaks by file:")
    for name, count in sorted(by_file.items(), key=lambda kv: -kv[1])[:15]:
        print("  %-58s %d" % (name, count))

    if args.report:
        out = REPOSITORY_ROOT / args.report
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as handle:
            handle.write("# Genre coupling in the engine\n\n")
            handle.write("Generated by `toolkit/genre_coupling_audit.py`. "
                         "`CONTENT_LEAK` rows branch on a genre word and are the "
                         "registry's work; `CAPABILITY` rows already branch on a "
                         "contract and can stay.\n\n")
            for name in ("CONTENT_LEAK", "CAPABILITY"):
                rows = by_class.get(name, [])
                handle.write("## %s (%d)\n\n" % (name, len(rows)))
                handle.write("| file | line | function | literal | theme |\n|---|---|---|---|---|\n")
                for finding in sorted(rows, key=lambda f: (f["file"], f["line"])):
                    handle.write("| `%s` | %d | `%s` | `%s` | %s |\n" % (
                        finding["file"], finding["line"], finding["function"],
                        finding["literal"].replace("|", "\\|"), finding["genre"]))
                handle.write("\n")
        print("\nreport: %s" % out.relative_to(REPOSITORY_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
