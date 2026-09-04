extends Control

## Launcher controller — shown before the main game scene.
##
## Responsibilities:
##   - Present "Play Offline" and "Connect Online" entry points.
##   - Pack launch parameters into Engine metadata so main_controller.gd
##     can read them on its _ready() without requiring an autoload singleton.
##   - Transition to the main game scene.
##
## Launch metadata keys written before scene transition:
##   "launch_host"          String  — hostname or IP to connect to
##   "launch_port"          int     — port number
##   "launch_mode"          String  — "offline" | "online"
##   "launch_auto_connect"  bool    — true = main scene connects on _ready()

const MAIN_SCENE := "res://scenes/main.tscn"
const DEFAULT_OFFLINE_HOST := "127.0.0.1"
const DEFAULT_PORT := 8765

@onready var offline_button: Button = $CenterContainer/LauncherVBox/OfflineButton
@onready var connect_online_button: Button = $CenterContainer/LauncherVBox/ConnectOnlineButton
@onready var online_panel: VBoxContainer = $CenterContainer/LauncherVBox/OnlinePanel
@onready var host_input: LineEdit = $CenterContainer/LauncherVBox/OnlinePanel/HostPortRow/HostInput
@onready var port_input: LineEdit = $CenterContainer/LauncherVBox/OnlinePanel/HostPortRow/PortInput
@onready var connect_button: Button = $CenterContainer/LauncherVBox/OnlinePanel/ConnectButton

func _ready() -> void:
	offline_button.pressed.connect(_on_offline_pressed)
	connect_online_button.pressed.connect(_on_connect_online_pressed)
	connect_button.pressed.connect(_on_connect_pressed)
	port_input.text_submitted.connect(func(_t: String) -> void: _on_connect_pressed())
	host_input.text_submitted.connect(func(_t: String) -> void: _on_connect_pressed())

func _on_offline_pressed() -> void:
	Engine.set_meta("launch_host", DEFAULT_OFFLINE_HOST)
	Engine.set_meta("launch_port", DEFAULT_PORT)
	Engine.set_meta("launch_mode", "offline")
	Engine.set_meta("launch_auto_connect", true)
	get_tree().change_scene_to_file(MAIN_SCENE)

func _on_connect_online_pressed() -> void:
	online_panel.visible = true
	connect_online_button.visible = false
	host_input.grab_focus()

func _on_connect_pressed() -> void:
	var host: String = host_input.text.strip_edges()
	if host == "":
		host = DEFAULT_OFFLINE_HOST
	var port: int = _safe_int(port_input.text, DEFAULT_PORT)
	Engine.set_meta("launch_host", host)
	Engine.set_meta("launch_port", port)
	Engine.set_meta("launch_mode", "online")
	Engine.set_meta("launch_auto_connect", true)
	get_tree().change_scene_to_file(MAIN_SCENE)

func _safe_int(text: String, fallback: int) -> int:
	var trimmed := text.strip_edges()
	if trimmed == "" or not trimmed.is_valid_int():
		return fallback
	return int(trimmed)
