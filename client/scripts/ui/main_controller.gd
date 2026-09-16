extends Control
class_name MainController

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
@onready var combat_title_label: Label = $VBox/AssetPreview/CombatTitle
@onready var combat_summary_label: Label = $VBox/AssetPreview/CombatSummary
@onready var combat_targets_label: RichTextLabel = $VBox/AssetPreview/CombatTargets
@onready var inventory_title_label: Label = $VBox/AssetPreview/InventoryTitle
@onready var inventory_summary_label: Label = $VBox/AssetPreview/InventorySummary
@onready var inventory_list_label: RichTextLabel = $VBox/AssetPreview/InventoryList
@onready var crafting_title_label: Label = $VBox/AssetPreview/CraftingTitle
@onready var crafting_summary_label: Label = $VBox/AssetPreview/CraftingSummary
@onready var crafting_list_label: RichTextLabel = $VBox/AssetPreview/CraftingList
@onready var collections_title_label: Label = $VBox/AssetPreview/CollectionsTitle
@onready var collections_summary_label: Label = $VBox/AssetPreview/CollectionsSummary
@onready var collections_list_label: RichTextLabel = $VBox/AssetPreview/CollectionsList
@onready var discoveries_title_label: Label = $VBox/AssetPreview/DiscoveriesTitle
@onready var discoveries_summary_label: Label = $VBox/AssetPreview/DiscoveriesSummary
@onready var discoveries_list_label: RichTextLabel = $VBox/AssetPreview/DiscoveriesList
@onready var relationships_title_label: Label = $VBox/AssetPreview/RelationshipsTitle
@onready var relationships_summary_label: Label = $VBox/AssetPreview/RelationshipsSummary
@onready var relationships_list_label: RichTextLabel = $VBox/AssetPreview/RelationshipsList
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

var network_lifecycle: NetworkLifecycleController
var operator_console: OperatorConsoleController
var profiles: ProfileController
var gm_auth: GmAuthController
var authoring_locks: AuthoringLockController
var finite_adventure_ui: FiniteAdventureUiController
var theme_controller: ThemeController
var accessibility: AccessibilityController
var game_state_payloads: GameStatePayloadsController

func _ready() -> void:
	network_lifecycle = NetworkLifecycleController.new(self)
	operator_console = OperatorConsoleController.new(self)
	profiles = ProfileController.new(self)
	gm_auth = GmAuthController.new(self)
	authoring_locks = AuthoringLockController.new(self)
	finite_adventure_ui = FiniteAdventureUiController.new(self)
	theme_controller = ThemeController.new(self)
	accessibility = AccessibilityController.new(self)
	game_state_payloads = GameStatePayloadsController.new(self)

	log_view.install_effect(BLIGHT_TEXT_EFFECT.new())
	log_view.install_effect(ATMOSPHERIC_TEXT_EFFECT.new())

	connect_button.pressed.connect(network_lifecycle._on_connect_pressed)
	disconnect_button.pressed.connect(network_lifecycle._on_disconnect_pressed)
	policy_button.pressed.connect(func() -> void: network_lifecycle._send_command_immediate("server policy"))
	field_pulse_button.pressed.connect(network_lifecycle._on_field_pulse_pressed)
	send_button.pressed.connect(network_lifecycle._on_send_pressed)
	command_input.text_submitted.connect(network_lifecycle._on_command_submitted)
	auto_reconnect_button.toggled.connect(network_lifecycle._on_auto_reconnect_toggled)
	gm_auth_button.pressed.connect(gm_auth._on_gm_auth_pressed)
	gm_auth_input.text_submitted.connect(func(_text: String) -> void: gm_auth._on_gm_auth_pressed())
	profile_refresh_button.pressed.connect(profiles._on_profile_refresh_pressed)
	profile_apply_button.pressed.connect(profiles._on_profile_apply_pressed)
	profile_cancel_button.pressed.connect(profiles._on_profile_cancel_pressed)
	profile_preset_select.item_selected.connect(profiles._on_profile_selected)
	operator_domain_select.item_selected.connect(operator_console._on_operator_domain_selected)
	operator_action_select.item_selected.connect(operator_console._on_operator_action_selected)
	operator_run_button.pressed.connect(operator_console._on_operator_run_pressed)
	operator_arg_input.text_submitted.connect(func(_text: String) -> void: operator_console._on_operator_run_pressed())
	adventure_catalog_select.item_selected.connect(finite_adventure_ui._on_adventure_catalog_selected)
	adventure_catalog_button.pressed.connect(func() -> void: finite_adventure_ui._request_finite_adventure_catalog())
	adventure_campaign_input.text_submitted.connect(func(_text: String) -> void: finite_adventure_ui._on_adventure_start_pressed())
	adventure_start_button.pressed.connect(finite_adventure_ui._on_adventure_start_pressed)
	adventure_status_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure status"))
	adventure_abandon_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure abandon"))
	adventure_checkpoint_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure checkpoint"))
	adventure_restore_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure restore"))
	adventure_reset_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure reset"))
	adventure_replay_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure replay"))
	adventure_summary_md_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure summary markdown"))
	adventure_summary_text_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure summary text"))
	adventure_summary_json_button.pressed.connect(func() -> void: finite_adventure_ui._send_adventure_command("adventure summary json"))

	btn_status.pressed.connect(func(): network_lifecycle._send_command_immediate("status"))
	btn_inventory.pressed.connect(func(): network_lifecycle._send_command_immediate("inventory"))
	btn_quests.pressed.connect(func(): network_lifecycle._send_command_immediate("quests"))
	btn_policy.pressed.connect(func(): network_lifecycle._send_command_immediate("server policy"))
	btn_n.pressed.connect(func(): network_lifecycle._send_command_immediate("north"))
	btn_s.pressed.connect(func(): network_lifecycle._send_command_immediate("south"))
	btn_e.pressed.connect(func(): network_lifecycle._send_command_immediate("east"))
	btn_w.pressed.connect(func(): network_lifecycle._send_command_immediate("west"))
	btn_nw.pressed.connect(func(): network_lifecycle._send_command_immediate("northwest"))
	btn_ne.pressed.connect(func(): network_lifecycle._send_command_immediate("northeast"))
	btn_sw.pressed.connect(func(): network_lifecycle._send_command_immediate("southwest"))
	btn_se.pressed.connect(func(): network_lifecycle._send_command_immediate("southeast"))
	btn_look.pressed.connect(func(): network_lifecycle._send_command_immediate("look"))
	authoring_acquire_button.pressed.connect(authoring_locks._on_authoring_acquire_pressed)
	authoring_renew_button.pressed.connect(authoring_locks._on_authoring_renew_pressed)
	authoring_release_button.pressed.connect(authoring_locks._on_authoring_release_pressed)
	authoring_edit_button.pressed.connect(authoring_locks._on_authoring_edit_pressed)
	authoring_edit_stale_button.pressed.connect(authoring_locks._on_authoring_edit_stale_pressed)
	authoring_asset_input.text_submitted.connect(func(_text: String) -> void: authoring_locks._request_lock_status())

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

	network_lifecycle._bind_client_signals(tcp_client, "TCP")
	network_lifecycle._bind_client_signals(ws_client, "WebSocket")
	theme_controller._load_theme_catalog()
	theme_controller._apply_theme("default")
	authoring_locks._refresh_authoring_status()
	profiles._refresh_profile_status()
	operator_console._refresh_operator_actions()
	_refresh_policy_affordances()
	network_lifecycle._sync_auto_reconnect_button()
	network_lifecycle._refresh_network_labels()
	_refresh_startup_diagnostics_labels()
	finite_adventure_ui._refresh_finite_adventure_catalog_picker()
	finite_adventure_ui._refresh_finite_adventure_panel()
	keybindings_manager.load()
	# Intercept the window-close button so we can clear the crash-recovery marker.
	get_tree().set_auto_accept_quit(false)
	crash_recovery.restore_requested.connect(network_lifecycle._on_crash_recovery_restore)
	crash_recovery.dismissed.connect(func() -> void: onboarding.show_if_first_run())
	char_create.name_submitted.connect(network_lifecycle._on_char_name_submitted)
	_apply_launch_config()
	crash_recovery.check_and_show()
	if not crash_recovery.visible:
		onboarding.show_if_first_run()

func _process(_delta: float) -> void:
	_authoring_status_refresh_accum_s += _delta
	if _authoring_status_refresh_accum_s >= 0.25:
		_authoring_status_refresh_accum_s = 0.0
		authoring_locks._refresh_authoring_status()
	authoring_locks._tick_authoring_auto_renew(0.25)
	if _reconnect_pending:
		var now: int = Time.get_ticks_msec()
		if now >= _reconnect_deadline_msec:
			_reconnect_pending = false
			_network_telemetry["reconnect_state"] = "attempting"
			network_lifecycle._refresh_network_labels()
			network_lifecycle._on_connect_pressed()
		else:
			network_lifecycle._refresh_network_labels()

func _input(event: InputEvent) -> void:
	if not event is InputEventKey:
		return
	var key_event := event as InputEventKey
	if not key_event.pressed:
		return
	# History navigation — only active while the command input has focus.
	if command_input.has_focus():
		if keybindings_manager.is_key_for_action("mud_history_prev", key_event.keycode):
			network_lifecycle._history_navigate(-1)
			get_viewport().set_input_as_handled()
			return
		if keybindings_manager.is_key_for_action("mud_history_next", key_event.keycode):
			network_lifecycle._history_navigate(1)
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
	operator_console._refresh_operator_actions()

func _is_connected_to_game_server() -> bool:
	return tcp_client.is_connected_to_server() or ws_client.is_connected_to_server()

func _on_meta_clicked(meta: Variant) -> void:
	var cmd = str(meta)
	if cmd.begins_with("cmd:"):
		network_lifecycle._send_command_immediate(cmd.substr(4))

func _on_line_received(line: String) -> void:
	_network_telemetry["lines_received"] = int(_network_telemetry.get("lines_received", 0)) + 1
	network_lifecycle._refresh_network_labels()
	var event: Dictionary = parser.parse_event(line)
	var event_type: String = str(event.get("type", "unknown"))
	var payload: Variant = event.get("payload", "")
	if event_type == "hello":
		_append_log("[color=aqua]HELLO[/color] %s" % JSON.stringify(payload))
		if typeof(payload) == TYPE_DICTIONARY:
			var body: Dictionary = payload as Dictionary
			var operator_catalog_value: Variant = body.get("operator_catalog", {})
			if typeof(operator_catalog_value) == TYPE_DICTIONARY:
				operator_console._apply_operator_catalog_payload(operator_catalog_value as Dictionary)
			var startup_diag_value: Variant = body.get("startup_diagnostics", {})
			if typeof(startup_diag_value) == TYPE_DICTIONARY:
				_apply_startup_diagnostics_payload(startup_diag_value as Dictionary)
			var sid: String = str(body.get("session_id", "")).strip_edges()
			if sid != "":
				_session_id = sid
				_resume_session_id = sid
				crash_recovery.record_session_id(sid)
				authoring_locks._request_lock_status()
				profiles._request_profile_presets()
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
				authoring_locks._request_lock_status()
				profiles._request_profile_presets()
	elif event_type == "lock_state":
		authoring_locks._apply_lock_state_payload(payload)
		_append_log("[color=yellow]Lock state: %s[/color]" % JSON.stringify(payload))
	elif event_type == "lock_state_delta":
		authoring_locks._apply_lock_delta_payload(payload)
		_append_log("[color=yellow]Lock delta: %s[/color]" % JSON.stringify(payload))
	elif event_type == "protocol_mismatch":
		network_lifecycle._apply_degraded_mode("Protocol mismatch with server; enabling compatibility mode.")
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
		game_state_payloads._handle_asset_payload(payload)
	elif event_type == "status":
		game_state_payloads._handle_status_payload(payload)
	elif event_type == "combat":
		game_state_payloads._handle_combat_payload(payload)
	elif event_type == "inventory":
		game_state_payloads._handle_inventory_payload(payload)
	elif event_type == "crafting":
		game_state_payloads._handle_crafting_payload(payload)
	elif event_type == "collections":
		game_state_payloads._handle_collections_payload(payload)
	elif event_type == "discoveries":
		game_state_payloads._handle_discoveries_payload(payload)
	elif event_type == "relationships":
		game_state_payloads._handle_relationships_payload(payload)
	elif event_type == "quests":
		game_state_payloads._handle_quests_payload(payload)
	elif event_type == "nearby":
		game_state_payloads._handle_nearby_payload(payload)
	elif event_type == "world_state":
		game_state_payloads._handle_world_state_payload(payload)
	elif event_type == "world_effects_status":
		game_state_payloads._handle_world_effects_status_payload(payload)
	elif event_type == "world_effects_providers":
		game_state_payloads._handle_world_effects_providers_payload(payload)
	elif event_type == "server_policy":
		_handle_server_policy_payload(payload)
	elif event_type == "finite_adventure_state":
		finite_adventure_ui._handle_finite_adventure_state_payload(payload)
	elif event_type == "finite_adventure_summary":
		finite_adventure_ui._handle_finite_adventure_summary_payload(payload)
	elif event_type == "finite_adventure_report":
		finite_adventure_ui._handle_finite_adventure_report_payload(payload)
	elif event_type == "finite_adventure_catalog":
		finite_adventure_ui._handle_finite_adventure_catalog_payload(payload)
	elif event_type == "audit_result":
		_handle_audit_result_payload(payload)
	elif event_type == "profile_presets":
		profiles._handle_profile_presets_payload(payload)
	elif event_type == "auth_state":
		gm_auth._handle_auth_state_payload(payload)
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
		operator_console._apply_operator_catalog_payload(operator_catalog_value as Dictionary)
	var lines: PackedStringArray = PackedStringArray()
	lines.append("[b][color=aqua]Server Policy[/color][/b]")

	var profile_source: String = str(body.get("profile_source_path", "")).strip_edges()
	if profile_source == "":
		profile_source = "(default runtime profile)"
	_active_profile_path = profile_source
	var active_from_policy: String = profiles._extract_profile_preset_from_path(profile_source)
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
				finite_adventure_ui._refresh_finite_adventure_catalog_picker()
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
				finite_adventure_ui._request_finite_adventure_catalog()
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
	profiles._refresh_profile_status()
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
	var combat_enabled: bool = _game_system_enabled("combat")
	var crafting_enabled: bool = _game_system_enabled("crafting")
	var collections_enabled: bool = _game_system_enabled("collections")
	var discoveries_enabled: bool = _game_system_enabled("discoveries")
	var relationships_enabled: bool = _game_system_enabled("social")
	btn_inventory.visible = inventory_enabled
	btn_quests.visible = quests_enabled
	inventory_title_label.visible = inventory_enabled
	inventory_summary_label.visible = inventory_enabled
	inventory_list_label.visible = inventory_enabled
	crafting_title_label.visible = crafting_enabled
	crafting_summary_label.visible = crafting_enabled
	crafting_list_label.visible = crafting_enabled
	collections_title_label.visible = collections_enabled
	collections_summary_label.visible = collections_enabled
	collections_list_label.visible = collections_enabled
	discoveries_title_label.visible = discoveries_enabled
	discoveries_summary_label.visible = discoveries_enabled
	discoveries_list_label.visible = discoveries_enabled
	relationships_title_label.visible = relationships_enabled
	relationships_summary_label.visible = relationships_enabled
	relationships_list_label.visible = relationships_enabled
	journal_title_label.visible = quests_enabled
	journal_summary_label.visible = quests_enabled
	journal_list_label.visible = quests_enabled
	combat_title_label.visible = combat_enabled
	combat_summary_label.visible = combat_enabled
	combat_targets_label.visible = combat_enabled
	# Campaign/adventure controls currently depend on quest state. Hide them for
	# a game contract that deliberately has no quest system.
	adventure_row.visible = quests_enabled
	adventure_title_label.visible = quests_enabled
	adventure_state_label.visible = quests_enabled
	adventure_summary_label.visible = quests_enabled
	adventure_catalog_label.visible = quests_enabled
	adventure_objective_label.visible = quests_enabled
	adventure_report_label.visible = quests_enabled

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

func _sha256_hex(text: String) -> String:
	var ctx := HashingContext.new()
	var err: int = ctx.start(HashingContext.HASH_SHA256)
	if err != OK:
		return ""
	ctx.update(text.to_utf8_buffer())
	return ctx.finish().hex_encode()

func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		crash_recovery.clear_marker()
		get_tree().quit()
	elif what == NOTIFICATION_APPLICATION_PAUSED:
		_append_log("[color=yellow]App suspended. Conserving network...[/color]")
		if tcp_client.is_connected_to_server() or ws_client.is_connected_to_server():
			_resume_session_id = _session_id
			network_lifecycle._active_client_send_line(JSON.stringify({"type": "disconnect"}))
			tcp_client.disconnect_from_server()
			ws_client.disconnect_from_server()
	elif what == NOTIFICATION_APPLICATION_RESUMED:
		_append_log("[color=yellow]App resumed.[/color]")
		if not (tcp_client.is_connected_to_server() or ws_client.is_connected_to_server()):
			if _auto_reconnect_enabled and _resume_session_id != "":
				network_lifecycle._schedule_reconnect()

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
		network_lifecycle._on_connect_pressed()
