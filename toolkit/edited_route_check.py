"""Play one authored route on a content set and report what happened.

The world editor's journey tests edit a scratch copy of a content set through
its real inspectors, save it through the engine-checked path, and then run
this against the copy (and against the unedited set) to show the edit changes
play -- the M2 gate's "a nontrivial edit, then a runtime journey", rather than
a form that merely saves.

Each route boots a deterministic HeadlessServer on the given set, drives it
through player commands, and prints one JSON object of measured outcomes. It
asserts nothing itself: the caller knows what the edit should have changed.

Usage:
    python toolkit/edited_route_check.py <content-set> <route> [key=value ...]

Routes:
    combat_ability  spell=<ability id> target=<NPC template id>
        Teach the spell, place the target beside the player, cast once, and
        report the target's health before and after and whether it died.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "server"))


def _server(content_set: str):
    from engine.server.headless_server import HeadlessServer

    return HeadlessServer(db_path=":memory:", content_set_path=content_set, deterministic_test_mode=True)


def _player(server, name: str = "Rowan"):
    session = server.create_session(player_id="route_check")
    server.execute_command(session.session_id, f"char create {name}")
    return session, server.get_player_for_session(session.session_id)


def _text(events) -> str:
    """The player-facing text of a command's events (the rest is status payload)."""
    lines = []
    for event in events or []:
        if isinstance(event, dict) and event.get("type") == "text":
            payload = event.get("payload")
            text = payload.get("text", "") if isinstance(payload, dict) else payload
            if text:
                lines.append(str(text))
    return "\n".join(lines)


def combat_ability(content_set: str, spell: str, target: str) -> dict:
    from engine.magic.spell_registry import get_spell
    from engine.npcs.npc_factory import NPCFactory

    server = _server(content_set)
    try:
        session, player = _player(server)
        ability = get_spell(spell)
        if ability is None:
            return {"ok": False, "error": f"ability '{spell}' did not load"}
        player.learn_spell(spell)
        magic = player.runtime_state.magic
        magic.mana = magic.max_mana = max(magic.max_mana, 999)
        world = server.world
        npc = NPCFactory.create_npc_from_template(
            target, world, f"route_{target}",
            current_region_id=player.current_region_id, current_room_id=player.current_room_id,
        )
        if npc is None:
            return {"ok": False, "error": f"NPC template '{target}' did not build"}
        world.add_npc(npc)
        before = npc.health
        output = server.execute_command(session.session_id, f"cast {ability.name} on {npc.name}")
        return {
            "ok": True, "route": "combat_ability", "spell": spell, "target": target,
            "health_before": before, "health_after": max(0, npc.health), "died": not npc.is_alive,
            "damage_value": [effect.get("value") for effect in ability.effects if effect.get("type") == "damage"],
            "output": _text(output)[-400:],
        }
    finally:
        server.shutdown()


def _count(player, item_id: str) -> int:
    return sum(slot.quantity for slot in player.inventory.slots if slot.item and slot.item.obj_id == item_id)


def _give(server, player, item_id: str, quantity: int = 1) -> None:
    from engine.items.item_factory import ItemFactory

    for _ in range(quantity):
        player.inventory.add_item(ItemFactory.create_item_from_template(item_id, server.world))


def gather_craft_use(content_set: str, node: str, tool: str, recipe: str, extra: str = "", use: str = "") -> dict:
    """Gather from `node` with `tool`, craft `recipe`, then use one result.

    `extra` names ingredients handed over rather than gathered (id:qty,...);
    `use` is the item used at the end (default: the recipe's result).
    """
    from engine.items.item_factory import ItemFactory

    server = _server(content_set)
    try:
        session, player = _player(server)
        world = server.world
        recipe_obj = server.crafting_manager.recipes.get(recipe) if server.crafting_manager is not None else None
        if recipe_obj is None:
            return {"ok": False, "error": f"recipe '{recipe}' did not load"}
        _give(server, player, tool)
        for part in filter(None, extra.split(",")):
            item_id, _, quantity = part.partition(":")
            _give(server, player, item_id, int(quantity or 1))
        node_item = ItemFactory.create_item_from_template(node, world)
        room = world.get_region(player.current_region_id).get_room(player.current_room_id)
        room.add_item(node_item)
        resource = node_item.get_property("resource_item_id")
        gathered_before = _count(player, resource)
        gather_text = _text(server.execute_command(session.session_id, f"gather {node_item.name}"))
        gathered = _count(player, resource) - gathered_before
        result_id = recipe_obj.result_item_id
        crafted_before = _count(player, result_id)
        craft_text = _text(server.execute_command(session.session_id, f"craft {recipe_obj.name}"))
        crafted = _count(player, result_id) - crafted_before
        used_item = use or result_id
        player.health = max(1, player.max_health // 2)
        health_before = player.health
        use_text = _text(server.execute_command(session.session_id, f"use {ItemFactory.create_item_from_template(used_item, world).name}"))
        return {
            "ok": True, "route": "gather_craft_use", "gathered": gathered, "crafted": crafted,
            "healed": player.health - health_before, "result_left": _count(player, result_id),
            "output": "\n".join([gather_text, craft_text, use_text])[-500:],
        }
    finally:
        server.shutdown()


def dialogue_quest_reward(content_set: str, giver: str, topic: str, recipe: str, deliver: str, inputs: str = "") -> dict:
    """Accept the board's first quest, be taught its recipe in conversation,
    make the delivery and hand it over; report what the completion paid.

    `giver` is the NPC's display name, `topic` the reply that teaches the
    recipe, `deliver` the delivered item's display name, and `inputs` the
    ingredients handed over rather than gathered (id:qty,...).
    """
    server = _server(content_set)
    try:
        session, player = _player(server)
        gold_before = player.runtime_state.gold or 0
        accepted = _text(server.execute_command(session.session_id, "accept quest 1"))
        taught = _text(server.execute_command(session.session_id, f"talk {giver}"))
        taught += "\n" + _text(server.execute_command(session.session_id, f"reply {topic}"))
        learned = recipe in player.known_recipe_ids
        for part in filter(None, inputs.split(",")):
            item_id, _, quantity = part.partition(":")
            _give(server, player, item_id, int(quantity or 1))
        crafted = _text(server.execute_command(session.session_id, f"craft {recipe}"))
        completed = _text(server.execute_command(session.session_id, f"give {deliver} to {giver}"))
        # What the completion reports paying; `experience` resets on a level-up.
        paid_xp = re.search(r"(\d+) XP", completed)
        return {
            "ok": True, "route": "dialogue_quest_reward", "accepted": "Quest Accepted" in accepted,
            "recipe_learned": learned, "completed": "Quest Complete" in completed,
            "xp_paid": int(paid_xp.group(1)) if paid_xp else 0, "gold_gained": (player.runtime_state.gold or 0) - gold_before,
            "relationships": dict(player.npc_relationships),
            "output": completed[-500:],
        }
    finally:
        server.shutdown()


def discovery_advancement(content_set: str, item: str) -> dict:
    """Pick up `item` where the player stands; report the discoveries it made,
    the XP the advancement ledger paid for it, and what the player was told."""
    from engine.items.item_factory import ItemFactory

    server = _server(content_set)
    try:
        session, player = _player(server)
        world = server.world
        manager = world.advancement_manager
        progression = player.runtime_state.progression

        def total_xp() -> int:
            # `experience` restarts at each level; the curve gives what came before.
            return int(manager.xp_to_reach_level(progression.level)) + int(progression.experience)

        found = ItemFactory.create_item_from_template(item, world)
        world.get_region(player.current_region_id).get_room(player.current_room_id).add_item(found)
        discoveries_before = set(player.discoveries)
        xp_before = total_xp()
        output = _text(server.execute_command(session.session_id, f"get {found.name}"))
        return {
            "ok": True, "route": "discovery_advancement",
            "discoveries": sorted(set(player.discoveries) - discoveries_before),
            "xp_gained": total_xp() - xp_before, "output": output[-500:],
        }
    finally:
        server.shutdown()


def gift_relationship(content_set: str, item: str, npc: str, template: str) -> dict:
    """Give `item` to the NPC named `npc` (template `template`); report the
    relationship points it earned, the tier reached and its vendor discount."""
    from engine.social.relationships import relationship_discount, relationship_tier

    server = _server(content_set)
    try:
        session, player = _player(server)
        _give(server, player, item)
        from engine.items.item_factory import ItemFactory

        name = ItemFactory.create_item_from_template(item, server.world).name
        output = _text(server.execute_command(session.session_id, f"give {name} to {npc}"))
        score = int(player.npc_relationships.get(template, 0))
        return {
            "ok": True, "route": "gift_relationship", "points": score,
            "tier": relationship_tier(score, server.world), "discount": relationship_discount(score, server.world),
            "output": output[-300:],
        }
    finally:
        server.shutdown()


def kill_loot(content_set: str, target: str, kills: str = "10", spell: str = "magic_missile") -> dict:
    """Kill `kills` NPCs of template `target` with `spell` (each brought to 1
    health first, so every cast is a kill) and count what fell to the floor.
    `ambient` counts drops the template's own loot table cannot explain --
    the ruleset's ambient loot pools. The server is seeded, so the rolls
    repeat run to run."""
    from engine.npcs.npc_factory import NPCFactory
    from engine.magic.spell_registry import get_spell

    server = _server(content_set)
    try:
        session, player = _player(server)
        ability = get_spell(spell)
        if ability is None:
            return {"ok": False, "error": f"ability '{spell}' did not load"}
        player.learn_spell(spell)
        magic = player.runtime_state.magic
        world = server.world
        region, room = player.current_region_id, player.current_room_id

        def floor_ids() -> list:
            return [item.obj_id for item in world.get_items_in_room(region, room)]

        drops: dict = {}
        own_table: set = set()
        killed = 0
        for index in range(int(kills)):
            npc = NPCFactory.create_npc_from_template(target, world, f"route_{target}_{index}", current_region_id=region, current_room_id=room)
            if npc is None:
                return {"ok": False, "error": f"NPC template '{target}' did not build"}
            own_table = set((npc.loot_table or {}).keys())
            world.add_npc(npc)
            npc.health = 1
            magic.mana = magic.max_mana = max(magic.max_mana, 999)
            magic.cooldowns.clear()
            before = floor_ids()
            server.execute_command(session.session_id, f"cast {ability.name} on {npc.name}")
            killed += 0 if npc.is_alive else 1
            after = floor_ids()
            for item_id in before:
                after.remove(item_id)
            for item_id in after:
                drops[item_id] = drops.get(item_id, 0) + 1
            for item in list(world.get_items_in_room(region, room)):
                world.remove_item_from_room(region, room, item.obj_id)
        ambient = {item_id: count for item_id, count in drops.items() if item_id not in own_table}
        return {"ok": True, "route": "kill_loot", "killed": killed, "drops": drops, "ambient": ambient}
    finally:
        server.shutdown()


ROUTES = {
    "combat_ability": combat_ability, "gather_craft_use": gather_craft_use,
    "dialogue_quest_reward": dialogue_quest_reward, "discovery_advancement": discovery_advancement,
    "gift_relationship": gift_relationship, "kill_loot": kill_loot,
}


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[2] not in ROUTES:
        print(json.dumps({"ok": False, "error": f"usage: <content-set> <route: {'|'.join(ROUTES)}> [key=value ...]"}))
        return 2
    arguments = dict(part.split("=", 1) for part in sys.argv[3:] if "=" in part)
    try:
        result = ROUTES[sys.argv[2]](sys.argv[1], **arguments)
    except Exception as error:  # noqa: BLE001 - a crash is the finding
        result = {"ok": False, "error": f"{type(error).__name__}: {error}"}
    # One line, last, so a caller can take it from the end of noisy output.
    print("ROUTE_RESULT " + json.dumps(result, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
