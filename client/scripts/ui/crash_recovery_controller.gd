extends Control
class_name CrashRecoveryController

## Crash / unclean-exit recovery controller.
##
## Lifecycle:
##   1. On connection:  write_marker(host, port, transport)
##   2. On hello:       record_session_id(session_id)  — updates the marker in place
##   3. On clean exit:  clear_marker()
##   4. Next launch:    check_and_show() — detects stale marker, shows recovery UI
##
## "Clean exit" means the player pressed Disconnect, the server sent goodbye,
## or the window was closed normally (via NOTIFICATION_WM_CLOSE_REQUEST).
## Any other termination leaves the marker, triggering recovery on next launch.
##
## Signals emitted by the UI buttons:
##   restore_requested(host, port, session_id, transport)
##   dismissed

const MARKER_PATH := "user://session_alive.json"

signal restore_requested(host: String, port: int, session_id: String, transport: String)
signal dismissed

@onready var detail_label: RichTextLabel = $CenterContainer/Panel/VBox/DetailLabel
@onready var restore_button: Button = $CenterContainer/Panel/VBox/ButtonRow/RestoreButton
@onready var fresh_button: Button = $CenterContainer/Panel/VBox/ButtonRow/FreshButton

var _marker_data: Dictionary = {}


func _ready() -> void:
	restore_button.pressed.connect(_on_restore_pressed)
	fresh_button.pressed.connect(_on_fresh_pressed)
	visible = false


# ── Public API ────────────────────────────────────────────────────────────────

func check_and_show() -> void:
	"""Read the marker file. If it exists, populate the dialog and show it."""
	if not FileAccess.file_exists(MARKER_PATH):
		return
	var file := FileAccess.open(MARKER_PATH, FileAccess.READ)
	if file == null:
		return
	var raw := file.get_as_text()
	file.close()
	var parsed: Variant = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		clear_marker()
		return
	_marker_data = parsed as Dictionary
	_populate_detail_label()
	visible = true


func write_marker(host: String, port: int, transport: String) -> void:
	"""Write (or overwrite) the session-alive marker with current connection info."""
	var data: Dictionary = {
		"host": host,
		"port": port,
		"transport": transport,
		"session_id": "",
		"written_at": Time.get_datetime_string_from_system(),
	}
	_write_json(data)


func record_session_id(session_id: String) -> void:
	"""Update the marker with the session_id received in the hello event."""
	if not FileAccess.file_exists(MARKER_PATH):
		return
	var file := FileAccess.open(MARKER_PATH, FileAccess.READ)
	if file == null:
		return
	var raw := file.get_as_text()
	file.close()
	var parsed: Variant = JSON.parse_string(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		return
	var data: Dictionary = parsed as Dictionary
	data["session_id"] = session_id
	_write_json(data)


func clear_marker() -> void:
	"""Remove the session-alive marker (call on any clean exit path)."""
	if FileAccess.file_exists(MARKER_PATH):
		DirAccess.remove_absolute(ProjectSettings.globalize_path(MARKER_PATH))


func has_marker() -> bool:
	"""Return true if an uncleared marker exists on disk."""
	return FileAccess.file_exists(MARKER_PATH)


# ── Button handlers ───────────────────────────────────────────────────────────

func _on_restore_pressed() -> void:
	visible = false
	var host: String = str(_marker_data.get("host", "127.0.0.1"))
	var port: int = int(_marker_data.get("port", 8765))
	var session_id: String = str(_marker_data.get("session_id", ""))
	var transport: String = str(_marker_data.get("transport", "WebSocket"))
	clear_marker()
	restore_requested.emit(host, port, session_id, transport)


func _on_fresh_pressed() -> void:
	visible = false
	clear_marker()
	dismissed.emit()


# ── Internal ──────────────────────────────────────────────────────────────────

func _populate_detail_label() -> void:
	var host: String = str(_marker_data.get("host", "?"))
	var port: int = int(_marker_data.get("port", 0))
	var transport: String = str(_marker_data.get("transport", "?"))
	var session_id: String = str(_marker_data.get("session_id", ""))
	var written_at: String = str(_marker_data.get("written_at", "unknown"))

	var session_line: String = ""
	if session_id != "":
		session_line = "\n  Session ID: %s" % session_id

	detail_label.text = (
		"[b]An unclean exit was detected from your last session.[/b]\n\n"
		+ "Last session:\n"
		+ "  Server: %s:%d  (%s)\n" % [host, port, transport]
		+ "  Time:   %s" % written_at
		+ session_line
		+ "\n\nReconnect to resume where you left off, or start fresh."
	)


func _write_json(data: Dictionary) -> void:
	var file := FileAccess.open(MARKER_PATH, FileAccess.WRITE)
	if file == null:
		push_warning("CrashRecoveryController: cannot write %s (err %d)" % [
			MARKER_PATH, FileAccess.get_open_error()
		])
		return
	file.store_string(JSON.stringify(data))
	file.close()
