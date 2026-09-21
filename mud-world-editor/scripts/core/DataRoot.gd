# scripts/core/DataRoot.gd
#
# Where the world lives. One source: the same content-set directory the game
# server loads. See docs/roadmap/editor-content-source.md.
#
# The editor used to hard-code `res://data/...` -- its own mirror tree, kept in
# step with the real content by a one-way export script. That worked while the
# editor was mostly a viewer and stopped working when it became the authoring
# front-end: the mirror was missing 164 item ids and 52 NPC ids, and the Content
# Library showed one villager where the game has twenty-one.
#
# Resolution order (first hit wins):
#   1. `--data-root <path>` on the command line
#   2. `user://editor_settings.json` -> {"content_set_root": "..."}
#   3. `<project>/../content_sets/fantasy_frontier`   (a checkout)
#   4. `<project>/data`                               (a standalone copy)
#
# The resolved path is shown in the window title, so nobody has to guess which
# world they are editing.

class_name DataRoot
extends RefCounted

const SaveIO = preload("res://scripts/data/SaveIO.gd")

const DEFAULT_CONTENT_SET := "../content_sets/fantasy_frontier"
const SETTINGS_PATH := "user://editor_settings.json"
const EDITOR_STATE_DIR := "editor"
# The engine's own manifest name (`content_set.CONTENT_SET_MANIFEST_NAME`), and
# what makes a directory a content set rather than just a directory.
const CONTENT_SET_MANIFEST_NAME := "content_set.manifest.json"

# Content folders the editor reads and writes. These are the game's own folders;
# the editor adds nothing to `data/` that the server would not understand.
const CONTENT_DIRS := {
	"npcs": "npcs",
	"items": "items",
	"magic": "magic",
	# The engine prefers `abilities/` over `magic/` for ability definitions, so a
	# content set whose abilities are not spells can name its own directory. The
	# editor asks for a set's abilities rather than for its magic (see
	# DatabaseManager.abilities_dir).
	"abilities": "abilities",
	"quests": "quests",
	"campaigns": "campaigns",
	"regions": "regions",
	"combat": "combat",
	"crafting": "crafting",
	"dialogue": "dialogue",
}

static var _resolved: String = ""
static var _source: String = ""

# --- resolution ---------------------------------------------------------------

static func resolve() -> String:
	if _resolved != "":
		return _resolved
	_resolved = _resolve_uncached()
	return _resolved

static func _resolve_uncached() -> String:
	var from_cli := _from_command_line()
	if from_cli != "":
		_source = "command line"
		return from_cli

	var from_settings := _from_settings()
	if from_settings != "":
		_source = "editor settings"
		return from_settings

	var project_root := ProjectSettings.globalize_path("res://")
	var checkout := _normalize(project_root.path_join(DEFAULT_CONTENT_SET))
	if DirAccess.dir_exists_absolute(checkout):
		_source = "checkout layout"
		return checkout

	var standalone := _normalize(project_root.path_join("data"))
	if DirAccess.dir_exists_absolute(standalone):
		_source = "standalone copy"
		return standalone

	# Nothing found: report the checkout path we would have used, so the error
	# message names somewhere real.
	_source = "missing"
	return checkout

static func _from_command_line() -> String:
	for argument in OS.get_cmdline_args() + OS.get_cmdline_user_args():
		if not argument.begins_with("--data-root"):
			continue
		var value := ""
		if argument.contains("="):
			value = argument.split("=", true, 1)[1]
		var normalized := _normalize(value)
		if normalized != "" and DirAccess.dir_exists_absolute(normalized):
			return normalized
		push_error("DataRoot: --data-root does not exist: " + value)
	return ""

static func _from_settings() -> String:
	if not FileAccess.file_exists(SETTINGS_PATH):
		return ""
	var parsed := JSON.new()
	if parsed.parse(FileAccess.get_file_as_string(SETTINGS_PATH)) != OK:
		return ""
	var payload = parsed.get_data()
	if typeof(payload) != TYPE_DICTIONARY:
		return ""
	var configured := _normalize(str(payload.get("content_set_root", "")))
	if configured != "" and DirAccess.dir_exists_absolute(configured):
		return configured
	return ""

# Accept either a content-set root (`.../fantasy_frontier`) or one of its
# subdirectories (`.../fantasy_frontier/data`), because both are natural things
# to paste on a command line.
static func _normalize(path: String) -> String:
	var text := str(path).strip_edges()
	if text == "":
		return ""
	var absolute := text
	if text.begins_with("res://") or text.begins_with("user://"):
		absolute = ProjectSettings.globalize_path(text)
	elif not text.is_absolute_path():
		absolute = ProjectSettings.globalize_path("res://").path_join(text)
	absolute = absolute.simplify_path()
	var tail := absolute.get_file()
	if tail == "data" and absolute.get_base_dir().get_file() != "":
		# A `data` directory resolves to the content set that owns it.
		var parent := absolute.get_base_dir()
		if DirAccess.dir_exists_absolute(parent.path_join(EDITOR_STATE_DIR)) \
		or DirAccess.dir_exists_absolute(parent.path_join("rules")):
			return parent
	return absolute

static func source_description() -> String:
	resolve()
	return _source


# --- switching worlds ---------------------------------------------------------
# The resolution order above has always been able to load any content set; what
# was missing was a way to *choose* one without relaunching the editor with
# `--data-root`. These three make the choice from inside, and remember it.

# Every content set beside this checkout that has a manifest. A directory without
# one is not offered: the engine would refuse to load it.
static func available_content_sets() -> Array:
	var sets_root := _normalize(ProjectSettings.globalize_path("res://").path_join("../content_sets"))
	var found: Array = []
	var dir := DirAccess.open(sets_root)
	if dir == null:
		return found
	dir.list_dir_begin()
	var name := dir.get_next()
	while name != "":
		if dir.current_is_dir() and not name.begins_with("."):
			var candidate := sets_root.path_join(name)
			if FileAccess.file_exists(candidate.path_join("content_set.manifest.json")):
				found.append(candidate)
		name = dir.get_next()
	dir.list_dir_end()
	found.sort()
	return found


# Point the editor at another content set for this session. Returns false when
# the path is not a content set, so the caller can say so rather than half-switch.
#
# "Is a content set" means the manifest is there, the same test
# `available_content_sets` applies before offering one: a directory that merely
# exists -- the repository root, a `tmp/` folder, one set's `data/` subdirectory --
# used to be accepted, and the editor reloaded into a world with no regions, no
# items and no way to tell that the path had been wrong.
static func set_root(path: String) -> bool:
	var normalized := _normalize(path)
	if normalized == "" or not DirAccess.dir_exists_absolute(normalized):
		return false
	if not FileAccess.file_exists(normalized.path_join(CONTENT_SET_MANIFEST_NAME)):
		return false
	_resolved = normalized
	_source = "editor settings"
	return true


# Remember the choice, so the next launch opens the same world. Written through
# SaveIO like everything else, because a settings file that silently failed to
# write would make the editor reopen the wrong world with no explanation.
static func write_settings(path: String) -> Dictionary:
	return SaveIO.write_json(SETTINGS_PATH, {"content_set_root": _normalize(path)})

# --- paths --------------------------------------------------------------------

static func root() -> String:
	return resolve()

static func data_dir() -> String:
	return root().path_join("data")

static func ruleset_path() -> String:
	return root().path_join("rules").path_join("ruleset.json")

static func content_dir(name: String) -> String:
	var folder := str(CONTENT_DIRS.get(name, name))
	return data_dir().path_join(folder)

static func content_file(name: String) -> String:
	return data_dir().path_join(name)

# Editor-only state. The server never reads this directory.
static func editor_dir() -> String:
	return root().path_join(EDITOR_STATE_DIR)

static func editor_file(name: String) -> String:
	return editor_dir().path_join(name)

static func region_editor_file(region_id: String) -> String:
	return editor_dir().path_join("regions").path_join(region_id + ".editor.json")

static func ensure_editor_dirs() -> void:
	for path in [editor_dir(), editor_dir().path_join("regions"), editor_dir().path_join("templates")]:
		if not DirAccess.dir_exists_absolute(path):
			DirAccess.make_dir_recursive_absolute(path)

# --- reporting -----------------------------------------------------------------

static func describe() -> String:
	var resolved := resolve()
	if _source == "missing":
		return "CONTENT NOT FOUND (expected %s)" % resolved
	return "%s  [%s]" % [resolved, _source]
