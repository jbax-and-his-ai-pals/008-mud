# scripts/text/typewriter.gd
#
# Reveals marked passages of the game log a few characters at a time. The server marks a passage
# it wants read slowly (`[[PACE:25]]...[[/PACE]]`, turned into `[pace=25]...[/pace]` by
# server_markup.gd); everything else is appended at once, as before.
#
# The whole text goes into the label immediately, so layout and scrolling are settled, and
# `visible_characters` is what moves: it runs through a queue of (end position, speed) runs, so
# plain text that arrives after a slow passage waits its turn and the order of the page is kept.
# `finish()` shows everything now: the player skips ahead by clicking the log or sending a
# command.
#
# Reached through `preload`.
extends Node

var label: RichTextLabel
var enabled: bool = true       # the player's own switch: off shows everything at once

var _queue: Array = []         # [end_character_count, characters_per_second (0 = at once)]
var _shown: float = 0.0
static var _pace_pattern: RegEx


## Splits bbcode into runs: [[text, characters_per_second], ...]; 0 means at once.
static func runs_of(bbcode: String) -> Array:
	if _pace_pattern == null:
		_pace_pattern = RegEx.new()
		_pace_pattern.compile("\\[pace=(\\d+)\\]|\\[/pace\\]")
	var runs: Array = []
	var position := 0
	var speed := 0.0
	for found in _pace_pattern.search_all(bbcode):
		if found.get_start() > position:
			runs.append([bbcode.substr(position, found.get_start() - position), speed])
		position = found.get_end()
		speed = float(found.get_string(1)) if found.get_string(1) != "" else 0.0
	if position < bbcode.length():
		runs.append([bbcode.substr(position), speed])
	return runs


## Pace markers removed, for a log that is not revealed gradually.
static func without_pace(bbcode: String) -> String:
	if bbcode.find("[pace=") == -1 and bbcode.find("[/pace]") == -1:
		return bbcode
	var plain := ""
	for run in runs_of(bbcode):
		plain += str(run[0])
	return plain


func append(bbcode: String) -> void:
	var runs := runs_of(bbcode)
	var slow := false
	for run in runs:
		if float(run[1]) > 0.0:
			slow = true
	if (not slow or not enabled) and _queue.is_empty():
		for run in runs:
			label.append_text(str(run[0]))
		return
	if _queue.is_empty():
		_shown = float(label.get_total_character_count())
		label.visible_characters = int(_shown)
	for run in runs:
		label.append_text(str(run[0]))
		_queue.append([label.get_total_character_count(), float(run[1]) if enabled else 0.0])


func is_revealing() -> bool:
	return not _queue.is_empty()


## Show everything that is still hidden, now.
func finish() -> void:
	if _queue.is_empty():
		return
	_queue.clear()
	label.visible_characters = -1


func _process(delta: float) -> void:
	if _queue.is_empty():
		return
	var budget := delta
	while not _queue.is_empty():
		var head: Array = _queue[0]
		var end := float(head[0])
		var speed := float(head[1])
		if speed <= 0.0:
			_shown = end
		else:
			var needed := (end - _shown) / speed
			if needed > budget:
				_shown += speed * budget
				budget = 0.0
			else:
				_shown = end
				budget -= needed
		if _shown >= end:
			_queue.pop_front()
		else:
			break
	label.visible_characters = -1 if _queue.is_empty() else int(_shown)
