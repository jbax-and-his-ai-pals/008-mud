# scripts/data/ReferenceIndex.gd
#
# "What names this id?" -- the question a rename or a delete has to answer first.
#
# The walking belongs to `toolkit/reference_index.py`, which shares
# `REFERENCE_FAMILIES` with the reference gate. The editor must not hold a second
# opinion about what a reference *is*: that is the defect class this project has
# paid for most often, so this script runs that tool, caches the answer for the
# open content set, and phrases it for a confirmation dialog.
#
# The phrasing matters. The index covers the families the sweep walks -- items,
# NPCs, abilities, rooms, collections and recipes -- and not, yet, room
# placements, exits, dialogue bindings, guild places or quest spawn rooms. So an
# empty answer is reported as "nothing in the indexed families names this" and
# followed by what is not covered. It is never reported as "unused".
class_name ReferenceIndex
extends RefCounted

const SCRIPT_RELATIVE_PATH := "toolkit/reference_index.py"

## Editor content types and the index family that can name them. A type absent
## from this table is one the sweep does not read yet; the dialog says so rather
## than implying that there is nothing to check.
const FAMILY_BY_TYPE := {
	"item": "items",
	"npc": "npcs",
	"magic": "abilities",
	"recipe": "recipes",
	"collection": "collections",
}

var _payload: Dictionary = {}
var _loaded := false
var _error := ""

func loaded() -> bool:
	return _loaded

func error() -> String:
	return _error

func payload() -> Dictionary:
	return _payload

func clear() -> void:
	_payload = {}
	_loaded = false
	_error = ""

## Run the index over one content set's `data/` root. Synchronous, like the engine
## validator: the author asked a question and is waiting for the answer.
##
## `python_exe` is usually left empty: the interpreter is discovered the same way
## the rest of the editor discovers it, including a `--python` argument, which is
## how the headless checks point at a known interpreter.
func load_for(data_root: String, python_exe: String = "") -> Dictionary:
	clear()
	var repo_root := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
	var script_path := repo_root.path_join(SCRIPT_RELATIVE_PATH)
	if not FileAccess.file_exists(script_path):
		_error = "The reference index is not at %s." % script_path
		return result()
	var python := python_exe if python_exe != "" else _interpreter(repo_root)
	var output: Array = []
	var exit_code := OS.execute(python, [script_path, data_root, "--json"], output, false)
	var raw: String = str(output[0]) if output.size() > 0 else ""
	var parsed = EngineValidator.last_json_object(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		_error = "The reference index printed no result (exit %d).\n%s" % [exit_code, raw.strip_edges().right(400)]
		return result()
	_payload = parsed
	_loaded = true
	return result()

# `--python <path>` first (the headless checks pass it), then the layouts the rest
# of the editor looks for, then whatever `python` resolves to.
func _interpreter(repo_root: String) -> String:
	var args := OS.get_cmdline_user_args()
	for index in range(args.size() - 1):
		if args[index] == "--python":
			return str(args[index + 1])
	for candidate in [
		repo_root.path_join(".venv/Scripts/python.exe"),
		repo_root.path_join(".venv/bin/python"),
		repo_root.path_join(".conda/python.exe"),
	]:
		if FileAccess.file_exists(candidate):
			return candidate
	return "python"

func result() -> Dictionary:
	return {"ok": _loaded, "error": _error, "payload": _payload}

## The index family that can name entries of this editor type, or "" when the
## sweep does not read that kind yet.
func family_for_type(type: String) -> String:
	return str(FAMILY_BY_TYPE.get(type, ""))

## Every indexed reference to `id`: `[{family, file, path, resolved}]`.
func referrers_of(id: String, family: String = "") -> Array:
	var out: Array = []
	var families: Dictionary = _payload.get("families", {}) if _payload.get("families") is Dictionary else {}
	for family_name in families:
		if family != "" and str(family_name) != family:
			continue
		var entries: Dictionary = families[family_name]
		if not entries.has(id) or not entries[id] is Array:
			continue
		for where in entries[id]:
			if not where is Dictionary:
				continue
			out.append({
				"family": str(family_name),
				"file": str(where.get("file", "")),
				"path": str(where.get("path", "")),
				"resolved": bool(where.get("resolved", true)),
			})
	return out

## The sentence a delete or rename confirmation shows. Always states the scope,
## so an empty answer cannot be read as permission.
func describe(id: String, type: String = "", limit: int = 4) -> String:
	if not _loaded:
		return "Reference check unavailable: %s" % (_error if _error != "" else "the index has not been run.")
	var family := family_for_type(type)
	if family == "":
		return "The reference index does not read %s entries yet, so nothing can be checked automatically." % type
	var hits := referrers_of(id, family)
	if hits.is_empty():
		return "Nothing in the indexed families names this id.\n\n%s" % scope_note()
	var lines: Array = ["Named %d time(s):" % hits.size()]
	var shown: int = 0
	for hit in hits:
		if shown >= limit:
			lines.append("  ... and %d more." % (hits.size() - limit))
			break
		lines.append("  %s\n    %s" % [hit["file"], hit["path"]])
		shown += 1
	lines.append("")
	lines.append(scope_note())
	return "\n".join(lines)

## What the index does and does not read, in one sentence, for the dialog.
func scope_note() -> String:
	var coverage: Dictionary = _payload.get("coverage", {}) if _payload.get("coverage") is Dictionary else {}
	var indexed: Array = coverage.get("indexed", []) if coverage.get("indexed") is Array else []
	var not_indexed: Array = coverage.get("not_indexed", []) if coverage.get("not_indexed") is Array else []
	if indexed.is_empty():
		return "The index reports no coverage, so this answer is not evidence either way."
	return "Indexed: %s. Not indexed (so an empty answer is not proof of disuse): %s." % [
		", ".join(indexed),
		"; ".join(not_indexed) if not not_indexed.is_empty() else "nothing",
	]
