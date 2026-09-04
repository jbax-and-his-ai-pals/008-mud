from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CLIENT_MAIN_SCENE = ROOT / "client" / "scenes" / "main.tscn"
CLIENT_MAIN_CONTROLLER = ROOT / "client" / "scripts" / "ui" / "main_controller.gd"


class TestOperatorPaletteContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.scene_text = CLIENT_MAIN_SCENE.read_text(encoding="utf-8")
        cls.controller_text = CLIENT_MAIN_CONTROLLER.read_text(encoding="utf-8")

    def test_scene_has_operator_palette_nodes(self) -> None:
        expected_nodes = [
            '[node name="OperatorRow" type="HBoxContainer" parent="VBox"]',
            '[node name="OperatorDomainSelect" type="OptionButton" parent="VBox/OperatorRow"]',
            '[node name="OperatorActionSelect" type="OptionButton" parent="VBox/OperatorRow"]',
            '[node name="OperatorValueSelect" type="OptionButton" parent="VBox/OperatorRow"]',
            '[node name="OperatorArgInput" type="LineEdit" parent="VBox/OperatorRow"]',
            '[node name="OperatorRunButton" type="Button" parent="VBox/OperatorRow"]',
            '[node name="OperatorStatusLabel" type="Label" parent="VBox"]',
        ]
        for node_line in expected_nodes:
            self.assertIn(node_line, self.scene_text)

    def test_scene_domain_selector_lists_expected_domains(self) -> None:
        for label in ["Policy", "Profiles", "World Effects", "Auth", "Authoring"]:
            self.assertIn(f'popup/item_', self.scene_text)
            self.assertIn(f'text = "{label}"', self.scene_text)

    def test_controller_has_operator_onready_bindings(self) -> None:
        expected_bindings = [
            "operator_domain_select: OptionButton = $VBox/OperatorRow/OperatorDomainSelect",
            "operator_action_select: OptionButton = $VBox/OperatorRow/OperatorActionSelect",
            "operator_value_select: OptionButton = $VBox/OperatorRow/OperatorValueSelect",
            "operator_arg_input: LineEdit = $VBox/OperatorRow/OperatorArgInput",
            "operator_run_button: Button = $VBox/OperatorRow/OperatorRunButton",
            "operator_status_label: Label = $VBox/OperatorStatusLabel",
        ]
        for binding in expected_bindings:
            self.assertIn(binding, self.controller_text)

    def test_controller_wires_palette_signals(self) -> None:
        expected_connections = [
            "operator_domain_select.item_selected.connect(_on_operator_domain_selected)",
            "operator_action_select.item_selected.connect(_on_operator_action_selected)",
            "operator_run_button.pressed.connect(_on_operator_run_pressed)",
            "operator_arg_input.text_submitted.connect(func(_text: String) -> void: _on_operator_run_pressed())",
        ]
        for connection in expected_connections:
            self.assertIn(connection, self.controller_text)

    def test_controller_defines_palette_action_map(self) -> None:
        expected_markers = [
            "var _operator_action_maps: Dictionary = {",
            '"Policy": ["Fetch Policy"]',
            '"Profiles": ["List Profiles", "Apply Selected"]',
            '"World Effects": ["Providers", "Status", "Use Provider"]',
            '"Auth": ["GM Status", "GM Deauth", "GM Auth"]',
            '"Authoring": ["Lock Status", "Acquire Lock", "Renew Lock", "Release Lock", "Edit Next", "Edit Stale"]',
        ]
        for marker in expected_markers:
            self.assertIn(marker, self.controller_text)

    def test_controller_populates_picker_values_from_live_state(self) -> None:
        expected_markers = [
            "func _refresh_operator_values() -> void:",
            "if not used_server_options and domain == \"Profiles\" and action == \"Apply Selected\":",
            "for preset_name: String in _known_profile_presets:",
            "elif not used_server_options and domain == \"World Effects\" and action == \"Use Provider\":",
            "_world_effects_status.get(\"available_providers\", [])",
            "operator_value_select.add_item(provider_name)",
        ]
        for marker in expected_markers:
            self.assertIn(marker, self.controller_text)

    def test_controller_enforces_gm_gate_for_provider_switch(self) -> None:
        expected_markers = [
            "var _operator_catalog_requirements: Dictionary = {}",
            "func _operator_requirements_for(domain: String, action: String) -> Dictionary:",
            "var gm_required: bool = bool(requirements.get(\"requires_gm\", false))",
            "if gm_required and not _gm_granted:",
            "Operator: GM session required for this action.",
        ]
        for marker in expected_markers:
            self.assertIn(marker, self.controller_text)

    def test_controller_supports_manual_override_for_profile_and_provider(self) -> None:
        expected_markers = [
            "var picked_value: String = _operator_selected_value()",
            "var selected_preset: String = arg if arg != \"\" else picked_value",
            "var provider_id: String = arg if arg != \"\" else picked_value",
        ]
        for marker in expected_markers:
            self.assertIn(marker, self.controller_text)


if __name__ == "__main__":
    unittest.main()
