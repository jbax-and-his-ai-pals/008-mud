# engine/commands/gathering.py
from engine.commands.command_system import command
from engine.config import FORMAT_ERROR, FORMAT_RESET, FORMAT_SUCCESS
from engine.items.item_factory import ItemFactory
from engine.items.resource_node import ResourceNode

@command("gather", ["mine", "harvest", "chop"], "interaction", "Gather resources from a node.\nUsage: gather <target>", content_capability="gathering")
def gather_handler(args, context):
    world = context["world"]
    player = context.get('player')
    if not args: return f"{FORMAT_ERROR}Gather from what?{FORMAT_RESET}"

    target_name = " ".join(args).lower()
    target = world.find_item_in_room_for_player(target_name, player)

    if not target: return f"{FORMAT_ERROR}You don't see '{target_name}' here.{FORMAT_RESET}"

    if isinstance(target, ResourceNode):
        return target.gather(player, world)
    else:
        return f"{FORMAT_ERROR}You cannot gather from {target.name}.{FORMAT_RESET}"


@command("plant", [], "interaction", "Plant a crop in a garden plot.\nUsage: plant <crop>", content_capability="gathering")
def plant_handler(args, context):
    """A garden plot's own cultivation decision: a ResourceNode authored
    with zero starting charges and a plantable_crops list. Planting just
    reconfigures that same node's resource_item_id/charges/respawn_days at
    runtime -- gather (already aliased to "harvest") then works completely
    unmodified, the same way it does for any other resource node."""
    world = context["world"]
    player = context.get('player')
    if not player: return f"{FORMAT_ERROR}You must start or load a game first.{FORMAT_RESET}"
    if not args: return f"{FORMAT_ERROR}Plant what?{FORMAT_RESET}"

    crop_name = " ".join(args).lower()
    target = world.find_item_in_room_for_player("garden plot", player)
    if not target or not isinstance(target, ResourceNode):
        return f"{FORMAT_ERROR}There's no garden plot here to plant in.{FORMAT_RESET}"

    crops = target.get_property("plantable_crops", [])
    if not isinstance(crops, list) or not crops:
        return f"{FORMAT_ERROR}Nothing can be planted here.{FORMAT_RESET}"

    match = next(
        (
            crop for crop in crops
            if isinstance(crop, dict)
            and crop_name in (str(crop.get("label", "")).lower(), str(crop.get("id", "")).lower())
        ),
        None,
    )
    if not match:
        options = ", ".join(str(crop.get("label", "?")) for crop in crops if isinstance(crop, dict))
        return f"{FORMAT_ERROR}You can plant: {options}.{FORMAT_RESET}"

    seed_item_id = str(match.get("seed_item_id", "")).strip()
    if seed_item_id:
        if player.inventory.count_item(seed_item_id) < 1:
            template = ItemFactory.get_template(seed_item_id, world)
            seed_name = template.get("name", seed_item_id) if template else seed_item_id
            return f"{FORMAT_ERROR}You need {seed_name} to plant that.{FORMAT_RESET}"
        removed_type, _removed_qty, _msg = player.inventory.remove_item(seed_item_id, 1)
        if not removed_type:
            return f"{FORMAT_ERROR}Unable to use your seeds.{FORMAT_RESET}"

    charges = int(match.get("charges", target.get_property("max_charges", 1) or 1))
    target.update_property("resource_item_id", match.get("resource_item_id"))
    target.update_property("charges", charges)
    target.update_property("max_charges", charges)
    target.update_property("respawn_days", int(match.get("respawn_days", target.get_property("respawn_days", 0))))
    target.update_property("depleted_day", None)
    if "material_quality" in match:
        target.update_property("material_quality", match["material_quality"])

    label = match.get("label", crop_name)
    return f"{FORMAT_SUCCESS}You plant {label} in the garden plot. It should be ready to harvest soon.{FORMAT_RESET}"
