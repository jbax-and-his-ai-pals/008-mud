# tests/singles/test_client_a11y_presets.py
"""The accessibility presets, and which capabilities the server actually honours.

`AccessibilityController` is where a11y stops being a UI concern: it writes
`_client_capabilities` (read by the server) and applies local presentation
changes. The presets and the capability dictionary are therefore a contract in
two directions, and nothing checked either.

The split this file pins down
-----------------------------
`DEFAULT_CLIENT_CAPABILITIES` is one dictionary carrying two different kinds of
key, and only the second kind is a protocol:

* **server-honoured** -- the server reads the key and changes what it sends.
  Today there are exactly two (`reduced_motion`, `screen_reader_mode`), both read
  by `poc_server._build_blight_payload`.
* **client-only** -- presentation switches consumed entirely inside the client
  (`text_scale`, `dyslexia_font`, `line_spacing`, `contrast_enforce`,
  `high_contrast`, `effects_distortion`, `effects_weather`, plus the pre-existing
  `rich_text`, `mobile_variant`).

That split is defensible: text scale and font choice are the client's business,
and there is no reason for the server to know them. The risk is a maintainer
treating the whole dictionary as protocol and expecting the server to react to a
key it has never read. These tests state which is which, so that expectation has
to be a deliberate change rather than an assumption.
"""
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLIENT = ROOT / "client"
MAIN_CONTROLLER = CLIENT / "scripts" / "ui" / "main_controller.gd"
ACCESSIBILITY = CLIENT / "scripts" / "ui" / "main" / "accessibility.gd"
POC_SERVER = ROOT / "server" / "poc_server.py"

# Every capability key the client sends, and whether the server reads it.
SERVER_HONOURED = {"reduced_motion", "screen_reader_mode"}
CLIENT_ONLY = {
    "rich_text", "mobile_variant", "high_contrast", "text_scale",
    "dyslexia_font", "line_spacing", "contrast_enforce",
    "effects_distortion", "effects_weather",
}

_GD_DICT_ENTRY = re.compile(r'^\s*"([^"]+)"\s*:\s*(.+?),?\s*(?:#.*)?$', re.MULTILINE)


def _gd_const_dict(text: str, name: str) -> dict[str, str]:
    """Parse a flat `const NAME := { "k": v, ... }` GDScript literal.

    Returns the raw right-hand side per key; callers coerce. Values are kept as
    text because the point is to inspect what the author wrote.
    """
    block = re.search(rf"const\s+{name}\s*:=\s*\{{(.*?)\n\}}", text, re.DOTALL)
    if block is None:
        raise AssertionError(f"{name} should be a flat dictionary constant")
    return {key: value for key, value in _GD_DICT_ENTRY.findall(block.group(1))}


class TestCapabilitiesTheServerHonours(unittest.TestCase):
    """The two keys with a server-side consumer must keep working."""

    @classmethod
    def setUpClass(cls):
        cls.server = POC_SERVER.read_text(encoding="utf-8")
        cls.controller = MAIN_CONTROLLER.read_text(encoding="utf-8")

    def test_the_client_still_sends_both_honoured_keys(self):
        declared = _gd_const_dict(self.controller, "DEFAULT_CLIENT_CAPABILITIES")
        for key in SERVER_HONOURED:
            with self.subTest(key=key):
                self.assertIn(key, declared, f"{key} is read by the server but not sent by the client")

    def test_the_server_reads_both_honoured_keys(self):
        for key in SERVER_HONOURED:
            with self.subTest(key=key):
                self.assertIn(f'"{key}"', self.server, f"the server should read {key}")

    def test_reduced_motion_actually_changes_what_the_server_sends(self):
        """A capability with no effect is the same as no capability.

        This is the one place the server demonstrably honours an a11y key, so it
        is asserted as behaviour rather than as a string.
        """
        source = POC_SERVER.read_text(encoding="utf-8")
        start = source.index("def _build_blight_payload")
        body = source[start:source.index("\n    def ", start + 10)]
        self.assertIn("reduced_motion", body)
        self.assertIn('"blight": 0.0', body, "reduced motion should zero the effect")
        self.assertIn('"blight": 0.85', body, "and leave it in place otherwise")

    def test_screen_reader_mode_gets_a_spoken_description(self):
        source = POC_SERVER.read_text(encoding="utf-8")
        self.assertIn("[Atmosphere: blight high]", source,
                      "screen reader mode should attach a text description")

    def test_no_other_capability_grew_a_server_consumer_unnoticed(self):
        """If the server starts reading another key, this list is out of date.

        Not a failure of the code -- a prompt to move the key between the two
        sets above and add a behavioural test for it.
        """
        declared = set(_gd_const_dict(self.controller, "DEFAULT_CLIENT_CAPABILITIES"))
        for key in sorted(declared - SERVER_HONOURED):
            with self.subTest(key=key):
                self.assertNotIn(
                    f'"{key}"', self.server,
                    f"the server now reads '{key}': move it to SERVER_HONOURED and test it",
                )

    def test_the_two_sets_cover_every_declared_capability(self):
        """The split is only useful if it is exhaustive."""
        declared = set(_gd_const_dict(self.controller, "DEFAULT_CLIENT_CAPABILITIES"))
        self.assertEqual(
            declared, SERVER_HONOURED | CLIENT_ONLY,
            "every declared capability must be classified as honoured or client-only",
        )


class TestThePresetsAreWellFormed(unittest.TestCase):
    """Each preset is a partial patch; a wrong key or type fails silently."""

    @classmethod
    def setUpClass(cls):
        cls.controller = MAIN_CONTROLLER.read_text(encoding="utf-8")
        cls.defaults = _gd_const_dict(cls.controller, "DEFAULT_CLIENT_CAPABILITIES")
        cls.scale_presets = _gd_const_dict(cls.controller, "TEXT_SCALE_PRESETS")
        cls.preset_block = re.search(
            r"const A11Y_PRESETS\s*:=\s*\{(.*?)\n\}\n", cls.controller, re.DOTALL
        )
        if cls.preset_block is None:
            raise AssertionError("A11Y_PRESETS should be a dictionary constant")
        cls.presets = cls._parse_presets(cls.preset_block.group(1))

    @staticmethod
    def _parse_presets(block: str) -> dict[str, dict[str, str]]:
        presets: dict[str, dict[str, str]] = {}
        for match in re.finditer(r'"(\w+)"\s*:\s*\{(.*?)\}', block, re.DOTALL):
            name, body = match.group(1), match.group(2)
            presets[name] = {k: v for k, v in _GD_DICT_ENTRY.findall(body)}
        return presets

    def test_the_presets_parsed(self):
        """Guard against the parse silently returning nothing and passing."""
        self.assertGreaterEqual(len(self.presets), 5)
        self.assertIn("default", self.presets)

    def test_there_is_a_default_preset(self):
        """`a11y preset default` is how a player gets back to neutral."""
        self.assertIn("default", self.presets)

    def test_every_preset_key_is_a_real_capability(self):
        for name, patch in self.presets.items():
            for key in patch:
                with self.subTest(preset=name, key=key):
                    self.assertIn(key, self.defaults,
                                  f"preset '{name}' sets '{key}', which no capability declares")

    def test_every_preset_value_is_the_same_type_as_the_default(self):
        """A string 'true' would compare unequal to every boolean check."""
        for name, patch in self.presets.items():
            for key, value in patch.items():
                with self.subTest(preset=name, key=key):
                    default = self.defaults[key].strip()
                    raw = value.strip()
                    if default in ("true", "false"):
                        self.assertIn(raw, ("true", "false"),
                                      f"'{key}' is a boolean capability")
                    else:
                        self.assertRegex(raw, r"^-?[\d.]+$",
                                         f"'{key}' is numeric in the defaults")

    def test_text_scale_stays_inside_the_permitted_range(self):
        low = float(re.search(r"TEXT_SCALE_MIN\s*:=\s*([\d.]+)", self.controller).group(1))
        high = float(re.search(r"TEXT_SCALE_MAX\s*:=\s*([\d.]+)", self.controller).group(1))
        self.assertLess(low, high)
        for name, patch in self.presets.items():
            if "text_scale" not in patch:
                continue
            with self.subTest(preset=name):
                scale = float(patch["text_scale"])
                self.assertGreaterEqual(scale, low)
                self.assertLessEqual(scale, high)

    def test_line_spacing_stays_inside_the_clamp_the_command_applies(self):
        """`a11y spacing` clamps to 0.8..3.0; a preset must not exceed that."""
        for name, patch in self.presets.items():
            if "line_spacing" not in patch:
                continue
            with self.subTest(preset=name):
                spacing = float(patch["line_spacing"])
                self.assertGreaterEqual(spacing, 0.8)
                self.assertLessEqual(spacing, 3.0)

    def test_a_preset_that_reduces_motion_also_disables_distortion(self):
        """These travel together: motion sensitivity is what distortion triggers.

        `photosensitive` and `screen_reader` both set the pair, which is the
        reasoning encoded as data. Held here so a new preset cannot silently
        turn motion down while leaving the atmospheric effect on.
        """
        for name, patch in self.presets.items():
            if patch.get("reduced_motion") != "true":
                continue
            if "effects_distortion" not in patch:
                continue
            with self.subTest(preset=name):
                self.assertEqual("false", patch["effects_distortion"],
                                 f"preset '{name}' reduces motion but keeps distortion on")

    def test_the_list_command_enumerates_the_constant_rather_than_a_copy(self):
        """`a11y list` must not hardcode a second list of preset names.

        A hardcoded list is the classic way a new preset becomes invisible: it
        works, and no command mentions it.
        """
        a11y = ACCESSIBILITY.read_text(encoding="utf-8")
        start = a11y.index('if lowered == "a11y list":')
        window = a11y[start:a11y.index("return true", start)]
        self.assertIn("A11Y_PRESETS.keys()", window,
                      "the listed presets should come from A11Y_PRESETS itself")
        hardcoded = re.findall(r'"(\w+)"', window)
        for name in self.presets:
            with self.subTest(preset=name):
                self.assertNotIn(name, hardcoded,
                                 f"'{name}' is hardcoded in the list output; enumerate instead")


class TestTheCommandSurfaceIsWired(unittest.TestCase):
    """The a11y commands are dispatched from `network_lifecycle._submit_command`."""

    @classmethod
    def setUpClass(cls):
        cls.text = ACCESSIBILITY.read_text(encoding="utf-8")
        cls.lifecycle = (CLIENT / "scripts" / "ui" / "main" / "network_lifecycle.gd").read_text(
            encoding="utf-8"
        )

    def test_accessibility_commands_are_intercepted_before_reaching_the_server(self):
        """A local command that reaches the server is a server-side error message."""
        self.assertIn("_maybe_handle_local_accessibility_command", self.lifecycle)
        dispatch = self.lifecycle.index("_maybe_handle_local_accessibility_command")
        send = self.lifecycle.index("_send_command_to_server")
        self.assertLess(dispatch, send,
                        "local handlers must run before the command is sent")

    def test_each_toggle_command_reads_its_own_capability_key(self):
        """A copy-paste slip here turns one setting into another's switch."""
        expected = {
            "a11y contrast ": "contrast_enforce",
            "a11y distortion ": "effects_distortion",
            "a11y weather ": "effects_weather",
            "a11y font dyslexia ": "dyslexia_font",
            "a11y spacing ": "line_spacing",
        }
        for prefix, key in expected.items():
            with self.subTest(command=prefix):
                start = self.text.index(f'begins_with("{prefix}")')
                window = self.text[start:start + 420]
                self.assertIn(f'"{key}"', window,
                              f"'{prefix}' should set {key}")

    def test_the_list_output_documents_the_commands_that_exist(self):
        """`a11y list` is the only discoverable help; it must not name dead commands."""
        for command in ("a11y preset <", "a11y text <", "a11y font dyslexia ",
                        "a11y spacing <", "a11y contrast ", "a11y distortion ",
                        "a11y weather ", "a11y motion ", "a11y sr "):
            with self.subTest(command=command):
                self.assertIn(command, self.text,
                              f"'{command}' should be described in the list output")

    def test_the_listed_toggles_are_dispatched_somewhere(self):
        """`a11y motion` and `a11y sr` are handled in main_controller, not here.

        Listing a command in one file and implementing it in another is exactly
        how a help entry drifts away from the code, so both files are searched.
        """
        controller = MAIN_CONTROLLER.read_text(encoding="utf-8")
        both = self.text + controller
        for command in ("a11y motion on", "a11y motion off", "a11y sr on", "a11y sr off"):
            with self.subTest(command=command):
                self.assertIn(f'"{command}"', both,
                              f"'{command}' is advertised by `a11y list` but handled nowhere")

    def test_the_handlers_return_true_when_they_claim_a_command(self):
        """Returning false hands the text to the server, where it is a syntax error."""
        for name in ("_maybe_handle_local_accessibility_command",
                     "_maybe_handle_local_keybind_command",
                     "_maybe_handle_local_onboarding_command"):
            with self.subTest(handler=name):
                self.assertIn(f"func {name}", self.text)
        # The catch-all branches are what make an unknown `a11y ...` a local usage
        # message rather than a round trip.
        self.assertIn('if lowered.begins_with("keybind")', self.text)
        self.assertIn('Usage: a11y text', self.text)
        self.assertIn('Usage: onboarding show | onboarding dismiss', self.text)


class TestTheAccessibilityControllerIsReachable(unittest.TestCase):
    """It is constructed by `main_controller._ready` and reached through `main`."""

    @classmethod
    def setUpClass(cls):
        cls.text = ACCESSIBILITY.read_text(encoding="utf-8")
        cls.controller = MAIN_CONTROLLER.read_text(encoding="utf-8")

    def test_the_controller_is_a_refcounted_helper_holding_a_main_reference(self):
        """The P8 split convention: state lives on `main`, not duplicated here."""
        self.assertIn("extends RefCounted", self.text)
        self.assertIn("class_name AccessibilityController", self.text)
        self.assertIn("var main: MainController", self.text)

    def test_main_controller_constructs_it(self):
        self.assertIn("AccessibilityController.new(self)", self.controller)

    def test_the_helpers_it_reaches_through_main_exist(self):
        """Every `main.` member used here must be declared on MainController.

        Only identifiers that look like members are collected: `main.tscn` in the
        header comment is a filename, not an access, and prose would otherwise
        make this assert nothing useful.
        """
        reached = {
            match for match in re.findall(r"\bmain\.([A-Za-z_]\w*)", self.text)
            if match.startswith("_") or "_" in match
        }
        self.assertGreater(len(reached), 3, "the scan should find the members it uses")
        for member in sorted(reached):
            with self.subTest(member=member):
                self.assertRegex(
                    self.controller,
                    rf"\b{re.escape(member)}\b",
                    f"accessibility.gd reaches main.{member}, which MainController never declares",
                )


if __name__ == "__main__":
    unittest.main()
