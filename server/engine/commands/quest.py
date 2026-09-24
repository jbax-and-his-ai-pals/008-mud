# engine/commands/quest.py
import uuid
from engine.commands.command_system import command, registered_commands
from engine.config import FORMAT_SUCCESS, FORMAT_ERROR, FORMAT_RESET, FORMAT_HIGHLIGHT, FORMAT_CATEGORY, FORMAT_TITLE, QUEST_BOARD_ALIASES
from engine.core.quests.packages import declared_packages
from engine.items.item_factory import ItemFactory
from engine.player import Player
from engine.world import world
from engine.social.relationships import relationship_key
from engine.presentation import is_player_mode, show_internals


def _getting_started_block(world) -> str:
    """A persistent, always-available orientation reminder.

    Reuses the same opening-guidance text shown once at character creation
    (HeadlessServer.build_opening_guidance) so a player who skims past it or
    returns after a break can pull it back up via `journal` instead of it
    being gone for good.
    """
    server = getattr(world, "server", None)
    if server is None or not hasattr(server, "build_opening_guidance"):
        return ""
    guidance = server.build_opening_guidance()
    if not guidance:
        return ""
    return f"{FORMAT_TITLE}Getting Started{FORMAT_RESET}\n{'-'*20}\n\n{guidance}"


def _optional(value) -> str:
    """Normalize an optional authored field for display.

    The journal used to render missing optional objective fields as a literal
    `?` (e.g. `... in ?.`), because the f-strings defaulted straight to "?".
    A player has no way to read that, and for `deliver` objectives it appeared
    on the very first quest a new player accepts. Missing detail is now simply
    omitted; callers only add the clause when this returns something.
    """
    return str(value).strip() if value is not None else ""


def _stage_instruction(quest_data, stage_index) -> str:
    """The authored, player-facing instruction for the quest's current stage.

    `quests.json` authors this per stage ("Gather herbs, craft a wildflower
    posy, and deliver it to Elder Thorne."), and it is the text a player
    actually needs. It was previously only shown by the generic fallback
    branch, so typed objectives -- kill, fetch, deliver -- all rendered a
    degraded templated line instead and the authored prose was never seen.
    """
    stages = quest_data.get("stages") or []
    try:
        index = int(stage_index)
    except (TypeError, ValueError):
        return ""
    if 0 <= index < len(stages):
        return _optional(stages[index].get("description"))
    return ""


def _deliver_item_display_name(world, objective) -> str:
    """Name a deliver objective's item without falling back to a bare,
    tautological noun ("the item") or a raw internal template id."""
    authored_name = str(objective.get("item_to_deliver_name", "")).strip()
    if authored_name:
        return authored_name
    template_id = str(objective.get("item_template_id", "")).strip()
    if template_id:
        template = ItemFactory.get_template(template_id, world)
        if template:
            name = str(template.get("name", "")).strip()
            if name:
                return name
    return "the item"

def _relationship_requirement(quest_data):
    """Return a safe relationship gate for a board quest instance."""
    try:
        return max(0, int(quest_data.get("relationship_min", 0)))
    except (TypeError, ValueError):
        return 0

def _resolve_relationship_npc(world, relationship_npc_id: str):
    """A board quest's `relationship_npc_id` is set from `giver_template_id`
    (see QuestManager._add_authored_board_quests), a template id -- not a
    live NPC's actual instance id, which `world.get_npc` looks up by. Fall
    back to a template_id scan (the same pattern quest reward application
    already uses) so board quests can still name the real giver NPC."""
    npc = world.get_npc(relationship_npc_id)
    if npc is not None:
        return npc
    return next(
        (candidate for candidate in world.npcs.values() if getattr(candidate, "template_id", None) == relationship_npc_id),
        None,
    )

# Need to import handle_accept_offer
from engine.commands.interaction.npcs import handle_accept_offer

def _is_player_at_quest_board(player: Player, quest_manager) -> bool:
    """Checks if the player's current location is one of the valid quest board locations."""
    board_locations = quest_manager.config.get("quest_board_locations", [])
    player_location_str = f"{player.current_region_id}:{player.current_room_id}"
    return player_location_str in board_locations

def _board_availability(world, player, quest_data):
    """Whether a board entry is offered, and the trust figures behind it.

    Returns (available, current_trust, required_trust). A quest with no
    relationship gate is always available.
    """
    relationship_required = _relationship_requirement(quest_data)
    if not relationship_required:
        return True, 0, 0
    relationship_npc_id = str(
        quest_data.get("relationship_npc_id", quest_data.get("giver_instance_id", ""))
    )
    giver = _resolve_relationship_npc(world, relationship_npc_id)
    bond_key = relationship_key(giver) if giver is not None else relationship_npc_id
    current = int(getattr(player, "npc_relationships", {}).get(bond_key, 0))
    return current >= relationship_required, current, relationship_required


def _board_fingerprint(world) -> str:
    """A cheap identity for the current board contents.

    Used to detect that the board changed between `look board` and
    `accept quest <n>`, so a stored display mapping is never applied to a
    different list.
    """
    return "|".join(str(q.get("instance_id", "")) for q in world.quest_board)


def _store_board_mapping(world, session_id, mapping):
    """Remember displayed-number -> board-index for this viewer.

    Stored per session rather than per world: two players looking at the same
    board may legitimately see different tasks.
    """
    if not session_id:
        return
    store = getattr(world, "_board_display_maps", None)
    if not isinstance(store, dict):
        store = {}
        world._board_display_maps = store
    store[session_id] = {"fingerprint": _board_fingerprint(world), "map": dict(mapping)}


def _shown_on_board(world, player, quest_manager, quest_data, player_mode) -> bool:
    """Whether `look board` lists this notice for this player (and so gives it
    a number): the notice is currently offered, and in player mode its giver
    already trusts them."""
    board_available, _notice = quest_manager.authored_board_entry_available(player, quest_data)
    if not board_available:
        return False
    available, _current, _required = _board_availability(world, player, quest_data)
    return available or not player_mode


def _visible_board_mapping(world, player, quest_manager, player_mode) -> dict:
    """Displayed number -> board index, as `look board` would number it now."""
    mapping = {}
    for index, quest_data in enumerate(world.quest_board):
        if _shown_on_board(world, player, quest_manager, quest_data, player_mode):
            mapping[len(mapping) + 1] = index
    return mapping


def _resolve_board_index(world, session_id, displayed_number):
    """Map a displayed board number to a board list index.

    In test mode the mapping is the identity and this is unnecessary, but it is
    still consulted so both modes follow one code path. Returns None when the
    board has changed since it was displayed, so the caller can fall back.
    """
    store = getattr(world, "_board_display_maps", None)
    if not isinstance(store, dict) or not session_id:
        return None
    entry = store.get(session_id)
    if not isinstance(entry, dict):
        return None
    if entry.get("fingerprint") != _board_fingerprint(world):
        return None
    mapping = entry.get("map")
    if not isinstance(mapping, dict):
        return None
    return mapping.get(displayed_number)


@command(name="look board", aliases=QUEST_BOARD_ALIASES, category="interaction", help_text="Look at the quest board for available tasks.", content_capability="quests")
def look_board_handler(args, context):
    world = context["world"]
    player = context.get('player')
    quest_manager = world.quest_manager

    if not _is_player_at_quest_board(player, quest_manager):
        return f"{FORMAT_ERROR}You don't see a {world.quest_board_name().lower()} here.{FORMAT_RESET}"

    # A repeatable notice reappears only after its authored, hidden delay.
    # Looking at the board is the natural point to check that narrow condition;
    # unlike a general refill, it never turns an intentionally empty board into
    # a pile of newly generated work.
    quest_manager.refresh_repeatable_board_tasks(player)
    available_quests = world.quest_board

    board_name = world.quest_board_name()
    if not available_quests:
        notices = quest_manager.authored_board_unavailable_notices(player)
        if notices:
            return f"{board_name}\n" + "\n".join(notices)
        return f"The {board_name.lower()} is currently empty."

    # In player mode a task whose giver does not trust you yet is simply not
    # offered -- the world gets richer as you earn it, rather than presenting a
    # menu of things you are not allowed to have.
    player_mode = is_player_mode(context)

    response = f"{FORMAT_TITLE}{board_name}{FORMAT_RESET}\n" + "-"*20 + "\nAvailable Tasks:\n\n"
    display_map = {}
    displayed = 0
    unavailable_notices = []
    for i, quest_data in enumerate(available_quests):
        giver_instance_id = quest_data.get("giver_instance_id")
        rewards = quest_data.get("rewards", {})

        board_available, unavailable_notice = quest_manager.authored_board_entry_available(player, quest_data)
        if not board_available and unavailable_notice and unavailable_notice not in unavailable_notices:
            unavailable_notices.append(unavailable_notice)
        if not _shown_on_board(world, player, quest_manager, quest_data, player_mode):
            continue
        available, current_trust, required_trust = _board_availability(world, player, quest_data)

        giver_name = f"{board_name} Notice"
        if giver_instance_id != "quest_board":
            giver_npc = world.get_npc(giver_instance_id) 
            giver_name = giver_npc.name if giver_npc else "Unknown"

        # Use helper for safety
        objective = quest_manager.get_active_objective(quest_data) or {}
        quest_type = objective.get("type", "unknown")
        
        quantity_summary = ""
        if quest_type in ["kill", "fetch"]:
            quantity = objective.get("required_quantity")
            if quantity:
                quantity_summary = f" ({quantity})"
        
        reward_parts = []
        if world.uses_progression():
            reward_parts.append(f"{rewards.get('xp', 0)} XP")
        if world.ruleset_system_enabled("economy"):
            reward_parts.append(f"{rewards.get('gold', 0)} {world.currency_name().capitalize()}")
        reward_summary = ", ".join(reward_parts) if reward_parts else "—"

        # Trust progress is engine internals; players only see it in test mode.
        trust_summary = ""
        if required_trust and not player_mode:
            trust_summary = f"   Trust: {current_trust}/{required_trust}"
            if not available:
                trust_summary += " (locked)"

        displayed += 1
        display_map[displayed] = i
        response += (f"{FORMAT_CATEGORY}[{displayed}]{FORMAT_RESET} {quest_data.get('title', 'Unnamed Quest')}{FORMAT_HIGHLIGHT}{quantity_summary}{FORMAT_RESET}\n"
                    f"   Giver: {giver_name}\n"
                    f"   Reward: {reward_summary}\n{trust_summary}\n\n")

    # A resting repeatable task is normally absent from the shared board, so
    # it never passes through the per-notice loop above. Keep its authored
    # explanation visible even when procedural work remains available.
    for notice in quest_manager.authored_board_unavailable_notices(player):
        if notice not in unavailable_notices:
            unavailable_notices.append(notice)

    if displayed == 0:
        # Everything posted is gated. Say so in the world's voice, without
        # naming thresholds the player has no way to act on.
        if unavailable_notices:
            return f"{board_name}\n" + "\n".join(unavailable_notices)
        return f"The {board_name.lower()} has nothing for you just now."

    _store_board_mapping(world, context.get("session_id"), display_map)
    if unavailable_notices:
        response += "\n" + "\n".join(unavailable_notices) + "\n"
    response += f"Type '{FORMAT_HIGHLIGHT}accept quest <#>{FORMAT_RESET}' to take a task."
    return response

@command(name="accept quest", aliases=["accept"], category="interaction", help_text="Accept a quest from the board or an offer from an NPC.\nUsage: accept <# | topic>", content_capability="quests")
def accept_quest_handler(args, context):
    """
    Handles accepting quests.
    1. If args are numeric (e.g. "accept 1"), it interacts with the Quest Board.
    2. If args are text (e.g. "accept mission"), it delegates to NPC dialogue.
    """
    world = context["world"]
    player = context.get('player')
    quest_manager = world.quest_manager

    # --- 1. DETERMINE TARGET (Board vs NPC) ---
    is_numeric = False
    quest_index = -1
    
    if args:
        # Check for "quest 1" or just "1"
        target_arg = args[0]
        if target_arg.lower() == "quest" and len(args) > 1:
            target_arg = args[1]
        
        if target_arg.isdigit():
            is_numeric = True
            quest_index = int(target_arg) - 1

    # --- 2. NPC CONVERSATION FALLBACK ---
    # If not a number, or if we aren't at a board, try to accept offer from NPC
    at_board = _is_player_at_quest_board(player, quest_manager)
    
    if not is_numeric or not at_board:
        # Call the dedicated handler for NPC offers
        return handle_accept_offer(args, context)

    # --- 3. QUEST BOARD LOGIC ---
    # Translate the number the player saw into a board index. In player mode
    # gated tasks are not displayed, so the visible numbering is contiguous and
    # differs from the underlying list order. In test mode the mapping is the
    # identity, but it is consulted either way so both modes share one path.
    mapped_index = _resolve_board_index(world, context.get("session_id"), quest_index + 1)
    if mapped_index is None:
        # Nothing displayed yet, or the board changed since: number it the way
        # `look board` would for this player now. Falling back to the raw list
        # counted the notices a player-mode board hides, so "accept quest 4"
        # before looking took a different, trust-gated notice.
        mapped_index = _visible_board_mapping(world, player, quest_manager, is_player_mode(context)).get(quest_index + 1, -1)
    quest_index = mapped_index

    if quest_index < 0 or quest_index >= len(world.quest_board):
        return f"{FORMAT_ERROR}Invalid quest number.{FORMAT_RESET}"

    quest_to_accept = world.quest_board[quest_index]
    board_available, unavailable_notice = quest_manager.authored_board_entry_available(player, quest_to_accept)
    if not board_available:
        message = unavailable_notice or "That notice is no longer available."
        return f"{FORMAT_ERROR}{message}{FORMAT_RESET}"
    quest_to_accept = world.quest_board.pop(quest_index)
    relationship_required = _relationship_requirement(quest_to_accept)
    relationship_npc_id = str(quest_to_accept.get("relationship_npc_id", quest_to_accept.get("giver_instance_id", "")))
    if relationship_required:
        giver = _resolve_relationship_npc(world, relationship_npc_id)
        bond_key = relationship_key(giver) if giver is not None else relationship_npc_id
        current_relationship = int(getattr(player, "npc_relationships", {}).get(bond_key, 0))
        if current_relationship < relationship_required:
            world.quest_board.insert(quest_index, quest_to_accept)
            giver_name = giver.name if giver is not None else "whoever posted this"
            if is_player_mode(context):
                # A giver speaks for themselves; relationship thresholds are
                # engine internals a player cannot act on directly.
                return (
                    f"{FORMAT_ERROR}{giver_name} isn't ready to trust you with that yet."
                    f"{FORMAT_RESET}"
                )
            return f"{FORMAT_ERROR}{giver_name} doesn't trust you enough yet ({current_relationship}/{relationship_required} relationship).{FORMAT_RESET}"
    quest_to_accept["state"] = "active"
    quest_instance_id = quest_to_accept.get("instance_id")

    # --- INSTANCE QUEST HANDLING ---
    meta_data = quest_to_accept.get("meta_instance_data")
    acceptance_message = ""
    
    if meta_data:
        # Flatten for the manager call
        quest_to_accept.update(meta_data)
        quest_to_accept["completion_check_enabled"] = False
        
        success, message, giver_npc_id = world.instantiate_quest_region(quest_to_accept, requesting_player=player)
        
        if not success:
            world.quest_board.insert(quest_index, quest_to_accept)
            return f"{FORMAT_ERROR}Could not start quest: {message}{FORMAT_RESET}"
            
        # Update Giver info if dynamically spawned
        if giver_npc_id:
            # Update stage 0 turn-in to the specific giver instance
            quest_to_accept["stages"][0]["turn_in_id"] = giver_npc_id
            quest_to_accept["giver_instance_id"] = giver_npc_id
            
            giver_npc = world.get_npc(giver_npc_id)
            if giver_npc:
                 entry_point = meta_data.get("entry_point", {})
                 entry_region = world.get_region(entry_point.get("region_id"))
                 entry_room = entry_region.get_room(entry_point.get("room_id")) if entry_region else None
                 location_desc = entry_room.name if entry_room else "a nearby house"
                 
                 extended = giver_npc.dialog.get("greeting_extended", "").format(entry_location_desc=location_desc)
                 message += f" \"{extended}\""
        
        acceptance_message = f"{FORMAT_SUCCESS}[Quest Accepted] {quest_to_accept.get('title')}{FORMAT_RESET}\n{FORMAT_HIGHLIGHT}{message}{FORMAT_RESET}"

    # --- STANDARD QUEST HANDLING ---
    else:
        # A delivery hands over what is being delivered. One rule for one
        # delivery and for a courier run to several recipients, so a multi-stop
        # quest is startable by a real player instead of asking them to conjure
        # the goods (see engine/core/quests/packages.py).
        objective = quest_manager.get_active_objective(quest_to_accept)
        packages, package_problem = declared_packages(world, objective)
        if package_problem:
            world.quest_board.insert(quest_index, quest_to_accept)
            return f"{FORMAT_ERROR}{package_problem}{FORMAT_RESET}"
        acceptance_message = f"{FORMAT_SUCCESS}[Quest Accepted] {quest_to_accept.get('title')}{FORMAT_RESET}"
        if packages:
            handed_over = []
            for package in packages:
                can, msg = player.inventory.can_add_item(package)
                if not can:
                    # Give back anything already handed over: a refused job must
                    # not leave the player carrying half of it.
                    if handed_over:
                        player.inventory.remove_item_instances(handed_over)
                    world.quest_board.insert(quest_index, quest_to_accept)
                    return f"{FORMAT_ERROR}Inventory full: {msg}{FORMAT_RESET}"
                player.inventory.add_item(package)
                handed_over.append(package)
            note = "(You received the package)" if len(packages) == 1 else "(You received the packages)"
            acceptance_message += f"\n{note}"

    player.runtime_state.quests.active[quest_instance_id] = quest_to_accept
    quest_manager.replenish_board(None, player)
    return acceptance_message + "\n(Check your 'journal' for details)"

@command(name="journal", aliases=["quests", "log", "j"], category="information",
         help_text="View your active or completed quests.\nUsage: journal [completed]", content_capability="quests")
def journal_handler(args, context):
    player = context.get("player")
    if not player:
        return "Player not found."
    active_quests = player.runtime_state.quests.active
    completed_quests = player.runtime_state.quests.completed

    if args and args[0].lower() == "completed":
        all_completed_quests = {**player.runtime_state.quests.completed, **player.runtime_state.quests.archived}
        if not all_completed_quests:
            return "You have not completed any quests yet."
        
        response = f"{FORMAT_TITLE}Completed Quests ({len(all_completed_quests)}){FORMAT_RESET}\n{'-'*20}\n\n"
        sorted_completed = sorted(all_completed_quests.values(), key=lambda q: q.get("title", ""))
        
        for quest_data in sorted_completed:
            response += f"- {quest_data.get('title', 'Unnamed Quest')}\n"
        return response.strip()

    if not active_quests:
        return _getting_started_block(context["world"]) or "Your quest journal is empty."

    response = f"{FORMAT_TITLE}Active Quests{FORMAT_RESET}\n{'-'*20}\n\n"
    found_active = False
    sorted_active = sorted(active_quests.values(), key=lambda q: q.get("title", ""))
    
    for quest_data in sorted_active:
         if quest_data.get("state") in ["active", "ready_to_complete"]:
             found_active = True
             
             # Use manager helper
             objective = context["world"].quest_manager.get_active_objective(quest_data) or {}
             obj_type = objective.get("type", "unknown")
             
             title = quest_data.get("title", "Unnamed Quest")
             
             # Resolve Giver / Turn-In
             stages = quest_data.get("stages", [])
             idx = quest_data.get("current_stage_index", 0)
             turn_in_target = quest_data.get("giver_instance_id")
             if stages and idx < len(stages):
                 stage_target = stages[idx].get("turn_in_id")
                 if stage_target: turn_in_target = stage_target
             
             giver_npc = context["world"].get_npc(turn_in_target)
             if giver_npc is None and turn_in_target:
                 giver_npc = next(
                     (
                         npc for npc in context["world"].npcs.values()
                         if getattr(npc, "template_id", None) == turn_in_target
                     ),
                     None,
                 )
             giver_name = giver_npc.name if giver_npc else "Unknown"
             if turn_in_target == "quest_board": giver_name = context["world"].quest_board_name()
             
             destination_label = "Report to"
             destination_name = giver_name
             if obj_type == "deliver":
                 destination_label = "Deliver to"
                 destination_name = str(objective.get("recipient_name", "")).strip() or "Unknown"
             response += f"{FORMAT_CATEGORY}{title}{FORMAT_RESET} ({destination_label}: {destination_name})\n"
             state_display = quest_data.get("state", "unknown").replace('_', ' ').capitalize(); response += f"  Status: {state_display}\n"
             routes = context["world"].quest_manager.get_active_objectives(quest_data)
             if len(routes) > 1:
                 response += "  Choose one route:\n"
                 for route in routes:
                     if route.get("type") == "deliver":
                         response += f"    - Deliver {_deliver_item_display_name(context['world'], route)} to {route.get('recipient_name', 'the recipient')}.\n"
                     else:
                         response += f"    - {route.get('description', 'Complete this route.')}\n"
             
             if obj_type == "kill":
                 # Authored kill objectives name the target in the singular
                 # ("an elite troll", "the Bandit King"); procedural ones only
                 # have a plural template name. Prefer whichever reads properly:
                 # a one-off named target should not be described as "1 targets".
                 target_plural = _optional(objective.get("target_name_plural"))
                 target_singular = _optional(objective.get("target_name"))
                 required = objective.get("required_quantity")
                 try:
                     required_int = int(required) if required not in (None, "") else None
                 except (TypeError, ValueError):
                     required_int = None

                 if target_singular and (required_int is None or required_int <= 1):
                     task = f"  Task: Defeat {target_singular}"
                 else:
                     target_label = target_plural or target_singular or "your targets"
                     progress = ""
                     if required_int is not None:
                         progress = f"{objective.get('current_quantity', 0)}/{required_int} "
                     task = f"  Task: Defeat {progress}{target_label}"
                 location = _optional(objective.get("location_hint"))
                 if location:
                     task += f" in {location}"
                 response += task + ".\n"
             
             elif obj_type == "group_kill":
                 response += f"  Task: Hunt the following targets:\n"
                 targets = objective.get("targets", {})
                 for tid, t_data in targets.items():
                     t_name = t_data.get("name", "Enemies")
                     req = t_data.get("required", 1)
                     cur = t_data.get("current", 0)
                     status_col = FORMAT_SUCCESS if cur >= req else FORMAT_RESET
                     response += f"    - {status_col}{t_name}: {cur}/{req}{FORMAT_RESET}\n"

             elif obj_type == "fetch":
                  required_item_id = objective.get("item_id", ""); current_have = player.inventory.count_item(required_item_id)
                  item_plural = _optional(objective.get("item_name_plural")) or "the required items"
                  required = objective.get("required_quantity")
                  progress = f"{current_have}/{required} " if required not in (None, "") else f"{current_have} "
                  task = f"  Task: Gather {progress}{item_plural}"
                  source = _optional(objective.get("source_enemy_name_plural"))
                  if source:
                      task += f" (from {source})"
                  location = _optional(objective.get("location_hint"))
                  if location:
                      task += f" in {location}"
                  response += task + ".\n"
             
             elif obj_type == "deliver":
                  package_instance_id = objective.get("item_instance_id", ""); has_package = player.inventory.find_item_by_id(package_instance_id) is not None
                  package_status = f"{FORMAT_HIGHLIGHT}(You have the package){FORMAT_RESET}" if has_package else f"{FORMAT_ERROR}(You don't have the package!){FORMAT_RESET}"
                  recipient = _optional(objective.get("recipient_name")) or "the recipient"
                  task = f"  Task: Deliver {_deliver_item_display_name(context['world'], objective)} to {recipient}"
                  location = _optional(objective.get("recipient_location_description"))
                  if location:
                      task += f" in {location}"
                  response += f"{task}. {package_status}\n"
             
             else: 
                  # Generic fallback
                  desc = objective.get("description")
                  if not desc and stages and idx < len(stages):
                      desc = stages[idx].get("description")
                  
                  response += f"  Task: {desc or 'Complete the objective.'}\n"

             # The authored stage instruction is the clearest statement of what
             # to do, so always show it when the objective's own condition text
             # cannot carry the whole picture (which is every typed objective
             # without a location_hint, i.e. the starting commissions).
             instruction = _stage_instruction(quest_data, idx)
             if instruction and obj_type != "unknown":
                 response += f"  {FORMAT_HIGHLIGHT}{instruction}{FORMAT_RESET}\n"
             
             if quest_data.get('state') == "ready_to_complete":
                 # Say how, not only that: talking to the giver does not offer
                 # the hand-in, so "Ready to turn in!" alone left a player who
                 # had done the work standing in front of the right person.
                 # The phrase is the content set's own first turn-in phrase.
                 how = ""
                 if giver_npc is not None and turn_in_target != "quest_board":
                     phrases = context["world"].ruleset_section("quest_generation").get("turn_in_phrases") or ["complete"]
                     how = f" ({FORMAT_RESET}talk {giver_name} {phrases[0]}{FORMAT_HIGHLIGHT})"
                 response += f"  {FORMAT_HIGHLIGHT}Ready to turn in!{how}{FORMAT_RESET}\n"
             response += "\n"

    if not found_active:
        return _getting_started_block(context["world"]) or "You have no active quests."

    getting_started = _getting_started_block(context["world"])
    if getting_started:
        response += "\n" + getting_started
    return response.strip()
