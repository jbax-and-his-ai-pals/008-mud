# tests/singles/test_client_theme_packs.py
"""The shipped theme packs, and the rules the client validates them against.

`ThemeController._load_theme_catalog` reads every `res://themes/*.json`, runs it
through `_validate_theme_pack`, and silently skips anything that fails -- the
player sees a log line and the theme simply does not exist. Nothing in either
gate looked at these files, so a pack could be shipped unloadable and the only
symptom would be a theme missing from `theme list`.

Two kinds of check:

* **Files against the validator.** Every shipped pack must pass the same checks
  the client applies, so what is committed is what the client will accept.
* **Data against the code that reads it.** A key in a pack that no code path
  reads is inventory, not content: it looks like configuration and does nothing.
  `ui_strings` and `icon_tokens` are checked for that in both directions.
"""
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / "client"
THEMES_DIR = CLIENT / "themes"
THEME_CONTROLLER = CLIENT / "scripts" / "ui" / "main" / "theme_controller.gd"
MAIN_CONTROLLER = CLIENT / "scripts" / "ui" / "main_controller.gd"

# From `_validate_theme_pack`: required non-empty strings, and optional keys that
# must be dictionaries when present.
REQUIRED_STRING_KEYS = ("theme_id", "display_name")
OPTIONAL_DICT_KEYS = ("ui_strings", "lexicon", "style_tokens", "icon_tokens")


def _load_packs() -> dict[str, dict]:
    return {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(THEMES_DIR.glob("*.json"))
    }


class TestThePackFilesPassTheClientsOwnValidation(unittest.TestCase):
    """The validator's rules, applied to what is actually committed."""

    @classmethod
    def setUpClass(cls):
        cls.packs = _load_packs()
        cls.controller = THEME_CONTROLLER.read_text(encoding="utf-8")

    def test_the_theme_directory_has_packs_to_check(self):
        """Guard against a moved directory making every test below vacuous."""
        self.assertTrue(THEMES_DIR.is_dir(), f"{THEMES_DIR} should exist")
        self.assertGreater(len(self.packs), 0)

    def test_every_pack_has_a_theme_id_and_display_name(self):
        for name, pack in self.packs.items():
            for key in REQUIRED_STRING_KEYS:
                with self.subTest(pack=name, key=key):
                    value = str(pack.get(key, "")).strip()
                    self.assertTrue(value, f"{name} needs a non-empty {key}")

    def test_theme_ids_are_lowercase_and_unique(self):
        """`_validate_theme_pack` lowercases the id; two packs must not collide.

        A collision means one pack silently replaces another in the catalog.
        """
        seen: dict[str, str] = {}
        for name, pack in self.packs.items():
            theme_id = str(pack.get("theme_id", "")).strip()
            with self.subTest(pack=name):
                self.assertEqual(theme_id, theme_id.lower(),
                                 "the client lowercases theme_id, so it should already be lowercase")
                self.assertNotIn(theme_id, seen,
                                 f"'{theme_id}' is claimed by both {seen.get(theme_id)} and {name}")
                seen[theme_id] = name

    def test_optional_sections_are_dictionaries_when_present(self):
        for name, pack in self.packs.items():
            for key in OPTIONAL_DICT_KEYS:
                if key not in pack:
                    continue
                with self.subTest(pack=name, key=key):
                    self.assertIsInstance(pack[key], dict,
                                          f"{name}: {key} must be a dictionary")

    def test_style_colours_are_html_colours_the_parser_accepts(self):
        """`_parse_theme_color` falls back silently on a bad string.

        A typo'd colour is therefore not an error anywhere -- it is just the
        default colour, which is exactly the kind of bug nobody reports.
        """
        html = re.compile(r"^#[0-9a-fA-F]{6}$|^#[0-9a-fA-F]{8}$")
        for name, pack in self.packs.items():
            tokens = pack.get("style_tokens", {})
            for key in ("accent_color", "text_color"):
                if key not in tokens:
                    continue
                with self.subTest(pack=name, token=key):
                    self.assertRegex(str(tokens[key]), html,
                                     f"{name}: {key} should be a #RRGGBB colour")

    def test_ui_density_is_inside_the_range_the_client_clamps_to(self):
        """`_apply_theme_style` clamps to 2..20; a value outside it is a silent change."""
        for name, pack in self.packs.items():
            tokens = pack.get("style_tokens", {})
            if "ui_density" not in tokens:
                continue
            with self.subTest(pack=name):
                density = int(tokens["ui_density"])
                self.assertGreaterEqual(density, 2)
                self.assertLessEqual(density, 20)

    def test_a_default_pack_exists(self):
        """`theme list` and the fallback strings both assume a 'default'."""
        self.assertIn("default", {str(p.get("theme_id", "")).strip() for p in self.packs.values()})


class TestTheStringInventoryIsActuallyRead(unittest.TestCase):
    """A ui_string or icon_token nobody reads is configuration theatre."""

    @classmethod
    def setUpClass(cls):
        cls.packs = _load_packs()
        cls.controller = THEME_CONTROLLER.read_text(encoding="utf-8")

    def _consumed_ui_strings(self) -> set[str]:
        """Keys read out of the `ui_strings` dictionary in `_apply_theme`."""
        start = self.controller.index("func _apply_theme(")
        body = self.controller[start:self.controller.index("\nfunc ", start + 10)]
        return set(re.findall(r'ui\.get\("([^"]+)"', body))

    def _consumed_icon_tokens(self) -> set[str]:
        """Icon tokens are read from `game_state_payloads.gd`, not the controller.

        `_icon_token` is defined on ThemeController but every call site is in the
        payload builders, so the whole client directory is the search space.
        """
        found: set[str] = set()
        for path in CLIENT.rglob("*.gd"):
            found.update(re.findall(r'_icon_token\("([^"]+)"', path.read_text(encoding="utf-8")))
        return found

    def test_every_ui_string_in_every_pack_is_read_by_the_controller(self):
        consumed = self._consumed_ui_strings()
        self.assertGreater(len(consumed), 5, "the scan should find the ui_string reads")
        for name, pack in self.packs.items():
            for key in pack.get("ui_strings", {}):
                with self.subTest(pack=name, key=key):
                    self.assertIn(key, consumed,
                                  f"{name}: ui_strings.{key} is never read, so it does nothing")

    def test_every_icon_token_in_every_pack_is_read_somewhere_in_the_client(self):
        consumed = self._consumed_icon_tokens()
        self.assertGreater(len(consumed), 3, "the scan should find the icon token reads")
        for name, pack in self.packs.items():
            for key in pack.get("icon_tokens", {}):
                with self.subTest(pack=name, key=key):
                    self.assertIn(key, consumed,
                                  f"{name}: icon_tokens.{key} is never read, so it does nothing")

    def test_the_strings_the_default_pack_does_not_define_are_a_known_list(self):
        """The default pack falls back to English for three titles.

        Not a failure -- `_apply_theme` supplies a literal for every key -- but it
        is the difference between a finished catalogue and one that looks finished,
        so it is pinned rather than left to drift. Adding a key here should be a
        deliberate act; defining one shrinks the list.
        """
        default = next(p for p in self.packs.values()
                       if str(p.get("theme_id", "")).strip() == "default")
        provided = set(default.get("ui_strings", {}))
        missing = sorted(self._consumed_ui_strings() - provided)
        self.assertEqual(
            ["adventure_title", "collections_title", "discoveries_title"], missing,
            "the default pack's coverage changed: update this list and the pack together",
        )

    def test_the_icon_token_sets_agree_between_packs(self):
        """All packs ship the same 12 tokens, so a theme cannot lose an icon.

        A partial set would fall back per-key, mixing two visual languages.
        """
        provided = {
            name: set(pack.get("icon_tokens", {})) for name, pack in self.packs.items()
        }
        reference_name = "default.json"
        self.assertIn(reference_name, provided)
        reference = provided[reference_name]
        self.assertGreater(len(reference), 5)
        for name, keys in provided.items():
            with self.subTest(pack=name):
                self.assertEqual(reference, keys,
                                 f"{name} should ship the same icon_tokens as {reference_name}")


class TestTheThemeCommandsAreReachable(unittest.TestCase):
    """Local theme commands must be intercepted before the server sees them."""

    @classmethod
    def setUpClass(cls):
        cls.controller = THEME_CONTROLLER.read_text(encoding="utf-8")
        cls.lifecycle = (CLIENT / "scripts" / "ui" / "main" / "network_lifecycle.gd").read_text(
            encoding="utf-8"
        )

    def test_the_controller_reads_the_directory_main_controller_declares(self):
        """Two files, one directory: a rename in either breaks the other."""
        declared = re.search(r'const THEME_PACK_DIR\s*:=\s*"res://([^"]+)"',
                             MAIN_CONTROLLER.read_text(encoding="utf-8"))
        self.assertIsNotNone(declared, "THEME_PACK_DIR should be a constant")
        self.assertEqual("themes", declared.group(1))
        self.assertTrue((CLIENT / declared.group(1)).is_dir())
        self.assertIn("main.THEME_PACK_DIR", self.controller,
                      "the controller should use the declared directory, not its own copy")

    def test_theme_commands_are_intercepted_before_reaching_the_server(self):
        self.assertIn("_maybe_handle_local_theme_command", self.lifecycle)
        dispatch = self.lifecycle.index("_maybe_handle_local_theme_command")
        send = self.lifecycle.index("_send_command_to_server")
        self.assertLess(dispatch, send, "local handlers must run before the command is sent")

    def test_the_unknown_theme_message_points_at_a_way_to_recover(self):
        """A dead end is a bug in its own right."""
        self.assertIn("Unknown theme:", self.controller)
        self.assertIn("theme list", self.controller,
                      "the error should tell the player how to see the real names")



class TestContentSetsAskForAPackTheClientShips(unittest.TestCase):
    """A content set's `presentation.theme_pack` reaches the client in `hello`.

    The client applies it only if it ships a pack with that `theme_id`, and
    otherwise keeps its theme -- so a name no pack has (three sets said
    `modern_neutral`, which never existed) or a path (fantasy_frontier said
    `../../../client/themes/fantasy_classic.json`) chooses nothing. The engine
    checks the id's form; whether it is installed is a client fact, so it is
    checked here, for the sets this repository ships.
    """

    def test_every_shipped_set_names_a_shipped_pack(self):
        pack_ids = {pack.get("theme_id") for pack in _load_packs().values()}
        for presentation in sorted((ROOT / "content_sets").glob("*/presentation/*.json")):
            with self.subTest(presentation=str(presentation.relative_to(ROOT))):
                declared = json.loads(presentation.read_text(encoding="utf-8")).get("theme_pack")
                self.assertIn(declared, pack_ids)

    def test_hello_applies_the_declared_pack(self):
        main = MAIN_CONTROLLER.read_text(encoding="utf-8")
        hello = main[main.index('if event_type == "hello":'):main.index('elif event_type == "session_resumed":')]
        self.assertIn('body.get("presentation"', hello)
        self.assertIn("apply_content_set_theme", hello)

    def test_a_players_own_choice_is_not_overridden(self):
        controller = THEME_CONTROLLER.read_text(encoding="utf-8")
        handler = controller[controller.index("func _maybe_handle_local_theme_command"):controller.index("func apply_content_set_theme")]
        self.assertIn("player_chose_theme = true", handler)
        apply = controller[controller.index("func apply_content_set_theme"):]
        self.assertIn("player_chose_theme", apply[:apply.index("_apply_theme(theme_id)")],
                      "the content set's pack must be skipped once the player has chosen one")


if __name__ == "__main__":
    unittest.main()
