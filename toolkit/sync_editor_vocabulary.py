#!/usr/bin/env python3
"""Write the editor's copy of the dialogue vocabulary from the engine's definition of it.

The engine defines each condition kind (`engine/conditions.py::CONDITION_SPECS`) and each effect
(`engine/dialogue/effects.py::EFFECT_EDITOR`) once, with the label, hint and field kinds an author sees. The editor
keeps those in `mud-world-editor/scripts/data/DialogueSchema.gd`; that file's two tables are *generated* by this script,
so adding a kind or an effect is an engine edit followed by:

    python toolkit/sync_editor_vocabulary.py            # rewrite DialogueSchema.gd's tables
    python toolkit/sync_editor_vocabulary.py --check    # exit 1 if they are out of date (the unit tests run this)

Never edit the generated tables by hand: the next run replaces them.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("MUD_LOG_LEVEL", "WARNING")
sys.path.insert(0, str(REPO_ROOT / "server"))

SCHEMA = REPO_ROOT / "mud-world-editor" / "scripts" / "data" / "DialogueSchema.gd"
CONDITIONS_NOTE = "# GENERATED from engine/conditions.py::CONDITION_SPECS by toolkit/sync_editor_vocabulary.py; do not edit by hand.\n"
EFFECTS_NOTE = "# GENERATED from engine/dialogue/effects.py::EFFECT_EDITOR by toolkit/sync_editor_vocabulary.py; do not edit by hand.\n"


def q(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def condition_table() -> str:
    from engine.conditions import CONDITION_SPECS

    out = [CONDITIONS_NOTE + "const CONDITION_KINDS := {"]
    for kind, spec in CONDITION_SPECS.items():
        fields = "{%s}" % ", ".join("%s: %s" % (q(key), q(value)) for key, value in spec["fields"].items())
        out += ["\t%s: {" % q(kind), "\t\t\"label\": %s," % q(spec["label"]), "\t\t\"fields\": %s," % fields,
                "\t\t\"note\": %s," % q(spec["note"]), "\t},"]
    out.append("}")
    return "\n".join(out) + "\n"


def effect_table() -> str:
    from engine.dialogue.effects import EFFECT_EDITOR

    out = [EFFECTS_NOTE + "const EFFECTS := {"]
    for key, spec in EFFECT_EDITOR.items():
        parts = ["\"label\": %s" % q(spec["label"]), "\"shape\": %s" % q(spec["hint"]), "\"kind\": %s" % q(spec["kind"])]
        if spec.get("accepts_true"):
            parts.append("\"accepts_true\": true")
        out.append("\t%s: {%s}," % (q(key), ", ".join(parts)))
    out.append("}")
    return "\n".join(out) + "\n"


def regenerate(text: str) -> str:
    for name, table in (("CONDITION_KINDS", condition_table()), ("EFFECTS", effect_table())):
        pattern = re.compile(r"(?:# GENERATED[^\n]*\n)?const %s := \{.*?\n\}\n" % name, re.DOTALL)
        if not pattern.search(text):
            raise SystemExit("DialogueSchema.gd has no `const %s` table to replace" % name)
        text = pattern.sub(lambda _match: table, text, count=1)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report whether the editor's tables are current, change nothing")
    args = parser.parse_args()

    raw = SCHEMA.read_text(encoding="utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    current = raw.replace("\r\n", "\n")
    fresh = regenerate(current)
    if fresh == current:
        print("the editor's dialogue vocabulary is current")
        return 0
    if args.check:
        print("DialogueSchema.gd's tables are out of date; run: python toolkit/sync_editor_vocabulary.py")
        return 1
    SCHEMA.write_text(fresh.replace("\n", newline), encoding="utf-8", newline="")
    print("rewrote %s" % SCHEMA.relative_to(REPO_ROOT).as_posix())
    return 0


if __name__ == "__main__":
    sys.exit(main())
