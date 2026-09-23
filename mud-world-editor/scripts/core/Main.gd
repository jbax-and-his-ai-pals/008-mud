# scripts/core/Main.gd
extends Node2D

const SaveIO = preload("res://scripts/data/SaveIO.gd")
const ReferenceIndexScript = preload("res://scripts/data/ReferenceIndex.gd")
const SaveCheckpoint = preload("res://scripts/data/SaveCheckpoint.gd")

# Managers
var region_mgr: RegionManager
var world_mgr: WorldManager
var database_mgr: DatabaseManager
var cmd_proc: CommandProcessor

# "What names this id?", answered by the toolkit's reference index. Cached per
# content set: it is a subprocess, and the answer only changes when the set does.
var reference_index = ReferenceIndexScript.new()

# Controllers
var ui_mgr: EditorUIManager
var inspector: InspectorController
var graph_controller: GraphController
var camera_controller: CameraController
var action_handler: ActionHandler

# State
var state: EditorState
var view_states: Dictionary = {}
var editor_clipboard: Array = []
var cached_hierarchy: Dictionary = {}
var _content_validation_thread: Thread = null
var _content_validation_label := ""
var _release_gate_thread: Thread = null

# Input state
var mouse_down_pos: Vector2
var deselection_primed: bool = false
var is_dragging_object: bool = false
const DRAG_PIXEL_THRESHOLD = 10
var label_drag_source := ""

# Scene Refs
@onready var main_camera = $MainCamera
@onready var room_container = $RoomContainer
@onready var connection_layer = $ConnectionLayer
@onready var ui_layer = $UILayer
var grid_layer: GridLayer
var district_layer: Node2D
var district_label_layer: Node2D

func _ready():
	# Quitting is handled in _notification: closing the window used to discard
	# everything since the last manual save without a word.
	get_tree().auto_accept_quit = false
	# Agree the content root before anything loads, and say which world this is.
	# The editor used to keep its own mirror of the content; it now edits the
	# real content set, and the title is the only place that fact is visible.
	DisplayServer.window_set_title("MUD world editor — %s" % DataRoot.describe())
	if DataRoot.source_description() == "missing":
		push_error("No content set found. Pass --data-root <path> or run from a checkout.")

	region_mgr = RegionManager.new()
	world_mgr = WorldManager.new()
	database_mgr = DatabaseManager.new()
	cmd_proc = CommandProcessor.new()
	state = EditorState.new()

	grid_layer = GridLayer.new(); add_child(grid_layer); move_child(grid_layer, 0)
	grid_layer.setup(main_camera)
	grid_layer.visible = false
	district_layer = Node2D.new(); district_layer.name = "DistrictLayer"; add_child(district_layer); move_child(district_layer, 1)
	district_label_layer = Node2D.new(); district_label_layer.name = "DistrictLabelLayer"; add_child(district_label_layer)

	ui_mgr = EditorUIManager.new(); ui_mgr.setup(ui_layer, database_mgr, world_mgr)
	inspector = InspectorController.new(); inspector.setup(ui_layer, region_mgr, world_mgr, database_mgr)
	graph_controller = GraphController.new(); graph_controller.setup(room_container, connection_layer, state, district_layer, district_label_layer)
	camera_controller = CameraController.new(); camera_controller.setup(main_camera, ui_mgr)
	action_handler = ActionHandler.new(); action_handler.setup(self, state, cmd_proc, region_mgr, world_mgr, graph_controller, ui_mgr, inspector)
	action_handler.district_preview_changed.connect(func(preview):
		state.district_preview = preview if not preview.is_empty() else _empty_district_preview()
		_refresh_district_toolbar()
		graph_controller.queue_redraw()
	)
	
	inspector.set_action_handler(action_handler)
	
	_connect_ui_signals()
	_connect_inspector_signals()
	_connect_graph_signals()
	
	_bootstrap_ui()
	# Open the region the game starts in, so the editor comes up on real
	# content rather than an empty graph.
	var start_region := _start_region_filename()
	if start_region != "": _load_region(start_region)
	else: _load_region("")

func _process(_delta):
	if ui_mgr:
		ui_mgr.update_status_coords(get_global_mouse_position())
		if ui_mgr.search_modal.visible and ui_mgr.search_data_cache.is_empty():
			ui_mgr.cache_search_data(world_mgr.get_all_world_data(), database_mgr.npcs, database_mgr.items)
	_poll_content_validation()
	_poll_release_gate()


func _exit_tree():
	# A thread may still be booting the test world while the editor closes. Join it
	# before Godot tears down its runtime; it never touches scene objects itself.
	if _content_validation_thread != null:
		if _content_validation_thread.is_alive():
			_content_validation_thread.wait_to_finish()
		_content_validation_thread = null
	if _release_gate_thread != null:
		if _release_gate_thread.is_alive():
			_release_gate_thread.wait_to_finish()
		_release_gate_thread = null

# The content set's own start region (`town` in fantasy_frontier), discovered by
# name rather than hard-coded, so a different content set opens on its own world.
func _start_region_filename() -> String:
	var directory := DataRoot.content_dir("regions")
	for candidate in ["town.json", "start.json"]:
		if FileAccess.file_exists(directory.path_join(candidate)):
			return candidate
	# Otherwise: the first region the set has.
	var dir := DirAccess.open(directory)
	if dir == null:
		return ""
	dir.list_dir_begin()
	var file_name := dir.get_next()
	while file_name != "":
		if not dir.current_is_dir() and file_name.ends_with(".json"):
			return file_name
		file_name = dir.get_next()
	return ""

func _bootstrap_ui():
	# The shared content set already exists; what may not is the editor's own
	# state directory, which holds layout rather than game data.
	DataRoot.ensure_editor_dirs()
	_update_db_ui()
	_load_region_vocab_into_creator()

# Populates the New Region wizard's biome/region_type dropdowns and NPC
# population list from real data (the content set's own classification
# vocabulary, and every currently-loaded NPC template) instead of a
# hardcoded list that would drift from whatever content set this data
# actually belongs to.
func _load_region_vocab_into_creator():
	var biomes: Array = []
	var region_types: Array = []
	var ruleset_path := DataRoot.ruleset_path()
	if FileAccess.file_exists(ruleset_path):
		var f = FileAccess.open(ruleset_path, FileAccess.READ)
		if f:
			var json = JSON.new()
			if json.parse(f.get_as_text()) == OK:
				var ruleset = json.get_data()
				var regions_cfg = ruleset.get("world", {}).get("regions", {}) if typeof(ruleset) == TYPE_DICTIONARY else {}
				biomes = regions_cfg.get("biomes", [])
				region_types = regions_cfg.get("region_types", [])
	ui_mgr.creator_modal.set_vocab(biomes, region_types)
	var npc_ids: Array = database_mgr.npcs.keys(); npc_ids.sort()
	ui_mgr.creator_modal.set_npc_options(npc_ids)

func _update_db_ui():
	ui_mgr.update_db_lists(
		database_mgr.npcs, 
		database_mgr.items, 
		database_mgr.templates,
		database_mgr.magic,
		database_mgr.quests,
		database_mgr.recipes,
		database_mgr.dialogues,
		database_mgr.titles,
		database_mgr.collections,
		database_mgr.discoveries,
		database_mgr.backgrounds,
		database_mgr.campaigns,
		database_mgr.topics,
		database_mgr.affix_prefixes,
		database_mgr.affix_suffixes,
		database_mgr.item_sets,
		database_mgr.dirty_flags
	)

func _connect_ui_signals():
	ui_mgr.request_load_region.connect(_load_region)
	ui_mgr.request_validate.connect(_show_validation_results)
	ui_mgr.request_acknowledge_validation_warning.connect(func(warning_id): world_mgr.acknowledge_warning(warning_id); _show_validation_results())
	ui_mgr.request_reset_ignored_validation_warnings.connect(func(): world_mgr.reset_ignored_warnings(); _show_validation_results())
	ui_mgr.request_acknowledge_content_validation_warnings.connect(func(warning_ids):
		world_mgr.acknowledge_content_warnings(warning_ids)
		ui_mgr.hide_content_validation()
		_validate_content()
	)
	ui_mgr.request_reset_ignored_content_validation_warnings.connect(func():
		world_mgr.reset_ignored_content_warnings()
		ui_mgr.hide_content_validation()
		_validate_content()
	)
	ui_mgr.label_arrange_mode_changed.connect(func(enabled):
		if state.is_world_view: return
		graph_controller.set_label_arrange_mode(enabled)
		if not enabled:
			label_drag_source = ""
			graph_controller.set_label_swap_target("")
			graph_controller.set_label_drag_source("")
			graph_controller.set_label_swap_preview("", "")
	)
	ui_mgr.request_room_label_rename.connect(func(room_id, new_name): action_handler.rename_room_label(room_id, new_name))
	ui_mgr.technical_ids_visibility_changed.connect(func(enabled): graph_controller.set_show_technical_ids(enabled))
	ui_mgr.request_validate_region_policy.connect(_validate_region_policy)
	ui_mgr.request_validate_content.connect(_validate_content)
	ui_mgr.request_run_release_gate.connect(_run_release_gate)
	ui_mgr.request_edit_ruleset.connect(func(): ui_mgr.show_ruleset_editor())
	ui_mgr.request_edit_manifest.connect(func(): ui_mgr.show_manifest_editor())
	ui_mgr.ruleset_saved.connect(func():
		database_mgr.catalog.load_contracts()
		_load_region_vocab_into_creator()
		_update_db_ui()
		ui_mgr.refresh_configuration_views(database_mgr.catalog)
	)
	# The manifest decides where a character starts and which systems exist, so a
	# save reloads the catalog and revalidates rather than leaving the title and
	# the inspector's vocabulary describing the previous configuration.
	ui_mgr.manifest_saved.connect(func():
		database_mgr.catalog.load_contracts()
		_load_region_vocab_into_creator()
		_update_db_ui()
		ui_mgr.refresh_configuration_views(database_mgr.catalog)
		_validate_content()
	)
	ui_mgr.request_show_contracts.connect(func(): ui_mgr.show_contracts())
	ui_mgr.request_edit_contracts.connect(func(): ui_mgr.show_contract_editor())
	ui_mgr.contracts_saved.connect(func():
		database_mgr.catalog.load_contracts()
		_update_db_ui()
		ui_mgr.refresh_configuration_views(database_mgr.catalog)
	)
	ui_mgr.request_edit_combat_vocabulary.connect(func(): ui_mgr.show_combat_vocabulary_editor())
	ui_mgr.combat_vocabulary_saved.connect(func():
		database_mgr.combat_vocabulary.load()
		_update_db_ui()
		ui_mgr.refresh_configuration_views(database_mgr.catalog)
	)
	ui_mgr.request_choose_content_set.connect(func(): ui_mgr.show_content_set_chooser())
	ui_mgr.request_switch_content_set.connect(_request_switch_content_set)
	ui_mgr.request_open_creator_modal.connect(func(): ui_mgr.creator_modal.set_target_options(world_mgr.get_global_hierarchy()))
	ui_mgr.request_open_district_modal.connect(func():
		if not state.is_world_view and not region_mgr.data.get("rooms", {}).is_empty():
			ui_mgr.district_modal.open_for_rooms(region_mgr.data.rooms)
	)
	ui_mgr.request_create_connection.connect(action_handler.create_connection)
	ui_mgr.request_create_region.connect(_create_region)
	ui_mgr.request_place_district.connect(func(definition): action_handler.begin_district_placement(definition, main_camera.position))
	ui_mgr.request_district_confirm.connect(func(): action_handler.commit_district_placement(state.district_preview))
	ui_mgr.request_district_cancel.connect(_cancel_district_placement)
	ui_mgr.context_action.connect(action_handler.handle_context_action)
	ui_mgr.snap_toggled.connect(func(b): state.snap_enabled=b; graph_controller.set_snap(b); grid_layer.visible=(b and not state.is_world_view); grid_layer.queue_redraw())
	ui_mgr.show_districts_toggled.connect(func(b):
		district_layer.visible = b
		district_label_layer.visible = b
		graph_controller.districts_visible = b
		# A district that was selected before districts got hidden would
		# otherwise leave its info panel showing (and its highlight primed
		# to reappear) even though nothing is visibly selected anymore.
		if not b and state.selected_district_id != "": _deselect_all()
	)
	ui_mgr.creation_direction_selected.connect(action_handler.create_room_from_anchor)
	ui_mgr.tool_changed.connect(func(m, d): state.cur_tool_mode=m; state.cur_tool_data=d; ui_mgr.update_tool_display(m, d); if m!=EditorUIManager.ToolMode.SELECT: _deselect_all())
	ui_mgr.request_jump_to_room.connect(_jump_to_room)
	ui_mgr.request_show_district.connect(func(_region_id, district_id): _select_district(district_id))
	ui_mgr.request_jump_to_error.connect(func(f, i): 
		if f != region_mgr.current_filename: _load_region(f, false, true)
		await get_tree().create_timer(0.01).timeout; _jump_to_room(i)
	)
	ui_mgr.request_toggle_world_view.connect(func(enabled): _set_world_view(enabled))
	ui_mgr.request_auto_layout.connect(_on_request_layout)
	ui_mgr.request_center_view.connect(func(): camera_controller.center_on_nodes(graph_controller.get_active_nodes()))
	ui_mgr.request_copy.connect(_on_copy_request)
	ui_mgr.request_paste.connect(_on_paste_request)
	
	# Connect View Mode
	ui_mgr.view_mode_changed.connect(func(mode): graph_controller.set_view_mode(mode))

	ui_mgr.request_select_db_entry.connect(func(t, id): 
		if t=="template": return
		var d
		match t:
			"npc": d = database_mgr.npcs[id]
			"item": d = database_mgr.items[id]
			"magic": d = database_mgr.magic[id]
			"quest": d = database_mgr.quests[id]
		inspector.load_db_object(t, id, d); _deselect_room_only()
	)
	ui_mgr.request_create_db_entry.connect(func(t):
		var id = "new_" + t; var d = {"name": "New " + t.capitalize()}
		match t:
			"npc": database_mgr.add_npc(id, d)
			"monster":
				# Monsters remain NPC definitions underneath, but start in the
				# dedicated monster grouping used by the database and spawner.
				d["friendly"] = false
				d["faction"] = "hostile"
				database_mgr.add_npc(id, d)
			"item": database_mgr.add_item(id, d)
			"gem":
				d.merge({
					"name": "New Gem",
					"description": "A newly defined gemstone species.",
					"type": "Gem",
					"rarity": "common",
					"weight": 0.1,
					"value": 10.0,
					"stackable": true,
					"gem_generation": {"size_bias": 0.0, "quality_bias": 0.0},
				})
				database_mgr.add_item(id, d)
			"magic":
				# A new ability has to be *loadable*, not merely present: the
				# engine's `Spell` requires a description and at least one typed
				# effect, and `spell_registry` builds a whole file inside one
				# `try` -- so one placeholder that raises stops every remaining
				# ability in that file from registering. This used to seed
				# `effects: []` and no description, which made "Create Ability"
				# the one button in the editor that could break a content set.
				d.merge({
					"description": "A newly defined ability.",
					"target_type": "enemy",
					"mana_cost": 5,
					"cooldown": 3,
					"level_required": 1,
					"effects": [{"type": "damage", "value": 5, "damage_type": "physical"}],
				})
				database_mgr.add_magic(id, d)
			"quest": database_mgr.add_quest(id, d)
			"recipe":
				# The engine reads a recipe's ids against real templates, so a new
				# one starts with the result empty rather than naming a placeholder
				# the content validator would reject.
				d.merge({
					"description": "Creates something.",
					"result_item_id": "",
					"result_quantity": 1,
					"station_required": null,
					"ingredients": [],
					"aliases": [],
				})
				database_mgr.add_recipe(id, d)
			"dialogue":
				# A new conversation is a valid graph before anything is typed:
				# one opening node with a way out, so it never fails validation
				# merely by existing.
				d = DialogueInspector.data_defaults()
				d["id"] = id
				database_mgr.add_dialogue(id, d)
			"title":
				# No condition yet, so nothing is granted until one is authored --
				# an ungated title would confer itself to every character.
				d = {"name": "New Title", "description": ""}
				database_mgr.add_title(id, d)
			"discovery":
				d = {"name": "New Discovery", "description": "", "item_ids": []}
				database_mgr.add_discovery(id, d)
			"collection":
				d = {"name": "New Collection", "description": "", "items": [], "rewards": {}}
				database_mgr.add_collection(id, d)
			"background":
				d = {"name": "New Background", "description": "", "stats": {}, "inventory": [], "starting_gold": 0}
				database_mgr.add_background(id, d)
			"campaign":
				# A single END node as its own start: the campaign completes the
				# instant it is started rather than failing to load or crashing on
				# an unresolved node reference, the same "never invalid merely by
				# existing" rule the new-dialogue default follows.
				d = {
					"campaign_id": id, "name": "New Campaign", "description": "",
					"start_node_id": "start",
					"nodes": {"start": {"description": "The story ends.", "type": "END", "outcome": "complete"}},
				}
				database_mgr.add_campaign(id, d)
			"topic":
				d = {"display_name": "New Topic", "keywords": [], "responses": []}
				database_mgr.add_topic(id, d)
			"affix_prefix", "affix_suffix":
				# Applies to nothing until the author names item types, and does
				# nothing until a modifier row exists -- so a new affix is inert
				# rather than silently changing every generated item.
				d = {"allowed_types": [], "level_min": 1, "modifiers": {}, "value_mult": 1.0}
				if t == "affix_suffix": database_mgr.add_affix_suffix(id, d)
				else: database_mgr.add_affix_prefix(id, d)
			"item_set":
				d = {"name": "New Item Set", "items": [], "bonuses": {}}
				database_mgr.add_item_set(id, d)
		_update_db_ui()
	)
	ui_mgr.request_delete_db_entry.connect(_confirm_delete_db_entry)
	inspector.request_entry_rename.connect(_on_request_entry_rename)
	ui_mgr.database_modified.connect(func(t, id):
		database_mgr.mark_dirty(t, id)
		_update_db_ui()
	)
	ui_mgr.database_saved.connect(func(): _update_db_ui())
	ui_mgr.request_delete_room_confirm.connect(action_handler.execute_delete_room)
	ui_mgr.request_quit_save.connect(func(): _save_everything(); if not _has_unsaved_work(): get_tree().quit())
	ui_mgr.request_quit_discard.connect(func(): get_tree().quit())

func _connect_inspector_signals():
	inspector.request_rename.connect(func(o, n): 
		cmd_proc.commit(
			func(): region_mgr.rename_room(o, n); _refresh_view(); _on_node_click(n, false); _update_explorer_dirty_state(),
			func(): region_mgr.rename_room(n, o); _refresh_view(); _on_node_click(o, false); _update_explorer_dirty_state(),
			"Rename Room"
		)
	)
	inspector.request_connection_modal.connect(func(): 
		if state.selected_ids.size() == 1: 
			var id = state.selected_ids[0]
			_open_connection_form(id, region_mgr.data.rooms[id].name)
	)
	inspector.connection_created.connect(func(src, dir, target, two_way, rev):
		action_handler.create_connection(src, dir, target, two_way, rev)
		_close_connection_mode(src)
	)
	# Same connection, but the form stays open on the same source so the next room
	# can be connected without re-picking the source and the direction.
	inspector.connection_created_and_continue.connect(
		func(src, dir, target, two_way, rev):
			action_handler.create_connection(src, dir, target, two_way, rev)
	)
	inspector.target_selected_in_connector.connect(_on_connection_target_selected)
	inspector.request_delete_connection.connect(_on_delete_connection_requested)
	inspector.request_curve_change.connect(_on_curve_change_requested)
	inspector.request_save_template.connect(_on_save_template_request)
	inspector.request_jump_to_room.connect(_jump_to_room)
	inspector.save_triggered.connect(func(): _save_everything())
	inspector.reload_triggered.connect(func():
		_deselect_all(); 
		if state.is_world_view: world_mgr.load_world_layout(); _refresh_view(); camera_controller.center_on_nodes(graph_controller.get_active_nodes())
		else: _load_region(region_mgr.current_filename, true)
	)
	inspector.data_modified.connect(_on_data_modified)
	inspector.database_modified.connect(func():
		if inspector.current_inspector:
			if inspector.cur_mode == "quest":
				database_mgr.mark_dirty("quest", inspector.current_inspector.cur_id)
			elif inspector.cur_mode in ["npc", "item", "magic"]:
				database_mgr.mark_dirty(inspector.cur_mode, inspector.current_inspector.cur_id)
		_update_db_ui()
	)
	
	inspector.request_graph_edit_mode.connect(func(qid):
		var q_data = database_mgr.quests.get(qid, {})
		inspector.load_quest_mode(qid)
		graph_controller.load_quest_graph(qid, q_data)
		camera_controller.center_on_nodes(graph_controller.get_active_nodes())
	)

# Pure panning/zooming never changes anything graph_controller draws in the
# local view -- connections and district territory are all in world space,
# so the camera moving under them needs no redraw at all (Godot's Camera2D
# already reprojects existing draw commands). GridLayer is the one real
# exception: it regenerates its lines from the camera's current position/
# zoom every time, so it always needs this. Skipping the graph redraw here
# matters because it was re-running the district territory computation --
# not cheap -- on every single mouse-motion frame of a pan or every wheel
# tick, for content that never actually changed. World/quest view keeps
# redrawing on every camera move as before: world view's connection lines
# scale their width against the camera's zoom, so they do depend on it.
func _redraw_after_camera_input():
	grid_layer.queue_redraw()
	if graph_controller.current_mode != GraphController.ViewMode.LOCAL:
		graph_controller.queue_redraw()

func _connect_graph_signals():
	graph_controller.world_region_selected.connect(_on_world_region_selected)
	graph_controller.node_drag_started.connect(func(_id): is_dragging_object = true)
	# A room card normally absorbs every mouse event over it, but middle-
	# button panning should work no matter what's under the cursor -- the
	# room forwards that one button's events up through this same signal
	# chain instead of swallowing them, so it reaches the camera exactly as
	# if _unhandled_input had received it directly.
	graph_controller.camera_pan_input.connect(func(event):
		if camera_controller.handle_input(event):
			if camera_controller.is_panning: is_dragging_object = true
			_redraw_after_camera_input()
	)
	graph_controller.room_label_clicked.connect(func(id):
		label_drag_source = ""
		graph_controller.set_label_drag_source("")
		graph_controller.set_label_swap_preview("", "")
		if region_mgr.data.rooms.has(id): ui_mgr.show_room_label_editor(id, str(region_mgr.data.rooms[id].get("name", "")))
	)
	graph_controller.room_label_drag_started.connect(func(id):
		label_drag_source = id
		graph_controller.set_label_drag_source(id)
	)
	graph_controller.room_label_dragged.connect(func(_id):
		var target_id := graph_controller.get_room_under_mouse(get_global_mouse_position())
		var preview_target := target_id if target_id != label_drag_source else ""
		graph_controller.set_label_swap_target(preview_target)
		graph_controller.set_label_swap_preview(label_drag_source, preview_target)
	)
	graph_controller.room_label_drag_ended.connect(func(_id):
		var target_id := graph_controller.get_room_under_mouse(get_global_mouse_position())
		graph_controller.set_label_swap_target("")
		graph_controller.set_label_drag_source("")
		graph_controller.set_label_swap_preview("", "")
		if label_drag_source != "" and target_id != "" and target_id != label_drag_source:
			action_handler.swap_room_labels(label_drag_source, target_id)
		label_drag_source = ""
	)
	graph_controller.world_view_builder.region_dragged.connect(func(): is_dragging_object = true)
	graph_controller.node_selected.connect(func(id): _on_node_click(id, Input.is_key_pressed(KEY_SHIFT)))
	graph_controller.node_double_clicked.connect(func(id): camera_controller.focus_on(graph_controller.get_node_position(id), true))
	graph_controller.node_drag_started.connect(func(id):
		# No moving rooms while the connection form is open. Dragging a room to
		# pick it is the same gesture as dragging it to move it, and a room moved
		# by accident is a content change that reaches the save -- so in connection
		# mode the drag simply does not start, rather than starting and being undone.
		if state.connection_mode: return
		if not state.is_selected(id): return 
		state.drag_start_positions.clear()
		for sel_id in state.selected_ids: state.drag_start_positions[sel_id] = graph_controller.get_node_position(sel_id)
	)
	graph_controller.node_dragging.connect(func(id, current_pos):
		var id_str = str(id)
		if not state.is_selected(id_str) or not state.drag_start_positions.has(id_str): return
		var delta = current_pos - state.drag_start_positions[id_str]
		for sel_id in state.selected_ids:
			if sel_id != id_str and state.drag_start_positions.has(sel_id):
				graph_controller.set_node_position(sel_id, state.drag_start_positions[sel_id] + delta)
	)
	graph_controller.node_dragged.connect(func(id, new_pos):
		is_dragging_object = false
		var id_str = str(id)
		if state.drag_start_positions.has(id_str) and state.is_selected(id_str):
			var delta = new_pos - state.drag_start_positions[id_str]
			if delta.length_squared() > 1.0: action_handler.commit_batch_move(delta)
	)
	graph_controller.node_right_clicked.connect(func(id):
		if state.is_world_view: return
		if ":" in str(id):
			var parts = id.split(":"); var target_region_file = parts[0] + ".json"; var target_room_id = parts[1]
			_load_region(target_region_file, false, true); await get_tree().create_timer(0.05).timeout; _jump_to_room(target_room_id)
		else: ui_mgr.show_context_menu({"Rename":0, "Delete":99, "Set Start":3}); ui_mgr.context_menu.set_meta("target_type", "room"); ui_mgr.context_menu.set_meta("target_id", str(id))
	)
	graph_controller.connection_drag_started.connect(func(id): state.dragging_conn={"active":true, "start":graph_controller.get_node_position(id), "end":Vector2.ZERO, "src":id})
	graph_controller.region_connection_drag_started.connect(func(rid, local_pos):
		var node = graph_controller.world_view_builder.world_region_nodes.get(rid)
		if not node: return
		var anchor_room: String = node.get_nearest_room_id(local_pos)
		if anchor_room == "": return
		var world_start: Vector2 = node.global_position + (node.get_room_local_center(anchor_room) * node.scale)
		state.world_dragging_conn = {"active": true, "start": world_start, "end": world_start, "src_region": rid, "src_room": anchor_room}
		is_dragging_object = true
	)
	graph_controller.creation_drag_started.connect(func(id, pos): state.creating_conn={"active":true, "start_pos":pos, "end_pos":pos, "src_id":id})
	graph_controller.region_moved.connect(func(id, old, new):
		cmd_proc.commit(
			func(): world_mgr.update_world_node_pos(id, new); _refresh_view(),
			func(): world_mgr.update_world_node_pos(id, old); _refresh_view(),
			"Move Region"
		)
	)
	graph_controller.request_region_edit.connect(func(id): ui_mgr.btn_world_view.button_pressed = false; _load_region(id + ".json", false, true))

func _unhandled_input(event):
	if event is InputEventKey and event.pressed:
		if event.keycode == KEY_Z and event.ctrl_pressed: cmd_proc.undo(); if not state.is_world_view: _refresh_view(); _on_data_modified()
		elif event.keycode == KEY_Y and event.ctrl_pressed: cmd_proc.redo(); if not state.is_world_view: _refresh_view(); _on_data_modified()
		elif event.keycode == KEY_ESCAPE:
			if state.cur_tool_mode != EditorUIManager.ToolMode.SELECT: ui_mgr.tool_changed.emit(EditorUIManager.ToolMode.SELECT, {})
			elif state.is_box_selecting: state.is_box_selecting = false; graph_controller.update_selection_box(Rect2(), false)
		elif event.keycode == KEY_F: camera_controller.center_on_nodes(graph_controller.get_active_nodes())
		elif event.keycode == KEY_F and event.ctrl_pressed: ui_mgr.show_search_modal()

	if ui_mgr.is_mouse_over_ui(): return

	if state.district_preview.get("active", false):
		_handle_district_preview_input(event)
		return

	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		var mouse_pos = get_global_mouse_position()
		var is_on_node = _is_mouse_on_any_node(mouse_pos)

		if event.pressed:
			is_dragging_object = false
			if not is_on_node and not state.is_box_selecting and state.cur_tool_mode == EditorUIManager.ToolMode.STAMP and state.cur_tool_data.get("type") == "room_template":
				_stamp_template_at(mouse_pos)
				return 

			if not is_on_node and not state.is_box_selecting:
				var pressed_district_id := "" if state.is_world_view else graph_controller.get_district_id_at(mouse_pos)
				if pressed_district_id != "":
					_select_district(pressed_district_id)
					var start_positions := {}
					for room_id_variant in _district_member_ids(pressed_district_id):
						var room_id := str(room_id_variant)
						if region_mgr.data.get("rooms", {}).has(room_id):
							start_positions[room_id] = graph_controller.get_node_position(room_id)
					state.district_move_dragging = {"active": true, "district_id": pressed_district_id, "mouse_start": mouse_pos, "positions": start_positions}
					return
				deselection_primed = true; mouse_down_pos = mouse_pos
		else:
			if deselection_primed and not is_dragging_object and mouse_pos.distance_to(mouse_down_pos) < DRAG_PIXEL_THRESHOLD: _on_empty_click(mouse_pos)
			deselection_primed = false; is_dragging_object = false

	if not state.is_box_selecting and camera_controller.handle_input(event):
		if camera_controller.is_panning: is_dragging_object = true
		_redraw_after_camera_input()
		return

	if state.dragging_conn.get("active", false):
		if event is InputEventMouseButton and not event.pressed:
			var target_id = graph_controller.get_room_under_mouse(get_global_mouse_position())
			var src_name = region_mgr.data.rooms.get(state.dragging_conn.src, {}).get("name", "...")
			if target_id != "" and target_id != state.dragging_conn.src: 
				_open_connection_form(state.dragging_conn.src, src_name, target_id)
			else: _open_connection_form(state.dragging_conn.src, src_name)
			state.dragging_conn.active = false; graph_controller.queue_redraw()
		elif event is InputEventMouseMotion: graph_controller.queue_redraw()
		return

	if state.world_dragging_conn.get("active", false):
		if event is InputEventMouseButton and not event.pressed:
			var mouse_pos = get_global_mouse_position()
			var cam_zoom = main_camera.zoom.x if main_camera else 1.0
			var src_region: String = state.world_dragging_conn.src_region
			var src_room: String = state.world_dragging_conn.src_room
			var target_region := graph_controller.get_world_region_id_at(mouse_pos, cam_zoom)
			if target_region == src_region: target_region = ""
			state.world_dragging_conn.active = false
			graph_controller.queue_redraw()
			_open_world_connection_form(src_region, src_room, target_region)
		elif event is InputEventMouseMotion:
			state.world_dragging_conn.end = get_global_mouse_position()
			graph_controller.queue_redraw()
		return

	if state.district_move_dragging.get("active", false):
		if event is InputEventMouseButton and not event.pressed:
			var delta: Vector2 = get_global_mouse_position() - state.district_move_dragging.mouse_start
			var start_positions: Dictionary = state.district_move_dragging.positions
			state.district_move_dragging = {"active": false, "district_id": "", "mouse_start": Vector2.ZERO, "positions": {}}
			is_dragging_object = false
			if delta.length_squared() > 1.0: _commit_district_move(start_positions, delta)
			else: graph_controller.queue_redraw()
		elif event is InputEventMouseMotion:
			var delta: Vector2 = get_global_mouse_position() - state.district_move_dragging.mouse_start
			if state.snap_enabled: delta = Vector2(round(delta.x / 32.0) * 32.0, round(delta.y / 32.0) * 32.0)
			for room_id in state.district_move_dragging.positions:
				graph_controller.set_node_position(room_id, state.district_move_dragging.positions[room_id] + delta)
			graph_controller.queue_redraw()
		return

	if state.creating_conn.get("active", false) and event is InputEventMouseButton and not event.pressed:
		ui_mgr.show_creation_menu(event.position); state.creating_conn.active = false; graph_controller.queue_redraw()
		return

	if state.cur_tool_mode == EditorUIManager.ToolMode.SELECT and event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT and event.pressed and event.shift_pressed:
		state.is_box_selecting = true; state.box_select_start = get_global_mouse_position()
		return

func _is_mouse_on_any_node(mouse_pos: Vector2) -> bool:
	if state.is_world_view:
		var cam_zoom = main_camera.zoom.x if main_camera else 1.0
		return graph_controller.get_world_region_id_at(mouse_pos, cam_zoom) != ""
	else:
		return graph_controller.get_room_under_mouse(mouse_pos) != ""

func _handle_district_preview_input(event):
	var preview: Dictionary = state.district_preview
	if event is InputEventKey and event.pressed and event.keycode == KEY_ESCAPE:
		_cancel_district_placement(); return
	# Navigation remains available while a district is only a ghost. Left-drag
	# is reserved for moving it; wheel zoom and middle-drag pan the map.
	var navigation_input: bool = event is InputEventMouseButton and event.button_index in [MOUSE_BUTTON_WHEEL_UP, MOUSE_BUTTON_WHEEL_DOWN, MOUSE_BUTTON_MIDDLE]
	if navigation_input or (event is InputEventMouseMotion and camera_controller.is_panning):
		if camera_controller.handle_input(event):
			_redraw_after_camera_input()
		return
	if event is InputEventMouseButton and event.button_index == MOUSE_BUTTON_LEFT:
		if event.pressed:
			state.district_dragging = {"active": true, "mouse_start": get_global_mouse_position(), "positions": preview.get("positions", {}).duplicate(true)}
		else:
			state.district_dragging.active = false
	elif event is InputEventMouseMotion and state.district_dragging.get("active", false):
		var delta: Vector2 = get_global_mouse_position() - state.district_dragging.mouse_start
		if state.snap_enabled: delta = Vector2(round(delta.x / 32.0) * 32.0, round(delta.y / 32.0) * 32.0)
		var moved := {}
		for room_id in state.district_dragging.positions: moved[room_id] = state.district_dragging.positions[room_id] + delta
		action_handler.update_district_placement_positions(moved)

func _cancel_district_placement():
	state.district_preview = _empty_district_preview()
	state.district_dragging = {"active": false, "mouse_start": Vector2.ZERO, "positions": {}}
	ui_mgr.set_district_workflow(false); graph_controller.queue_redraw()

func _empty_district_preview() -> Dictionary:
	return {"active": false, "valid": false, "positions": {}, "rooms": {}, "district": {}}

func _refresh_district_toolbar():
	var preview: Dictionary = state.district_preview
	ui_mgr.set_district_workflow(bool(preview.get("active", false)), bool(preview.get("valid", false)))

func _stamp_template_at(pos: Vector2):
	var template_id = state.cur_tool_data.get("id")
	if not database_mgr.templates.has(template_id): return
	
	var tmpl_data = database_mgr.templates[template_id]
	var new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
	while region_mgr.data.rooms.has(new_id):
		new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
	
	var new_room_data = tmpl_data.duplicate(true)
	new_room_data.erase("_filename")
	new_room_data.erase("id")
	new_room_data.exits = {} 
	new_room_data._editor_pos = [pos.x, pos.y]
	
	cmd_proc.commit(
		func():
			region_mgr.add_room_data(new_id, new_room_data)
			_refresh_view(); _on_node_click(new_id, false)
			region_mgr.mark_room_dirty(new_id); _update_explorer_dirty_state(),
		func():
			region_mgr.remove_room_data(new_id)
			_refresh_view(); _update_explorer_dirty_state(),
		"Stamp Room Template"
	)

func _on_save_template_request(room_id):
	if not region_mgr.data.rooms.has(room_id): return
	var room_data = region_mgr.data.rooms[room_id].duplicate(true)
	var template_id = room_data.get("name", "template").to_snake_case() + "_tpl"
	database_mgr.save_template(template_id, room_data)
	_update_db_ui()
	print("Saved template: " + template_id)

func _on_copy_request():
	editor_clipboard.clear()
	if state.selected_ids.is_empty(): return
	for id in state.selected_ids:
		if region_mgr.data.rooms.has(id):
			editor_clipboard.append(region_mgr.data.rooms[id].duplicate(true))
	print("Copied %d rooms." % editor_clipboard.size())

func _on_paste_request():
	if editor_clipboard.is_empty() or state.is_world_view: return
	var new_ids = []; var paste_offset = Vector2(50, 50)
	for room_data in editor_clipboard:
		var new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
		while region_mgr.data.rooms.has(new_id):
			new_id = "room_" + str(Time.get_ticks_msec()) + "_" + str(randi() % 1000)
			
		var new_data = room_data.duplicate(true)
		var old_pos = Vector2(new_data._editor_pos[0], new_data._editor_pos[1])
		var new_pos = old_pos + paste_offset
		new_data._editor_pos = [new_pos.x, new_pos.y]
		new_data.exits = {}
		region_mgr.add_room_data(new_id, new_data)
		region_mgr.mark_room_dirty(new_id)
		new_ids.append(new_id)
	
	_refresh_view()
	state.set_selection(new_ids)
	_update_selection_state()
	_update_explorer_dirty_state()
	print("Pasted %d rooms." % editor_clipboard.size())

func _load_region(file, force_reload: bool = false, keep_ui_visible: bool = false):
	if state.is_world_view:
		# Use helper to sync button state
		ui_mgr.set_world_view_button_state(false)
		_set_world_view(false)

	if not force_reload and file == region_mgr.current_filename and file != "": return

	# Leaving a region with unsaved edits used to discard them silently: nothing
	# on this path looked at `is_region_dirty`. Ask instead -- and make refusing
	# the default, so a stray click in the Explorer tree cannot cost an hour.
	if region_mgr.is_region_dirty and file != region_mgr.current_filename:
		var target: String = str(file) if file != "" else "an empty view"
		var save_then_load := func():
			if _save_everything(): _load_region_now(file, force_reload, keep_ui_visible)
		ui_mgr.confirm(
			"Unsaved changes",
			"%s has unsaved changes. Loading %s will discard them." % [
				region_mgr.current_filename, target,
			],
			"Save changes and load",
			save_then_load,
			"Keep editing",
		)
		ui_mgr.set_confirm_extra_button(
			"Discard changes and load",
			func(): _load_region_now(file, force_reload, keep_ui_visible),
		)
		return

	_load_region_now(file, force_reload, keep_ui_visible)

func _load_region_now(file, force_reload: bool = false, keep_ui_visible: bool = false):
	var previous_filename := region_mgr.current_filename
	if previous_filename != "": view_states[previous_filename] = {"pos": main_camera.position, "zoom": main_camera.zoom}

	var loaded: bool = file == "" or region_mgr.load_region(file)
	if not loaded:
		# Keep showing what is on screen, and say why. The old path replaced the
		# region with a blank one under the real filename and only pushed an
		# error, so the next Save wrote the blank region over the file.
		ui_mgr.show_error(
			"Could not load region",
			region_mgr.load_error if region_mgr.load_error != "" else "The region could not be loaded.",
		)
		return

	# Undo closures capture one region's data. After a load they would replay
	# against a different one, so the history goes with the region it belongs to.
	cmd_proc.clear_history()

	if not keep_ui_visible: _deselect_all()
	_refresh_view()

	if view_states.has(file):
		var vs = view_states[file]; main_camera.position = vs.pos; main_camera.zoom = vs.zoom
	else:
		camera_controller.center_on_nodes(graph_controller.get_active_nodes())

	var rooms = region_mgr.data.get("rooms", {})
	var exit_count = 0
	for r in rooms.values():
		exit_count += r.get("exits", {}).size()
	ui_mgr.update_status_info(region_mgr.data.get("name", file), rooms.size(), "", exit_count)
	ui_mgr.call_deferred("refresh_explorer", world_mgr.get_global_hierarchy(), file, "")
	inspector.set_region_dirty(region_mgr.is_region_dirty)

func _create_region(name, rooms_data, region_meta: Dictionary = {}):
	if not name.ends_with(".json"): name += ".json"
	var properties: Dictionary = {}
	var biome = String(region_meta.get("biome", ""))
	var region_type = String(region_meta.get("region_type", ""))
	if biome != "": properties["biome"] = biome
	if region_type != "": properties["region_type"] = region_type
	var level_min = int(region_meta.get("level_min", 0))
	var level_max = int(region_meta.get("level_max", 0))
	var spawner: Dictionary = {}
	if level_min > 0 and level_max >= level_min:
		properties["level_band"] = {"min": level_min, "max": level_max}
		spawner["level_range"] = [level_min, level_max]

	var npc_ids: Array = region_meta.get("npc_ids", [])
	var density: float = float(region_meta.get("population_density", 0.0))
	if npc_ids.size() > 0 and density > 0.0:
		spawner["monster_types"] = {}
		for npc_id in npc_ids: spawner["monster_types"][npc_id] = 1
		_populate_rooms_with_npcs(rooms_data, npc_ids, density)

	var new_region_id: String = name.replace(".json", "")
	var connect: Dictionary = region_meta.get("connect", {})
	if not connect.is_empty():
		_wire_entrance_connection(new_region_id, rooms_data, connect)

	var new_data: Dictionary = { "region_id": new_region_id, "description": "New region", "rooms": rooms_data }
	if not properties.is_empty(): new_data["properties"] = properties
	if not spawner.is_empty(): new_data["spawner"] = spawner

	var region_path := DataRoot.content_dir("regions").path_join(name)
	if not DirAccess.dir_exists_absolute(DataRoot.content_dir("regions")):
		DirAccess.make_dir_recursive_absolute(DataRoot.content_dir("regions"))
	var written := SaveIO.write_json(region_path, EditorLayout.strip_region(new_data))
	if not written.get("ok", false):
		ui_mgr.show_error("Could not create %s" % name, written.get("error", ""))
		return
	# A new region is not in the cached Explorer hierarchy yet, so rebuild it --
	# otherwise the region the author just made is missing from the tree until
	# the editor is restarted.
	cached_hierarchy = world_mgr.get_global_hierarchy()
	_load_region(name)

# Scatters the chosen NPC templates across roughly `density` (0-1) of the
# generated rooms as initial_npcs entries, so a generated region ships with
# some population instead of standing completely empty. One instance_id
# suffix per placement keeps ids unique if the same template is placed more
# than once (the runtime NPC factory requires unique instance ids).
func _populate_rooms_with_npcs(rooms_data: Dictionary, npc_ids: Array, density: float):
	var room_ids: Array = rooms_data.keys()
	room_ids.shuffle()
	var target_count = int(ceil(room_ids.size() * clamp(density, 0.0, 1.0)))
	var placed = 0
	for room_id in room_ids:
		if placed >= target_count: break
		var npc_id = npc_ids[randi() % npc_ids.size()]
		var room = rooms_data[room_id]
		if not room.has("initial_npcs"): room["initial_npcs"] = []
		room["initial_npcs"].append({"template_id": npc_id, "instance_id": "%s_%s" % [npc_id, room_id]})
		placed += 1

# Wires the new region's chosen entrance room to an existing region/room in
# both directions, so a generated region doesn't have to be stitched into
# the world by hand afterward. The forward exit is written straight into
# rooms_data (this region's own file, not yet on disk). The reciprocal exit
# has to land in a *different* region's data -- if that region happens to
# be the one currently open in the editor, patch region_mgr's in-memory
# copy and mark it dirty (so an unsaved edit there isn't clobbered by a
# direct file write, and the reciprocal exit is included whenever it's next
# saved); otherwise read-modify-write its file directly, the same technique
# RegionManager._patch_external_references already uses for rename-patching
# other regions' files.
func _wire_entrance_connection(new_region_id: String, rooms_data: Dictionary, connect: Dictionary):
	var entrance_room: String = String(connect.get("entrance_room", ""))
	var direction: String = String(connect.get("direction", ""))
	var target_region: String = String(connect.get("target_region", ""))
	var target_room: String = String(connect.get("target_room", ""))
	if entrance_room == "" or direction == "" or target_region == "" or target_room == "": return
	if not rooms_data.has(entrance_room): return

	if not rooms_data[entrance_room].has("exits"): rooms_data[entrance_room]["exits"] = {}
	rooms_data[entrance_room]["exits"][direction] = "%s:%s" % [target_region, target_room]

	var inv_dir: String = Constants.INV_DIR_MAP.get(direction, "")
	if inv_dir == "": return
	var reciprocal_exit: String = "%s:%s" % [new_region_id, entrance_room]

	if region_mgr.current_filename != "" and region_mgr.data.get("region_id", "") == target_region:
		if region_mgr.data.get("rooms", {}).has(target_room):
			if not region_mgr.data.rooms[target_room].has("exits"): region_mgr.data.rooms[target_room]["exits"] = {}
			region_mgr.data.rooms[target_room]["exits"][inv_dir] = reciprocal_exit
			region_mgr.mark_room_dirty(target_room)
			# _create_region switches the open region to the newly created
			# one right after this call returns, so an edit left merely
			# "dirty" here would be silently discarded rather than waiting
			# for a save that's never coming -- persist it immediately.
			var saved := region_mgr.save_region()
			if not saved.get("ok", false):
				ui_mgr.show_error("Could not save %s" % region_mgr.current_filename, saved.get("error", ""))
		return

	var target_filename: String = String(world_mgr.get_global_hierarchy().get(target_region, {}).get("filename", ""))
	if target_filename == "": return
	var full_path: String = DataRoot.content_dir("regions").path_join(target_filename)
	var f = FileAccess.open(full_path, FileAccess.READ)
	if not f: return
	var json = JSON.new()
	if json.parse(f.get_as_text()) != OK: return
	f.close()
	var data = json.get_data()
	if typeof(data) != TYPE_DICTIONARY or not data.get("rooms", {}).has(target_room): return
	if not data["rooms"][target_room].has("exits"): data["rooms"][target_room]["exits"] = {}
	data["rooms"][target_room]["exits"][inv_dir] = reciprocal_exit
	# Same stripper and same verified writer as every other save of a file the
	# engine reads: this write used to be raw, unverified, and could leave
	# `_editor_*` keys in another region's content.
	var written := SaveIO.write_json(full_path, EditorLayout.strip_region(data))
	if not written.get("ok", false):
		ui_mgr.show_error("Could not write the return exit into %s" % target_filename, written.get("error", ""))

func _show_validation_results():
	var visible_findings: Array = []
	var ignored_count := 0

	# The engine's own reference verdict first, because it is the one that decides
	# whether the game loads the region. This used to be the editor's walker alone,
	# so an author reading this modal got one wording for "this exit points nowhere"
	# here and a different one from the Content Validation button for the same fact.
	#
	# Filtered to the two reference sources: the rest of `editor_validate.py`'s
	# checks are about items, quests and contracts, and this modal is about links.
	# Nothing is lost by that -- the unfiltered run has its own button.
	visible_findings.append_array(_engine_reference_findings())

	for finding in world_mgr.validate_world_links():
		if world_mgr.is_suppressible_warning(finding) and world_mgr.is_warning_ignored(finding):
			ignored_count += 1
		else:
			visible_findings.append(finding)
	ui_mgr.show_validation_results(visible_findings, ignored_count)


## Reference findings from the engine, as display strings.
##
## Empty when it cannot run -- no interpreter, no validator -- because a link modal
## that refuses to open is worse than one that shows only its own findings. The
## Content Validation button reports the same gap in full.
func _engine_reference_findings() -> Array:
	var project_root: String = ProjectSettings.globalize_path("res://")
	var repo_root: String = project_root.trim_suffix("/").get_base_dir()
	var validator_script: String = repo_root.path_join("toolkit/editor_validate.py")
	var python_exe: String = _find_python(repo_root)
	if not FileAccess.file_exists(validator_script) or python_exe == "":
		return []

	var output: Array = []
	OS.execute(
		python_exe,
		[validator_script, DataRoot.root(), "--only", "references,stale"],
		output, false,
	)
	var raw: String = str(output[0]) if output.size() > 0 else ""
	var parsed = EngineValidator.last_json_object(raw)
	if typeof(parsed) != TYPE_DICTIONARY:
		return []

	var findings: Array = []
	for issue in parsed.get("issues", []):
		var severity := str(issue.get("severity", "warning"))
		if severity != "error":
			# This modal is a to-do list. Warnings have their own place, and mixing
			# them in makes the errors harder to find.
			continue
		findings.append("[%s] %s: %s" % [
			str(issue.get("path", "")), "engine", str(issue.get("message", "")),
		])
	return findings

func _validate_region_policy():
	# Everything here used to be built from `res://data/...`, the editor's own
	# mirror tree, which has not existed since the editor started editing the
	# shared content set -- so this check always answered "No data/ruleset.json
	# found" and never ran. The paths come from DataRoot now, like every other
	# reader in the editor.
	var project_root: String = ProjectSettings.globalize_path("res://")
	var repo_root: String = project_root.trim_suffix("/").get_base_dir()
	var validator_script: String = repo_root.path_join("toolkit/region_policy_validator.py")
	var content_root: String = DataRoot.data_dir()
	var ruleset_path: String = DataRoot.ruleset_path()

	var python_exe: String = _find_python(repo_root)
	if python_exe == "":
		ui_mgr.show_region_policy_results(false, [], (
			"No Python interpreter found. Looked for .venv/Scripts/python.exe, "
			+ ".venv/bin/python, .conda/python.exe and python on PATH, under %s."
		) % repo_root)
		return
	if not FileAccess.file_exists(validator_script):
		ui_mgr.show_region_policy_results(false, [], "Validator not found at %s." % validator_script)
		return
	if not FileAccess.file_exists(ruleset_path):
		ui_mgr.show_region_policy_results(false, [], (
			"No ruleset at %s -- this content set does not declare one, so there is no "
			+ "region policy to check against."
		) % ruleset_path)
		return

	var output: Array = []
	var exit_code = OS.execute(python_exe, [validator_script, content_root, "--ruleset", ruleset_path, "--json"], output, false)
	var raw: String = output[0] if output.size() > 0 else ""
	var json_line: String = ""
	for line in raw.split("\n"):
		if line.strip_edges() != "": json_line = line
	var parsed = JSON.parse_string(json_line)
	if typeof(parsed) != TYPE_DICTIONARY:
		ui_mgr.show_region_policy_results(false, [], "Could not parse validator output (exit code %d):\n%s" % [exit_code, raw])
		return
	ui_mgr.show_region_policy_results(bool(parsed.get("ok", false)), parsed.get("issues", []))

# The engine's own verdict, run over the content set this editor is pointed at.
# Slower than the link check (it starts Python) and worth it: it is the same
# validation the build runs, so "the editor is happy" and "the game will load it"
# stop being different questions.
func _validate_content():
	if _content_validation_thread != null:
		return
	var project_root: String = ProjectSettings.globalize_path("res://")
	var repo_root: String = project_root.trim_suffix("/").get_base_dir()
	var python_exe: String = _find_python(repo_root)
	_content_validation_label = DataRoot.root()
	_content_validation_thread = Thread.new()
	var started := _content_validation_thread.start(
		_run_content_validation.bind(_content_validation_label, repo_root, python_exe)
	)
	if started != OK:
		_content_validation_thread = null
		ui_mgr.show_content_validation({
			"ran": false,
			"error": "Could not start open-set validation (error %d)." % started,
		}, _content_validation_label)
		return
	ui_mgr.set_content_validation_running(true)


func _run_content_validation(content_set_root: String, repo_root: String, python_exe: String) -> Dictionary:
	return EngineValidator.run(content_set_root, repo_root, python_exe)


func _poll_content_validation():
	if _content_validation_thread == null or _content_validation_thread.is_alive():
		return
	var result = _content_validation_thread.wait_to_finish()
	_content_validation_thread = null
	ui_mgr.set_content_validation_running(false)
	var displayed_result: Dictionary = result if result is Dictionary else {
		"ran": false,
		"error": "Open-set validation stopped before returning a result.",
	}
	ui_mgr.show_content_validation(_filter_acknowledged_content_warnings(displayed_result), _content_validation_label)

# Acknowledgement is a presentation choice in the editor only: the validator's
# raw result remains intact, error findings always remain visible, and the next
# changed warning receives a different stable key and returns to the report.
func _filter_acknowledged_content_warnings(result: Dictionary) -> Dictionary:
	if not result.get("ran", false): return result
	var visible: Array = []
	var ignored_count := 0
	for raw_issue in result.get("issues", []):
		if raw_issue is Dictionary and str(raw_issue.get("severity", "")) == "warning":
			var warning_id := str(raw_issue.get("warning_id", ""))
			if warning_id != "" and world_mgr.is_content_warning_ignored(warning_id):
				ignored_count += 1
				continue
		visible.append(raw_issue)
	var filtered := result.duplicate(true)
	filtered["issues"] = visible
	filtered["ignored_warning_count"] = ignored_count
	var counts: Dictionary = filtered.get("counts", {}).duplicate(true)
	counts["warning"] = 0
	for issue in visible:
		if issue is Dictionary and str(issue.get("severity", "")) == "warning": counts["warning"] += 1
	filtered["counts"] = counts
	return filtered

func _run_release_gate():
	if _release_gate_thread != null: return
	var project_root: String = ProjectSettings.globalize_path("res://")
	var repo_root: String = project_root.trim_suffix("/").get_base_dir()
	var python_exe: String = _find_python(repo_root)
	_release_gate_thread = Thread.new()
	var started := _release_gate_thread.start(EngineValidator.run_release_gate.bind(repo_root, python_exe))
	if started != OK:
		_release_gate_thread = null
		ui_mgr.show_release_gate_result({"ran": false, "error": "Could not start the release gate (error %d)." % started})
		return
	ui_mgr.set_release_gate_running(true)

func _poll_release_gate():
	if _release_gate_thread == null or _release_gate_thread.is_alive(): return
	var result = _release_gate_thread.wait_to_finish()
	_release_gate_thread = null
	ui_mgr.set_release_gate_running(false)
	ui_mgr.show_release_gate_result(result if result is Dictionary else {
		"ran": false, "error": "The release gate stopped before returning a result.",
	})

# The first interpreter that actually exists, so this does not depend on one
# particular virtualenv layout. Returns "" when there is none.
func _find_python(repo_root: String) -> String:
	var candidates := [
		repo_root.path_join(".venv/Scripts/python.exe"),
		repo_root.path_join(".venv/bin/python"),
		repo_root.path_join(".conda/python.exe"),
	]
	for candidate in candidates:
		if FileAccess.file_exists(candidate):
			return candidate
	return "python"

# --- saving, quitting and deletion ------------------------------------------
# These exist because every one of them used to be silent: a failed write looked
# like a successful one, a region switch discarded edits without asking, closing
# the window discarded everything, and deleting from the content library was one
# click with no confirmation and no undo.

func _has_unsaved_work() -> bool:
	return region_mgr.is_region_dirty or database_mgr.has_unsaved_changes() or ui_mgr.has_configuration_drafts()

func _save_everything() -> bool:
	# Every dirty thing, in one press, whatever view is on screen. This used to
	# return early twice: in the world view it saved the layout and stopped, and
	# with a clean region it returned without ever reaching `save_all()`. Both
	# paths are reachable from the "Save and switch" button, so an author who had
	# edited an NPC or an item -- library work, not region work -- was told their
	# work was saved and then had it dropped when the next set's `load_all()`
	# cleared the dirty flags.
	#
	# A checkpoint is taken first because this writes many files one at a time:
	# atomic writes still leave a half-updated set if the fourth fails. The
	# in-memory caches are deliberately *not* rolled back -- the author's work
	# stays on screen and stays dirty, so the fix is to save again.
	var checkpoint := SaveCheckpoint.begin(DataRoot.root())
	var had_region_changes := region_mgr.is_region_dirty
	var had_library_changes := database_mgr.has_unsaved_changes()
	if state.is_world_view:
		var layout := world_mgr.save_world_layout()
		if not layout.get("ok", false):
			return _report_failed_save(checkpoint, "Could not save the world layout", str(layout.get("error", "")))

	if region_mgr.is_region_dirty:
		var saved := region_mgr.save_region()
		if not saved.get("ok", false):
			# Deliberately still dirty. A Save that failed but cleared the dirty flag
			# is how an author closed the editor believing their work was on disk.
			return _report_failed_save(checkpoint, "Could not save %s" % region_mgr.current_filename, str(saved.get("error", "")))
		region_mgr.mark_clean()

	# The same button saves the content library, which is where a region's item
	# and NPC changes live. Report its failures with the same loudness.
	if database_mgr.has_unsaved_changes():
		var database := database_mgr.save_all()
		if not database.get("ok", true):
			_restore_dirty_data_state(had_region_changes, had_library_changes)
			return _report_failed_save(checkpoint, "Some content files could not be saved",
				"\n".join(database.get("errors", [])))

	# A file writing successfully is not an accepted authoring operation by itself:
	# it must still be a set the engine accepts.  Configuration drafts already stage
	# their own candidate through this verdict; this closes the equivalent gap for
	# ordinary region and library writes.  On refusal the checkpoint restores disk
	# while the in-memory edits stay marked dirty for correction or retry.
	# Headless manager tests and legacy callers can point DataRoot at a bare data
	# folder. That is not an authorable content set (and the UI's normal chooser
	# refuses it), so there is no engine manifest to validate. Real editor sets
	# always carry the manifest and therefore always take the fail-closed path.
	if (had_region_changes or had_library_changes) and FileAccess.file_exists(DataRoot.root().path_join("content_set.manifest.json")):
		var repo_root := ProjectSettings.globalize_path("res://").trim_suffix("/").get_base_dir()
		var verdict := EngineValidator.run(DataRoot.root(), repo_root, _find_python(repo_root))
		if not verdict.get("ran", false):
			_restore_dirty_data_state(had_region_changes, had_library_changes)
			return _report_failed_save(checkpoint, "Could not validate saved content", str(verdict.get("error", "The engine validator did not run.")))
		if not verdict.get("ok", false):
			_restore_dirty_data_state(had_region_changes, had_library_changes)
			return _report_failed_save(checkpoint, "Engine validation refused the saved content", _validation_error_summary(verdict))

	if not ui_mgr.save_configuration_drafts(): return false
	SaveCheckpoint.prune(DataRoot.root())
	if had_region_changes or had_library_changes:
		reference_index.clear()
	_update_explorer_dirty_state(); _update_db_ui()
	return true

## Restore the visible dirty state after `SaveCheckpoint` restores disk.  The
## values on screen are intentionally kept as the author's draft; hiding their
## dirty state here would make the next set switch discard them.
func _restore_dirty_data_state(had_region_changes: bool, had_library_changes: bool) -> void:
	if had_region_changes:
		region_mgr.mark_region_dirty()
	if had_library_changes:
		database_mgr.mark_all_dirty()

func _validation_error_summary(verdict: Dictionary) -> String:
	var lines: Array = []
	for issue in verdict.get("issues", []):
		if issue is Dictionary and str(issue.get("severity", "error")) == "error":
			var path := str(issue.get("path", ""))
			lines.append((path + ": " if path != "" else "") + str(issue.get("message", "Engine validation failed.")))
			if lines.size() >= 12:
				lines.append("… additional errors omitted; open Open Set Validation for the full report.")
				break
	return "\n".join(lines) if not lines.is_empty() else "The engine rejected this content. Open Set Validation for the full report."

## Report a failed save, after putting the set back the way it was.
##
## The message says which of the two happened, because "your set was restored"
## and "restoring it also failed" call for different next steps, and a silent
## half-written set is the state this checkpoint exists to prevent.
func _report_failed_save(checkpoint: Dictionary, title: String, message: String) -> bool:
	var note := ""
	if checkpoint.get("ok", false):
		var restored := SaveCheckpoint.restore(str(checkpoint.get("dir", "")), DataRoot.root())
		if restored.get("ok", false):
			note = "\n\nThe content set was put back as it was before this save (%d files). Your unsaved work is still open; fix the cause and save again." % int(restored.get("restored", 0))
		else:
			note = "\n\nThe content set could NOT be put back, so some files may be half-written: %s" % str(restored.get("error", ""))
	elif str(checkpoint.get("error", "")) != "":
		note = "\n\nNo checkpoint was taken, so the set may be partly written: %s" % str(checkpoint.get("error", ""))
	ui_mgr.show_error(title, message + note)
	_update_explorer_dirty_state(); _update_db_ui()
	return false

func _confirm_delete_db_entry(type: String, id: String):
	if not database_mgr.has_entry(type, id):
		return
	# Deleting a referenced identity has no repair path yet.  Refusing is more
	# honest than asking for confirmation and then knowingly leaving broken content;
	# use Rename to preserve indexed references, or remove the dependencies first.
	if not reference_index.loaded():
		var loaded := reference_index.load_for(DataRoot.data_dir())
		if not loaded.get("ok", false):
			ui_mgr.show_error("Delete blocked", "Reference check unavailable. No destructive edit is allowed until it can run:\n\n%s" % str(loaded.get("error", "unknown index error")))
			return
	var family := reference_index.family_for_type(type)
	var referrers: Array = reference_index.referrers_of(id, family) if family != "" else []
	if not referrers.is_empty():
		ui_mgr.show_error("Delete blocked", "'%s' is still named %d time(s). This editor does not yet offer a safe delete-and-repair operation. Rename it, or remove these dependencies first.\n\n%s" % [id, referrers.size(), reference_index.describe(id, type)])
		return
	ui_mgr.confirm(
		"Delete %s" % id,
		"Delete the %s '%s' from the content library?\n\n%s\n\nIts file is rewritten on the next save. Ctrl+Z will put it back until then." % [type, id, _referrers_note(type, id)],
		"Delete",
		func(): _delete_db_entry(type, id),
		"Cancel",
		DialogStyle.COLOR_DANGER,
	)

## What names this id, before it is deleted.
##
## The answer comes from `toolkit/reference_index.py` -- the reverse of the gate's
## reference sweep, sharing its families so the two cannot disagree about what a
## reference is. The index is run on first use and cached; a failure says so rather
## than quietly reading as "nothing refers to this".
func _referrers_note(type: String, id: String) -> String:
	if not reference_index.loaded():
		var loaded := reference_index.load_for(DataRoot.data_dir())
		if not loaded.get("ok", false):
			return "Reference check unavailable: %s" % str(loaded.get("error", "the index did not run."))
	return reference_index.describe(id, type)

func _delete_db_entry(type: String, id: String):
	var existing := database_mgr.entry(type, id)
	if existing.is_empty():
		return
	cmd_proc.commit(
		func():
			database_mgr.delete_entry(type, id)
			_update_db_ui(); inspector.clear_selection(),
		func():
			database_mgr.restore_entry(type, id, existing)
			_update_db_ui(); inspector.clear_selection(),
		"Delete %s '%s'" % [type, id],
	)

# --- renaming an entry ---------------------------------------------------------
#
# A rename is the one edit that can break content the author is not looking at: a
# recipe's result, a loot table key, a vendor line, a spawner weight. The index
# says where those are, so the confirmation can name them and the rename can
# repair the ones it can reach.

func _on_request_entry_rename(type: String, old_id: String, new_id: String):
	if not database_mgr.has_entry(type, old_id):
		return
	if database_mgr.has_entry(type, new_id):
		ui_mgr.confirm(
			"Rename %s" % old_id,
			"'%s' already exists in this content set. Nothing was changed." % new_id,
			"OK", func(): pass, "", DialogStyle.COLOR_DANGER,
		)
		return
	var plan := _rename_plan(type, old_id)
	if not (plan.get("blocked", []) as Array).is_empty():
		ui_mgr.show_error("Rename blocked", "Nothing was changed. The reference plan has paths that cannot be repaired safely:\n\n%s" % plan["summary"])
		return
	ui_mgr.confirm(
		"Rename %s to %s" % [old_id, new_id],
		"Rename the %s '%s' to '%s'?\n\n%s" % [type, old_id, new_id, plan["summary"]],
		"Rename",
		func(): _apply_entry_rename(type, old_id, new_id, plan),
		"Cancel",
	)

## What the index knows about this id, split by what a rename can do about it:
## the library caches, the region files, and anything that fails at apply time.
func _rename_plan(type: String, old_id: String) -> Dictionary:
	var plan := {"repairable": [], "region": [], "blocked": [], "summary": ""}
	if not reference_index.loaded():
		var loaded := reference_index.load_for(DataRoot.data_dir())
		if not loaded.get("ok", false):
			plan["summary"] = "Reference check unavailable: %s\n\nNothing can be checked, so nothing will be repaired." % str(loaded.get("error", "the index did not run."))
			return plan
	var family := reference_index.family_for_type(type)
	if family == "":
		plan["summary"] = "The reference index does not read %s entries yet, so no referrers can be checked or repaired." % type
		return plan
	for hit in reference_index.referrers_of(old_id, family):
		if str(hit["file"]).begins_with("regions/"):
			var region_check := region_mgr.can_patch_reference(hit["file"], hit["path"], old_id, "__preview__%s" % old_id)
			if region_check.get("ok", false):
				plan["region"].append(hit)
			else:
				plan["blocked"].append({"file": hit["file"], "path": hit["path"], "error": region_check.get("error", "could not preflight")})
		else:
			var library_check := database_mgr.can_patch_reference(hit["file"], hit["path"], old_id, "__preview__%s" % old_id)
			if library_check.get("ok", false):
				plan["repairable"].append(hit)
			else:
				plan["blocked"].append({"file": hit["file"], "path": hit["path"], "error": library_check.get("error", "could not preflight")})
	var lines: Array = []
	lines.append("Review before apply — the rename stays in the current draft until Save Changes validates the content set.")
	if not plan["blocked"].is_empty():
		lines.append("")
		lines.append("Cannot safely repair %d reference(s):" % plan["blocked"].size())
		for hit in plan["blocked"]:
			lines.append("  %s\n    %s\n    %s" % [hit["file"], hit["path"], hit["error"]])
	if plan["repairable"].is_empty() and plan["region"].is_empty():
		lines.append("Nothing in the indexed families names this id, so no other file needs to change.")
	else:
		if not plan["repairable"].is_empty():
			lines.append("%d reference(s) will be updated:" % plan["repairable"].size())
			for hit in plan["repairable"]:
				lines.append("  %s\n    %s" % [hit["file"], hit["path"]])
		if not plan["region"].is_empty():
			lines.append("%d reference(s) live in region files and will be updated there:" % plan["region"].size())
			for hit in plan["region"]:
				lines.append("  %s\n    %s" % [hit["file"], hit["path"]])
			lines.append("  (a region file that cannot be parsed is left alone and reported)")
	lines.append("")
	lines.append(reference_index.scope_note())
	plan["summary"] = "\n".join(lines)
	return plan

func _apply_entry_rename(type: String, old_id: String, new_id: String, plan: Dictionary):
	if not (plan.get("blocked", []) as Array).is_empty():
		ui_mgr.show_error("Rename blocked", "This rename was not applied because its preflight no longer permits every repair.")
		return
	var patched: Array = []
	var failures: Array = []
	for hit in plan["repairable"]:
		var result := database_mgr.patch_reference(hit["file"], hit["path"], old_id, new_id)
		if result.get("ok", false):
			patched.append({"file": hit["file"], "path": str(result.get("path_after", hit["path"]))})
		else:
			failures.append("%s\n    %s\n    %s" % [hit["file"], hit["path"], str(result.get("error", "could not be updated"))])
	for hit in plan["region"]:
		var result := region_mgr.patch_reference(hit["file"], hit["path"], old_id, new_id)
		if result.get("ok", false):
			patched.append({"file": hit["file"], "path": str(result.get("path_after", hit["path"]))})
		else:
			failures.append("%s\n    %s\n    %s" % [hit["file"], hit["path"], str(result.get("error", "could not be updated"))])

	cmd_proc.commit(
		func():
			database_mgr.rename_entry(type, old_id, new_id)
			_update_db_ui()
			inspector.load_db_object(type, new_id, database_mgr.entry(type, new_id))
			if not failures.is_empty():
				ui_mgr.confirm(
					"Rename partly applied",
					"Renamed to '%s'. These references could not be updated and still name '%s':\n\n%s" % [new_id, old_id, "\n".join(failures)],
					"OK", func(): pass, "", DialogStyle.COLOR_DANGER,
				),
		func():
			# Undo in reverse: the recorded `path_after` is the path the reference
			# now lives at, which differs from the original in key mode.
			for hit in patched:
				if str(hit["file"]).begins_with("regions/"):
					region_mgr.patch_reference(hit["file"], hit["path"], new_id, old_id)
				else:
					database_mgr.patch_reference(hit["file"], hit["path"], new_id, old_id)
			database_mgr.rename_entry(type, new_id, old_id)
			_update_db_ui()
			inspector.load_db_object(type, old_id, database_mgr.entry(type, old_id)),
		"Rename %s '%s' to '%s'" % [type, old_id, new_id],
	)

func _notification(what):
	if what == NOTIFICATION_WM_CLOSE_REQUEST:
		_request_quit()

# --- switching content set ----------------------------------------------------
# The editor can load any content set it is pointed at; this is the "pointed at"
# part, from inside the app. Switching reloads the world rather than restarting:
# every manager reads its content at load time, so the reload is the same sequence
# startup runs, minus the window.

func _request_switch_content_set(path: String):
	if path == "" or path == DataRoot.root():
		return
	if not _has_unsaved_work():
		_switch_content_set(path)
		return
	var save_then_switch := func():
		if _save_everything():
			_switch_content_set(path)
	ui_mgr.confirm(
		"Unsaved changes",
		"%s is not saved. Switching to %s will reload the world; save first, or leave the changes behind."
			% [DataRoot.root().get_file(), path.get_file()],
		"Save and switch",
		save_then_switch,
		"Keep editing",
	)
	# A second exit from the prompt: switching without saving is a real choice an
	# author makes, and refusing to offer it just means they save junk first.
	ui_mgr.set_confirm_extra_button("Switch without saving", func(): _switch_content_set(path))

func _switch_content_set(path: String):
	if not DataRoot.set_root(path):
		ui_mgr.show_error("Could not open %s" % path, "That directory is not there any more.")
		return

	# Remember it for the next launch, and say so if that failed: reopening the
	# previous world silently would look like the switch simply did not work.
	var written := DataRoot.write_settings(path)
	if not written.get("ok", false):
		ui_mgr.show_error("Could not remember this content set", str(written.get("error", "")))

	# Everything below this line refers to the set being left. Undo closures in
	# particular capture the *old* dictionaries, so they must go before the load
	# replaces them -- clearing them after a successful load (as this did) left
	# them armed when the new set's start region failed to load, where an undo
	# would push the previous world's data into this one.
	cmd_proc.clear_history()
	_reset_per_set_state()

	region_mgr.reset()
	view_states.clear()
	cached_hierarchy.clear()
	database_mgr.load_all()
	world_mgr.load_world_layout()
	ui_mgr.set_catalog(database_mgr.catalog)
	DisplayServer.window_set_title("MUD world editor — %s" % DataRoot.describe())

	_update_db_ui()
	_load_region_vocab_into_creator()
	var start_region := _start_region_filename()
	_load_region(start_region if start_region != "" else "")

## State that belongs to the content set being left, cleared on the way out.
##
## Each of these is keyed by, or holds, an id from one world: a tool armed with
## the previous set's stamp id draws that id into this set's rooms, a clipboard
## pastes a template that does not exist here, a cached search index answers with
## entries that are gone, and a library selection keeps an inspector writing into
## an orphaned dictionary while reporting this set's id as dirty.
func _reset_per_set_state():
	ui_mgr.discard_configuration_drafts()
	state.cur_tool_mode = EditorUIManager.ToolMode.SELECT
	state.cur_tool_data = {}
	editor_clipboard = []
	world_mgr.ignored_validation_warnings.clear()
	world_mgr.ignored_content_validation_warnings.clear()
	ui_mgr.clear_search_cache()
	ui_mgr.clear_library_selection()
	# The reference index describes the set that was open when it ran, so its
	# answer would be about the wrong world after a switch.
	reference_index.clear()

func _request_quit():
	if not _has_unsaved_work():
		get_tree().quit()
		return
	var what: Array = []
	if region_mgr.is_region_dirty: what.append(region_mgr.current_filename)
	if database_mgr.has_unsaved_changes(): what.append("the content library")
	if ui_mgr.has_configuration_drafts(): what.append("game configuration")
	ui_mgr.show_quit_prompt(
		"Unsaved changes in %s.\n\nSave before quitting, or leave the changes behind." % ", ".join(what)
	)

func _on_node_click(id: String, shift_mod: bool):
	if state.is_world_view: return

	# Connection mode first, before every tool: while the form is open, a click on
	# the map means "this is the far end of the connection" and nothing else. The
	# paint and stamp tools are checked below, so leaving this late would let a
	# click both pick a target AND paint a property onto it.
	if state.connection_mode or inspector.cur_mode == "connection":
		# A cross-region target (from a proxy node) carries "region:room"; a
		# same-region target is just the bare room id, since it's already in
		# whichever region is currently loaded.
		if ":" in id:
			var parts = id.split(":"); inspector.set_connection_target(parts[0], parts[1])
		else:
			inspector.set_connection_target(str(region_mgr.data.get("region_id", "")), id)
		return

	match state.cur_tool_mode:
		EditorUIManager.ToolMode.PAINT:
			var k = state.cur_tool_data.get("key", ""); var v = state.cur_tool_data.get("val", "")
			if k and region_mgr.data.rooms.has(id): 
				if not region_mgr.data.rooms[id].has("properties"): region_mgr.data.rooms[id]["properties"] = {}
				var val = v if not v in ["true", "false"] else v == "true"
				region_mgr.data.rooms[id]["properties"][k] = val; _on_data_modified()
			return
		EditorUIManager.ToolMode.STAMP:
			if state.cur_tool_data.get("type") == "room_template": return 
			if not region_mgr.data.rooms.has(id): return
			var t = state.cur_tool_data.get("type"); var cid = state.cur_tool_data.get("id")
			var key = "initial_npcs" if t == "npc" else "items"
			var data_key = "template_id" if t == "npc" else "item_id"
			if not region_mgr.data.rooms[id].has(key): region_mgr.data.rooms[id][key] = []
			region_mgr.data.rooms[id][key].append({data_key: cid}); _on_data_modified()
			return
	
	if state.dragging_conn.active and id != state.dragging_conn.src: return

	if shift_mod:
		if state.is_selected(id): state.remove_from_selection(id)
		else: state.add_to_selection(id)
	elif not state.is_selected(id):
		state.set_selection([id])
	
	_update_selection_state()

## Open the connection form and enter connection mode.
##
## One entry point for both ways in (the Link button and a drag from one room to
## another), so the mode cannot be set on one path and forgotten on the other.
func _open_connection_form(src_id: String, src_name: String, target_id: String = "", dir: String = ""):
	state.connection_mode = true
	inspector.load_connection_form(src_id, src_name, world_mgr.get_global_hierarchy(), region_mgr.current_filename, target_id, dir)
	graph_controller.queue_redraw()


## Leave connection mode and put the inspector back on the room it started from.
##
## Called when a connection is made, so the form closes and the map returns to its
## normal state rather than leaving the author in a half-finished dialog.
func _close_connection_mode(src_id: String = ""):
	state.connection_mode = false
	var back_to := src_id
	if back_to == "" and inspector.connection_editor != null:
		back_to = str(inspector.connection_editor.conn_src_id)
	if back_to != "" and region_mgr.data.rooms.has(back_to):
		inspector.load_room(back_to, region_mgr.data.rooms[back_to])
	else:
		inspector.clear_selection()
	graph_controller.queue_redraw()


func _on_connection_target_selected(target_id: String):
	state.highlighted_target_id = target_id
	if target_id != "" and inspector.connection_editor:
		state.connection_preview.active = true
		state.connection_preview.source_id = inspector.connection_editor.conn_src_id
		state.connection_preview.target_id = target_id
	else:
		state.connection_preview.active = false
		# Cleared target with no form left means the author cancelled: leave
		# connection mode so the map stops reading clicks as target picks.
		if inspector.cur_mode != "connection":
			state.connection_mode = false
	graph_controller.update_highlight_visuals(); graph_controller.queue_redraw()


## Re-shape how one exit is drawn. Editor-only state: it lives in
## `_editor_exit_layout`, which `EditorLayout.split_region` keeps out of the
## content files, so a bow choice never reaches the game.
##
## Committed through `cmd_proc` like every other edit, because which way a curve
## bows is a decision an author changes their mind about.
func _on_curve_change_requested(source_id: String, direction: String, curve_action: String):
	if not region_mgr.data.rooms.has(source_id):
		return
	var room: Dictionary = region_mgr.data.rooms[source_id]
	var before: Dictionary = {}
	if room.has("_editor_exit_layout"):
		before = (room["_editor_exit_layout"] as Dictionary).duplicate(true)

	var after := before.duplicate(true)
	var entry: Dictionary = {}
	if after.has(direction) and after[direction] is Dictionary:
		entry = (after[direction] as Dictionary).duplicate(true)

	if curve_action == "straight":
		# Clear back to the automatic side, dropping the entry when it holds
		# nothing else -- an empty override is state a save would carry for nothing.
		entry.erase("curve")
	elif curve_action == "amount_default":
		entry.erase("curve_amount")
	elif curve_action == "amount":
		# Cycle the three distances. The cycle returns to `normal` by returning an
		# empty string, because `normal` is what the renderer draws with no
		# override -- writing it as a key would be state that means nothing.
		var next_amount := RoomConnectionsPanel.next_curve_amount(
			str(entry.get("curve_amount", RoomConnectionsPanel.CURVE_AMOUNT_DEFAULT))
		)
		if next_amount == "":
			entry.erase("curve_amount")
		else:
			entry["curve_amount"] = next_amount
	else:
		# Cycle: automatic -> left -> right -> automatic. Cycling rather than
		# toggling means there is a way back to automatic without a modifier.
		match str(entry.get("curve", "")):
			"": entry["curve"] = "left"
			"left": entry["curve"] = "right"
			_: entry.erase("curve")

	if entry.is_empty(): after.erase(direction)
	else: after[direction] = entry

	cmd_proc.commit(
		func():
			if after.is_empty(): room.erase("_editor_exit_layout")
			else: room["_editor_exit_layout"] = after
			region_mgr.mark_room_dirty(source_id)
			_refresh_view()
			_update_explorer_dirty_state(),
		func():
			if before.is_empty(): room.erase("_editor_exit_layout")
			else: room["_editor_exit_layout"] = before
			region_mgr.mark_room_dirty(source_id)
			_refresh_view()
			_update_explorer_dirty_state(),
		"Curve Direction"
	)
	graph_controller.queue_redraw()


## Remove an exit, and by default the exit pointing back the other way.
##
## Reciprocity is the default because that is what an author means almost every
## time: connections are authored in pairs, and removing one end of a pair leaves
## a half-link that still draws on the map and still claims to lead somewhere.
## Removing a single end is the case that needs saying so, which is why the panel
## offers it as a separate, quieter button.
##
## Committed through `cmd_proc` so it undoes as one step: a delete that removed
## two ends but undid one would be worse than no undo at all.
func _on_delete_connection_requested(source_id: String, direction: String, target: String, also_reciprocal: bool):
	var forward_target := str(target)
	if ":" in forward_target:
		var parts := forward_target.split(":")
		if parts[0] == region_mgr.data.region_id:
			forward_target = parts[1]

	# The far end, when there is one and it is in this region. A cross-region
	# reciprocal lives in another file; deleting both ends there means editing a
	# region this view has not loaded, so it is left to the one-way removal.
	var back_dir := ""
	if also_reciprocal and not ":" in str(target) and region_mgr.data.rooms.has(forward_target):
		var target_exits: Dictionary = region_mgr.data.rooms[forward_target].get("exits", {})
		for other_dir in target_exits:
			if str(target_exits[other_dir]) == str(source_id) and str(other_dir) != str(direction):
				back_dir = str(other_dir)
				break

	var removed_forward := false
	cmd_proc.commit(
		func():
			region_mgr.remove_exit(source_id, direction)
			region_mgr.mark_room_dirty(source_id)
			removed_forward = true
			if back_dir != "":
				region_mgr.remove_exit(forward_target, back_dir)
				region_mgr.mark_room_dirty(forward_target)
			_refresh_view()
			_update_explorer_dirty_state(),
		func():
			if removed_forward:
				region_mgr.add_exit(source_id, direction, forward_target)
				region_mgr.mark_room_dirty(source_id)
			if back_dir != "":
				region_mgr.add_exit(forward_target, back_dir, source_id)
				region_mgr.mark_room_dirty(forward_target)
			_refresh_view()
			_update_explorer_dirty_state(),
		"Remove Connection" if back_dir == "" else "Remove Connection (both ways)"
	)
	# The panel renders from the room's own exits, so reload it. `_on_node_click`
	# is how every other edit refreshes the inspector, and it is safe here because
	# this room is already the one being inspected.
	_on_node_click(source_id, false)


func _on_world_region_selected(region_id: String):
	if not state.is_world_view: return
	state.set_selection([region_id])
	graph_controller.update_selection_visuals(state.selected_ids)
	var all_data = world_mgr.get_all_world_data()
	if all_data.has(region_id): inspector.load_region_root(all_data[region_id])
	graph_controller.queue_redraw()

func _update_selection_state():
	if state.district_preview.get("active", false):
		return
	state.district_preview = _empty_district_preview()
	graph_controller.update_selection_visuals(state.selected_ids)
	graph_controller.queue_redraw() # clears any stale district highlight from before this room selection
	if state.selected_ids.size() == 1:
		var id = state.selected_ids[0]
		
		if region_mgr.data.rooms.has(id):
			inspector.load_room(id, region_mgr.data.rooms[id]); ui_mgr.select_room_item(id)
		else: inspector.load_external_ref(id)
	elif state.selected_ids.size() > 1:
		inspector.load_multi_selection(state.selected_ids); ui_mgr.select_room_item("")
	else:
		_deselect_all(false)

func _jump_to_room(id):
	_on_node_click(id, false); camera_controller.focus_on(graph_controller.get_node_position(id), true)

# Finishes a connection dragged from a region's shape in the world view.
# Writing an exit always requires the source room's own region to be the
# one actually loaded (region_mgr.data), so this switches to it -- the
# same "load the region a cross-region link points at" step local view's
# own proxy-node jump already does -- and opens the same room+direction
# form a local-view drag opens, with the target region (if one was dropped
# on) and a direction guessed from the two regions' relative position on
# the world map pre-filled. Nothing here removes the ability to pick a
# different target region/room or direction; those are exactly what the
# form's own controls are for.
func _open_world_connection_form(src_region: String, src_room: String, target_region: String):
	var hierarchy := world_mgr.get_global_hierarchy()
	var src_filename: String = String(hierarchy.get(src_region, {}).get("filename", ""))
	if src_filename == "": return
	if region_mgr.current_filename != src_filename:
		_load_region(src_filename, false, true)
	if not region_mgr.data.rooms.has(src_room): return
	var src_name := str(region_mgr.data.rooms[src_room].get("name", src_room))

	var target_hint := ""
	var guessed_dir := ""
	if target_region != "":
		target_hint = target_region + ":"
		var src_node = graph_controller.world_view_builder.world_region_nodes.get(src_region)
		var tgt_node = graph_controller.world_view_builder.world_region_nodes.get(target_region)
		if src_node and tgt_node:
			guessed_dir = _guess_world_direction(src_node.global_position, tgt_node.global_position)

	inspector.load_connection_form(src_room, src_name, hierarchy, region_mgr.current_filename, target_hint, guessed_dir)

# The compass direction whose vector best matches the line from one
# region's world-map position to another's -- an authoring default, not a
# claim about the actual room-level geometry, which the target picker and
# direction field in the form that follows remain free to override.
func _guess_world_direction(from_pos: Vector2, to_pos: Vector2) -> String:
	var delta := to_pos - from_pos
	if delta.length() < 1.0: return ""
	var best_dir := ""
	var best_dot := -INF
	for dir_name in ["north", "northeast", "east", "southeast", "south", "southwest", "west", "northwest"]:
		var vec: Vector2 = Constants.DIR_VECTORS[dir_name]
		var dot: float = delta.normalized().dot(vec.normalized())
		if dot > best_dot:
			best_dot = dot
			best_dir = dir_name
	return best_dir

func _refresh_view():
	graph_controller.rebuild(region_mgr.data, world_mgr.get_all_world_data(), world_mgr.world_node_positions, region_mgr.current_filename)

func _set_world_view(enabled: bool):
	var cache_key = "world_view" if state.is_world_view else region_mgr.current_filename
	if cache_key != "": view_states[cache_key] = {"pos": main_camera.position, "zoom": main_camera.zoom}
	
	state.is_world_view = enabled
	state.creating_conn = { "active": false }; state.dragging_conn = { "active": false }
	_deselect_all()
	grid_layer.visible = state.snap_enabled and not state.is_world_view
	_refresh_view()
	
	if enabled:
		_show_world_overview()
		var all_data = world_mgr.get_all_world_data()
		var total_rooms := 0
		for r_data in all_data.values(): total_rooms += r_data.get("rooms", {}).size()
		ui_mgr.update_status_info("World Map", total_rooms, "%d Regions" % all_data.size())

		if view_states.has("world_view"):
			var vs = view_states["world_view"]; main_camera.position = vs.pos; main_camera.zoom = vs.zoom
		else: main_camera.zoom = Vector2.ONE; camera_controller.center_on_nodes(graph_controller.get_active_nodes())
	elif view_states.has(region_mgr.current_filename):
		# Re-calculate and display region info when switching back
		var rooms = region_mgr.data.get("rooms", {})
		var exit_count = 0
		for r in rooms.values():
			exit_count += r.get("exits", {}).size()
		ui_mgr.update_status_info(region_mgr.data.get("name", region_mgr.current_filename), rooms.size(), "", exit_count)
		
		var vs = view_states[region_mgr.current_filename]; main_camera.position = vs.pos; main_camera.zoom = vs.zoom

func _on_request_layout():
	if state.is_world_view:
		var all_data = world_mgr.get_all_world_data()
		var old_positions = world_mgr.world_node_positions.duplicate()
		var new_positions = LayoutOptimizer.optimize_world_layout(all_data)
		cmd_proc.commit(
			func():
				for rid in new_positions: world_mgr.update_world_node_pos(rid, new_positions[rid])
				_refresh_view(),
			func():
				world_mgr.world_node_positions = old_positions; _refresh_view(),
			"Auto-Arrange World Map"
		)
	else:
		var old_pos = {}; for id in region_mgr.data.rooms: old_pos[id] = Vector2(region_mgr.data.rooms[id]._editor_pos[0], region_mgr.data.rooms[id]._editor_pos[1])
		var new_pos = LayoutOptimizer.optimize_layout(region_mgr.data.rooms)
		var old_exit_layout := {}
		for id in region_mgr.data.rooms:
			if region_mgr.data.rooms[id].has("_editor_exit_layout"):
				old_exit_layout[id] = region_mgr.data.rooms[id]["_editor_exit_layout"].duplicate(true)
		var new_exit_layout = LayoutOptimizer.infer_exit_layout_metadata(region_mgr.data.rooms, new_pos)
		cmd_proc.commit(
			func():
				for id in new_pos: region_mgr.set_room_pos(id, new_pos[id])
				for id in region_mgr.data.rooms:
					if new_exit_layout.has(id):
						region_mgr.data.rooms[id]["_editor_exit_layout"] = new_exit_layout[id]
					elif region_mgr.data.rooms[id].has("_editor_exit_layout"):
						region_mgr.data.rooms[id].erase("_editor_exit_layout")
				for id in new_pos: region_mgr.mark_room_dirty(id)
				_refresh_view(); camera_controller.center_on_nodes(graph_controller.get_active_nodes()); _update_explorer_dirty_state(),
			func():
				for id in old_pos: region_mgr.set_room_pos(id, old_pos[id])
				for id in region_mgr.data.rooms:
					if old_exit_layout.has(id):
						region_mgr.data.rooms[id]["_editor_exit_layout"] = old_exit_layout[id]
					elif region_mgr.data.rooms[id].has("_editor_exit_layout"):
						region_mgr.data.rooms[id].erase("_editor_exit_layout")
				for id in old_pos: region_mgr.mark_room_dirty(id)
				_refresh_view(); camera_controller.center_on_nodes(graph_controller.get_active_nodes()); _update_explorer_dirty_state(),
			"Auto-Arrange Layout"
		)

func _deselect_all(_hide_ui: bool = true):
	state.clear_selection()
	graph_controller.update_selection_visuals([])
	# There's always something useful to show on the right: the region (or
	# world map) nothing-selected still belongs to, not a blank panel or an
	# unhelpful "Arrangement Mode" placeholder.
	if state.is_world_view: _show_world_overview()
	else: inspector.load_region_root(region_mgr.data)
	# A district highlight lives on district_layer's own _draw(), unlike a
	# room's selection border (a StyleBoxFlat that redraws itself on
	# change) -- clearing the selection needs an explicit redraw to make
	# that highlight actually disappear.
	graph_controller.queue_redraw()

func _show_world_overview():
	var all_data = world_mgr.get_all_world_data()
	var total_rooms := 0
	for r_data in all_data.values(): total_rooms += r_data.get("rooms", {}).size()
	inspector.load_world_mode(all_data.size(), total_rooms)

func _deselect_room_only():
	state.clear_selection(); graph_controller.update_selection_visuals([]); graph_controller.queue_redraw()

# A click that missed every room node. In the local view, that empty space
# still might be inside a district's territory -- select the district
# itself rather than treating it as a plain deselect.
func _on_empty_click(mouse_pos: Vector2):
	if not state.is_world_view:
		var district_id := graph_controller.get_district_id_at(mouse_pos)
		if district_id != "":
			_select_district(district_id)
			return
	_deselect_all()

func _select_district(district_id: String):
	state.set_district_selection(district_id)
	graph_controller.update_selection_visuals([])
	graph_controller.queue_redraw()
	inspector.load_district(district_id, region_mgr.data)

func _district_member_ids(district_id: String) -> Array:
	return region_mgr.data.get("properties", {}).get("districts", {}).get(district_id, {}).get("members", [])

# Committing a whole-district drag as one undoable step, the same
# do/undo-closure pattern Auto-Arrange Layout already uses for a batch of
# room moves -- so Ctrl+Z reverts every member room in one step, not one
# per room.
func _commit_district_move(start_positions: Dictionary, delta: Vector2):
	var new_positions := {}
	for room_id in start_positions: new_positions[room_id] = start_positions[room_id] + delta
	cmd_proc.commit(
		func():
			for id in new_positions: region_mgr.set_room_pos(id, new_positions[id])
			_refresh_view(),
		func():
			for id in start_positions: region_mgr.set_room_pos(id, start_positions[id])
			_refresh_view(),
		"Move District"
	)

func _on_data_modified():
	if not state.is_world_view:
		region_mgr.mark_region_dirty()
		for id in state.selected_ids:
			region_mgr.mark_room_dirty(id)
			graph_controller.update_specific_node(id, region_mgr.data)
		_update_explorer_dirty_state()
	graph_controller.queue_redraw()

func _update_explorer_dirty_state():
	if cached_hierarchy.is_empty():
		cached_hierarchy = world_mgr.get_global_hierarchy()
	
	if region_mgr.data.has("region_id"):
		var rid = region_mgr.data.region_id
		var live_rooms = {}
		for r_id in region_mgr.data.rooms:
			live_rooms[r_id] = region_mgr.data.rooms[r_id].get("name", "Unnamed")
		
		cached_hierarchy[rid] = {
			"filename": region_mgr.current_filename,
			"rooms": live_rooms,
			"districts": region_mgr.data.get("properties", {}).get("districts", {})
		}

	var selected = state.selected_ids[0] if not state.selected_ids.is_empty() else ""
	ui_mgr.refresh_explorer(cached_hierarchy, region_mgr.current_filename, selected)
	ui_mgr.update_dirty_visuals(region_mgr.current_filename, region_mgr.is_region_dirty, region_mgr.dirty_room_ids)
	inspector.set_region_dirty(region_mgr.is_region_dirty)
