# engine/commands/interaction/use_give.py
import time
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS, USE_COMMAND_PREPOSITIONS, GIVE_COMMAND_PREPOSITION
from engine.items.consumable import Consumable
from engine.items.key import Key
from engine.social.relationships import apply_relationship_milestones, next_relationship_milestone, relationship_key, relationship_rules, relationship_tier


def _world_day_key(world) -> str:
    manager = getattr(getattr(world, "game", None), "time_manager", None)
    if manager is None:
        return "untracked"
    return f"{manager.year}-{manager.month}-{manager.day}"


def _gift_affinity(npc, item, world) -> tuple[int, list[str]]:
    """Score a gift and expose only generic, data-authored affinity reasons."""
    values = relationship_rules(world).get("gift_values", {})
    points = int(values.get("crafted", 5)) if bool(item.get_property("crafted_by_player", False)) else int(values.get("ordinary", 1))
    reasons: list[str] = ["crafted" if bool(item.get_property("crafted_by_player", False)) else "ordinary"]
    preferences = npc.properties.get("gift_preferences", {})
    if not isinstance(preferences, dict):
        return points, reasons
    item_id = str(getattr(item, "obj_id", ""))
    category = str(item.get_property("category", ""))
    if item_id in preferences.get("preferred_item_ids", []):
        points += int(values.get("preferred_item", 4))
        reasons.append("preferred")
    if category and category in preferences.get("preferred_categories", []):
        points += int(values.get("preferred_category", 2))
        reasons.append("preferred")
    gift_tags = item.get_property("gift_tags", [])
    if not isinstance(gift_tags, list):
        gift_tags = []
    preferred_tags = preferences.get("preferred_gift_tags", [])
    disliked_tags = preferences.get("disliked_gift_tags", [])
    if not isinstance(preferred_tags, list):
        preferred_tags = []
    if not isinstance(disliked_tags, list):
        disliked_tags = []
    for tag in gift_tags:
        points += int(relationship_rules(world).get("gift_tag_values", {}).get(str(tag), 0))
        if tag in preferred_tags:
            points += int(values.get("preferred_tag", 0))
            reasons.append("preferred")
        if tag in disliked_tags:
            points += int(values.get("disliked_tag", 0))
            reasons.append("disliked")
    if item_id in preferences.get("disliked_item_ids", []):
        points = max(0, points + int(values.get("disliked_item", -3)))
        reasons.append("disliked")
    quality_bonus = item.get_property("gift_quality_bonus", 0)
    if isinstance(quality_bonus, int) and not isinstance(quality_bonus, bool) and quality_bonus > 0:
        points += quality_bonus
        reasons.append("quality")
    return max(0, points), reasons

@command("use", ["activate", "drink", "eat", "apply"], "interaction", "Use an item.\nUsage: use <item> [on <target>]")
def use_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Use what?{FORMAT_RESET}"

    prep_idx = -1
    for i, w in enumerate(args):
        if w.lower() in USE_COMMAND_PREPOSITIONS: prep_idx = i; break
        
    if prep_idx != -1:
        item_name = " ".join(args[:prep_idx]).lower()
        target_name = " ".join(args[prep_idx+1:]).lower()
    else:
        item_name = " ".join(args).lower()
        target_name = None

    item = player.inventory.find_item_by_name(item_name)
    if not item: return f"{FORMAT_ERROR}You don't have '{item_name}'.{FORMAT_RESET}"

    target = None
    if target_name:
        target = (
            world.find_item_in_room_for_player(target_name, player)
            or player.inventory.find_item_by_name(target_name, exclude=item)
            or world.find_npc_in_room_for_player(target_name, player)
        )
        if not target and target_name in ["self", "me"]: target = player
        if not target: return f"{FORMAT_ERROR}Target '{target_name}' not found.{FORMAT_RESET}"
    
    # Validation for Keys
    if isinstance(item, Key) and not target:
         return f"{FORMAT_ERROR}Use key on what?{FORMAT_RESET}"

    try:
        # Some use() methods don't take target kwarg, some do. 
        # Base Item.use accepts **kwargs.
        if target:
             res = item.use(user=player, target=target)
        else:
             res = item.use(user=player)

        # Consumable Logic
        if isinstance(item, Consumable) and item.get_property("uses", 1) <= 0:
             player.inventory.remove_item(item.obj_id)

        return f"{FORMAT_HIGHLIGHT}{res}{FORMAT_RESET}"

    except Exception as e:
        return f"{FORMAT_ERROR}Failed to use item: {e}{FORMAT_RESET}"

@command("give", [], "interaction", "Give item to NPC.\nUsage: give <item> to <npc>")
def give_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not player.is_alive: return f"{FORMAT_ERROR}You are dead.{FORMAT_RESET}"
    
    if GIVE_COMMAND_PREPOSITION not in [a.lower() for a in args]:
        return f"{FORMAT_ERROR}Usage: give <item> {GIVE_COMMAND_PREPOSITION} <npc>{FORMAT_RESET}"
    
    try:
        idx = [a.lower() for a in args].index(GIVE_COMMAND_PREPOSITION)
        item_name = " ".join(args[:idx]).lower()
        npc_name = " ".join(args[idx+1:]).lower()
    except (ValueError, AttributeError): return f"{FORMAT_ERROR}Parse error.{FORMAT_RESET}"

    item = player.inventory.find_item_by_name(item_name)
    if not item: return f"{FORMAT_ERROR}You don't have '{item_name}'.{FORMAT_RESET}"
    
    npc = world.find_npc_in_room_for_player(npc_name, player)
    if not npc: return f"{FORMAT_ERROR}NPC '{npc_name}' not found.{FORMAT_RESET}"

    # Quest Delivery Logic
    matching_quest = None

    quests_active = player.runtime_state.quests.active if player.runtime_state.quests is not None else {}
    for q_id, q_data in quests_active.items():
        if q_data.get("state") != "active": continue
        
        qm = world.quest_manager
        objectives = qm.get_active_objectives(q_data) or [q_data.get("objective", {})]
        for objective in objectives:
            if not isinstance(objective, dict):
                continue
            # When an active delivery asks for quality, choose the best
            # matching inventory instance by default. Quality-bearing outputs
            # are deliberately separate items, and a player should not need a
            # hidden instance-id command merely because an ordinary version is
            # also in their pack.
            required_quality = objective.get("min_material_quality_score", 0)
            required_quality = max(0, int(required_quality)) if isinstance(required_quality, int) and not isinstance(required_quality, bool) else 0
            if objective.get("type") == "deliver" and required_quality > 0 and objective.get("item_template_id") == item.obj_id:
                candidates = [
                    slot.item for slot in player.inventory.slots
                    if slot.item is not None and slot.item.obj_id == item.obj_id
                    and isinstance(slot.item.get_property("material_quality_score", 0), int)
                    and not isinstance(slot.item.get_property("material_quality_score", 0), bool)
                    and slot.item.get_property("material_quality_score", 0) >= required_quality
                ]
                if candidates:
                    item = max(candidates, key=lambda candidate: candidate.get_property("material_quality_score", 0))
            accepts_instance = objective.get("item_instance_id") == item.obj_id
            accepts_template = objective.get("item_template_id") == item.obj_id
            crafted_only = bool(objective.get("crafted_only", False))
            if (objective.get("type") != "deliver" or not (accepts_instance or accepts_template)
                or (crafted_only and not bool(item.get_property("crafted_by_player", False)))):
                continue
            # A content set can target a stable NPC template or a particular
            # runtime instance. Template targeting is useful for authored
            # commissions because instance ids are intentionally ephemeral.
            recipient_instance_id = objective.get("recipient_instance_id")
            recipient_template_id = objective.get("recipient_template_id")
            if recipient_instance_id == npc.obj_id or recipient_template_id == getattr(npc, "template_id", None):
                item_quality = item.get_property("material_quality_score", 0)
                item_quality = int(item_quality) if isinstance(item_quality, int) and not isinstance(item_quality, bool) else 0
                if item_quality < required_quality:
                    return f"{FORMAT_ERROR}This delivery requires material quality {required_quality} or better (this item has {item_quality}).{FORMAT_RESET}"
                matching_quest = (q_id, q_data, objective)
                break
            # Wrong recipient for a matching route.
            return f"{FORMAT_ERROR}You should give the {item.name} to {objective.get('recipient_name', 'someone else')}, not {npc.name}.{FORMAT_RESET}"
        if matching_quest:
            break

    if matching_quest:
        # It's a quest delivery!
        quest_id, quest_data, _completed_objective = matching_quest
        
        # Remove item
        rem_item, count, _ = player.inventory.remove_item(item.obj_id, 1)
        if not rem_item: return f"{FORMAT_ERROR}Failed to remove item.{FORMAT_RESET}"
        
        # Complete Quest
        qm = world.quest_manager
        rewards_msg = qm.complete_quest(player, quest_id)
        
        npc_response = npc.dialog.get(f"complete_{quest_id}", npc.dialog.get("quest_complete", "Thank you!"))
        
        msg = f"{FORMAT_SUCCESS}[Quest Complete] {quest_data.get('title')}{FORMAT_RESET}\n"
        msg += f"{FORMAT_HIGHLIGHT}\"{npc_response}\"{FORMAT_RESET}\n"
        if rewards_msg: msg += rewards_msg
        
        return msg
        
    else:
        # Standard Gift
        npc_key = relationship_key(npc)
        today = _world_day_key(world)
        if player.npc_gift_days.get(npc_key) == today:
            return f"{FORMAT_HIGHLIGHT}{npc.name} appreciates the thought, but asks you to save another gift for another day.{FORMAT_RESET}"
        rem_item, count, _ = player.inventory.remove_item(item.obj_id, 1)
        if rem_item:
            # Add to NPC inventory if possible
            if hasattr(npc, 'inventory'):
                npc.inventory.add_item(rem_item)
            old_score = int(player.npc_relationships.get(npc_key, 0))
            gained, affinity_reasons = _gift_affinity(npc, rem_item, world)
            new_score = min(100, old_score + gained)
            player.npc_relationships[npc_key] = new_score
            player.npc_gift_days[npc_key] = today
            milestone_note = apply_relationship_milestones(player, npc, old_score, new_score, world)
            crafted_note = " Your handiwork makes the gift feel personal." if rem_item.get_property("crafted_by_player", False) else ""
            preference_note = " It clearly suits their tastes." if "preferred" in affinity_reasons else ""
            disliked_note = " They accept it politely, but it misses the mark." if "disliked" in affinity_reasons else ""
            quality_note = " Its quality is immediately apparent." if "quality" in affinity_reasons else ""
            response = (
                f"{FORMAT_SUCCESS}You give the {rem_item.name} to {npc.name}.{FORMAT_RESET}"
                f"{crafted_note}{preference_note}{disliked_note}{quality_note}\n"
                f"Relationship: +{gained} ({new_score}/100, {relationship_tier(new_score, world)})."
            )
            return response + (f"\n{milestone_note}" if milestone_note else "")
        return f"{FORMAT_ERROR}Failed to remove item.{FORMAT_RESET}"


@command("relationship", ["bond", "friendship"], "information", "Check your relationship with an NPC.\nUsage: relationship <npc>")
def relationship_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args:
        return f"{FORMAT_ERROR}Relationship with whom? Usage: relationship <npc>{FORMAT_RESET}"
    npc = world.find_npc_in_room_for_player(" ".join(args).lower(), player)
    if not npc:
        return f"{FORMAT_ERROR}NPC '{' '.join(args)}' not found here.{FORMAT_RESET}"
    score = int(player.npc_relationships.get(relationship_key(npc), 0))
    gifted_today = player.npc_gift_days.get(relationship_key(npc)) == _world_day_key(world)
    next_gift = "Gift given today" if gifted_today else "A gift would be welcome today"
    milestone = next_relationship_milestone(player, npc, score)
    milestone_note = f" Next milestone: {milestone['min']}/100." if milestone else " No unclaimed milestones."
    return f"{FORMAT_HIGHLIGHT}{npc.name}: {relationship_tier(score, world)} ({score}/100){FORMAT_RESET}\n{next_gift}.{milestone_note}"


@command("relationships", ["bonds", "friends"], "information", "Review all known personal relationships.")
def relationships_handler(args, context):
    world = context["world"]
    player = context.get("player")
    if not player:
        return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not player.npc_relationships:
        return "You have not built a personal relationship yet. Gifts, orders, and commissions can help."
    npcs_by_key = {relationship_key(npc): npc for npc in world.npcs.values()}
    lines = [f"{FORMAT_HIGHLIGHT}RELATIONSHIPS{FORMAT_RESET}"]
    for key, score in sorted(player.npc_relationships.items(), key=lambda pair: (-int(pair[1]), pair[0])):
        npc = npcs_by_key.get(key)
        name = npc.name if npc is not None else key.replace("_", " ").title()
        milestone = next_relationship_milestone(player, npc, int(score)) if npc is not None else None
        suffix = f" — next milestone {milestone['min']}/100" if milestone else ""
        lines.append(f"- {name}: {relationship_tier(int(score), world)} ({score}/100){suffix}")
    return "\n".join(lines)
