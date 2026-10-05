# engine/npcs/combat.py
from typing import TYPE_CHECKING, Any, Dict, Optional, Union
import random
import time
from engine.config import (
    HIT_CHANCE_AGILITY_FACTOR, LEVEL_DIFF_COMBAT_MODIFIERS, MAX_HIT_CHANCE, MIN_HIT_CHANCE, MINIMUM_DAMAGE_TAKEN, FORMAT_RESET,
    FORMAT_SUCCESS, NPC_ATTACK_DAMAGE_VARIATION_RANGE, NPC_BASE_HIT_CHANCE,
    NPC_LOW_MANA_RETREAT_THRESHOLD,
    DEFAULT_WEAPON_DAMAGE_TYPE
)
from engine.config.config_display import FORMAT_ERROR
from engine.core.combat_system import CombatSystem
from engine.contracts.equipment import choose_attack_mode
from engine.npcs import companion_gear, combat_detail, pacing
from engine.magic.effects import apply_spell_effect
from engine.magic.spell_registry import get_spell
from engine.utils.text_formatter import format_target_name, get_level_diff_category
from engine.utils.utils import calculate_xp_gain, format_loot_drop_message, format_name_for_display

if TYPE_CHECKING:
    from .npc import NPC
    from engine.player import Player


def _combat_targets(actor):
    runtime_state = getattr(actor, "runtime_state", None)
    return runtime_state.combat.targets if runtime_state is not None else actor.combat_targets


def _progression_level(actor):
    runtime_state = getattr(actor, "runtime_state", None)
    if runtime_state is None:
        return actor.level
    if runtime_state.progression is None:
        return 1
    return runtime_state.progression.level


def get_relation_to(viewer: Union['NPC', 'Player'], target: Union['NPC', 'Player']) -> int:
    """
    Calculates relationship. 
    If Viewer is NPC and Target is Player: Base Matrix + Player Rep.
    """
    if not hasattr(viewer, 'faction') or not hasattr(target, 'faction'): return 0

    # The world's matrix, not the engine's flat one: a content set that declares
    # its own factions (ruleset `factions`) has to be able to name its enemies,
    # or combat is the one system that would never notice.
    from engine.world import factions as faction_rules

    world = getattr(viewer, "world", None) or getattr(target, "world", None)
    base_val = faction_rules.attitude(world, viewer, target)

    # 2. Player Reputation Modifier
    # Only applies if the viewer is an NPC judging the Player
    modifier = 0
    from engine.player import Player
    if isinstance(target, Player):
        modifier = target.reputation.get(viewer.faction, 0)
        
    return base_val + modifier

def is_hostile_to(npc: 'NPC', other) -> bool:
    return get_relation_to(npc, other) < 0

def is_pacifist(npc) -> bool:
    """`properties.pacifist`: it never fights back, nor starts a fight (an acolyte at an altar). A companion in hiding takes no part."""
    properties = getattr(npc, "properties", None)
    return isinstance(properties, dict) and (properties.get("pacifist") is True or properties.get("hidden") is True)


def is_untargetable(npc) -> bool:
    """`properties.untargetable`: nothing picks it as a target and nothing it is hit by hurts it (a child carried,
    asleep, through a fight). Pair it with `pacifist` for someone who takes no part at all."""
    properties = getattr(npc, "properties", None)
    return isinstance(properties, dict) and (properties.get("untargetable") is True or properties.get("hidden") is True)


def enter_combat(npc: 'NPC', target):
    if not npc.is_alive or not target or not getattr(target, 'is_alive', False): return
    if is_pacifist(npc) or is_untargetable(target): return
    npc.in_combat = True
    npc.combat_targets.add(target)
    if hasattr(target, 'enter_combat') and npc not in _combat_targets(target):
        target.enter_combat(npc)

def exit_combat(npc: 'NPC', target: Optional[Any] = None):
    if target:
        if target in npc.combat_targets:
            npc.combat_targets.remove(target)
            if hasattr(target, "exit_combat"):
                target.exit_combat(npc)
    else:
        targets_to_remove = list(npc.combat_targets)
        for t in targets_to_remove:
            npc.combat_targets.discard(t)
            if hasattr(t, "exit_combat"):
                t.exit_combat(npc)
                
    if not npc.combat_targets:
        npc.in_combat = False
        npc.combat_target = None

def attack(npc: 'NPC', target) -> Dict[str, Any]:
    # Resolve viewer: the target player if alive in room, else any co-located player.
    world = npc.world
    viewer = None
    if world:
        if hasattr(target, 'obj_id') and hasattr(target, 'current_room_id'):
            viewer = target if getattr(target, 'is_alive', False) else None
        viewer = world.get_viewer_for_npc(npc, preferred_player=viewer)

    weapon_damage_type = companion_gear.weapon_type_of(npc) or npc.properties.get("weapon_damage_type", DEFAULT_WEAPON_DAMAGE_TYPE)

    # --- BOSS MECHANICS ---
    # Check for special abilities defined in properties
    special_abilities = npc.properties.get("special_abilities", [])
    if special_abilities:
        import random
        # Simple Logic: 20% chance to trigger a special if available
        if random.random() < 0.2:
            ability = random.choice(special_abilities)
            name = ability.get("name", "Special Attack")
            damage_mult = ability.get("damage_multiplier", 1.5)
            message = ability.get("message", f"{npc.name} uses a special attack!")
            
            # Execute Special
            combat_result = CombatSystem.execute_attack(
                attacker=npc,
                defender=target,
                attack_power=int(npc.attack_power * damage_mult),
                weapon_name=name,
                viewer=viewer,
                weapon_damage_type=weapon_damage_type
            )
            
            # Override message with boss flavor text
            combat_result["message"] = f"{FORMAT_ERROR}{message}{FORMAT_RESET}\n{combat_result['message']}"
            return {"message": combat_result["message"], "target_defeated": combat_result["target_defeated"]}

    # What it holds is named in the blow, and a weapon with several ways of being used uses one at random.
    weapon = companion_gear.main_hand(npc)
    mode = choose_attack_mode(world, weapon) if weapon is not None else None
    attack_power = npc.attack_power
    if mode:
        weapon_damage_type = str(mode.get("weapon_damage_type") or weapon_damage_type)
        attack_power += int(mode.get("damage_bonus", 0) or 0)

    combat_result = CombatSystem.execute_attack(
        attacker=npc,
        defender=target,
        attack_power=attack_power,
        weapon_name=weapon.name if weapon is not None else "attack",
        viewer=viewer,
        weapon_damage_type=weapon_damage_type,
        mode=mode,
    )

    return {"message": combat_result["message"], "target_defeated": combat_result["target_defeated"],
            "routine": True, "damage": combat_result.get("damage", 0)}

def cast_spell(npc: 'NPC', spell, target, current_time: float) -> Dict[str, Any]:
    is_actively_hostile = target in npc.combat_targets or is_hostile_to(npc, target)

    if spell.target_type == 'friendly' and is_actively_hostile:
        return attack(npc, target)

    if spell.target_type in ('enemy', 'all_enemies') and not is_actively_hostile:
        return attack(npc, target)
        
    if npc.mana < spell.mana_cost: return {"message": f"{npc.name} lacks mana."}
    health_cost = spell.health_cost(npc.max_health)
    if health_cost and npc.health <= health_cost: return {"message": f"{npc.name} cannot afford {spell.name}."}
    npc.mana -= spell.mana_cost
    npc.health -= health_cost
    npc.spell_cooldowns[spell.spell_id] = current_time + spell.cooldown
    world = npc.world
    viewer = None
    if world:
        viewer = world.get_viewer_for_npc(npc)
    if spell.target_type == 'all_enemies' and world:
        # An area ability reaches every enemy in the room at once (a song that puts them all to sleep).
        enemies = [t for t in list(world.get_players_in_room(npc.current_region_id, npc.current_room_id, alive_only=True))
                   + [o for o in world.get_npcs_in_room(npc.current_region_id, npc.current_room_id) if o.is_alive]
                   if t is not npc and is_hostile_to(npc, t) and not is_untargetable(t)]
        lines = [spell.format_cast_message(npc)]
        for index, enemy in enumerate(enemies or [target]):
            _, text = apply_spell_effect(npc, enemy, spell, viewer, first_target=index == 0)
            if text:
                lines.append(text)
        return {"message": chr(10).join(lines), "target_defeated": False}

    _, effect_message = apply_spell_effect(npc, target, spell, viewer)
    
    full_message = f"{spell.format_cast_message(npc)}\n{effect_message}"
    
    return {"message": full_message, "target_defeated": not getattr(target, 'is_alive', True)}

def try_attack(npc: 'NPC', world, current_time: float) -> Optional[str]:
    if is_pacifist(npc):
        return None
    from . import ai as npc_ai 
    
    # Find any player in the same room for message routing / XP attribution
    player = world.get_viewer_for_npc(npc)
    owner = world.get_player_by_id(npc.properties.get("owner_id")) if getattr(npc, "properties", None) else None
    
    if current_time - npc.last_combat_action < pacing.cooldown_of(world, npc.combat_cooldown): return None
    if not pacing.room_is_open(world, npc, current_time): return None   # someone else has the beat
    
    target = npc.combat_target
    if not (target and target.is_alive and target.current_room_id == npc.current_room_id):
        valid_targets = [t for t in npc.combat_targets if t and t.is_alive and t.current_room_id == npc.current_room_id and not is_untargetable(t)]
        if not valid_targets: exit_combat(npc); return None
        target = random.choice(valid_targets); npc.combat_target = target

    if npc.has_effect_tag("confuse"):
        # A confused creature strikes at whoever is nearest, friend or foe.
        crowd = list(world.get_players_in_room(npc.current_region_id, npc.current_room_id, alive_only=True))
        crowd += [other for other in world.get_npcs_in_room(npc.current_region_id, npc.current_room_id) if other.is_alive]
        crowd = [other for other in crowd if other is not npc and not is_untargetable(other)]
        if crowd:
            target = random.choice(crowd)

    from engine.npcs import phases as npc_phases

    if npc_phases.is_untouchable(target):
        return None   # nothing to be gained by striking at mist: it waits for the creature to harden

    chosen_spell = None
    if npc.max_mana > 0 and npc.usable_spells and not npc.has_effect_tag("silence") and random.random() < npc.spell_cast_chance:
        if npc.mana / npc.max_mana < NPC_LOW_MANA_RETREAT_THRESHOLD:
            retreat_message = npc_ai.start_retreat(npc, world, current_time, player)
            if retreat_message:
                return retreat_message 
        
        available_spells = [s for s_id in npc.usable_spells if (s := get_spell(s_id)) 
                            and current_time >= npc.spell_cooldowns.get(s_id, 0) 
                            and npc.mana >= s.mana_cost]
        
        offensive_spells = [s for s in available_spells if s.target_type in ('enemy', 'all_enemies')]

        if offensive_spells:
            chosen_spell = random.choice(offensive_spells)

    action_result = None
    if chosen_spell:
        action_result = cast_spell(npc, chosen_spell, target, current_time)
        npc.last_combat_action = current_time
    elif current_time - npc.last_attack_time >= pacing.cooldown_of(world, npc.attack_cooldown):
        action_result = attack(npc, target)
        npc.last_attack_time = npc.last_combat_action = current_time
    
    if action_result:
        pacing.note_action(world, npc, current_time)
        messages = [action_result.get("message")]
        
        if action_result.get("target_defeated", False):
            exit_combat(npc, target)
            xp_gainer = owner if owner is not None else npc
            kill_note = None   # what a trigger says about the death; was discarded
            # Only a creature is "killed": a minion that finishes off a *player* used to
            # raise an npc_killed for them too.
            credited_players = [owner] if owner is not None else []
            if owner is None and getattr(target, "runtime_state", None) is None and is_hostile_to(target, npc):
                # A friend of the players finished an enemy in front of them (Kessa and the Fog Drake): it
                # is the victory of every player standing there as far as the story is concerned, so each
                # one's quest and any scene hear of it. The experience stays with whoever struck the blow.
                credited_players = [
                    candidate for candidate in world.get_players_for_npc(npc, alive_only=True)
                    if not is_hostile_to(npc, candidate)
                ]
            if getattr(target, "runtime_state", None) is None:
                notes = {}
                # A death a player watched fires the story's `npc_killed` triggers whoever struck the blow, and
                # whether or not the victim was an enemy (soldiers cutting down acolytes); only an enemy pays out.
                witnesses = credited_players or world.get_players_for_npc(npc, alive_only=True)
                for candidate in witnesses:
                    note = world.dispatch_event(
                        "npc_killed", {"player": candidate, "npc": target, "witness": not credited_players})
                    if note:
                        notes[candidate.obj_id] = note
                kill_note = notes.pop(player.obj_id, None) if player is not None else None
                for other_id, note in notes.items():   # the others are told wherever they are
                    other = world.get_player_by_id(other_id)
                    if other is not None:
                        world.notify_player(other, note)
            credited = credited_players[0] if credited_players else None

            # Everyone who hurt the creature earns a share of the experience and the money, whoever struck
            # the blow. The player watching is told in this very message, before what the death set off.
            from engine.core import kill_credit
            shares = kill_credit.player_shares(target) if credited is not None else []
            earned = ""
            if shares:
                earned = kill_credit.award_participants(
                    world, target, shares, gold=kill_credit.roll_gold(target), inline=player)
                if owner is not None:
                    xp_gainer = None   # the owner was paid as a participant; not a second time
            if earned:
                messages.append("\n" + earned)

            if xp_gainer:
                # Both the killer and the victim need a resolved level. An NPC
                # can now land the killing blow on a *player* (and on a player's
                # minions), and Player has no `.level` attribute -- level lives
                # at runtime_state.progression.level. Passing a bare
                # `target.level` here raised AttributeError on the world tick,
                # so the command never returned to the player.
                #
                # Gaining XP when the victim is a player is intentional (see the
                # faction XP tests): the hostile that wins a fight gets tougher,
                # which makes leaving a dangerous region alone matter.
                victim_level = _progression_level(target)
                victim_max_health = getattr(target, "max_health", 0) or 0
                xp = calculate_xp_gain(
                    _progression_level(xp_gainer), victim_level, victim_max_health
                )
                if xp > 0 and hasattr(xp_gainer, "gain_experience"):
                    leveled, level_msg = xp_gainer.gain_experience(xp)
                    if leveled: messages.append(level_msg)
            
            if hasattr(target, 'die'):
                possible_loot = target.die(world)
                if possible_loot: messages.append(format_loot_drop_message(player, target, possible_loot))
            if kill_note:
                messages.append(kill_note)
        
        final_message = "\n".join(filter(None, messages))
        # Whose screen does this belong on? Normally the co-located player, and
        # only while they are alive -- a combat message from a room the player
        # is not watching must not leak.
        #
        # The one exception is the player *being killed*: by the time we get
        # here `target` is already dead, so the old `player.is_alive` guard
        # discarded the "You have been defeated!" line and the player died in
        # total silence. The victim must always be told.
        player_was_killed = (
            player is not None
            and target is player
            and not getattr(player, "is_alive", True)
        )
        player_is_watching = (
            player is not None
            and getattr(player, "is_alive", False)
            and player.current_region_id == npc.current_region_id
            and player.current_room_id == npc.current_room_id
        )
        if player_was_killed:
            return final_message
        if player_is_watching:
            return combat_detail.shape(world, player, npc, target, action_result, final_message, current_time)
    return None
