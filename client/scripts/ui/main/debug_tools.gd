# scripts/ui/main/debug_tools.gd
# What a tester gets when the server was started with `--allow-debug-commands` (the desktop launcher's "Quick play"): a
# small row above the command line with a button that skips the scene being played and a picker of the set's checkpoints
# (scenes named `checkpoint_<name>`) with a button that jumps to one. The server says whether to show it, and which
# checkpoints there are, in the `debug_tools` part of its hello; the buttons just send the same commands a tester could type
# (`scene skip`, `checkpoint <name>`). Without the flag nothing is shown.
#
# Reached through `preload`, not a `class_name`, so the headless client checks need no class cache.
extends RefCounted

var main
var row: HBoxContainer
var picker: OptionButton


func _init(main_ref) -> void:
	main = main_ref


## Called with the server's hello payload.
func apply_hello(body: Dictionary) -> void:
	var info = body.get("debug_tools", {})
	if not (info is Dictionary) or not bool((info as Dictionary).get("enabled", false)):
		_remove()
		return
	_build((info as Dictionary).get("checkpoints", []))


func _remove() -> void:
	if row != null and is_instance_valid(row):
		row.get_parent().remove_child(row)
		row.queue_free()
	row = null
	picker = null


func _build(checkpoints) -> void:
	_remove()
	var command_row: Node = main.command_input.get_parent()
	var column: Node = command_row.get_parent()
	row = HBoxContainer.new()
	row.name = "DebugTools"
	row.add_theme_constant_override("separation", 6)
	var label := Label.new()
	label.text = "Test tools"
	label.modulate = Color(0.75, 0.8, 0.6)
	row.add_child(label)
	var skip := Button.new()
	skip.name = "DebugSkipScene"
	skip.text = "Skip scene"
	skip.tooltip_text = "Tell the rest of the scene that is playing at once (scene skip)."
	skip.pressed.connect(func(): main.network_lifecycle._send_command_to_server("scene skip"))
	row.add_child(skip)
	picker = OptionButton.new()
	picker.name = "DebugCheckpoint"
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	if checkpoints is Array:
		for entry in checkpoints:
			if entry is Dictionary:
				var id := str((entry as Dictionary).get("id", ""))
				if id == "":
					continue
				var note := str((entry as Dictionary).get("note", ""))
				picker.add_item("Checkpoint: %s" % id)
				picker.set_item_metadata(picker.item_count - 1, id)
				picker.set_item_tooltip(picker.item_count - 1, note)
	row.add_child(picker)
	var go := Button.new()
	go.name = "DebugGo"
	go.text = "Go"
	go.tooltip_text = "Jump to the chosen checkpoint (checkpoint <name>)."
	go.disabled = picker.item_count == 0
	go.pressed.connect(func():
		if picker.item_count > 0 and picker.selected >= 0:
			main.network_lifecycle._send_command_to_server("checkpoint %s" % str(picker.get_item_metadata(picker.selected))))
	row.add_child(go)
	main.keep_focus_on_command_line(row)   # the command line keeps focus, so these must not take it or a click is cancelled
	column.add_child(row)
	column.move_child(row, command_row.get_index())
