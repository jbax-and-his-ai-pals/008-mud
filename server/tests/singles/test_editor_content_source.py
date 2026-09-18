# tests/singles/test_editor_content_source.py
"""Tripwire: the world editor and the server read one content source.

The editor used to read and write `mud-world-editor/data/`, its own mirror of the
world, kept in step with the real content by a one-way export script. That held
while the editor was a viewer; once it became the authoring front-end the two
trees stopped agreeing -- the mirror was missing 164 item ids and 52 NPC ids,
weapons.json had one entry where the game has 23, and the Gems tab's rarity
authoring never reached the game that consumes it.

`documentation/roadmap/editor-content-source.md` records the decision. This test
keeps it honest, because the failure mode is silent: pointing an editor file at
`res://data/...` again would keep working, just against the wrong world.
"""

import json
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
EDITOR_ROOT = REPOSITORY_ROOT / "mud-world-editor"
EDITOR_SCRIPTS = EDITOR_ROOT / "scripts"
CONTENT_SET = REPOSITORY_ROOT / "content_sets" / "fantasy_frontier"

# `res://` stays for the editor's own assets; it is content that must be
# resolved, so only these prefixes are allowed in a path literal.
ALLOWED_RES_PREFIXES = ("res://scripts/", "res://scenes/", "res://themes/",
                        "res://assets/", "res://fonts/", "res://icons/")


def gdscript_files(root: Path) -> list[Path]:
    return sorted(root.rglob("*.gd")) if root.is_dir() else []


class TestEditorReadsTheSharedContentSet(unittest.TestCase):
    def test_no_editor_script_hard_codes_a_content_path(self) -> None:
        offenders: list[str] = []
        for path in gdscript_files(EDITOR_SCRIPTS):
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                stripped = line.strip()
                if stripped.startswith("#") or '"res://' not in line:
                    continue
                for fragment in line.split('"'):
                    if not fragment.startswith("res://"):
                        continue
                    if fragment in ALLOWED_RES_PREFIXES or any(
                        fragment.startswith(prefix) for prefix in ALLOWED_RES_PREFIXES
                    ):
                        continue
                    if fragment == "res://":
                        continue
                    # `res://<file>.tscn`-style asset references are fine; a
                    # *content* path is one that names a data folder or file.
                    if fragment.endswith((".tscn", ".gd", ".tres", ".svg", ".ttf", ".theme")):
                        continue
                    offenders.append("%s:%d: %s" % (path.relative_to(REPOSITORY_ROOT), number, fragment))
        self.assertEqual(
            [], offenders,
            "Editor scripts must resolve content through DataRoot, not a literal "
            "res:// path:\n  " + "\n  ".join(offenders),
        )

    def test_data_root_resolves_to_the_canonical_content_set(self) -> None:
        source = (EDITOR_SCRIPTS / "core" / "DataRoot.gd").read_text(encoding="utf-8")
        self.assertIn('DEFAULT_CONTENT_SET := "../content_sets/fantasy_frontier"', source)
        # Checkout layout: <repo>/mud-world-editor/../content_sets/fantasy_frontier
        resolved = (EDITOR_ROOT / ".." / "content_sets" / "fantasy_frontier").resolve()
        self.assertEqual(CONTENT_SET.resolve(), resolved)
        self.assertTrue((CONTENT_SET / "data" / "regions").is_dir())

    def test_the_retired_mirror_is_not_the_editors_data_directory(self) -> None:
        """`<project>/data` is a fallback; it must not be the legacy mirror."""
        self.assertFalse((EDITOR_ROOT / "data").exists())
        if (EDITOR_ROOT / "legacy-mirror").exists():
            self.assertTrue(
                (EDITOR_ROOT / "legacy-mirror" / "README.md").is_file(),
                "a retained legacy mirror must say why it is still here",
            )


class TestCanonicalContentStaysClean(unittest.TestCase):
    def test_no_editor_layout_keys_in_the_content_set(self) -> None:
        """`_editor_pos` and friends belong in `editor/`, not in shipped content.

        RegionManager has always documented that content-set-authored rooms carry
        no `_editor_pos`; the sidecar is what makes that true now that the editor
        writes to these files directly.
        """
        offenders: list[str] = []
        data_dir = CONTENT_SET / "data"
        for path in sorted(data_dir.rglob("*.json")):
            text = path.read_text(encoding="utf-8")
            if "_editor_" not in text:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if '"_editor_' in line:
                    offenders.append("%s:%d: %s" % (path.relative_to(REPOSITORY_ROOT), number, line.strip()[:80]))
        self.assertEqual(
            [], offenders,
            "Editor layout metadata leaked into the content the game reads:\n  "
            + "\n  ".join(offenders),
        )

    def test_editor_state_directory_is_loaded_by_nothing(self) -> None:
        """The server's loader must not walk `editor/`."""
        editor_dir = CONTENT_SET / "editor"
        if not editor_dir.is_dir():
            self.skipTest("no editor state written yet")
        loader = (REPOSITORY_ROOT / "server" / "engine" / "world" / "definition_loader.py").read_text(encoding="utf-8")
        self.assertNotIn('"editor"', loader)
        validator = (REPOSITORY_ROOT / "server" / "engine" / "server" / "content_set.py").read_text(encoding="utf-8")
        for folder in ('"editor"', "'editor'"):
            self.assertNotIn(
                "content_root / %s" % folder, validator,
                "the content validator should not treat editor state as content",
            )

    def test_districts_resolve_from_canonical_region_data(self) -> None:
        """Districts are content: the server reads them for titles and atmosphere."""
        town = json.loads((CONTENT_SET / "data" / "regions" / "town.json").read_text(encoding="utf-8"))
        districts = (town.get("properties") or {}).get("districts") or {}
        self.assertGreaterEqual(len(districts), 5, "town's districts were lost")
        rooms = set((town.get("rooms") or {}).keys())
        for district_id, district in districts.items():
            members = district.get("members") or []
            self.assertTrue(members, "district '%s' has no members" % district_id)
            unknown = [room for room in members if room not in rooms]
            self.assertEqual([], unknown, "district '%s' names rooms that do not exist" % district_id)

    def test_gems_carry_the_authored_rarity_the_generator_reads(self) -> None:
        gems = json.loads((CONTENT_SET / "data" / "items" / "gems.json").read_text(encoding="utf-8"))
        tagged = [gem_id for gem_id, gem in gems.items()
                  if isinstance(gem, dict) and gem.get("rarity")]
        self.assertGreaterEqual(
            len(tagged), 30,
            "gem rarity authoring is missing; the generator falls back to guessing "
            "a rarity from value for every gem",
        )

    def test_nothing_relies_on_the_retired_class_name_generation_fallback(self) -> None:
        """A rolling template must say so through a family.

        Until P9 the engine recognised `"type": "Gem"` and rolled instances for
        it, which is a genre word standing in for a declaration. That fallback is
        gone: a family declares the `generated_instance` capability and names a
        generation profile. This asserts the shipped content actually carries
        that declaration, because the alternative -- a gem silently reverting to
        one plain template -- looks exactly like a working game.

        It is a content guardrail rather than engine logic on purpose: the point
        of the retirement is that the engine no longer knows the word.
        """
        contracts = json.loads(
            (CONTENT_SET / "data" / "contracts" / "world_contracts.json").read_text(encoding="utf-8")
        )
        families = {entry["id"]: entry for entry in contracts.get("item_families", [])}
        rolling = {
            family_id for family_id, family in families.items()
            if "generated_instance" in (family.get("capabilities") or [])
        }
        self.assertIn("collectible_stone", rolling, "no family declares generated instances")

        offenders: list[str] = []
        total = 0
        for path in sorted((CONTENT_SET / "data" / "items").glob("*.json")):
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                continue
            for item_id, template in payload.items():
                if not isinstance(template, dict) or template.get("type") != "Gem":
                    continue
                total += 1
                declared = str(template.get("item_family", "") or "")
                if declared not in rolling:
                    offenders.append("%s (%s:%s)" % (item_id, path.name, declared or "no family"))
        self.assertGreater(total, 0, "no Gem-class templates found; the sweep assumption changed")
        self.assertEqual([], offenders, "these would no longer roll instances: " + ", ".join(offenders))


if __name__ == "__main__":
    unittest.main()
