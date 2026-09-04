extends Control

const BLIGHT_TEXT_EFFECT: Script = preload("res://scripts/ui/effects/blight_text_effect.gd")
const ATMOSPHERIC_TEXT_EFFECT: Script = preload("res://scripts/ui/effects/atmospheric_text_effect.gd")
const DEFAULT_CLIENT_CAPABILITIES := {
	"rich_text":          true,
	"mobile_variant":     false,
	"reduced_motion":     false,
	"high_contrast":      false,
	"screen_reader_mode": false,
	"text_scale":         1.0,
	# A1: text legibility
	"dyslexia_font":      false,   # swap to OpenDyslexic / high-legibility font
	"line_spacing":       1.0,     # multiplier applied to RichTextLabel line spacing
	"contrast_enforce":   false,   # apply minimum contrast policy to all text colours
	# A2/A3: colour and motion safety
	"effects_distortion": true,    # atmospheric text distortion (blight/wavey)
	"effects_weather":    true,    # weather/screen shader overlays
}
const TEXT_SCALE_PRESETS := {
	"small": 0.9,
	"medium": 1.0,
	"large": 1.2,
	"xlarge": 1.4
}
const TEXT_SCALE_MIN := 0.75
const TEXT_SCALE_MAX := 2.0
const THEME_PACK_DIR := "res://themes"

# M3: Mobile performance budget targets (informational — used by startup/perf checks).
const MOBILE_STARTUP_BUDGET_MS    := 3000   # cold start to first frame
const MOBILE_RECONNECT_BUDGET_MS  := 1500   # resume → first server response
const MOBILE_MEMORY_BUDGET_MB_LOW := 128    # low-tier device ceiling
const MOBILE_MEMORY_BUDGET_MB_MID := 256    # mid-tier device ceiling

# Accessibility presets: each entry is a partial patch applied to _client_capabilities.
# Keys absent from a preset are left unchanged so presets compose safely.
const A11Y_PRESETS := {
	"default": {
		"high_contrast":      false,
		"reduced_motion":     false,
		"screen_reader_mode": false,
		"text_scale":         1.0,
		"dyslexia_font":      false,
		"line_spacing":       1.0,
		"contrast_enforce":   false,
		"effects_distortion": true,
		"effects_weather":    true,
	},
	"high_contrast": {
		"high_contrast":    true,
		"contrast_enforce": true,
		"text_scale":       1.2,
	},
	"low_vision": {
		"high_contrast":    true,
		"contrast_enforce": true,
		"text_scale":       1.4,
		"line_spacing":     1.3,
		"dyslexia_font":    true,
	},
	"dyslexia": {
		"dyslexia_font": true,
		"line_spacing":  1.25,
		"text_scale":    1.1,
	},
	"screen_reader": {
		"screen_reader_mode":  true,
		"reduced_motion":      true,
		"effects_distortion":  false,
		"effects_weather":     false,
	},
	"reduced_motion": {
		"reduced_motion":     true,
		"effects_distortion": false,
	},
	"photosensitive": {
		"reduced_motion":     true,
		"effects_distortion": false,
		"effects_weather":    false,
	},
}
const THEME_DEFAULT_ACCENT := Color(0.75, 0.9, 1.0, 1.0)
const THEME_DEFAULT_TEXT := Color(0.9, 0.9, 0.9, 1.0)
const THEME_DEFAULT_DENSITY := 8
const HISTORY_MAX_SIZE := 100
var _client_capabilities: Dictionary = DEFAULT_CLIENT_CAPABILITIES.duplicate(true)
var _asset_revisions: Dictionary = {}
var _session_id: String = "client_shell"
var _command_history: PackedStringArray = []
var _history_cursor: int = -1   # -1 = live input (not browsing history)
var _history_draft: String = "" # text saved when the player first presses Up
var _resume_session_id: String = ""
var _degraded_mode_active: bool = false
var _manual_disconnect_requested: bool = false
var _reconnect_attempts: int = 0
var _max_reconnect_attempts: int = 6
var _reconnect_pending: bool = false
var _reconnect_deadline_msec: int = 0
var _auto_reconnect_enabled: bool = true
var _theme_catalog: Dictionary = {}
var _active_theme_id: String = "default"
var _theme_icon_tokens: Dictionary = {}
var _authoring_lock_by_asset: Dictionary = {}
var _authoring_panel_state: Dictionary = {
	"asset_id": "",
	"lock_state": "none",
	"lock_owner": "",
	"lock_expires_at": 0.0,
	"lock_remaining_s": 0.0,
	"is_mine": false
}
var _authoring_status_refresh_accum_s: float = 0.0
var _authoring_auto_renew_enabled: bool = true
var _authoring_auto_renew_interval_s: float = 10.0
var _authoring_auto_renew_accum_s: float = 0.0
var _authoring_last_auto_renew_asset_id: String = ""
var _pending_profile_apply_preset: String = ""
var _known_profile_presets: PackedStringArray = []
var _active_profile_preset: String = ""
var _active_profile_path: String = ""
var _server_profile_modes: Dictionary = {}
var _server_auth_policy: Dictionary = {}
var _session_entitlements: PackedStringArray = []
var _session_entitlements_known: bool = false
var _world_effects_status: Dictionary = {}
var _world_effects_cells_preview: Dictionary = {}
var _gm_granted: bool = false
var _gm_auth_configured: bool = false
var _gm_auth_cooldown_seconds: int = 0
var _operator_action_maps: Dictionary = {
	"Policy": ["Fetch Policy"],
	"Profiles": ["List Profiles", "Apply Selected"],
	"World Effects": ["Providers", "Status", "Use Provider"],
	"Auth": ["GM Status", "GM Deauth", "GM Auth"],
	"Authoring": ["Lock Status", "Acquire Lock", "Renew Lock", "Release Lock", "Edit Next", "Edit Stale"]
}
var _operator_catalog_value_options: Dictionary = {}
var _operator_catalog_requirements: Dictionary = {}
var _network_telemetry: Dictionary = {
	"connect_attempts": 0,
	"connect_successes": 0,
	"disconnects": 0,
	"errors": 0,
	"lines_received": 0,
	"lines_sent": 0,
	"last_transport": "",
	"last_error": "",
	"last_connected_at": "",
	"last_disconnected_at": "",
	"reconnect_state": "idle",
	"auto_reconnect_enabled": true
}
var _startup_diagnostics: Dictionary = {}
var _finite_adventure_state: Dictionary = {}
var _finite_adventure_summary: Dictionary = {}
var _finite_adventure_report: Dictionary = {}
var _finite_adventure_catalog: Array = []
var _finite_adventure_catalog_requested: bool = false
var _latest_quests_payload: Dictionary = {}
var _game_contract: Dictionary = {}

@onready var host_input: LineEdit = $VBox/ConnectionRow/HostInput
@onready var port_input: LineEdit = $VBox/ConnectionRow/PortInput
@onready var connect_button: Button = $VBox/ConnectionRow/ConnectButton
@onready var disconnect_button: Button = $VBox/ConnectionRow/DisconnectButton
@onready var policy_button: Button = $VBox/ConnectionRow/PolicyButton
@onready var field_pulse_button: Button = $VBox/ConnectionRow/FieldPulseButton
@onready var field_id_input: LineEdit = $VBox/ConnectionRow/FieldIdInput
@onready var field_x_input: LineEdit = $VBox/ConnectionRow/FieldXInput
@onready var field_y_input: LineEdit = $VBox/ConnectionRow/FieldYInput
@onready var field_value_input: LineEdit = $VBox/ConnectionRow/FieldValueInput
@onready var transport_select: OptionButton = $VBox/ConnectionRow/TransportSelect
@onready var auto_reconnect_button: Button = $VBox/ConnectionRow/AutoReconnectButton
@onready var gm_auth_input: LineEdit = $VBox/ConnectionRow/GmAuthInput
@onready var gm_auth_button: Button = $VBox/ConnectionRow/GmAuthButton
@onready var profile_preset_select: OptionButton = $VBox/ProfileRow/ProfilePresetSelect
@onready var profile_refresh_button: Button = $VBox/ProfileRow/ProfileRefreshButton
@onready var profile_apply_button: Button = $VBox/ProfileRow/ProfileApplyButton
@onready var profile_cancel_button: Button = $VBox/ProfileRow/ProfileCancelButton
@onready var profile_status_label: Label = $VBox/ProfileStatusLabel
@onready var operator_domain_select: OptionButton = $VBox/OperatorRow/OperatorDomainSelect
@onready var operator_action_select: OptionButton = $VBox/OperatorRow/OperatorActionSelect
@onready var operator_value_select: OptionButton = $VBox/OperatorRow/OperatorValueSelect
@onready var operator_arg_input: LineEdit = $VBox/OperatorRow/OperatorArgInput
@onready var operator_run_button: Button = $VBox/OperatorRow/OperatorRunButton
@onready var operator_status_label: Label = $VBox/OperatorStatusLabel
@onready var adventure_catalog_select: OptionButton = $VBox/AdventureRow/AdventureCatalogSelect
@onready var adventure_row: HBoxContainer = $VBox/AdventureRow
@onready var adventure_catalog_button: Button = $VBox/AdventureRow/AdventureCatalogButton
@onready var adventure_campaign_input: LineEdit = $VBox/AdventureRow/AdventureCampaignInput
@onready var adventure_start_button: Button = $VBox/AdventureRow/AdventureStartButton
@onready var adventure_status_button: Button = $VBox/AdventureRow/AdventureStatusButton
@onready var adventure_abandon_button: Button = $VBox/AdventureRow/AdventureAbandonButton
@onready var adventure_checkpoint_button: Button = $VBox/AdventureRow/AdventureCheckpointButton
@onready var adventure_restore_button: Button = $VBox/AdventureRow/AdventureRestoreButton
@onready var adventure_reset_button: Button = $VBox/AdventureRow/AdventureResetButton
@onready var adventure_replay_button: Button = $VBox/AdventureRow/AdventureReplayButton
@onready var adventure_summary_md_button: Button = $VBox/AdventureRow/AdventureSummaryMdButton
@onready var adventure_summary_text_button: Button = $VBox/AdventureRow/AdventureSummaryTextButton
@onready var adventure_summary_json_button: Button = $VBox/AdventureRow/AdventureSummaryJsonButton
@onready var log_view: RichTextLabel = $VBox/Log
@onready var status_title_label: Label = $VBox/AssetPreview/StatusTitle
@onready var status_primary_label: Label = $VBox/AssetPreview/StatusPrimary
@onready var status_vitals_label: Label = $VBox/AssetPreview/StatusVitals
@onready var status_effects_label: Label = $VBox/AssetPreview/StatusEffects
@onready var inventory_title_label: Label = $VBox/AssetPreview/InventoryTitle
@onready var inventory_summary_label: Label = $VBox/AssetPreview/InventorySummary
@onready var inventory_list_label: RichTextLabel = $VBox/AssetPreview/InventoryList
@onready var journal_title_label: Label = $VBox/AssetPreview/JournalTitle
@onready var journal_summary_label: Label = $VBox/AssetPreview/JournalSummary
@onready var journal_list_label: RichTextLabel = $VBox/AssetPreview/JournalList
@onready var nearby_title_label: Label = $VBox/AssetPreview/NearbyTitle
@onready var nearby_location_label: Label = $VBox/AssetPreview/NearbyLocation
@onready var nearby_exits_label: Label = $VBox/AssetPreview/NearbyExits
@onready var nearby_npcs_label: RichTextLabel = $VBox/AssetPreview/NearbyNpcs
@onready var nearby_items_label: RichTextLabel = $VBox/AssetPreview/NearbyItems
@onready var nearby_interactions_label: Label = $VBox/AssetPreview/NearbyInteractions
@onready var world_state_title_label: Label = $VBox/AssetPreview/WorldStateTitle
@onready var world_state_label: Label = $VBox/AssetPreview/WorldStateLabel
@onready var network_title_label: Label = $VBox/AssetPreview/NetworkTitle
@onready var network_summary_label: Label = $VBox/AssetPreview/NetworkSummary
@onready var network_detail_label: Label = $VBox/AssetPreview/NetworkDetail
@onready var server_policy_title_label: Label = $VBox/AssetPreview/ServerPolicyTitle
@onready var server_policy_summary_label: Label = $VBox/AssetPreview/ServerPolicySummary
@onready var server_policy_modes_label: Label = $VBox/AssetPreview/ServerPolicyModes
@onready var server_policy_providers_label: Label = $VBox/AssetPreview/ServerPolicyProviders
@onready var server_policy_warnings_label: Label = $VBox/AssetPreview/ServerPolicyWarnings
@onready var server_policy_auth_label: Label = $VBox/AssetPreview/ServerPolicyAuth
@onready var startup_diagnostics_title_label: Label = $VBox/AssetPreview/StartupDiagnosticsTitle
@onready var startup_diagnostics_summary_label: Label = $VBox/AssetPreview/StartupDiagnosticsSummary
@onready var startup_diagnostics_detail_label: Label = $VBox/AssetPreview/StartupDiagnosticsDetail
@onready var adventure_title_label: Label = $VBox/AssetPreview/AdventureTitle
@onready var adventure_state_label: Label = $VBox/AssetPreview/AdventureState
@onready var adventure_summary_label: Label = $VBox/AssetPreview/AdventureSummary
@onready var adventure_catalog_label: Label = $VBox/AssetPreview/AdventureCatalog
@onready var adventure_objective_label: RichTextLabel = $VBox/AssetPreview/AdventureObjective
@onready var adventure_report_label: RichTextLabel = $VBox/AssetPreview/AdventureReport
@onready var asset_title_label: Label = $VBox/AssetPreview/AssetTitle
@onready var asset_texture: TextureRect = $VBox/AssetPreview/AssetTexture
@onready var asset_alt_text: Label = $VBox/AssetPreview/AssetAltText
@onready var mobile_controls: VBoxContainer = $VBox/MobileControls
@onready var btn_status: Button = $VBox/MobileControls/QuickActions/BtnStatus
@onready var btn_inventory: Button = $VBox/MobileControls/QuickActions/BtnInventory
@onready var btn_quests: Button = $VBox/MobileControls/QuickActions/BtnQuests
@onready var btn_policy: Button = $VBox/MobileControls/QuickActions/BtnPolicy
@onready var btn_n: Button = $VBox/MobileControls/DPad/BtnN
@onready var btn_s: Button = $VBox/MobileControls/DPad/BtnS
@onready var btn_e: Button = $VBox/MobileControls/DPad/BtnE
@onready var btn_w: Button = $VBox/MobileControls/DPad/BtnW
@onready var btn_nw: Button = $VBox/MobileControls/DPad/BtnNW
@onready var btn_ne: Button = $VBox/MobileControls/DPad/BtnNE
@onready var btn_sw: Button = $VBox/MobileControls/DPad/BtnSW
@onready var btn_se: Button = $VBox/MobileControls/DPad/BtnSE
@onready var btn_look: Button = $VBox/MobileControls/DPad/BtnLook
@onready var authoring_asset_input: LineEdit = $VBox/AuthoringRow/AuthoringAssetInput
@onready var authoring_acquire_button: Button = $VBox/AuthoringRow/AuthoringAcquireButton
@onready var authoring_renew_button: Button = $VBox/AuthoringRow/AuthoringRenewButton
@onready var authoring_release_button: Button = $VBox/AuthoringRow/AuthoringReleaseButton
@onready var authoring_edit_button: Button = $VBox/AuthoringRow/AuthoringEditButton
@onready var authoring_edit_stale_button: Button = $VBox/AuthoringRow/AuthoringEditStaleButton
@onready var authoring_status_label: Label = $VBox/AuthoringStatus
@onready var command_input: LineEdit = $VBox/CommandRow/CommandInput
@onready var send_button: Button = $VBox/CommandRow/SendButton
@onready var root_vbox: VBoxContainer = $VBox
@onready var tcp_client: TcpClient = $TcpClient
@onready var ws_client: WsClient = $WsClient
@onready var parser: ProtocolParser = $ProtocolParser
@onready var svg_renderer: SvgRuntimeRenderer = $SvgRenderer
@onready var keybindings_manager: KeybindingsManager = $KeybindingsManager
@onready var onboarding: OnboardingController = $OnboardingOverlay
@onready var crash_recovery: CrashRecoveryController = $CrashRecoveryOverlay
@onready var char_create: CharCreateController = $CharCreateOverlay
@onready var atmosphere_layer: AtmosphereController = $AtmosphereLayer

func _ready() -> void:
	log_view.install_effect(BLIGHT_TEXT_EFFECT.new())
	log_view.install_effect(ATMOSPHERIC_TEXT_EFFECT.new())

	connect_button.pressed.connect(_on_connect_pressed)
	disconnect_button.pressed.connect(_on_disconnect_pressed)
	policy_button.pressed.connect(func() -> void: _send_command_immediate("server policy"))
	field_pulse_button.pressed.connect(_on_field_pulse_pressed)
	send_button.pressed.connect(_on_send_pressed)
	command_input.text_submitted.connect(_on_command_submitted)
	auto_reconnect_button.toggled.connect(_on_auto_reconnect_toggled)
	gm_auth_button.pressed.connect(_on_gm_auth_pressed)
	gm_auth_input.text_submitted.connect(func(_text: String) -> void: _on_gm_auth_pressed())
	profile_refresh_button.pressed.connect(_on_profile_refresh_pressed)
	profile_apply_button.pressed.connect(_on_profile_apply_pressed)
	profile_cancel_button.pressed.connect(_on_profile_cancel_pressed)
	profile_preset_select.item_selected.connect(_on_profile_selected)
	operator_domain_select.item_selected.connect(_on_operator_domain_selected)
	operator_action_select.item_selected.connect(_on_operator_action_selected)
	operator_run_button.pressed.connect(_on_operator_run_pressed)
	operator_arg_input.text_submitted.connect(func(_text: String) -> void: _on_operator_run_pressed())
	adventure_catalog_select.item_selected.connect(_on_adventure_catalog_selected)
	adventure_catalog_button.pressed.connect(func() -> void: _request_finite_adventure_catalog())
	adventure_campaign_input.text_submitted.connect(func(_text: String) -> void: _on_adventure_start_pressed())
	adventure_start_button.pressed.connect(_on_adventure_start_pressed)
	adventure_status_button.pressed.connect(func() -> void: _send_adventure_command("adventure status"))
	adventure_abandon_button.pressed.connect(func() -> void: _send_adventure_command("adventure abandon"))
	adventure_checkpoint_button.pressed.connect(func() -> void: _send_adventure_command("adventure checkpoint"))
	adventure_restore_button.pressed.connect(func() -> void: _send_adventure_command("adventure restore"))
	adventure_reset_button.pressed.connect(func() -> void: _send_adventure_command("adventure reset"))
	adventure_replay_button.pressed.connect(func() -> void: _send_adventure_command("adventure replay"))
	adventure_summary_md_button.pressed.connect(func() -> void: _send_adventure_command("adventure summary markdown"))
	adventure_summary_text_button.pressed.connect(func() -> void: _send_adventure_command("adventure summary text"))
	adventure_summary_json_button.pressed.connect(func() -> void: _send_adventure_command("adventure summary json"))

	btn_status.pressed.connect(func(): _send_command_immediate("status"))
	btn_inventory.pressed.connect(func(): _send_command_immediate("inventory"))
	btn_quests.pressed.connect(func(): _send_command_immediate("quests"))
	btn_policy.pressed.connect(func(): _send_command_immediate("server policy"))
	btn_n.pressed.connect(func(): _send_command_immediate("north"))
	btn_s.pressed.connect(func(): _send_command_immediate("south"))
	btn_e.pressed.connect(func(): _send_command_immediate("east"))
	btn_w.pressed.connect(func(): _send_command_immediate("west"))
	btn_nw.pressed.connect(func(): _send_command_immediate("northwest"))
	btn_ne.pressed.connect(func(): _send_command_immediate("northeast"))
	btn_sw.pressed.connect(func(): _send_command_immediate("southwest"))
	btn_se.pressed.connect(func(): _send_command_immediate("southeast"))
	btn_look.pressed.connect(func(): _send_command_immediate("look"))
	authoring_acquire_button.pressed.connect(_on_authoring_acquire_pressed)
	authoring_renew_button.pressed.connect(_on_authoring_renew_pressed)
	authoring_release_button.pressed.connect(_on_authoring_release_pressed)
	authoring_edit_button.pressed.connect(_on_authoring_edit_pressed)
	authoring_edit_stale_button.pressed.connect(_on_authoring_edit_stale_pressed)
	authoring_asset_input.text_submitted.connect(func(_text: String) -> void: _request_lock_status())

	log_view.meta_clicked.connect(_on_meta_clicked)
	inventory_list_label.meta_clicked.connect(_on_meta_clicked)
	journal_list_label.meta_clicked.connect(_on_meta_clicked)
	nearby_npcs_label.meta_clicked.connect(_on_meta_clicked)
	nearby_items_label.meta_clicked.connect(_on_meta_clicked)

	var is_mobile = OS.has_feature("mobile") or OS.get_name() in ["Android", "iOS"]
	_client_capabilities["mobile_variant"] = is_mobile
	mobile_controls.visible = is_mobile
	if is_mobile:
		Engine.max_fps = 30

	_bind_client_signals(tcp_client, "TCP")
	_bind_client_signals(ws_client, "WebSocket")
	_load_theme_catalog()
	_apply_theme("default")
	_refresh_authoring_status()
	_refresh_profile_status()
	_refresh_operator_actions()
	_refresh_policy_affordances()
	_sync_auto_reconnect_button()
	_refresh_network_labels()
	_refresh_startup_diagnostics_labels()
	_refresh_finite_adventure_catalog_picker()
	_refresh_finite_adventure_panel()
	keybindings_manager.load()
	# Intercept the window-close button so we can clear the crash-recovery marker.
	get_tree().set_auto_accept_quit(false)
	crash_recovery.restore_requested.connect(_on_crash_recovery_restore)
	crash_recovery.dismissed.connect(func() -> void: onboarding.show_if_first_run())
	char_create.name_submitted.connect(_on_char_name_submitted)
	_apply_launch_config()
	crash_recovery.check_and_show()
	if not crash_recovery.visible:
		onboarding.show_if_first_run()

func _process(_delta: float) -> void:
	_authoring_status_refresh_accum_s += _delta
	if _authoring_status_refresh_accum_s >= 0.25:
		_authoring_status_refresh_accum_s = 0.0
		_refresh_authoring_status()
	_tick_authoring_auto_renew(0.25)
	if _reconnect_pending:
		var now: int = Time.get_ticks_msec()
		if now >= _reconnect_deadline_msec:
			_reconnect_pending = false
			_network_telemetry["reconnect_state"] = "attempting"
			_refresh_network_labels()
			_on_connect_pressed()
		else:
			_refresh_network_labels()

func _on_connect_pressed() -> void:
	_manual_disconnect_requested = false
	_finite_adventure_catalog.clear()
	_finite_adventure_catalog_requested = false
	_latest_quests_payload.clear()
	_game_contract.clear()
	_refresh_game_contract_affordances()
	_refresh_finite_adventure_catalog_picker()
	var host := host_input.text.strip_edges()
	var port := int(port_input.text)
	_network_telemetry["connect_attempts"] = int(_network_telemetry.get("connect_attempts", 0)) + 1
	if _using_websocket():
		_network_telemetry["last_transport"] = "WebSocket"
		ws_client.connect_to_server(host, port)
	else:
		_network_telemetry["last_transport"] = "TCP"
		tcp_client.connect_to_server(host, port)
	_refresh_network_labels()

func _on_disconnect_pressed() -> void:
	_manual_disconnect_requested = true
	_cancel_reconnect()
	crash_recovery.clear_marker()
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify({"type": "disconnect"}))
	tcp_client.disconnect_from_server()
	ws_client.disconnect_from_server()
	_refresh_network_labels()

func _on_send_pressed() -> void:
	_submit_command()

func _on_auto_reconnect_toggled(pressed: bool) -> void:
	_set_auto_reconnect_enabled(pressed, true)

func _on_field_pulse_pressed() -> void:
	var field_id: String = field_id_input.text.strip_edges().to_lower()
	if field_id == "":
		field_id = "blight"
	var x: int = _safe_int(field_x_input.text, 4)
	var y: int = _safe_int(field_y_input.text, 4)
	var value: float = clamp(_safe_float(field_value_input.text, 1.0), 0.0, 1.0)
	var cmd := "field pulse %s %d %d %.2f" % [field_id, x, y, value]
	var envelope: Dictionary = parser.build_command_envelope(cmd, _client_capabilities.duplicate(true), _session_id)
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(envelope))
	_append_log("[b]> %s[/b]" % cmd)
	_refresh_network_labels()

func _on_command_submitted(_text: String) -> void:
	_submit_command()

func _on_gm_auth_pressed() -> void:
	var token: String = gm_auth_input.text.strip_edges()
	if token == "":
		_append_log("[color=orange]Enter a GM token first.[/color]")
		return
	_send_command_to_server("gm auth %s" % token, "gm auth ********")
	gm_auth_input.text = ""

func _input(event: InputEvent) -> void:
	if not event is InputEventKey:
		return
	var key_event := event as InputEventKey
	if not key_event.pressed:
		return
	# History navigation — only active while the command input has focus.
	if command_input.has_focus():
		if keybindings_manager.is_key_for_action("mud_history_prev", key_event.keycode):
			_history_navigate(-1)
			get_viewport().set_input_as_handled()
			return
		if keybindings_manager.is_key_for_action("mud_history_next", key_event.keycode):
			_history_navigate(1)
			get_viewport().set_input_as_handled()
			return
	# Global hotkeys (active regardless of focus).
	if keybindings_manager.is_key_for_action("mud_focus_input", key_event.keycode):
		command_input.grab_focus()
		get_viewport().set_input_as_handled()
		return
	if keybindings_manager.is_key_for_action("mud_scroll_up", key_event.keycode):
		var sb := log_view.get_v_scroll_bar()
		sb.value = max(sb.min_value, sb.value - sb.page * 0.5)
		get_viewport().set_input_as_handled()
		return
	if keybindings_manager.is_key_for_action("mud_scroll_down", key_event.keycode):
		var sb := log_view.get_v_scroll_bar()
		sb.value = min(sb.max_value - sb.page, sb.value + sb.page * 0.5)
		get_viewport().set_input_as_handled()

func _history_navigate(direction: int) -> void:
	if _command_history.is_empty():
		return
	if direction < 0:  # Up — step toward older commands.
		if _history_cursor == -1:
			_history_draft = command_input.text
			_history_cursor = _command_history.size() - 1
		else:
			_history_cursor = max(0, _history_cursor - 1)
	else:  # Down — step toward newer / exit history.
		if _history_cursor == -1:
			return
		_history_cursor += 1
		if _history_cursor >= _command_history.size():
			_history_cursor = -1
			command_input.text = _history_draft
			command_input.caret_column = command_input.text.length()
			return
	command_input.text = _command_history[_history_cursor]
	command_input.caret_column = command_input.text.length()

func _push_history(cmd: String) -> void:
	if _command_history.is_empty() or _command_history[-1] != cmd:
		_command_history.append(cmd)
		if _command_history.size() > HISTORY_MAX_SIZE:
			_command_history.remove_at(0)
	_history_cursor = -1
	_history_draft = ""

func _submit_command() -> void:
	var cmd := command_input.text.strip_edges()
	if cmd == "":
		return
	_push_history(cmd)
	if _maybe_send_asset_update_command(cmd):
		command_input.text = ""
		return
	if _maybe_send_lock_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_network_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_theme_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_accessibility_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_keybind_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_onboarding_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_gm_command(cmd):
		command_input.text = ""
		return
	if _maybe_handle_local_profile_command(cmd):
		command_input.text = ""
		return
	_warn_if_command_conflicts_with_policy(cmd)
	_send_command_to_server(cmd)
	command_input.text = ""
	_refresh_network_labels()

func _on_char_name_submitted(name: String) -> void:
	"""Send 'char create <name>' when the player confirms the creation dialog."""
	_send_command_to_server("char create %s" % name)

func _send_command_immediate(cmd: String) -> void:
	var old_text = command_input.text
	command_input.text = cmd
	_submit_command()
	if not command_input.text:
		command_input.text = old_text

func _send_command_to_server(cmd: String, display_cmd: String = "") -> void:
	var envelope: Dictionary = parser.build_command_envelope(cmd, _resolve_client_capabilities(cmd), _session_id)
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(envelope))
	var shown: String = display_cmd
	if shown == "":
		shown = cmd
	_append_log("[b]> %s[/b]" % shown)

func _warn_if_command_conflicts_with_policy(cmd: String) -> void:
	var normalized: String = cmd.strip_edges().to_lower()
	if normalized == "":
		return
	var world_mutation_mode: String = str(_server_profile_modes.get("world_mutation", "")).to_lower()
	if world_mutation_mode == "readonly":
		if normalized.begins_with("@dig") or normalized.begins_with("@edit"):
			_append_log("[color=orange]Server policy: world mutation is readonly; this command may be rejected.[/color]")
	var combat_mode: String = str(_server_profile_modes.get("combat", "")).to_lower()
	if combat_mode == "disabled":
		if normalized.begins_with("attack ") or normalized == "attack":
			_append_log("[color=orange]Server policy: combat is disabled; this command may be rejected.[/color]")

func _refresh_policy_affordances() -> void:
	var world_mutation_mode: String = str(_server_profile_modes.get("world_mutation", "")).to_lower()
	var can_mutate_world: bool = world_mutation_mode != "readonly"
	var authoring_mode: String = str(_server_profile_modes.get("authoring", "")).to_lower()
	var requires_gm: bool = authoring_mode == "gm_only" or bool(_server_auth_policy.get("authoring_requires_gm", false))
	var authoring_allowed_by_profile: bool = authoring_mode == "" or authoring_mode == "enabled" or authoring_mode == "gm_only"
	var can_author: bool = can_mutate_world and authoring_allowed_by_profile and ((not requires_gm) or _gm_granted)
	authoring_acquire_button.disabled = not can_author
	authoring_release_button.disabled = not can_author
	authoring_renew_button.disabled = not can_author
	authoring_edit_button.disabled = not can_author
	authoring_edit_stale_button.disabled = not can_author
	field_pulse_button.disabled = not can_mutate_world
	var can_attempt_gm_auth: bool = _gm_auth_configured and _gm_auth_cooldown_seconds <= 0 and (not _gm_granted)
	gm_auth_button.disabled = not can_attempt_gm_auth
	gm_auth_input.editable = can_attempt_gm_auth
	_refresh_operator_actions()

func _operator_selected_domain() -> String:
	var selected_idx: int = operator_domain_select.get_selected()
	if selected_idx < 0:
		return "Policy"
	return operator_domain_select.get_item_text(selected_idx)

func _refresh_operator_actions() -> void:
	var domain: String = _operator_selected_domain()
	var actions_variant: Variant = _operator_action_maps.get(domain, [])
	var actions: Array = actions_variant as Array
	operator_action_select.clear()
	for action_variant in actions:
		operator_action_select.add_item(str(action_variant))
	operator_action_select.disabled = actions.is_empty()
	if not actions.is_empty():
		operator_action_select.select(0)
	_refresh_operator_values()
	_update_operator_palette_state()

func _operator_selected_action() -> String:
	var selected_idx: int = operator_action_select.get_selected()
	if selected_idx >= 0 and selected_idx < operator_action_select.get_item_count():
		return operator_action_select.get_item_text(selected_idx)
	return ""

func _operator_catalog_key(domain: String, action: String) -> String:
	return "%s:%s" % [domain, action]

func _operator_requirements_for(domain: String, action: String) -> Dictionary:
	var requirements_value: Variant = _operator_catalog_requirements.get(_operator_catalog_key(domain, action), {})
	if typeof(requirements_value) == TYPE_DICTIONARY:
		return requirements_value as Dictionary
	return {}

func _session_has_entitlement(entitlement_name: String) -> bool:
	var wanted: String = entitlement_name.strip_edges()
	if wanted == "":
		return true
	if not _session_entitlements_known:
		return true
	for entitlement in _session_entitlements:
		if str(entitlement) == wanted:
			return true
	return false

func _refresh_operator_values() -> void:
	var domain: String = _operator_selected_domain()
	var action: String = _operator_selected_action()
	operator_value_select.clear()
	var catalog_key: String = _operator_catalog_key(domain, action)
	var server_options_value: Variant = _operator_catalog_value_options.get(catalog_key, [])
	var used_server_options: bool = false
	if typeof(server_options_value) == TYPE_ARRAY:
		for option_variant in server_options_value as Array:
			var option_name: String = str(option_variant).strip_edges()
			if option_name != "":
				operator_value_select.add_item(option_name)
				used_server_options = true
	if not used_server_options and domain == "Profiles" and action == "Apply Selected":
		for preset_name: String in _known_profile_presets:
			operator_value_select.add_item(preset_name)
	elif not used_server_options and domain == "World Effects" and action == "Use Provider":
		var providers_value: Variant = _world_effects_status.get("available_providers", [])
		if typeof(providers_value) == TYPE_ARRAY:
			for provider_variant in providers_value as Array:
				var provider_name: String = str(provider_variant).strip_edges()
				if provider_name != "":
					operator_value_select.add_item(provider_name)
	operator_value_select.disabled = operator_value_select.get_item_count() == 0
	if operator_value_select.get_item_count() > 0:
		operator_value_select.select(0)

func _update_operator_palette_state() -> void:
	var connected: bool = _is_connected_to_game_server()
	var domain: String = _operator_selected_domain()
	var selected_action: String = _operator_selected_action()
	var requires_connected: bool = selected_action != ""
	var requirements: Dictionary = _operator_requirements_for(domain, selected_action)
	var gm_required: bool = bool(requirements.get("requires_gm", false))
	var required_entitlement: String = str(requirements.get("requires_entitlement", "")).strip_edges()
	var can_run: bool = connected and requires_connected
	if gm_required and not _gm_granted:
		can_run = false
	if required_entitlement != "" and not _session_has_entitlement(required_entitlement):
		can_run = false
	operator_run_button.disabled = not can_run
	operator_arg_input.editable = connected
	var hint: String = "Operator: choose domain/action, then Run."
	if not connected:
		hint = "Operator: connect first."
	elif gm_required and not _gm_granted:
		hint = "Operator: GM session required for this action."
	elif required_entitlement != "" and not _session_entitlements_known:
		hint = "Operator: entitlement state not published yet; action may still be denied by server."
	elif required_entitlement != "" and not _session_has_entitlement(required_entitlement):
		hint = "Operator: missing entitlement '%s' for this action." % required_entitlement
	elif domain == "World Effects" and selected_action == "Use Provider":
		hint = "Operator: choose provider from list (or type override), then Run."
	elif domain == "Profiles" and selected_action == "Apply Selected":
		hint = "Operator: choose preset from list (or type override), then Run."
	operator_status_label.text = hint

func _on_operator_domain_selected(_index: int) -> void:
	_refresh_operator_actions()

func _on_operator_action_selected(_index: int) -> void:
	_refresh_operator_values()
	_update_operator_palette_state()

func _operator_selected_value() -> String:
	var idx: int = operator_value_select.get_selected()
	if idx >= 0 and idx < operator_value_select.get_item_count():
		return operator_value_select.get_item_text(idx).strip_edges()
	return ""

func _on_operator_run_pressed() -> void:
	var domain: String = _operator_selected_domain()
	var action: String = _operator_selected_action()
	if action == "":
		return
	var requirements: Dictionary = _operator_requirements_for(domain, action)
	if bool(requirements.get("requires_gm", false)) and not _gm_granted:
		_append_log("[color=orange]GM session required for this operator action.[/color]")
		_update_operator_palette_state()
		return
	var required_entitlement: String = str(requirements.get("requires_entitlement", "")).strip_edges()
	if required_entitlement != "" and not _session_has_entitlement(required_entitlement):
		_append_log("[color=orange]Missing entitlement for this operator action: %s[/color]" % required_entitlement)
		_update_operator_palette_state()
		return
	var arg: String = operator_arg_input.text.strip_edges()
	var picked_value: String = _operator_selected_value()
	if domain == "Policy":
		_send_command_immediate("server policy")
	elif domain == "Profiles":
		if action == "List Profiles":
			_request_profile_presets()
		elif action == "Apply Selected":
			var selected_preset: String = arg if arg != "" else picked_value
			if selected_preset != "":
				_pending_profile_apply_preset = selected_preset
			_on_profile_apply_pressed()
	elif domain == "World Effects":
		if action == "Providers":
			_send_command_immediate("effects providers")
		elif action == "Status":
			_send_command_immediate("effects status")
		elif action == "Use Provider":
			var provider_id: String = arg if arg != "" else picked_value
			if provider_id == "":
				_append_log("[color=orange]Provide provider id in operator arg input first.[/color]")
				return
			_send_command_immediate("effects use %s" % provider_id)
	elif domain == "Auth":
		if action == "GM Status":
			_send_command_immediate("gm status")
		elif action == "GM Deauth":
			_send_command_immediate("gm deauth")
		elif action == "GM Auth":
			var token: String = arg
			if token == "":
				token = gm_auth_input.text.strip_edges()
			if token == "":
				_append_log("[color=orange]Provide GM token in arg input or GM token field first.[/color]")
				return
			_send_command_to_server("gm auth %s" % token, "gm auth ********")
	elif domain == "Authoring":
		if action == "Lock Status":
			_request_lock_status()
		elif action == "Acquire Lock":
			_on_authoring_acquire_pressed()
		elif action == "Renew Lock":
			_on_authoring_renew_pressed()
		elif action == "Release Lock":
			_on_authoring_release_pressed()
		elif action == "Edit Next":
			_on_authoring_edit_pressed()
		elif action == "Edit Stale":
			_on_authoring_edit_stale_pressed()
	_update_operator_palette_state()

func _request_profile_presets() -> void:
	if not _is_connected_to_game_server():
		return
	var envelope: Dictionary = parser.build_command_envelope("profile list", _resolve_client_capabilities("profile list"), _session_id)
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(envelope))
	_refresh_network_labels()

func _extract_profile_preset_from_path(path_value: String) -> String:
	var normalized: String = path_value.strip_edges().replace("\\", "/")
	if normalized == "":
		return ""
	var file_name: String = normalized.get_file()
	if file_name.ends_with(".profile.json"):
		return file_name.trim_suffix(".profile.json")
	return ""

func _sync_profile_select_from_known_presets() -> void:
	profile_preset_select.clear()
	for preset_name: String in _known_profile_presets:
		profile_preset_select.add_item(preset_name)
	if _known_profile_presets.is_empty():
		profile_preset_select.disabled = true
		return
	profile_preset_select.disabled = false
	var selected_index: int = 0
	for idx in range(_known_profile_presets.size()):
		if _known_profile_presets[idx] == _active_profile_preset:
			selected_index = idx
			break
	profile_preset_select.select(selected_index)

func _refresh_profile_status() -> void:
	var active_text: String = _active_profile_preset if _active_profile_preset != "" else "(unknown)"
	var pending_text: String = _pending_profile_apply_preset if _pending_profile_apply_preset != "" else "none"
	profile_status_label.text = "Profile: active %s | pending %s" % [active_text, pending_text]
	var can_apply: bool = _is_connected_to_game_server() and not _known_profile_presets.is_empty()
	profile_apply_button.disabled = not can_apply
	profile_refresh_button.disabled = not _is_connected_to_game_server()
	profile_cancel_button.disabled = _pending_profile_apply_preset == ""
	if _pending_profile_apply_preset == "":
		profile_apply_button.text = "Apply Selected"
	else:
		profile_apply_button.text = "Confirm Apply"
	_refresh_operator_values()
	_update_operator_palette_state()

func _on_profile_selected(index: int) -> void:
	if index < 0 or index >= _known_profile_presets.size():
		return
	var preset: String = _known_profile_presets[index]
	_pending_profile_apply_preset = preset
	_refresh_profile_status()

func _on_profile_refresh_pressed() -> void:
	_request_profile_presets()

func _on_profile_cancel_pressed() -> void:
	if _pending_profile_apply_preset != "":
		_append_log("[color=yellow]Cancelled profile apply: %s[/color]" % _pending_profile_apply_preset)
	_pending_profile_apply_preset = ""
	_refresh_profile_status()

func _on_profile_apply_pressed() -> void:
	var target_preset: String = ""
	if not _known_profile_presets.is_empty():
		var idx: int = profile_preset_select.get_selected()
		if idx >= 0 and idx < _known_profile_presets.size():
			target_preset = _known_profile_presets[idx]
	if target_preset == "":
		_append_log("[color=orange]No profile selected to apply.[/color]")
		_refresh_profile_status()
		return
	if _pending_profile_apply_preset != target_preset:
		_pending_profile_apply_preset = target_preset
		_append_log("[color=yellow]Pending profile apply: %s[/color]" % target_preset)
		_append_log("[color=yellow]Click Apply Selected again (or run 'profile apply confirm') to confirm.[/color]")
		_refresh_profile_status()
		return
	_append_log("[color=yellow]Confirming profile apply: %s[/color]" % target_preset)
	_send_command_to_server("profile apply %s" % target_preset)
	_pending_profile_apply_preset = ""
	_refresh_profile_status()

func _maybe_handle_local_profile_command(cmd: String) -> bool:
	var normalized: String = cmd.strip_edges().to_lower()
	if normalized == "profile help":
		_append_log("[color=aqua]Profile commands:[/color]")
		_append_log("[color=aqua]  profile list[/color]")
		_append_log("[color=aqua]  profile apply <preset>[/color]")
		_append_log("[color=aqua]  profile apply <index> (from latest list)[/color]")
		_append_log("[color=aqua]  profile apply confirm[/color]")
		_append_log("[color=aqua]  profile apply cancel[/color]")
		return true
	if normalized == "profile list" or normalized == "profiles":
		_append_log("[color=aqua]Tip: use profile apply <preset>, then profile apply confirm.[/color]")
		_request_profile_presets()
		return true
	if normalized == "profile apply confirm":
		if _pending_profile_apply_preset == "":
			_append_log("[color=orange]No pending profile apply request.[/color]")
			return true
		var final_cmd: String = "profile apply %s" % _pending_profile_apply_preset
		_pending_profile_apply_preset = ""
		_send_command_to_server(final_cmd)
		_refresh_profile_status()
		return true
	if normalized == "profile apply cancel":
		if _pending_profile_apply_preset == "":
			_append_log("[color=yellow]No pending profile apply request.[/color]")
		else:
			_append_log("[color=yellow]Cancelled profile apply: %s[/color]" % _pending_profile_apply_preset)
		_pending_profile_apply_preset = ""
		_refresh_profile_status()
		return true
	if normalized.begins_with("profile apply "):
		var parts: PackedStringArray = normalized.split(" ", false)
		if parts.size() < 3:
			_append_log("[color=orange]Usage: profile apply <preset_name>[/color]")
			return true
		var preset: String = parts[2].strip_edges()
		if preset == "":
			_append_log("[color=orange]Usage: profile apply <preset_name>[/color]")
			return true
		if preset.is_valid_int():
			var idx: int = int(preset) - 1
			if idx >= 0 and idx < _known_profile_presets.size():
				preset = _known_profile_presets[idx]
			else:
				_append_log("[color=orange]Unknown preset index %s. Run 'profile list' first.[/color]" % preset)
				return true
		_pending_profile_apply_preset = preset
		_append_log("[color=yellow]Pending profile apply: %s[/color]" % preset)
		_append_log("[color=yellow]Run 'profile apply confirm' to proceed or 'profile apply cancel'.[/color]")
		_refresh_profile_status()
		return true
	return false

func _maybe_handle_local_gm_command(cmd: String) -> bool:
	var normalized: String = cmd.strip_edges().to_lower()
	if normalized == "gm help":
		_append_log("[color=aqua]GM commands:[/color]")
		_append_log("[color=aqua]  gm auth <token>[/color]")
		_append_log("[color=aqua]  gm status[/color]")
		_append_log("[color=aqua]  gm deauth[/color]")
		_append_log("[color=aqua]Tip: token input is redacted in the local log.[/color]")
		return true
	if normalized == "gm status":
		_send_command_to_server("gm status")
		return true
	if normalized == "gm deauth":
		_send_command_to_server("gm deauth")
		return true
	if normalized == "gm auth":
		_append_log("[color=orange]Usage: gm auth <token>[/color]")
		return true
	if normalized.begins_with("gm auth "):
		var token: String = cmd.strip_edges().substr(8).strip_edges()
		if token == "":
			_append_log("[color=orange]Usage: gm auth <token>[/color]")
			return true
		_send_command_to_server("gm auth %s" % token, "gm auth ********")
		return true
	return false

func _authoring_asset_id() -> String:
	return authoring_asset_input.text.strip_edges()

func _on_authoring_acquire_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	_send_command_immediate("@dig %s" % asset_id)

func _on_authoring_renew_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	_send_command_immediate("@dig %s renew" % asset_id)

func _on_authoring_release_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	_authoring_auto_renew_accum_s = 0.0
	_authoring_last_auto_renew_asset_id = ""
	_send_command_immediate("@dig %s release" % asset_id)

func _on_authoring_edit_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	if not _ensure_lock_before_edit(asset_id):
		return
	_send_command_immediate("@edit %s next" % asset_id)

func _on_authoring_edit_stale_pressed() -> void:
	var asset_id: String = _authoring_asset_id()
	if not _ensure_lock_before_edit(asset_id):
		return
	_send_command_immediate("@edit %s stale" % asset_id)

func _request_lock_status() -> void:
	if not (tcp_client.is_connected_to_server() or ws_client.is_connected_to_server()):
		return
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(parser.build_lock_status_envelope(_session_id)))
	_refresh_network_labels()

func _is_connected_to_game_server() -> bool:
	return tcp_client.is_connected_to_server() or ws_client.is_connected_to_server()

func _current_authoring_asset_id() -> String:
	var aid: String = str(_authoring_panel_state.get("asset_id", "")).strip_edges()
	if aid == "":
		aid = authoring_asset_input.text.strip_edges()
	return aid

func _authoring_lock_is_mine(asset_id: String) -> bool:
	var aid: String = asset_id.strip_edges()
	if aid == "":
		return false
	if not _authoring_lock_by_asset.has(aid):
		return false
	var lock_info: Dictionary = _authoring_lock_by_asset.get(aid, {}) as Dictionary
	var owner: String = str(lock_info.get("owner_session_id", "")).strip_edges()
	return owner != "" and owner == _session_id

func _ensure_lock_before_edit(asset_id: String) -> bool:
	if _authoring_lock_is_mine(asset_id):
		return true
	_append_log("[color=orange]You do not currently hold the edit lock for '%s'. Acquire lock first.[/color]" % asset_id)
	_request_lock_status()
	return false

func _tick_authoring_auto_renew(delta_s: float) -> void:
	if not _authoring_auto_renew_enabled:
		return
	if not _is_connected_to_game_server():
		_authoring_auto_renew_accum_s = 0.0
		return
	var active_asset_id: String = _current_authoring_asset_id()
	if not _authoring_lock_is_mine(active_asset_id):
		_authoring_auto_renew_accum_s = 0.0
		_authoring_last_auto_renew_asset_id = ""
		return
	_authoring_auto_renew_accum_s += max(0.0, delta_s)
	if _authoring_auto_renew_accum_s < _authoring_auto_renew_interval_s:
		return
	_authoring_auto_renew_accum_s = 0.0
	_authoring_last_auto_renew_asset_id = active_asset_id
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(parser.build_lock_renew_envelope(active_asset_id, _session_id)))
	_refresh_network_labels()

func _apply_lock_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	_authoring_lock_by_asset.clear()
	var active_variant: Variant = body.get("active_locks", [])
	if typeof(active_variant) == TYPE_ARRAY:
		for entry_variant in active_variant as Array:
			if typeof(entry_variant) != TYPE_DICTIONARY:
				continue
			var entry: Dictionary = entry_variant as Dictionary
			var aid: String = str(entry.get("asset_id", "")).strip_edges()
			if aid == "":
				continue
			_authoring_lock_by_asset[aid] = {
				"owner_session_id": str(entry.get("owner_session_id", "")),
				"expires_at": float(entry.get("expires_at", 0.0))
			}
	var active_asset_id: String = _current_authoring_asset_id()
	if not _authoring_lock_is_mine(active_asset_id):
		_authoring_auto_renew_accum_s = 0.0
		_authoring_last_auto_renew_asset_id = ""
	_refresh_authoring_status()

func _apply_lock_delta_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var aid: String = str(body.get("asset_id", "")).strip_edges()
	if aid == "":
		return
	var state: String = str(body.get("state", "")).to_lower()
	if state == "released" or state == "released_disconnect":
		_authoring_lock_by_asset.erase(aid)
	else:
		_authoring_lock_by_asset[aid] = {
			"owner_session_id": str(body.get("owner_session_id", "")),
			"expires_at": float(body.get("expires_at", 0.0))
		}
	if not _authoring_lock_is_mine(aid):
		_authoring_auto_renew_accum_s = 0.0
		if _authoring_last_auto_renew_asset_id == aid:
			_authoring_last_auto_renew_asset_id = ""
	_refresh_authoring_status(aid)

func _refresh_authoring_status(preferred_asset_id: String = "") -> void:
	var aid: String = preferred_asset_id.strip_edges()
	if aid == "":
		aid = authoring_asset_input.text.strip_edges()

	var revision_text: String = "--"
	if _asset_revisions.has(aid):
		revision_text = str(int(_asset_revisions.get(aid, 0)))

	var lock_text: String = "none"
	var lock_state: String = "none"
	var lock_owner: String = ""
	var is_mine: bool = false
	var remain_s: float = 0.0
	var expires_at_s: float = 0.0
	if _authoring_lock_by_asset.has(aid):
		var lock_info: Dictionary = _authoring_lock_by_asset.get(aid, {}) as Dictionary
		var owner: String = str(lock_info.get("owner_session_id", "")).strip_edges()
		if owner == "":
			owner = "unknown"
		lock_owner = owner
		var owner_short: String = owner.left(8)
		var expires_at: float = float(lock_info.get("expires_at", 0.0))
		var remain: float = max(0.0, expires_at - Time.get_unix_time_from_system())
		remain_s = remain
		expires_at_s = expires_at
		is_mine = owner == _session_id
		lock_state = "mine" if is_mine else "theirs"
		lock_text = "owner %s (%.1fs)" % [owner_short, remain]

	_authoring_panel_state = {
		"asset_id": aid,
		"lock_state": lock_state,
		"lock_owner": lock_owner,
		"lock_expires_at": expires_at_s,
		"lock_remaining_s": remain_s,
		"is_mine": is_mine
	}

	var access_summary: String = _authoring_access_summary()
	authoring_status_label.text = "Authoring: asset %s  lock %s (%s)  rev %s  |  %s" % [aid, lock_text, lock_state, revision_text, access_summary]

func _authoring_access_summary() -> String:
	var world_mutation_mode: String = str(_server_profile_modes.get("world_mutation", "")).to_lower()
	if world_mutation_mode == "readonly":
		return "world readonly"
	var authoring_mode: String = str(_server_profile_modes.get("authoring", "")).to_lower()
	if authoring_mode == "disabled":
		return "authoring disabled"
	var requires_gm: bool = authoring_mode == "gm_only" or bool(_server_auth_policy.get("authoring_requires_gm", false))
	if requires_gm:
		if _gm_granted:
			return "authoring enabled (gm)"
		if not _gm_auth_configured:
			return "gm auth unavailable"
		if _gm_auth_cooldown_seconds > 0:
			return "gm cooldown %ds" % _gm_auth_cooldown_seconds
		return "gm auth required"
	return "authoring enabled"

func _on_meta_clicked(meta: Variant) -> void:
	var cmd = str(meta)
	if cmd.begins_with("cmd:"):
		_send_command_immediate(cmd.substr(4))

func _on_line_received(line: String) -> void:
	_network_telemetry["lines_received"] = int(_network_telemetry.get("lines_received", 0)) + 1
	_refresh_network_labels()
	var event: Dictionary = parser.parse_event(line)
	var event_type: String = str(event.get("type", "unknown"))
	var payload: Variant = event.get("payload", "")
	if event_type == "hello":
		_append_log("[color=aqua]HELLO[/color] %s" % JSON.stringify(payload))
		if typeof(payload) == TYPE_DICTIONARY:
			var body: Dictionary = payload as Dictionary
			var operator_catalog_value: Variant = body.get("operator_catalog", {})
			if typeof(operator_catalog_value) == TYPE_DICTIONARY:
				_apply_operator_catalog_payload(operator_catalog_value as Dictionary)
			var startup_diag_value: Variant = body.get("startup_diagnostics", {})
			if typeof(startup_diag_value) == TYPE_DICTIONARY:
				_apply_startup_diagnostics_payload(startup_diag_value as Dictionary)
			var sid: String = str(body.get("session_id", "")).strip_edges()
			if sid != "":
				_session_id = sid
				_resume_session_id = sid
				crash_recovery.record_session_id(sid)
				_request_lock_status()
				_request_profile_presets()
			# Show character creation dialog if the server requires it and this
			# session has no character yet.
			var already_has_char: bool = bool(body.get("has_character", false))
			var server_policy_val: Variant = body.get("server_policy", {})
			var char_creation_required: bool = false
			if typeof(server_policy_val) == TYPE_DICTIONARY:
				char_creation_required = bool((server_policy_val as Dictionary).get("require_character_creation", false))
			if char_creation_required and not already_has_char:
				char_create.show_dialog()
	elif event_type == "session_resumed":
		_append_log("[color=green]Session resumed.[/color]")
		if typeof(payload) == TYPE_DICTIONARY:
			var resumed_body: Dictionary = payload as Dictionary
			var resumed_id: String = str(resumed_body.get("session_id", "")).strip_edges()
			if resumed_id != "":
				_session_id = resumed_id
				_resume_session_id = resumed_id
				_request_lock_status()
				_request_profile_presets()
	elif event_type == "lock_state":
		_apply_lock_state_payload(payload)
		_append_log("[color=yellow]Lock state: %s[/color]" % JSON.stringify(payload))
	elif event_type == "lock_state_delta":
		_apply_lock_delta_payload(payload)
		_append_log("[color=yellow]Lock delta: %s[/color]" % JSON.stringify(payload))
	elif event_type == "protocol_mismatch":
		_apply_degraded_mode("Protocol mismatch with server; enabling compatibility mode.")
	elif event_type == "text":
		_append_log(_render_text_payload(payload))
		# Defensive fallback: if the server tells us no character exists, surface
		# the creation dialog even if the hello trigger was missed.
		var text_body: String = ""
		if typeof(payload) == TYPE_DICTIONARY:
			text_body = str((payload as Dictionary).get("text", ""))
		elif typeof(payload) == TYPE_STRING:
			text_body = str(payload)
		if "No character yet" in text_body and not char_create.visible:
			char_create.show_dialog()
	elif event_type == "error":
		_append_log("[color=red]%s[/color]" % str(payload))
	elif event_type == "goodbye":
		crash_recovery.clear_marker()
		_append_log("[color=yellow]Server closed session.[/color]")
	elif event_type == "asset":
		_handle_asset_payload(payload)
	elif event_type == "status":
		_handle_status_payload(payload)
	elif event_type == "inventory":
		_handle_inventory_payload(payload)
	elif event_type == "quests":
		_handle_quests_payload(payload)
	elif event_type == "nearby":
		_handle_nearby_payload(payload)
	elif event_type == "world_state":
		_handle_world_state_payload(payload)
	elif event_type == "world_effects_status":
		_handle_world_effects_status_payload(payload)
	elif event_type == "world_effects_providers":
		_handle_world_effects_providers_payload(payload)
	elif event_type == "server_policy":
		_handle_server_policy_payload(payload)
	elif event_type == "finite_adventure_state":
		_handle_finite_adventure_state_payload(payload)
	elif event_type == "finite_adventure_summary":
		_handle_finite_adventure_summary_payload(payload)
	elif event_type == "finite_adventure_report":
		_handle_finite_adventure_report_payload(payload)
	elif event_type == "finite_adventure_catalog":
		_handle_finite_adventure_catalog_payload(payload)
	elif event_type == "audit_result":
		_handle_audit_result_payload(payload)
	elif event_type == "profile_presets":
		_handle_profile_presets_payload(payload)
	elif event_type == "auth_state":
		_handle_auth_state_payload(payload)
	elif event_type == "asset_update_accepted":
		_append_log("[color=green]Asset update accepted: %s[/color]" % JSON.stringify(payload))
	elif event_type == "asset_update_rejected":
		_append_log("[color=orange]Asset update rejected: %s[/color]" % JSON.stringify(payload))
	elif event_type == "lock_acquired":
		_append_log("[color=green]Lock acquired: %s[/color]" % JSON.stringify(payload))
	elif event_type == "lock_released":
		_append_log("[color=yellow]Lock released: %s[/color]" % JSON.stringify(payload))
	elif event_type == "lock_renewed":
		_append_log("[color=green]Lock renewed: %s[/color]" % JSON.stringify(payload))
	elif event_type == "lock_denied":
		_append_log("[color=orange]Lock denied: %s[/color]" % JSON.stringify(payload))
	else:
		_append_log("[i]%s[/i] %s" % [event_type, JSON.stringify(payload)])

func _append_log(text: String) -> void:
	log_view.append_text(text + "\n")

func _handle_server_policy_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		_append_log("[color=orange]Server policy payload malformed.[/color]")
		server_policy_summary_label.text = "Profile: malformed payload"
		server_policy_modes_label.text = "Modes: --"
		server_policy_providers_label.text = "Providers: --"
		server_policy_warnings_label.text = "Warnings: payload invalid"
		startup_diagnostics_title_label.text = "Startup Diagnostics"
		startup_diagnostics_summary_label.text = "Warnings: unavailable  Fail-on-warning codes: unavailable"
		startup_diagnostics_detail_label.text = "Fixture: unavailable  Data root: unavailable"
		_server_profile_modes.clear()
		_refresh_policy_affordances()
		return
	var body: Dictionary = payload as Dictionary
	var startup_diag_value: Variant = body.get("startup_diagnostics", {})
	if typeof(startup_diag_value) == TYPE_DICTIONARY:
		_apply_startup_diagnostics_payload(startup_diag_value as Dictionary)
	var operator_catalog_value: Variant = body.get("operator_catalog", {})
	if typeof(operator_catalog_value) == TYPE_DICTIONARY:
		_apply_operator_catalog_payload(operator_catalog_value as Dictionary)
	var lines: PackedStringArray = PackedStringArray()
	lines.append("[b][color=aqua]Server Policy[/color][/b]")

	var profile_source: String = str(body.get("profile_source_path", "")).strip_edges()
	if profile_source == "":
		profile_source = "(default runtime profile)"
	_active_profile_path = profile_source
	var active_from_policy: String = _extract_profile_preset_from_path(profile_source)
	if active_from_policy != "":
		_active_profile_preset = active_from_policy
		if _pending_profile_apply_preset == active_from_policy:
			_pending_profile_apply_preset = ""
	server_policy_summary_label.text = "Profile: %s" % profile_source
	lines.append("Profile: %s" % profile_source)

	var warnings_value: Variant = body.get("boot_warnings", [])
	var warning_lines: PackedStringArray = PackedStringArray()
	if typeof(warnings_value) == TYPE_ARRAY:
		var warnings: Array = warnings_value as Array
		if warnings.is_empty():
			lines.append("Warnings: none")
			server_policy_warnings_label.text = "Warnings: none"
		else:
			lines.append("Warnings:")
			for warning_value: Variant in warnings:
				var warning_text: String = str(warning_value)
				lines.append("- %s" % warning_text)
				warning_lines.append(warning_text)
			server_policy_warnings_label.text = "Warnings: %s" % " | ".join(warning_lines)
	else:
		lines.append("Warnings: (unavailable)")
		server_policy_warnings_label.text = "Warnings: unavailable"

	if not _startup_diagnostics.is_empty():
		var diag_warning_count: int = int(_startup_diagnostics.get("warning_count", 0))
		var fail_codes_value: Variant = _startup_diagnostics.get("boot_warning_fail_codes", [])
		var fail_codes_count: int = 0
		if typeof(fail_codes_value) == TYPE_ARRAY:
			fail_codes_count = (fail_codes_value as Array).size()
		lines.append("Startup diagnostics: warnings=%d fail_codes=%d" % [diag_warning_count, fail_codes_count])
		var current_warning_line: String = server_policy_warnings_label.text
		server_policy_warnings_label.text = "%s | diag:%d warn, %d fail-codes" % [
			current_warning_line,
			diag_warning_count,
			fail_codes_count
		]

	var policy_value: Variant = body.get("server_policy", {})
	if typeof(policy_value) == TYPE_DICTIONARY:
		var policy: Dictionary = policy_value as Dictionary
		var content_set_value: Variant = policy.get("content_set", {})
		if typeof(content_set_value) == TYPE_DICTIONARY:
			var contract_value: Variant = (content_set_value as Dictionary).get("game_contract", {})
			_game_contract = (contract_value as Dictionary).duplicate(true) if typeof(contract_value) == TYPE_DICTIONARY else {}
		else:
			_game_contract.clear()
		var modes_value: Variant = policy.get("profile_modes", {})
		if typeof(modes_value) == TYPE_DICTIONARY:
			var modes: Dictionary = modes_value as Dictionary
			_server_profile_modes = modes.duplicate(true)
			server_policy_modes_label.text = "Modes: %s" % JSON.stringify(modes)
			lines.append("Modes: %s" % JSON.stringify(modes))
			if str(_server_profile_modes.get("world", "")) != "finite_adventure":
				_finite_adventure_catalog.clear()
				_finite_adventure_catalog_requested = false
				_refresh_finite_adventure_catalog_picker()
		else:
			_server_profile_modes.clear()
			server_policy_modes_label.text = "Modes: unavailable"
		var flags_value: Variant = policy.get("feature_flags", {})
		if typeof(flags_value) == TYPE_DICTIONARY:
			var flags: Dictionary = flags_value as Dictionary
			lines.append("Flags: %s" % JSON.stringify(flags))
		var adventure_policy_value: Variant = policy.get("adventure_policy", {})
		if typeof(adventure_policy_value) == TYPE_DICTIONARY:
			var adventure_policy: Dictionary = adventure_policy_value as Dictionary
			lines.append("Adventure policy: %s" % JSON.stringify(adventure_policy))
			var world_mode: String = str(_server_profile_modes.get("world", ""))
			if world_mode == "finite_adventure" and _is_connected_to_game_server() and _finite_adventure_catalog.is_empty() and (not _finite_adventure_catalog_requested):
				_request_finite_adventure_catalog()
		var auth_policy_value: Variant = policy.get("auth_policy", {})
		if typeof(auth_policy_value) == TYPE_DICTIONARY:
			_server_auth_policy = (auth_policy_value as Dictionary).duplicate(true)
			lines.append("Auth policy: %s" % JSON.stringify(_server_auth_policy))
		var providers_value: Variant = policy.get("active_providers", {})
		if typeof(providers_value) == TYPE_DICTIONARY:
			var providers: Dictionary = providers_value as Dictionary
			server_policy_providers_label.text = "Providers: %s" % JSON.stringify(providers)
			lines.append("Providers: %s" % JSON.stringify(providers))
		else:
			server_policy_providers_label.text = "Providers: unavailable"
	else:
		lines.append("Policy: (unavailable)")
		_server_profile_modes.clear()
		server_policy_modes_label.text = "Modes: unavailable"
		server_policy_providers_label.text = "Providers: unavailable"

	_refresh_game_contract_affordances()
	_refresh_policy_affordances()
	_refresh_profile_status()
	_append_log("\n".join(lines))

func _apply_startup_diagnostics_payload(payload: Dictionary) -> void:
	_startup_diagnostics = payload.duplicate(true)
	_refresh_startup_diagnostics_labels()

func _refresh_startup_diagnostics_labels() -> void:
	startup_diagnostics_title_label.text = "Startup Diagnostics"
	if _startup_diagnostics.is_empty():
		startup_diagnostics_summary_label.text = "Warnings: --  Fail-on-warning codes: --"
		startup_diagnostics_detail_label.text = "Fixture: --  Data root: --"
		return

	var warning_count: int = int(_startup_diagnostics.get("warning_count", 0))
	var fail_codes_value: Variant = _startup_diagnostics.get("boot_warning_fail_codes", [])
	var fail_codes_count: int = 0
	if typeof(fail_codes_value) == TYPE_ARRAY:
		fail_codes_count = (fail_codes_value as Array).size()
	startup_diagnostics_summary_label.text = "Warnings: %d  Fail-on-warning codes: %d" % [
		warning_count,
		fail_codes_count
	]

	var fixture_marker: String = str(_startup_diagnostics.get("fixture_refresh_marker", "")).strip_edges()
	if fixture_marker == "":
		fixture_marker = "none"
	var data_root: String = str(_startup_diagnostics.get("data_root", "")).strip_edges()
	if data_root == "":
		data_root = "(default)"
	startup_diagnostics_detail_label.text = "Fixture: %s  Data root: %s" % [fixture_marker, data_root]

func _game_system_enabled(system_name: String) -> bool:
	# A missing contract means an older server: preserve its existing UI rather
	# than guessing which mechanics it supports.
	if _game_contract.is_empty():
		return true
	var systems_value: Variant = _game_contract.get("systems", {})
	if typeof(systems_value) != TYPE_DICTIONARY:
		return true
	return bool((systems_value as Dictionary).get(system_name, false))

func _game_status_field_enabled(field_name: String) -> bool:
	if _game_contract.is_empty():
		return true
	var fields_value: Variant = _game_contract.get("status_fields", [])
	if typeof(fields_value) != TYPE_ARRAY:
		return false
	return (fields_value as Array).has(field_name)

func _refresh_game_contract_affordances() -> void:
	var inventory_enabled: bool = _game_system_enabled("inventory")
	var quests_enabled: bool = _game_system_enabled("quests")
	btn_inventory.visible = inventory_enabled
	btn_quests.visible = quests_enabled
	inventory_title_label.visible = inventory_enabled
	inventory_summary_label.visible = inventory_enabled
	inventory_list_label.visible = inventory_enabled
	journal_title_label.visible = quests_enabled
	journal_summary_label.visible = quests_enabled
	journal_list_label.visible = quests_enabled
	# Campaign/adventure controls currently depend on quest state. Hide them for
	# a game contract that deliberately has no quest system.
	adventure_row.visible = quests_enabled
	adventure_title_label.visible = quests_enabled
	adventure_state_label.visible = quests_enabled
	adventure_summary_label.visible = quests_enabled
	adventure_catalog_label.visible = quests_enabled
	adventure_objective_label.visible = quests_enabled
	adventure_report_label.visible = quests_enabled

func _handle_finite_adventure_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var previous_state: Dictionary = _finite_adventure_state.duplicate(true)
	_finite_adventure_state = (payload as Dictionary).duplicate(true)
	_maybe_log_finite_adventure_state_change(previous_state, _finite_adventure_state)
	_refresh_finite_adventure_panel()

func _handle_finite_adventure_summary_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var previous_summary: Dictionary = _finite_adventure_summary.duplicate(true)
	_finite_adventure_summary = (payload as Dictionary).duplicate(true)
	_maybe_log_finite_adventure_summary_change(previous_summary, _finite_adventure_summary)
	_refresh_finite_adventure_panel()

func _handle_finite_adventure_report_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	_finite_adventure_report = (payload as Dictionary).duplicate(true)
	if bool(_finite_adventure_report.get("available", false)):
		var format_name: String = str(_finite_adventure_report.get("format", "text"))
		var file_hint: String = str(_finite_adventure_report.get("file_name_hint", "")).strip_edges()
		_append_log("[color=aqua]Adventure report ready: %s%s[/color]" % [
			format_name,
			(" (%s)" % file_hint) if file_hint != "" else ""
		])
	_refresh_finite_adventure_panel()

func _handle_finite_adventure_catalog_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = (payload as Dictionary).duplicate(true)
	var entries_value: Variant = body.get("campaigns", [])
	_finite_adventure_catalog.clear()
	if typeof(entries_value) == TYPE_ARRAY:
		for entry_value in entries_value as Array:
			if typeof(entry_value) == TYPE_DICTIONARY:
				_finite_adventure_catalog.append((entry_value as Dictionary).duplicate(true))
	_finite_adventure_catalog_requested = true
	_refresh_finite_adventure_catalog_picker()
	var count: int = _finite_adventure_catalog.size()
	var default_campaign_id: String = str(body.get("default_campaign_id", "")).strip_edges()
	var suffix: String = ""
	if default_campaign_id != "":
		suffix = " Default: %s." % default_campaign_id
	_append_log("[color=aqua]Adventure catalog loaded: %d campaign(s).%s[/color]" % [count, suffix])
	_refresh_finite_adventure_panel()

func _refresh_finite_adventure_panel() -> void:
	adventure_title_label.text = "Adventure"
	if _finite_adventure_state.is_empty():
		adventure_state_label.text = "Run: unavailable"
	else:
		var enabled: bool = bool(_finite_adventure_state.get("enabled", false))
		var status: String = str(_finite_adventure_state.get("status", "not_started"))
		var campaign_id: String = str(_finite_adventure_state.get("campaign_id", "")).strip_edges()
		var default_campaign_id: String = str(_finite_adventure_state.get("default_campaign_id", "")).strip_edges()
		var current_node: String = str(_finite_adventure_state.get("current_node", "")).strip_edges()
		var checkpoint_available: bool = bool(_finite_adventure_state.get("checkpoint_available", false))
		var checkpoint_node: String = str(_finite_adventure_state.get("checkpoint_node", "")).strip_edges()
		var replay_supported: bool = bool(_finite_adventure_state.get("replay_supported", false))
		var run_label: String = "enabled" if enabled else "disabled"
		var parts: PackedStringArray = PackedStringArray()
		parts.append("Run: %s" % run_label)
		parts.append("status=%s" % status)
		if campaign_id != "":
			parts.append("campaign=%s" % campaign_id)
		elif default_campaign_id != "":
			parts.append("default=%s" % default_campaign_id)
		if current_node != "":
			parts.append("node=%s" % current_node)
		parts.append("checkpoint=%s" % ("yes" if checkpoint_available else "no"))
		if checkpoint_available and checkpoint_node != "":
			parts.append("restore=%s" % checkpoint_node)
		parts.append("replay=%s" % ("yes" if replay_supported else "no"))
		if not _finite_adventure_catalog.is_empty():
			parts.append("catalog=%d" % _finite_adventure_catalog.size())
		adventure_state_label.text = "  ".join(parts)
		if default_campaign_id != "" and adventure_campaign_input.text.strip_edges() == "":
			adventure_campaign_input.placeholder_text = "Campaign id (%s)" % default_campaign_id
		else:
			adventure_campaign_input.placeholder_text = "Campaign id (optional)"

	if _finite_adventure_summary.is_empty() or not bool(_finite_adventure_summary.get("available", false)):
		adventure_summary_label.text = "Summary: unavailable"
	else:
		var campaign_name: String = str(_finite_adventure_summary.get("campaign_name", "")).strip_edges()
		if campaign_name == "":
			campaign_name = str(_finite_adventure_summary.get("campaign_id", "(unknown)"))
		var status_text: String = str(_finite_adventure_summary.get("status", ""))
		var outcome: String = str(_finite_adventure_summary.get("outcome", ""))
		var player_name: String = str(_finite_adventure_summary.get("player_name", "")).strip_edges()
		var duration_value: Variant = _finite_adventure_summary.get("duration_seconds", null)
		var duration_text: String = "--"
		if typeof(duration_value) == TYPE_FLOAT or typeof(duration_value) == TYPE_INT:
			duration_text = "%.1fs" % float(duration_value)
		adventure_summary_label.text = "Summary: %s  %s/%s  player=%s  duration=%s" % [
			campaign_name,
			status_text,
			outcome,
			player_name if player_name != "" else "--",
			duration_text
		]

	if _finite_adventure_catalog.is_empty():
		adventure_catalog_label.text = "Campaigns: unavailable"
	else:
		var selected_campaign_id: String = _selected_finite_adventure_catalog_campaign_id()
		var catalog_parts: PackedStringArray = []
		catalog_parts.append("Campaigns: %d" % _finite_adventure_catalog.size())
		if selected_campaign_id != "":
			var selected_entry: Dictionary = _finite_adventure_catalog_entry(selected_campaign_id)
			var selected_name: String = str(selected_entry.get("name", selected_campaign_id)).strip_edges()
			var selected_desc: String = str(selected_entry.get("description", "")).strip_edges()
			catalog_parts.append("selected=%s" % selected_name)
			if selected_desc != "":
				catalog_parts.append(selected_desc)
		adventure_catalog_label.text = "  ".join(catalog_parts)

	adventure_objective_label.text = _render_finite_adventure_objective_bbcode()

	if _finite_adventure_report.is_empty() or not bool(_finite_adventure_report.get("available", false)):
		adventure_report_label.text = "[i]No adventure report yet.[/i]"
	else:
		var format_name: String = str(_finite_adventure_report.get("format", "text"))
		var file_hint: String = str(_finite_adventure_report.get("file_name_hint", "")).strip_edges()
		var content: String = _bbcode_escape(str(_finite_adventure_report.get("content", "")).strip_edges())
		var header: String = "[b]Report[/b] %s (%s)" % [format_name, file_hint if file_hint != "" else "--"]
		if format_name == "json" or format_name == "markdown":
			adventure_report_label.text = "%s\n[code]%s[/code]" % [header, content]
		else:
			adventure_report_label.text = "%s\n%s" % [header, content]
	_refresh_finite_adventure_actions()

func _refresh_finite_adventure_actions() -> void:
	var enabled: bool = bool(_finite_adventure_state.get("enabled", false))
	var status: String = str(_finite_adventure_state.get("status", "not_started"))
	var checkpoint_available: bool = bool(_finite_adventure_state.get("checkpoint_available", false))
	var replay_supported: bool = bool(_finite_adventure_state.get("replay_supported", false))
	var selected_catalog_campaign: String = _selected_finite_adventure_catalog_campaign_id()
	var has_campaign: bool = str(_finite_adventure_state.get("campaign_id", "")).strip_edges() != "" or str(_finite_adventure_state.get("default_campaign_id", "")).strip_edges() != "" or selected_catalog_campaign != "" or adventure_campaign_input.text.strip_edges() != ""
	var has_summary: bool = bool(_finite_adventure_summary.get("available", false))
	var active: bool = status == "active"
	var can_resume_from_summary: bool = status == "completed" or status == "abandoned" or status == "not_started"

	adventure_catalog_select.disabled = (not enabled) or active or adventure_catalog_select.item_count <= 1
	adventure_catalog_button.disabled = not enabled
	adventure_campaign_input.editable = enabled and not active
	adventure_start_button.disabled = (not enabled) or active or (not has_campaign)
	adventure_status_button.disabled = not enabled
	adventure_abandon_button.disabled = (not enabled) or (not active)
	adventure_checkpoint_button.disabled = (not enabled) or (not active)
	adventure_restore_button.disabled = (not enabled) or (not checkpoint_available)
	adventure_reset_button.disabled = (not enabled) or active or (not has_campaign)
	adventure_replay_button.disabled = (not enabled) or (not replay_supported) or (not can_resume_from_summary) or (not has_campaign)
	adventure_summary_text_button.disabled = (not enabled) or (not has_summary)
	adventure_summary_md_button.disabled = (not enabled) or (not has_summary)
	adventure_summary_json_button.disabled = (not enabled) or (not has_summary)

func _on_adventure_start_pressed() -> void:
	var campaign_id: String = adventure_campaign_input.text.strip_edges()
	if campaign_id == "":
		campaign_id = _selected_finite_adventure_catalog_campaign_id()
	if campaign_id == "":
		campaign_id = str(_finite_adventure_state.get("default_campaign_id", "")).strip_edges()
	if campaign_id == "":
		_send_adventure_command("adventure start")
		return
	_send_adventure_command("adventure start %s" % campaign_id)
	adventure_campaign_input.text = ""

func _request_finite_adventure_catalog() -> void:
	if not _is_connected_to_game_server():
		return
	_finite_adventure_catalog_requested = true
	_send_adventure_command("adventure list")

func _refresh_finite_adventure_catalog_picker() -> void:
	var current_selected_id: String = _selected_finite_adventure_catalog_campaign_id()
	adventure_catalog_select.clear()
	adventure_catalog_select.add_item("(choose campaign)")
	adventure_catalog_select.set_item_metadata(0, "")
	var selected_index: int = 0
	for entry in _finite_adventure_catalog:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var body: Dictionary = entry as Dictionary
		var campaign_id: String = str(body.get("campaign_id", "")).strip_edges()
		var campaign_name: String = str(body.get("name", campaign_id)).strip_edges()
		var is_default: bool = bool(body.get("is_default", false))
		var label: String = campaign_name
		if campaign_id != "" and campaign_id != campaign_name:
			label = "%s (%s)" % [campaign_name, campaign_id]
		if is_default:
			label += " [default]"
		adventure_catalog_select.add_item(label)
		var item_index: int = adventure_catalog_select.item_count - 1
		adventure_catalog_select.set_item_metadata(item_index, campaign_id)
		if current_selected_id != "" and campaign_id == current_selected_id:
			selected_index = item_index
		elif current_selected_id == "" and is_default:
			selected_index = item_index
	adventure_catalog_select.select(selected_index)

func _finite_adventure_catalog_entry(campaign_id: String) -> Dictionary:
	var wanted: String = campaign_id.strip_edges()
	if wanted == "":
		return {}
	for entry in _finite_adventure_catalog:
		if typeof(entry) != TYPE_DICTIONARY:
			continue
		var body: Dictionary = entry as Dictionary
		if str(body.get("campaign_id", "")).strip_edges() == wanted:
			return body
	return {}

func _selected_finite_adventure_catalog_campaign_id() -> String:
	var idx: int = adventure_catalog_select.get_selected()
	if idx < 0:
		return ""
	return str(adventure_catalog_select.get_item_metadata(idx)).strip_edges()

func _on_adventure_catalog_selected(index: int) -> void:
	if index < 0:
		return
	var campaign_id: String = str(adventure_catalog_select.get_item_metadata(index)).strip_edges()
	if campaign_id != "":
		adventure_campaign_input.text = campaign_id
	_refresh_finite_adventure_panel()

func _render_finite_adventure_objective_bbcode() -> String:
	var status: String = str(_finite_adventure_state.get("status", "not_started"))
	if status != "active":
		if status == "completed":
			return "[color=green]Adventure complete. Review summary or replay when ready.[/color]"
		if status == "abandoned":
			return "[color=yellow]Adventure abandoned. You can restore, reset, or replay.[/color]"
		return "[i]No active adventure objective.[/i]"

	var active_value: Variant = _latest_quests_payload.get("active", [])
	if typeof(active_value) != TYPE_ARRAY or (active_value as Array).is_empty():
		var current_node: String = str(_finite_adventure_state.get("current_node", "")).strip_edges()
		if current_node != "":
			return "[color=aqua]Adventure active at node '%s'. Quest details pending.[/color]" % _bbcode_escape(current_node)
		return "[color=aqua]Adventure active. Awaiting quest/objective details.[/color]"

	var first_variant: Variant = (active_value as Array)[0]
	if typeof(first_variant) != TYPE_DICTIONARY:
		return "[color=aqua]Adventure active. Objective data unavailable.[/color]"

	var quest: Dictionary = first_variant as Dictionary
	var title: String = _bbcode_escape(str(quest.get("title", "Unnamed Quest")))
	var state_text: String = _bbcode_escape(str(quest.get("state", "unknown")))
	var stage_text: String = ""
	var stages_value: Variant = quest.get("stages", [])
	if typeof(stages_value) == TYPE_ARRAY:
		for stage_variant in stages_value as Array:
			if typeof(stage_variant) != TYPE_DICTIONARY:
				continue
			var stage: Dictionary = stage_variant as Dictionary
			var stage_state: String = str(stage.get("state", "")).strip_edges().to_lower()
			if stage_state in ["active", "ready_to_complete", ""]:
				var description: String = str(stage.get("description", "")).strip_edges()
				if description != "":
					stage_text = _bbcode_escape(description)
					break
	var parts: PackedStringArray = []
	parts.append("[b]Active Objective[/b]: %s [%s]" % [title, state_text])
	if stage_text != "":
		parts.append(stage_text)
	var current_node: String = str(_finite_adventure_state.get("current_node", "")).strip_edges()
	if current_node != "":
		parts.append("[color=gray]Campaign node: %s[/color]" % _bbcode_escape(current_node))
	return "\n".join(parts)

func _maybe_log_finite_adventure_state_change(previous_state: Dictionary, next_state: Dictionary) -> void:
	var previous_status: String = str(previous_state.get("status", "not_started"))
	var next_status: String = str(next_state.get("status", "not_started"))
	var previous_campaign: String = str(previous_state.get("campaign_id", "")).strip_edges()
	var next_campaign: String = str(next_state.get("campaign_id", "")).strip_edges()
	if previous_state.is_empty() and next_state.is_empty():
		return
	if previous_status != next_status or previous_campaign != next_campaign:
		var campaign_label: String = next_campaign if next_campaign != "" else str(next_state.get("default_campaign_id", "")).strip_edges()
		if campaign_label == "":
			campaign_label = "(unspecified)"
		match next_status:
			"active":
				_append_log("[color=green]Adventure started: %s[/color]" % campaign_label)
			"completed":
				_append_log("[color=green]Adventure completed: %s[/color]" % campaign_label)
			"abandoned":
				_append_log("[color=yellow]Adventure abandoned: %s[/color]" % campaign_label)
			"not_started":
				if not previous_state.is_empty():
					_append_log("[color=aqua]Adventure reset to ready state.[/color]")
			_:
				_append_log("[color=aqua]Adventure status: %s (%s)[/color]" % [next_status, campaign_label])

	var previous_checkpoint: bool = bool(previous_state.get("checkpoint_available", false))
	var next_checkpoint: bool = bool(next_state.get("checkpoint_available", false))
	if not previous_checkpoint and next_checkpoint:
		var checkpoint_node: String = str(next_state.get("checkpoint_node", "")).strip_edges()
		if checkpoint_node == "":
			_append_log("[color=aqua]Adventure checkpoint saved.[/color]")
		else:
			_append_log("[color=aqua]Adventure checkpoint saved at %s.[/color]" % checkpoint_node)

func _maybe_log_finite_adventure_summary_change(previous_summary: Dictionary, next_summary: Dictionary) -> void:
	var previous_available: bool = bool(previous_summary.get("available", false))
	var next_available: bool = bool(next_summary.get("available", false))
	if not next_available:
		return
	var previous_status: String = str(previous_summary.get("status", ""))
	var next_status: String = str(next_summary.get("status", ""))
	var previous_outcome: String = str(previous_summary.get("outcome", ""))
	var next_outcome: String = str(next_summary.get("outcome", ""))
	if (not previous_available) or previous_status != next_status or previous_outcome != next_outcome:
		var campaign_name: String = str(next_summary.get("campaign_name", "")).strip_edges()
		if campaign_name == "":
			campaign_name = str(next_summary.get("campaign_id", "(unknown)"))
		_append_log("[color=aqua]Adventure summary updated: %s (%s/%s)[/color]" % [
			campaign_name,
			next_status if next_status != "" else "--",
			next_outcome if next_outcome != "" else "--"
		])

func _send_adventure_command(command: String) -> void:
	_send_command_immediate(command)

func _bbcode_escape(text: String) -> String:
	return text.replace("[", "[lb]").replace("]", "[rb]")

func _handle_audit_result_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		_append_log("[color=orange]Audit payload malformed.[/color]")
		return
	var body: Dictionary = payload as Dictionary
	var audit_type: String = str(body.get("audit", "unknown"))
	if audit_type == "boot_warnings":
		var warning_count: int = int(body.get("warning_count", 0))
		var codes_value: Variant = body.get("codes", {})
		var codes_json: String = "{}"
		if typeof(codes_value) == TYPE_DICTIONARY:
			codes_json = JSON.stringify(codes_value)
		_append_log("[color=aqua]Boot warning audit: %d warning(s), codes=%s[/color]" % [warning_count, codes_json])
		if body.has("warnings"):
			var warnings_value: Variant = body.get("warnings", [])
			if typeof(warnings_value) == TYPE_ARRAY:
				for warning_variant: Variant in warnings_value as Array:
					if typeof(warning_variant) == TYPE_DICTIONARY:
						var warning_entry: Dictionary = warning_variant as Dictionary
						var code: String = str(warning_entry.get("code", "server.unknown"))
						var msg: String = str(warning_entry.get("message", ""))
						_append_log("[color=gray]- %s: %s[/color]" % [code, msg])
		return
	if audit_type == "stale_refs":
		var err_count: int = int(body.get("error_count", 0))
		var warn_count: int = int(body.get("warn_count", 0))
		_append_log("[color=aqua]Stale-ref audit: errors=%d warnings=%d[/color]" % [err_count, warn_count])
		return
	_append_log("[color=aqua]Audit result (%s): %s[/color]" % [audit_type, JSON.stringify(body)])

func _apply_operator_catalog_payload(catalog: Dictionary) -> void:
	var domains_value: Variant = catalog.get("domains", {})
	if typeof(domains_value) == TYPE_DICTIONARY:
		var domains_dict: Dictionary = domains_value as Dictionary
		var remapped: Dictionary = {}
		for key_variant in domains_dict.keys():
			var domain_key: String = str(key_variant)
			var actions_value: Variant = domains_dict.get(key_variant, [])
			var actions: Array = []
			if typeof(actions_value) == TYPE_ARRAY:
				for action_variant in actions_value as Array:
					actions.append(str(action_variant))
			remapped[domain_key] = actions
		if not remapped.is_empty():
			_operator_action_maps = remapped
	var value_options_value: Variant = catalog.get("value_options", {})
	if typeof(value_options_value) == TYPE_DICTIONARY:
		_operator_catalog_value_options = (value_options_value as Dictionary).duplicate(true)
	var requirements_value: Variant = catalog.get("requirements", {})
	if typeof(requirements_value) == TYPE_DICTIONARY:
		_operator_catalog_requirements = (requirements_value as Dictionary).duplicate(true)
	else:
		_operator_catalog_requirements = {}
	_refresh_operator_actions()

func _handle_profile_presets_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	_known_profile_presets = PackedStringArray()
	_active_profile_path = str(body.get("active_profile_path", _active_profile_path)).strip_edges()
	var active_from_payload: String = _extract_profile_preset_from_path(_active_profile_path)
	if active_from_payload != "":
		_active_profile_preset = active_from_payload
	var presets_value: Variant = body.get("presets", [])
	if typeof(presets_value) == TYPE_ARRAY:
		_append_log("[color=aqua]Available profile presets:[/color]")
		var index: int = 1
		for preset_value: Variant in presets_value as Array:
			var preset_name: String = str(preset_value).strip_edges()
			if preset_name == "":
				continue
			_known_profile_presets.append(preset_name)
			_append_log("[color=aqua]  %d) %s[/color]" % [index, preset_name])
			index += 1
	if _known_profile_presets.is_empty():
		_append_log("[color=yellow]No profile presets are available on this server.[/color]")
	_operator_catalog_value_options["Profiles:Apply Selected"] = _known_profile_presets.duplicate()
	_sync_profile_select_from_known_presets()
	_refresh_profile_status()

func _handle_auth_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	_gm_granted = bool(body.get("gm_granted", false))
	_gm_auth_configured = bool(body.get("gm_auth_configured", false))
	_gm_auth_cooldown_seconds = int(body.get("gm_auth_cooldown_seconds", 0))
	_session_entitlements = PackedStringArray()
	_session_entitlements_known = false
	var entitlements_value: Variant = body.get("session_entitlements", null)
	if typeof(entitlements_value) == TYPE_ARRAY:
		_session_entitlements_known = true
		for entitlement_variant: Variant in entitlements_value as Array:
			var entitlement_name: String = str(entitlement_variant).strip_edges()
			if entitlement_name != "":
				_session_entitlements.append(entitlement_name)
	var authoring_mode: String = str(body.get("authoring_mode", str(_server_profile_modes.get("authoring", "unknown"))))
	server_policy_auth_label.text = "Auth: GM %s  Configured %s  Cooldown %ds" % [
		("yes" if _gm_granted else "no"),
		("yes" if _gm_auth_configured else "no"),
		max(0, _gm_auth_cooldown_seconds)
	]
	var status: String = "GM session: %s | auth configured: %s | authoring mode: %s" % [
		("yes" if _gm_granted else "no"),
		("yes" if _gm_auth_configured else "no"),
		authoring_mode
	]
	if _gm_auth_cooldown_seconds > 0:
		status += " | cooldown: %ds" % _gm_auth_cooldown_seconds
	_refresh_policy_affordances()
	_append_log("[color=aqua]%s[/color]" % status)

func _render_text_payload(payload: Variant) -> String:
	if typeof(payload) == TYPE_DICTIONARY:
		var body: Dictionary = payload as Dictionary
		var text: String = str(body.get("text", ""))
		var fx: Variant = body.get("fx", {})
		if typeof(fx) == TYPE_DICTIONARY:
			var fx_dict: Dictionary = fx as Dictionary
			if fx_dict.has("effect_type"):
				var effect_type: String = str(fx_dict.get("effect_type", ""))
				var severity: float = clamp(_to_float(fx_dict.get("severity", 0.0)), 0.0, 1.0)
				var duration_ms: int = int(fx_dict.get("duration_ms", 1200))
				if effect_type != "" and severity > 0.0:
					return "[atmo type=%s severity=%.3f duration_ms=%d]%s[/atmo]" % [effect_type, severity, duration_ms, text]
			var blight_severity: float = _to_float(fx_dict.get("blight", 0.0))
			if blight_severity > 0.0:
				var amp: float = clamp(blight_severity, 0.0, 1.0)
				var rate: float = 2.0 + (6.0 * amp)
				return "[blight amp=%.3f rate=%.3f]%s[/blight]" % [amp, rate, text]
		return text
	return str(payload)

func _resolve_client_capabilities(command_text: String) -> Dictionary:
	var lowered: String = command_text.strip_edges().to_lower()
	if lowered == "a11y motion off":
		_client_capabilities["reduced_motion"] = true
		_append_log("[color=yellow]Accessibility: reduced motion ON[/color]")
	elif lowered == "a11y motion on":
		_client_capabilities["reduced_motion"] = false
		_append_log("[color=yellow]Accessibility: reduced motion OFF[/color]")
	if lowered == "a11y sr on":
		_client_capabilities["screen_reader_mode"] = true
		_append_log("[color=yellow]Accessibility: screen reader mode ON[/color]")
	elif lowered == "a11y sr off":
		_client_capabilities["screen_reader_mode"] = false
		_append_log("[color=yellow]Accessibility: screen reader mode OFF[/color]")
	return _client_capabilities.duplicate(true)

func _to_float(value: Variant) -> float:
	match typeof(value):
		TYPE_FLOAT:
			return value
		TYPE_INT:
			return float(value)
		TYPE_STRING:
			return float(value)
		_:
			return 0.0

func _safe_int(text: String, fallback: int) -> int:
	var trimmed := text.strip_edges()
	if trimmed == "":
		return fallback
	if not trimmed.is_valid_int():
		return fallback
	return int(trimmed)

func _safe_float(text: String, fallback: float) -> float:
	var trimmed := text.strip_edges()
	if trimmed == "":
		return fallback
	if not trimmed.is_valid_float():
		return fallback
	return float(trimmed)

func _using_websocket() -> bool:
	return transport_select.selected == 1

func _active_client_send_line(line: String) -> void:
	if _using_websocket():
		ws_client.send_line(line)
	else:
		tcp_client.send_line(line)

func _bind_client_signals(client, label: String) -> void:
	client.connected.connect(func() -> void:
		_cancel_reconnect()
		_reconnect_attempts = 0
		_network_telemetry["connect_successes"] = int(_network_telemetry.get("connect_successes", 0)) + 1
		_network_telemetry["last_transport"] = label
		_network_telemetry["last_connected_at"] = Time.get_datetime_string_from_system()
		_append_log("[color=green]Connected (%s).[/color]" % label)
		crash_recovery.write_marker(host_input.text.strip_edges(), int(port_input.text), label)
		_refresh_network_labels()
		_refresh_profile_status()
		if _resume_session_id != "":
			_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
			_active_client_send_line(JSON.stringify(parser.build_resume_session_envelope(_resume_session_id)))
			_refresh_network_labels()
	)
	client.disconnected.connect(func() -> void:
		_network_telemetry["disconnects"] = int(_network_telemetry.get("disconnects", 0)) + 1
		_network_telemetry["last_disconnected_at"] = Time.get_datetime_string_from_system()
		_append_log("[color=yellow]Disconnected (%s).[/color]" % label)
		_refresh_profile_status()
		if not _manual_disconnect_requested and _should_auto_reconnect(label):
			_schedule_reconnect()
		_refresh_network_labels()
	)
	client.error.connect(func(message: String) -> void:
		_network_telemetry["errors"] = int(_network_telemetry.get("errors", 0)) + 1
		_network_telemetry["last_error"] = "%s: %s" % [label, message]
		_append_log("[color=red]Error (%s): %s[/color]" % [label, message])
		if not _manual_disconnect_requested and _should_auto_reconnect(label):
			if message.begins_with("Connect failed"):
				_schedule_reconnect()
		_refresh_network_labels()
	)
	client.line_received.connect(_on_line_received)

func _handle_asset_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		_append_log("[color=red]Invalid asset payload[/color]")
		return

	var body: Dictionary = payload as Dictionary
	if not body.has("asset_id") or not body.has("revision") or not body.has("checksum_sha256"):
		_append_log("[color=red]Asset payload missing required metadata.[/color]")
		return

	var asset_type: String = str(body.get("asset_type", ""))
	if asset_type != "svg_1bit":
		_append_log("[color=yellow]Unsupported asset type: %s[/color]" % asset_type)
		return

	var alt_text: String = str(body.get("alt_text", "Decorative image"))
	var asset_id: String = str(body.get("asset_id", ""))
	_asset_revisions[asset_id] = int(body.get("revision", 0))
	_refresh_authoring_status(asset_id)
	asset_alt_text.text = alt_text
	if bool(_client_capabilities.get("screen_reader_mode", false)):
		asset_texture.texture = null
		_append_log("[color=yellow]Screen-reader mode: showing alt text only.[/color]")
		return

	var svg_text: String = str(body.get("svg", ""))
	var checksum: String = str(body.get("checksum_sha256", ""))
	if checksum != _sha256_hex(svg_text):
		asset_texture.texture = null
		_append_log("[color=red]Asset checksum mismatch.[/color]")
		return

	var violations := svg_renderer._validate_svg_1bit(svg_text)
	if violations.size() > 0:
		for v in violations:
			_append_log("[color=orange]SVG 1-bit policy violation: %s[/color]" % v)
		asset_texture.texture = null
		_append_log("[color=red]Rejected SVG asset due to 1-bit policy violations.[/color]")
		return

	var texture: Texture2D = svg_renderer.render_svg_texture(svg_text, Vector2i(160, 160))
	if texture == null:
		asset_texture.texture = null
		_append_log("[color=red]Failed to render SVG asset.[/color]")
		return
	asset_texture.texture = texture
	_append_log("[color=aqua]Rendered SVG asset (%s r%s).[/color]" % [str(body.get("asset_id", "unknown")), str(body.get("revision", "?"))])

func _handle_world_state_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	if str(body.get("system", "")) not in ["blight", "world_field", "world_effects"]:
		return

	var cells_variant: Variant = body.get("cells", [])
	if typeof(cells_variant) != TYPE_ARRAY:
		return
	var cells: Array = cells_variant as Array
	var summary: String = _summarize_field_cells(cells)
	var field_id: String = str(body.get("field_id", "blight"))
	var polarity: String = str(body.get("polarity", "negative"))
	_world_effects_cells_preview[field_id] = summary
	atmosphere_layer.apply_world_state(field_id, polarity, cells)
	_render_world_effects_panel()
	_append_log("[color=teal]World state updated: %s (%s) %s[/color]" % [field_id, polarity, summary])

func _handle_world_effects_status_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	_world_effects_status = (payload as Dictionary).duplicate(true)
	var providers_value: Variant = _world_effects_status.get("available_providers", [])
	if typeof(providers_value) == TYPE_ARRAY:
		_operator_catalog_value_options["World Effects:Use Provider"] = (providers_value as Array).duplicate()
	_render_world_effects_panel()
	_refresh_operator_values()
	_update_operator_palette_state()

func _handle_world_effects_providers_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	_world_effects_status = (payload as Dictionary).duplicate(true)
	var providers_value: Variant = _world_effects_status.get("available_providers", [])
	if typeof(providers_value) == TYPE_ARRAY:
		_operator_catalog_value_options["World Effects:Use Provider"] = (providers_value as Array).duplicate()
	if typeof(providers_value) == TYPE_ARRAY:
		var providers: Array = providers_value as Array
		var names: PackedStringArray = PackedStringArray()
		for p in providers:
			names.append(str(p))
		_append_log("[color=aqua]World-effects providers: %s[/color]" % ", ".join(names))
	_render_world_effects_panel()
	_refresh_operator_values()
	_update_operator_palette_state()

func _render_world_effects_panel() -> void:
	var lines: PackedStringArray = PackedStringArray()
	var mode: String = str(_world_effects_status.get("mode", "unknown"))
	var provider: String = str(_world_effects_status.get("active_provider", "unknown"))
	lines.append("Mode=%s  Provider=%s" % [mode, provider])
	var keys: Array = _world_effects_cells_preview.keys()
	keys.sort()
	for key_variant in keys:
		var key: String = str(key_variant)
		lines.append("%s: %s" % [key, str(_world_effects_cells_preview.get(key, "no cells"))])
	world_state_label.text = "\n".join(lines)

func _handle_status_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var name: String = str(body.get("name", "Player"))
	var identity_parts: PackedStringArray = PackedStringArray([name])
	if _game_status_field_enabled("level") and body.has("level"):
		identity_parts.append("Level %d" % int(body.get("level", 0)))
	if _game_status_field_enabled("experience") and body.has("experience"):
		identity_parts.append("XP %d" % int(body.get("experience", 0)))
	status_primary_label.text = "  ".join(identity_parts)

	var health: Dictionary = body.get("health", {}) as Dictionary
	var hp_cur: int = int(health.get("current", 0))
	var hp_max: int = int(health.get("max", 0))

	# Color-independent critical-state indicators.
	# These text markers communicate urgency without relying on color alone,
	# supporting high-contrast and screen-reader modes.
	var hp_prefix: String = ""
	var vital_parts: PackedStringArray = PackedStringArray(["%sHP %d/%d" % [hp_prefix, hp_cur, hp_max]])
	if hp_max > 0:
		if hp_cur <= 0:
			hp_prefix = "[DEAD] "
		elif float(hp_cur) / float(hp_max) < 0.25:
			hp_prefix = "[CRIT] "
	if _game_status_field_enabled("mana") and body.has("mana"):
		var mana: Dictionary = body.get("mana", {}) as Dictionary
		var mp_cur: int = int(mana.get("current", 0))
		var mp_max: int = int(mana.get("max", 0))
		var mp_suffix: String = " [OOM]" if mp_max > 0 and mp_cur <= 0 else ""
		vital_parts.append("MP %d/%d%s" % [mp_cur, mp_max, mp_suffix])
	status_vitals_label.text = "  ".join(vital_parts)

	var effects: Array = body.get("effects", []) as Array
	if effects.is_empty():
		status_effects_label.text = "%s none" % _icon_token("status_effect", "Effects:")
	else:
		var effect_names: PackedStringArray = []
		for effect_value in effects:
			effect_names.append(str(effect_value))
		status_effects_label.text = "%s %s" % [_icon_token("status_effect", "Effects:"), ", ".join(effect_names)]

func _handle_inventory_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var slots_used: int = int(body.get("slots_used", 0))
	var slots_max: int = int(body.get("slots_max", 0))
	var total_weight: float = _to_float(body.get("total_weight", 0.0))
	var max_weight: float = _to_float(body.get("max_weight", 0.0))
	inventory_summary_label.text = "Slots %d/%d  Weight %.1f/%.1f" % [slots_used, slots_max, total_weight, max_weight]

	var items_variant: Variant = body.get("items", [])
	if typeof(items_variant) != TYPE_ARRAY:
		inventory_list_label.text = "[i]%s[/i]" % _icon_token("inventory_none", "No inventory data.")
		return

	var lines: PackedStringArray = []
	var items: Array = items_variant as Array
	for item_variant in items:
		if typeof(item_variant) != TYPE_DICTIONARY:
			continue
		var item: Dictionary = item_variant as Dictionary
		var item_name: String = str(item.get("name", "Unknown"))
		lines.append(
			"%s %d: [url=cmd:look %s]%s[/url] x%d (%.1f wt)" % [
				_icon_token("inventory_item_prefix", "-"),
				int(item.get("slot_index", -1)),
				item_name,
				item_name,
				int(item.get("quantity", 0)),
				_to_float(item.get("weight_total", 0.0)),
			]
		)
	if lines.is_empty():
		inventory_list_label.text = "[i]%s[/i]" % _icon_token("inventory_empty", "Inventory empty.")
		return
	inventory_list_label.text = "\n".join(lines)

func _handle_quests_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	_latest_quests_payload = body.duplicate(true)
	var active: Array = body.get("active", []) as Array
	var completed: Array = body.get("completed", []) as Array
	var archived: Array = body.get("archived", []) as Array
	journal_summary_label.text = "Active %d  Completed %d  Archived %d" % [active.size(), completed.size(), archived.size()]

	var lines: PackedStringArray = []
	var active_prefix: String = _icon_token("quest_active_prefix", "A:")
	var completed_prefix: String = _icon_token("quest_completed_prefix", "C:")
	var archived_prefix: String = _icon_token("quest_archived_prefix", "R:")
	for quest_variant in active:
		if typeof(quest_variant) != TYPE_DICTIONARY:
			continue
		var quest: Dictionary = quest_variant as Dictionary
		var title: String = str(quest.get("title", "Unnamed Quest"))
		lines.append("%s [url=cmd:journal %s]%s[/url] [%s]" % [active_prefix, title, title, str(quest.get("state", "unknown"))])
	for quest_variant in completed:
		if typeof(quest_variant) != TYPE_DICTIONARY:
			continue
		var quest: Dictionary = quest_variant as Dictionary
		var title: String = str(quest.get("title", "Unnamed Quest"))
		lines.append("%s [url=cmd:journal %s]%s[/url]" % [completed_prefix, title, title])
	for quest_variant in archived:
		if typeof(quest_variant) != TYPE_DICTIONARY:
			continue
		var quest: Dictionary = quest_variant as Dictionary
		var title: String = str(quest.get("title", "Unnamed Quest"))
		lines.append("%s [url=cmd:journal %s]%s[/url]" % [archived_prefix, title, title])

	if lines.is_empty():
		journal_list_label.text = "[i]%s[/i]" % _icon_token("quest_none", "No quests tracked.")
		_refresh_finite_adventure_panel()
		return
	journal_list_label.text = "\n".join(lines)
	_refresh_finite_adventure_panel()

func _handle_nearby_payload(payload: Variant) -> void:
	if typeof(payload) != TYPE_DICTIONARY:
		return
	var body: Dictionary = payload as Dictionary
	var location: Dictionary = body.get("location", {}) as Dictionary
	var region_name: String = str(location.get("region_name", "Unknown Region"))
	var room_name: String = str(location.get("room_name", "Unknown Room"))
	nearby_location_label.text = "%s / %s" % [region_name, room_name]

	var exits: Array = body.get("exits", []) as Array
	if exits.is_empty():
		nearby_exits_label.text = "Exits: none"
	else:
		var exit_names: PackedStringArray = []
		for exit_value in exits:
			var exit_str = str(exit_value)
			exit_names.append("[url=cmd:%s]%s[/url]" % [exit_str, exit_str])
		nearby_exits_label.text = "Exits: %s" % ", ".join(exit_names)

	var npc_lines: PackedStringArray = []
	for npc_variant in (body.get("npcs", []) as Array):
		if typeof(npc_variant) != TYPE_DICTIONARY:
			continue
		var npc: Dictionary = npc_variant as Dictionary
		var hostile_flag: bool = bool(npc.get("hostile", false))
		var tag: String = _icon_token("hostile_tag", "hostile") if hostile_flag else str(npc.get("faction", "neutral"))
		var npc_name: String = str(npc.get("name", "Unknown NPC"))
		var action: String = "attack" if hostile_flag else "look"
		npc_lines.append("[url=cmd:%s %s]%s[/url] [%s]" % [action, npc_name, npc_name, tag])
	if npc_lines.is_empty():
		nearby_npcs_label.text = "[i]%s[/i]" % _icon_token("npc_none", "No nearby NPCs.")
	else:
		nearby_npcs_label.text = "\n".join(npc_lines)

	var item_lines: PackedStringArray = []
	for item_variant in (body.get("items", []) as Array):
		if typeof(item_variant) != TYPE_DICTIONARY:
			continue
		var item: Dictionary = item_variant as Dictionary
		var item_name: String = str(item.get("name", "Unknown Item"))
		var portable: bool = bool(item.get("portable", true))
		var action: String = "take" if portable else "look"
		item_lines.append("%s [url=cmd:%s %s]%s[/url]" % [_icon_token("item_prefix", "-"), action, item_name, item_name])
	if item_lines.is_empty():
		nearby_items_label.text = "[i]%s[/i]" % _icon_token("item_none", "No nearby items.")
	else:
		nearby_items_label.text = "\n".join(item_lines)

	var interactions: Array = body.get("interactions", []) as Array
	if interactions.is_empty():
		nearby_interactions_label.text = "Try: look, inventory, status"
	else:
		var commands: PackedStringArray = []
		for command_value in interactions:
			commands.append(str(command_value))
		nearby_interactions_label.text = "Try: %s" % ", ".join(commands)

func _summarize_field_cells(cells: Array) -> String:
	if cells.is_empty():
		return "stable (no active cells)"

	var max_intensity: float = 0.0
	for cell_variant in cells:
		if typeof(cell_variant) != TYPE_DICTIONARY:
			continue
		var cell: Dictionary = cell_variant as Dictionary
		var value: float = _to_float(cell.get("value", cell.get("intensity", 0.0)))
		if value > max_intensity:
			max_intensity = value

	var intensity_word: String = "low"
	if max_intensity >= 0.75:
		intensity_word = "severe"
	elif max_intensity >= 0.4:
		intensity_word = "moderate"

	return "%d active cells, %s spread" % [cells.size(), intensity_word]

func _maybe_send_asset_update_command(cmd: String) -> bool:
	var tokens: PackedStringArray = cmd.strip_edges().split(" ", false)
	if tokens.is_empty():
		return false
	var lowered_head: String = tokens[0].to_lower()
	var is_legacy: bool = lowered_head == "assetupdate"
	var is_authoring: bool = lowered_head == "@edit"
	if not is_legacy and not is_authoring:
		return false

	var asset_id: String = _current_authoring_asset_id()
	var mode: String = "next"

	if is_legacy:
		if tokens.size() < 2:
			_append_log("[color=orange]Usage: assetupdate <next|stale>[/color]")
			return true
		mode = tokens[1].to_lower()
	else:
		if tokens.size() < 3:
			_append_log("[color=orange]Usage: @edit <asset_id> <next|stale>[/color]")
			return true
		asset_id = tokens[1].strip_edges()
		mode = tokens[2].to_lower()
		if asset_id == "":
			_append_log("[color=orange]Usage: @edit <asset_id> <next|stale>[/color]")
			return true

	if mode != "next" and mode != "stale":
		_append_log("[color=orange]Unknown edit mode '%s'. Use next or stale.[/color]" % mode)
		return true
	if is_authoring and not _ensure_lock_before_edit(asset_id):
		return true

	var known_revision: int = int(_asset_revisions.get(asset_id, 1))
	var base_revision: int = known_revision if mode == "next" else max(0, known_revision - 1)
	var svg_text := "<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'><rect width='32' height='32' fill='white'/><rect x='1' y='1' width='30' height='30' fill='black'/><rect x='6' y='6' width='20' height='20' fill='white'/><rect x='12' y='12' width='8' height='8' fill='black'/></svg>"
	var envelope: Dictionary = parser.build_asset_update_envelope(asset_id, base_revision, svg_text, "Updated concentric-square emblem.", _session_id)
	_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
	_active_client_send_line(JSON.stringify(envelope))
	_append_log("[b]> %s[/b]" % cmd)
	_refresh_network_labels()
	return true

func _maybe_send_lock_command(cmd: String) -> bool:
	var tokens: PackedStringArray = cmd.strip_edges().split(" ", false)
	if tokens.is_empty():
		return false
	var lowered_head: String = tokens[0].to_lower()
	var is_legacy: bool = lowered_head == "lock"
	var is_authoring: bool = lowered_head == "@dig"
	if not is_legacy and not is_authoring:
		return false

	var action: String = "acquire"
	var asset_id: String = _current_authoring_asset_id()

	if is_legacy:
		if tokens.size() < 2:
			_append_log("[color=orange]Usage: lock <acquire|release|renew|status>[/color]")
			return true
		action = tokens[1].to_lower()
	else:
		if tokens.size() < 2:
			_append_log("[color=orange]Usage: @dig <asset_id> [acquire|release|renew][/color]")
			return true
		asset_id = tokens[1].strip_edges()
		if tokens.size() >= 3:
			action = tokens[2].to_lower()
		if asset_id == "":
			_append_log("[color=orange]Usage: @dig <asset_id> [acquire|release|renew][/color]")
			return true

	if action == "acquire":
		_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
		_active_client_send_line(JSON.stringify(parser.build_lock_acquire_envelope(asset_id, _session_id)))
		_append_log("[b]> %s[/b]" % cmd)
		_refresh_network_labels()
		return true
	if action == "release":
		_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
		_active_client_send_line(JSON.stringify(parser.build_lock_release_envelope(asset_id, _session_id)))
		_append_log("[b]> %s[/b]" % cmd)
		_refresh_network_labels()
		return true
	if action == "renew":
		_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
		_active_client_send_line(JSON.stringify(parser.build_lock_renew_envelope(asset_id, _session_id)))
		_append_log("[b]> %s[/b]" % cmd)
		_refresh_network_labels()
		return true
	if action == "status":
		_request_lock_status()
		_append_log("[b]> %s[/b]" % cmd)
		return true
	_append_log("[color=orange]Unknown lock action '%s'. Use acquire, release, renew, or status.[/color]" % action)
	return true

func _sha256_hex(text: String) -> String:
	var ctx := HashingContext.new()
	var err: int = ctx.start(HashingContext.HASH_SHA256)
	if err != OK:
		return ""
	ctx.update(text.to_utf8_buffer())
	return ctx.finish().hex_encode()

func _apply_degraded_mode(reason: String) -> void:
	if _degraded_mode_active:
		return
	_degraded_mode_active = true
	_client_capabilities["rich_text"] = false
	_client_capabilities["reduced_motion"] = true
	_append_log("[color=orange]Degraded mode active: %s[/color]" % reason)

func _maybe_handle_local_accessibility_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()

	# ── a11y list ──────────────────────────────────────────────────────────
	if lowered == "a11y list":
		var preset_names: PackedStringArray = []
		for key: Variant in A11Y_PRESETS.keys():
			preset_names.append(str(key))
		preset_names.sort()
		_append_log("[color=aqua]A11y presets: %s[/color]" % ", ".join(preset_names))
		_append_log("[color=aqua]A11y commands:[/color]")
		_append_log("[color=aqua]  a11y preset <name>          — apply a named preset[/color]")
		_append_log("[color=aqua]  a11y text <small|medium|large|xlarge|pct>  — text scale[/color]")
		_append_log("[color=aqua]  a11y font dyslexia on/off   — high-legibility font[/color]")
		_append_log("[color=aqua]  a11y spacing <1.0..2.0>     — line spacing multiplier[/color]")
		_append_log("[color=aqua]  a11y contrast on/off        — minimum contrast enforcement[/color]")
		_append_log("[color=aqua]  a11y distortion on/off      — atmospheric text effects[/color]")
		_append_log("[color=aqua]  a11y weather on/off         — weather/screen shader effects[/color]")
		_append_log("[color=aqua]  a11y motion on/off          — reduced motion[/color]")
		_append_log("[color=aqua]  a11y sr on/off              — screen reader mode[/color]")
		return true

	# ── a11y preset <name> ─────────────────────────────────────────────────
	if lowered.begins_with("a11y preset "):
		var preset_name: String = lowered.substr(12).strip_edges()
		if not A11Y_PRESETS.has(preset_name):
			_append_log("[color=orange]Unknown preset '%s'. Try: a11y list[/color]" % preset_name)
			return true
		var patch: Dictionary = A11Y_PRESETS[preset_name] as Dictionary
		for key: Variant in patch.keys():
			_client_capabilities[str(key)] = patch[key]
		_append_log("[color=yellow]Accessibility preset: %s[/color]" % preset_name)
		if bool(_client_capabilities.get("high_contrast", false)):
			_append_log("[color=yellow]  high contrast ON[/color]")
		if bool(_client_capabilities.get("contrast_enforce", false)):
			_append_log("[color=yellow]  contrast enforcement ON[/color]")
		if bool(_client_capabilities.get("reduced_motion", false)):
			_append_log("[color=yellow]  reduced motion ON[/color]")
		if bool(_client_capabilities.get("screen_reader_mode", false)):
			_append_log("[color=yellow]  screen reader mode ON[/color]")
		if bool(_client_capabilities.get("dyslexia_font", false)):
			_append_log("[color=yellow]  dyslexia font ON[/color]")
			_apply_dyslexia_font(true)
		var spacing: float = _to_float(_client_capabilities.get("line_spacing", 1.0))
		if spacing != 1.0:
			_append_log("[color=yellow]  line spacing %.2f[/color]" % spacing)
			_apply_line_spacing(spacing)
		if not bool(_client_capabilities.get("effects_distortion", true)):
			_append_log("[color=yellow]  atmospheric distortion OFF[/color]")
		if not bool(_client_capabilities.get("effects_weather", true)):
			_append_log("[color=yellow]  weather effects OFF[/color]")
		var new_scale: float = _to_float(_client_capabilities.get("text_scale", 1.0))
		_apply_text_scale(new_scale)
		_append_log("[color=yellow]  text scale %.0f%%[/color]" % (new_scale * 100.0))
		return true

	# ── a11y font dyslexia on/off ──────────────────────────────────────────
	if lowered.begins_with("a11y font dyslexia "):
		var val: String = lowered.substr(19).strip_edges()
		if val == "on":
			_client_capabilities["dyslexia_font"] = true
			_apply_dyslexia_font(true)
			_append_log("[color=yellow]Accessibility: dyslexia-friendly font ON[/color]")
		elif val == "off":
			_client_capabilities["dyslexia_font"] = false
			_apply_dyslexia_font(false)
			_append_log("[color=yellow]Accessibility: dyslexia-friendly font OFF[/color]")
		else:
			_append_log("[color=orange]Usage: a11y font dyslexia on/off[/color]")
		return true

	# ── a11y spacing <multiplier> ──────────────────────────────────────────
	if lowered.begins_with("a11y spacing "):
		var val: String = lowered.substr(13).strip_edges()
		if val.is_valid_float():
			var sp: float = clamp(float(val), 0.8, 3.0)
			_client_capabilities["line_spacing"] = sp
			_apply_line_spacing(sp)
			_append_log("[color=yellow]Accessibility: line spacing %.2f[/color]" % sp)
		else:
			_append_log("[color=orange]Usage: a11y spacing <0.8..3.0>[/color]")
		return true

	# ── a11y contrast on/off ───────────────────────────────────────────────
	if lowered.begins_with("a11y contrast "):
		var val: String = lowered.substr(14).strip_edges()
		if val == "on":
			_client_capabilities["contrast_enforce"] = true
			_append_log("[color=yellow]Accessibility: minimum contrast enforcement ON[/color]")
		elif val == "off":
			_client_capabilities["contrast_enforce"] = false
			_append_log("[color=yellow]Accessibility: minimum contrast enforcement OFF[/color]")
		else:
			_append_log("[color=orange]Usage: a11y contrast on/off[/color]")
		return true

	# ── a11y distortion on/off ─────────────────────────────────────────────
	if lowered.begins_with("a11y distortion "):
		var val: String = lowered.substr(16).strip_edges()
		if val == "on":
			_client_capabilities["effects_distortion"] = true
			_apply_distortion_effects(true)
			_append_log("[color=yellow]Accessibility: atmospheric distortion ON[/color]")
		elif val == "off":
			_client_capabilities["effects_distortion"] = false
			_apply_distortion_effects(false)
			_append_log("[color=yellow]Accessibility: atmospheric distortion OFF[/color]")
		else:
			_append_log("[color=orange]Usage: a11y distortion on/off[/color]")
		return true

	# ── a11y weather on/off ────────────────────────────────────────────────
	if lowered.begins_with("a11y weather "):
		var val: String = lowered.substr(13).strip_edges()
		if val == "on":
			_client_capabilities["effects_weather"] = true
			_apply_weather_effects(true)
			_append_log("[color=yellow]Accessibility: weather effects ON[/color]")
		elif val == "off":
			_client_capabilities["effects_weather"] = false
			_apply_weather_effects(false)
			_append_log("[color=yellow]Accessibility: weather effects OFF[/color]")
		else:
			_append_log("[color=orange]Usage: a11y weather on/off[/color]")
		return true

	# ── a11y text <scale> ──────────────────────────────────────────────────
	var parts: PackedStringArray = lowered.split(" ", false)
	if parts.size() >= 3 and parts[0] == "a11y" and parts[1] == "text":
		var scale := -1.0
		var arg: String = parts[2]
		if TEXT_SCALE_PRESETS.has(arg):
			scale = float(TEXT_SCALE_PRESETS[arg])
		elif arg.is_valid_float():
			scale = clamp(float(arg) / 100.0, TEXT_SCALE_MIN, TEXT_SCALE_MAX)
		else:
			_append_log("[color=orange]Usage: a11y text <small|medium|large|xlarge|percent>[/color]")
			return true
		_apply_text_scale(scale)
		_append_log("[color=yellow]Accessibility: text scale %.0f%%[/color]" % (scale * 100.0))
		return true

	return false

# ── A11y apply helpers ──────────────────────────────────────────────────────

func _apply_dyslexia_font(enabled: bool) -> void:
	## Swap the log view font to a high-legibility face when enabled.
	## Falls back gracefully if the font resource isn't present.
	var font_path := "res://fonts/opendyslexic_regular.ttf" if enabled else ""
	if enabled and ResourceLoader.exists(font_path):
		var font: FontFile = load(font_path)
		log_view.add_theme_font_override("normal_font", font)
	else:
		log_view.remove_theme_font_override("normal_font")

func _apply_line_spacing(multiplier: float) -> void:
	## Apply line spacing multiplier to the main log view.
	var clamped: float = clamp(multiplier, 0.8, 3.0)
	log_view.add_theme_constant_override("line_separation", int((clamped - 1.0) * 20.0))

func _apply_distortion_effects(enabled: bool) -> void:
	## Toggle atmospheric text distortion effects (blight/wave).
	if is_instance_valid(atmosphere_layer):
		atmosphere_layer.visible = enabled
	# Uninstall/reinstall RichTextEffects on log_view based on flag.
	# Effects are installed at _ready; disabling clears them.
	if not enabled:
		log_view.install_effect(null)  # no-op clear — effects stay inert if atmosphere_layer is hidden
	_client_capabilities["effects_distortion"] = enabled

func _apply_weather_effects(enabled: bool) -> void:
	## Toggle weather/screen shader overlays.
	# The weather overlay node (if present) is controlled here.
	# If no dedicated weather node exists, this is a capability flag only —
	# the server reads effects_weather from the capabilities dict.
	_client_capabilities["effects_weather"] = enabled
	# Signal the server on next command cycle via capabilities update.
	_append_log("[color=gray](Weather effects toggle will apply on next server sync.)[/color]" if not enabled else "")


func _maybe_handle_local_onboarding_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()
	if lowered == "onboarding show":
		onboarding.show_panel()
		return true
	if lowered == "onboarding dismiss":
		onboarding.dismiss()
		_append_log("[color=aqua]Onboarding dismissed.[/color]")
		return true
	if lowered == "onboarding":
		_append_log("[color=orange]Usage: onboarding show | onboarding dismiss[/color]")
		return true
	return false

func _maybe_handle_local_keybind_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()

	# ── keybind list ───────────────────────────────────────────────────────────
	if lowered == "keybind list":
		_append_log("[color=aqua]Key bindings:[/color]")
		for line: String in keybindings_manager.get_summary_lines():
			_append_log(line)
		_append_log("[color=aqua]Commands: keybind set <action> <key>  |  keybind reset [action][/color]")
		return true

	# ── keybind reset [action] ─────────────────────────────────────────────────
	if lowered == "keybind reset":
		keybindings_manager.reset()
		_append_log("[color=yellow]Keybindings reset to defaults.[/color]")
		return true

	if lowered.begins_with("keybind reset "):
		var action: String = lowered.substr(14).strip_edges()
		if keybindings_manager.reset_action(action):
			_append_log("[color=yellow]Keybinding reset: %s[/color]" % action)
		else:
			_append_log("[color=orange]Unknown action '%s'. Try: keybind list[/color]" % action)
		return true

	# ── keybind set <action> <key> ─────────────────────────────────────────────
	if lowered.begins_with("keybind set "):
		var args: String = cmd.strip_edges().substr(12).strip_edges()
		var parts: PackedStringArray = args.split(" ", false)
		if parts.size() < 2:
			_append_log("[color=orange]Usage: keybind set <action> <key>[/color]")
			return true
		var action: String = parts[0].to_lower()
		var key_name: String = parts[1]  # preserve case; key names are Title-case
		if keybindings_manager.set_action_keys(action, PackedStringArray([key_name])):
			keybindings_manager.save()
			_append_log("[color=yellow]Keybinding updated: %s → %s[/color]" % [action, key_name])
		else:
			_append_log("[color=orange]Invalid action or key name. Try: keybind list[/color]")
		return true

	if lowered.begins_with("keybind"):
		_append_log("[color=orange]Usage: keybind list | keybind set <action> <key> | keybind reset [action][/color]")
		return true

	return false

func _maybe_handle_local_network_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()
	if lowered == "net diag":
		_append_log("[color=aqua]Network diag: %s[/color]" % JSON.stringify(_network_telemetry))
		return true
	if lowered == "net reconnect now":
		_cancel_reconnect()
		_reconnect_attempts = 0
		_append_log("[color=aqua]Manual reconnect requested.[/color]")
		_on_connect_pressed()
		return true
	if lowered == "net reconnect status":
		var status_text := "ON" if _auto_reconnect_enabled else "OFF"
		_append_log("[color=aqua]Auto reconnect: %s[/color]" % status_text)
		return true
	if lowered == "net reconnect on":
		_set_auto_reconnect_enabled(true, true)
		return true
	if lowered == "net reconnect off":
		_set_auto_reconnect_enabled(false, true)
		return true
	if lowered == "net resume now":
		if _resume_session_id == "":
			_append_log("[color=orange]No resume session id cached yet.[/color]")
			return true
		if not _is_connected_to_game_server():
			_append_log("[color=orange]Not connected. Use: net reconnect now[/color]")
			return true
		_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
		_active_client_send_line(JSON.stringify(parser.build_resume_session_envelope(_resume_session_id)))
		_append_log("[color=aqua]Resume requested for cached session.[/color]")
		_refresh_network_labels()
		return true
	if lowered.begins_with("net resume "):
		var wanted: String = cmd.strip_edges().substr(11).strip_edges()
		if wanted == "":
			_append_log("[color=orange]Usage: net resume <session_id>[/color]")
			return true
		_resume_session_id = wanted
		if not _is_connected_to_game_server():
			_append_log("[color=aqua]Resume session id cached. Connect to send resume.[/color]")
			return true
		_network_telemetry["lines_sent"] = int(_network_telemetry.get("lines_sent", 0)) + 1
		_active_client_send_line(JSON.stringify(parser.build_resume_session_envelope(_resume_session_id)))
		_append_log("[color=aqua]Resume requested for: %s[/color]" % _resume_session_id)
		_refresh_network_labels()
		return true
	if lowered == "net reset":
		var last_transport: String = str(_network_telemetry.get("last_transport", ""))
		var auto_reconnect_enabled: bool = bool(_network_telemetry.get("auto_reconnect_enabled", true))
		_network_telemetry = {
			"connect_attempts": 0,
			"connect_successes": 0,
			"disconnects": 0,
			"errors": 0,
			"lines_received": 0,
			"lines_sent": 0,
			"last_transport": last_transport,
			"last_error": "",
			"last_connected_at": "",
			"last_disconnected_at": "",
			"reconnect_state": "idle",
			"auto_reconnect_enabled": auto_reconnect_enabled
		}
		_append_log("[color=aqua]Network telemetry reset.[/color]")
		_refresh_network_labels()
		return true
	if lowered == "net export":
		var export_payload: Dictionary = _network_telemetry.duplicate(true)
		export_payload["session_id"] = _session_id
		export_payload["resume_session_id"] = _resume_session_id
		export_payload["timestamp"] = Time.get_datetime_string_from_system()
		var filename: String = "net_diag_%s.json" % Time.get_datetime_string_from_system().replace(":", "-")
		var path: String = "user://%s" % filename
		var file := FileAccess.open(path, FileAccess.WRITE)
		if file == null:
			_append_log("[color=red]Failed to export diagnostics: %s[/color]" % FileAccess.get_open_error())
			return true
		file.store_string(JSON.stringify(export_payload))
		file.close()
		_append_log("[color=aqua]Network diagnostics exported: %s[/color]" % path)
		return true
	return false

func _maybe_handle_local_theme_command(cmd: String) -> bool:
	var lowered: String = cmd.strip_edges().to_lower()
	if lowered == "theme list":
		var ids: PackedStringArray = []
		for key: Variant in _theme_catalog.keys():
			ids.append(str(key))
		ids.sort()
		_append_log("[color=aqua]Themes: %s[/color]" % ", ".join(ids))
		return true
	if not lowered.begins_with("theme use "):
		return false
	var theme_id: String = cmd.strip_edges().substr(10).strip_edges().to_lower()
	if theme_id == "":
		_append_log("[color=orange]Usage: theme use <theme_id>[/color]")
		return true
	if not _theme_catalog.has(theme_id):
		_append_log("[color=orange]Unknown theme: %s[/color]" % theme_id)
		return true
	_apply_theme(theme_id)
	return true

func _load_theme_catalog() -> void:
	_theme_catalog.clear()
	var dir: DirAccess = DirAccess.open(THEME_PACK_DIR)
	if dir == null:
		_append_log("[color=orange]Theme directory missing: %s[/color]" % THEME_PACK_DIR)
		return
	dir.list_dir_begin()
	var file_name: String = dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.get_extension().to_lower() == "json":
			var path: String = "%s/%s" % [THEME_PACK_DIR, file_name]
			var file: FileAccess = FileAccess.open(path, FileAccess.READ)
			if file != null:
				var raw: String = file.get_as_text()
				file.close()
				var parsed: Variant = JSON.parse_string(raw)
				if typeof(parsed) == TYPE_DICTIONARY:
					var pack: Dictionary = parsed as Dictionary
					var validation_errors: PackedStringArray = _validate_theme_pack(pack, file_name)
					if validation_errors.is_empty():
						var theme_id: String = str(pack.get("theme_id", "")).to_lower()
						_theme_catalog[theme_id] = pack
					else:
						_append_log("[color=orange]Theme skipped (%s): %s[/color]" % [
							file_name,
							"; ".join(validation_errors)
						])
		file_name = dir.get_next()
	dir.list_dir_end()
	if _theme_catalog.is_empty():
		_append_log("[color=orange]No theme packs loaded.[/color]")

func _apply_theme(theme_id: String) -> void:
	if not _theme_catalog.has(theme_id):
		return
	var pack: Dictionary = _theme_catalog.get(theme_id, {}) as Dictionary
	var ui: Dictionary = pack.get("ui_strings", {}) as Dictionary
	var lexicon: Dictionary = pack.get("lexicon", {}) as Dictionary
	var icon_tokens: Dictionary = pack.get("icon_tokens", {}) as Dictionary

	status_title_label.text = str(ui.get("status_title", "Status"))
	inventory_title_label.text = str(ui.get("inventory_title", "Inventory"))
	journal_title_label.text = str(ui.get("journal_title", "Journal"))
	nearby_title_label.text = str(ui.get("nearby_title", "Nearby"))
	world_state_title_label.text = str(ui.get("world_state_title", "World State"))
	network_title_label.text = str(ui.get("network_title", "Network"))
	adventure_title_label.text = str(ui.get("adventure_title", "Adventure"))
	asset_title_label.text = str(ui.get("asset_title", "Asset Preview"))
	connect_button.text = str(ui.get("connect_button", "Connect"))
	disconnect_button.text = str(ui.get("disconnect_button", "Disconnect"))
	send_button.text = str(ui.get("send_button", "Send"))

	var field_label: String = str(lexicon.get("world_field_id", "world_field"))
	field_id_input.text = field_label
	command_input.placeholder_text = str(ui.get("command_placeholder", "Type command..."))
	_theme_icon_tokens = icon_tokens.duplicate(true)
	_apply_theme_style(pack.get("style_tokens", {}) as Dictionary)
	_active_theme_id = theme_id
	_append_log("[color=green]Theme active: %s[/color]" % _active_theme_id)

func _validate_theme_pack(pack: Dictionary, source_name: String) -> PackedStringArray:
	var errors: PackedStringArray = []
	var theme_id: String = str(pack.get("theme_id", "")).strip_edges().to_lower()
	if theme_id == "":
		errors.append("%s missing theme_id" % source_name)
	var display_name: String = str(pack.get("display_name", "")).strip_edges()
	if display_name == "":
		errors.append("%s missing display_name" % source_name)
	if pack.has("ui_strings") and typeof(pack.get("ui_strings")) != TYPE_DICTIONARY:
		errors.append("%s ui_strings must be dictionary" % source_name)
	if pack.has("lexicon") and typeof(pack.get("lexicon")) != TYPE_DICTIONARY:
		errors.append("%s lexicon must be dictionary" % source_name)
	if pack.has("style_tokens") and typeof(pack.get("style_tokens")) != TYPE_DICTIONARY:
		errors.append("%s style_tokens must be dictionary" % source_name)
	if pack.has("icon_tokens") and typeof(pack.get("icon_tokens")) != TYPE_DICTIONARY:
		errors.append("%s icon_tokens must be dictionary" % source_name)
	return errors

func _icon_token(key: String, fallback: String) -> String:
	var value: String = str(_theme_icon_tokens.get(key, fallback))
	if value.strip_edges() == "":
		return fallback
	return value

func _apply_theme_style(style_tokens: Dictionary) -> void:
	var accent: Color = _parse_theme_color(style_tokens.get("accent_color", "#BFE6FF"), THEME_DEFAULT_ACCENT)
	var text_color: Color = _parse_theme_color(style_tokens.get("text_color", "#E6E6E6"), THEME_DEFAULT_TEXT)
	var spacing: int = clamp(int(style_tokens.get("ui_density", THEME_DEFAULT_DENSITY)), 2, 20)
	root_vbox.add_theme_constant_override("separation", spacing)

	status_title_label.self_modulate = accent
	inventory_title_label.self_modulate = accent
	journal_title_label.self_modulate = accent
	nearby_title_label.self_modulate = accent
	world_state_title_label.self_modulate = accent
	network_title_label.self_modulate = accent
	adventure_title_label.self_modulate = accent
	asset_title_label.self_modulate = accent

	status_primary_label.self_modulate = text_color
	status_vitals_label.self_modulate = text_color
	status_effects_label.self_modulate = text_color
	inventory_summary_label.self_modulate = text_color
	journal_summary_label.self_modulate = text_color
	nearby_location_label.self_modulate = text_color
	nearby_exits_label.self_modulate = text_color
	nearby_interactions_label.self_modulate = text_color
	world_state_label.self_modulate = text_color
	network_summary_label.self_modulate = text_color
	network_detail_label.self_modulate = text_color
	adventure_state_label.self_modulate = text_color
	adventure_summary_label.self_modulate = text_color
	adventure_catalog_label.self_modulate = text_color
	adventure_report_label.self_modulate = text_color
	asset_alt_text.self_modulate = text_color

func _parse_theme_color(value: Variant, fallback: Color) -> Color:
	if typeof(value) == TYPE_COLOR:
		return value as Color
	if typeof(value) == TYPE_STRING:
		var s: String = str(value)
		if s.is_valid_html_color():
			return Color.html(s)
	return fallback

func _apply_text_scale(scale: float) -> void:
	var clamped: float = clamp(scale, TEXT_SCALE_MIN, TEXT_SCALE_MAX)
	_client_capabilities["text_scale"] = clamped
	var window: Window = get_window()
	window.content_scale_factor = clamped

func _refresh_network_labels() -> void:
	var transport: String = str(_network_telemetry.get("last_transport", "--"))
	var attempts: int = int(_network_telemetry.get("connect_attempts", 0))
	var connects: int = int(_network_telemetry.get("connect_successes", 0))
	var disconnects: int = int(_network_telemetry.get("disconnects", 0))
	var errors: int = int(_network_telemetry.get("errors", 0))
	network_summary_label.text = "Transport %s  Attempts %d  Up %d  Down %d  Err %d" % [
		transport, attempts, connects, disconnects, errors
	]

	var sent: int = int(_network_telemetry.get("lines_sent", 0))
	var recv: int = int(_network_telemetry.get("lines_received", 0))
	var last_error: String = str(_network_telemetry.get("last_error", "")).strip_edges()
	var reconnect_state: String = str(_network_telemetry.get("reconnect_state", "idle"))
	var auto_reconnect_enabled: bool = bool(_network_telemetry.get("auto_reconnect_enabled", true))
	var countdown := ""
	if _reconnect_pending:
		var remaining: float = max(0.0, float(_reconnect_deadline_msec - Time.get_ticks_msec()) / 1000.0)
		countdown = "  Reconnect in %.1fs" % remaining
	if last_error == "":
		last_error = "none"
	var reconnect_mode: String = "ON" if auto_reconnect_enabled else "OFF"
	network_detail_label.text = "Sent %d  Recv %d  Last error: %s  Reconnect(%s): %s%s" % [
		sent, recv, last_error, reconnect_mode, reconnect_state, countdown
	]

func _should_auto_reconnect(label: String) -> bool:
	if not _auto_reconnect_enabled:
		return false
	return (_using_websocket() and label == "WebSocket") or ((not _using_websocket()) and label == "TCP")

func _schedule_reconnect() -> void:
	if _reconnect_attempts >= _max_reconnect_attempts:
		_network_telemetry["reconnect_state"] = "exhausted"
		_append_log("[color=orange]Reconnect exhausted after %d attempts.[/color]" % _reconnect_attempts)
		return
	_reconnect_attempts += 1
	var wait_seconds: int = min(30, int(pow(2.0, float(_reconnect_attempts - 1))))
	_reconnect_deadline_msec = Time.get_ticks_msec() + (wait_seconds * 1000)
	_reconnect_pending = true
	_network_telemetry["reconnect_state"] = "pending_%ds" % wait_seconds
	_append_log("[color=yellow]Auto reconnect attempt %d/%d in %ds.[/color]" % [
		_reconnect_attempts, _max_reconnect_attempts, wait_seconds
	])

func _cancel_reconnect() -> void:
	_reconnect_pending = false
	_network_telemetry["reconnect_state"] = "idle"

func _set_auto_reconnect_enabled(enabled: bool, log_change: bool) -> void:
	_auto_reconnect_enabled = enabled
	_network_telemetry["auto_reconnect_enabled"] = enabled
	if not enabled:
		_cancel_reconnect()
	if log_change:
		if enabled:
			_append_log("[color=aqua]Auto reconnect enabled.[/color]")
		else:
			_append_log("[color=aqua]Auto reconnect disabled.[/color]")
	_sync_auto_reconnect_button()
	_refresh_network_labels()

func _sync_auto_reconnect_button() -> void:
	auto_reconnect_button.button_pressed = _auto_reconnect_enabled
	auto_reconnect_button.text = "Auto Reconnect: %s" % ("ON" if _auto_reconnect_enabled else "OFF")

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		crash_recovery.clear_marker()
		get_tree().quit()
	elif what == NOTIFICATION_APPLICATION_PAUSED:
		_append_log("[color=yellow]App suspended. Conserving network...[/color]")
		if tcp_client.is_connected_to_server() or ws_client.is_connected_to_server():
			_resume_session_id = _session_id
			_active_client_send_line(JSON.stringify({"type": "disconnect"}))
			tcp_client.disconnect_from_server()
			ws_client.disconnect_from_server()
	elif what == NOTIFICATION_APPLICATION_RESUMED:
		_append_log("[color=yellow]App resumed.[/color]")
		if not (tcp_client.is_connected_to_server() or ws_client.is_connected_to_server()):
			if _auto_reconnect_enabled and _resume_session_id != "":
				_schedule_reconnect()

func _on_crash_recovery_restore(host: String, port: int, session_id: String, transport: String) -> void:
	host_input.text = host
	port_input.text = str(port)
	transport_select.selected = 1 if transport == "WebSocket" else 0
	_resume_session_id = session_id
	_append_log("[color=aqua]Crash recovery: reconnecting to %s:%d…[/color]" % [host, port])
	_on_connect_pressed()

func _apply_launch_config() -> void:
	## Read launch parameters written by launcher_controller.gd via Engine.set_meta().
	## All keys are consumed (removed) here so subsequent restarts start clean.
	##
	## Expected keys (all optional — launcher may not have run):
	##   launch_host          String  — overrides host_input.text
	##   launch_port          int     — overrides port_input.text
	##   launch_mode          String  — "offline" | "online"; logged on connect
	##   launch_auto_connect  bool    — if true, initiates connection immediately

	var mode := ""
	if Engine.has_meta("launch_mode"):
		mode = str(Engine.get_meta("launch_mode"))
		Engine.remove_meta("launch_mode")

	if Engine.has_meta("launch_host"):
		host_input.text = str(Engine.get_meta("launch_host"))
		Engine.remove_meta("launch_host")

	if Engine.has_meta("launch_port"):
		port_input.text = str(Engine.get_meta("launch_port"))
		Engine.remove_meta("launch_port")

	# Launcher always intends WebSocket (the runtime server is a WebSocket server).
	# Set the transport selector so _on_connect_pressed() picks the right client.
	if mode != "":
		transport_select.selected = 1  # WebSocket

	if mode == "offline":
		_append_log("[color=aqua]Offline mode — connecting to local server.[/color]")
	elif mode == "online":
		_append_log("[color=aqua]Online mode — connecting to remote server.[/color]")

	if Engine.has_meta("launch_auto_connect"):
		Engine.remove_meta("launch_auto_connect")
		_on_connect_pressed()
