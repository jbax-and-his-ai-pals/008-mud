# scripts/data/SaveIO.gd
#
# The one place the editor writes a content file, and the one place that checks
# it actually landed.
#
# Every writer used to look like this:
#
#     var f = FileAccess.open(path, FileAccess.WRITE)
#     if f: f.store_string(JSON.stringify(payload, "\t"))
#
# with no `else` and no return value. A read-only file, a full disk or a bad
# path was therefore indistinguishable from success: the caller cleared the
# dirty flag, the Save button greyed out as "saved", and the author's edits were
# gone with no message anywhere they were looking.
#
# Two conventions also live here because they are the same decision in every
# writer: content files are 4-space indented (the editor used tabs, so any save
# reformatted a whole file and destroyed its `git blame`), and what is written is
# read back before it counts as written.
#
# Key order is preserved deliberately. `JSON.stringify`'s `sort_keys` defaults to
# true, so every editor save used to alphabetise every object in the file it
# touched -- `region_id` landed after `name`, `properties` blocks were reordered,
# and a one-field edit still produced a whole-file diff.

class_name SaveIO
extends RefCounted

const INDENT := "    "
const SORT_KEYS := false


# Write `payload` as JSON to `path`. Returns {"ok": bool, "error": String}.
#
# The read-back is deliberate: a write that silently failed is exactly the
# failure this exists to catch, and it is invisible to `FileAccess` itself.
static func write_json(path: String, payload) -> Dictionary:
	var text := JSON.stringify(_normalize_numbers(payload), INDENT, SORT_KEYS)
	var file := FileAccess.open(path, FileAccess.WRITE)
	if file == null:
		return _failure(path, "could not open for writing (%s)" % _error_text(FileAccess.get_open_error()))
	file.store_string(text)
	file.close()

	if not FileAccess.file_exists(path):
		return _failure(path, "the file does not exist after writing")
	var check := FileAccess.open(path, FileAccess.READ)
	if check == null:
		return _failure(path, "the file was written but could not be read back (%s)"
			% _error_text(FileAccess.get_open_error()))
	var written := check.get_as_text()
	check.close()
	if written != text:
		return _failure(path, "what was written does not match what is on disk (wrote %d characters, read %d)"
			% [text.length(), written.length()])
	if JSON.parse_string(written) == null:
		return _failure(path, "the file read back is not valid JSON")
	return {"ok": true, "error": ""}


# JSON itself has no separate int/float type, and Godot's own parser returns
# every JSON number as a float -- `JSON.parse_string('{"n": 1}')["n"]` is
# `1.0`, not `1`. Every field the editor has ever loaded has therefore passed
# through that conversion, and writing it back verbatim turns a recipe's
# `"quantity": 1` into `"quantity": 1.0` even though nothing touched it --
# which the engine's content validators then reject as not-an-integer. A
# float with no fractional part is written as an int; `1.5` is left alone, so
# a genuinely fractional value (a multiplier, a fraction of a stat) is
# unaffected either way a consumer reads it back.
static func _normalize_numbers(value):
	if value is Dictionary:
		var out := {}
		for key in value: out[key] = _normalize_numbers(value[key])
		return out
	if value is Array:
		var out := []
		for entry in value: out.append(_normalize_numbers(entry))
		return out
	if value is float and not (is_nan(value) or is_inf(value)) and value == floor(value) \
			and absf(value) < 9223372036854775807.0:
		return int(value)
	return value


static func _failure(path: String, reason: String) -> Dictionary:
	var message := "Could not write %s: %s" % [path, reason]
	push_error(message)
	return {"ok": false, "error": message}


static func _error_text(code: int) -> String:
	return error_string(code) if code != OK else "unknown error"
