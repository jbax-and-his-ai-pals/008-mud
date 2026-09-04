# engine/player/combat.py
import random
import time
from typing import Dict, Any, Optional, Set, TYPE_CHECKING, cast

from engine.config import (
    PLAYER_BASE_ATTACK_POWER, PLAYER_ATTACK_POWER_STR_DIVISOR,
    PLAYER_BASE_DEFENSE, PLAYER_DEFENSE_DEX_DIVISOR,
    PLAYER_BASE_ATTACK_COOLDOWN, MIN_ATTACK_COOLDOWN,
    ITEM_DURABILITY_LOSS_ON_HIT,
    FORMAT_ERROR, FORMAT_SUCCESS, FORMAT_RESET
)
from engine.core.combat_system import CombatSystem
from engine.items.item import Item
from engine.items.weapon import Weapon
from engine.utils.utils import calculate_xp_gain, format_loot_drop_message

if TYPE_CHECKING:
    from engine.player.core import Player
    from engine.world.world import World

class PlayerCombatMixin:
    """Mixin for player combat logic."""

    def get_attack_power(self) -> int:
        p = cast('Player', self)
        attack = (p.runtime_state.combat.attack_power if p.runtime_state.combat is not None else 0) + p.get_effective_stat("strength") // PLAYER_ATTACK_POWER_STR_DIVISOR
        main_hand_weapon = p.equipment.get("main_hand")
        if isinstance(main_hand_weapon, Weapon) and main_hand_weapon.get_property("durability", 1) > 0:
            attack += main_hand_weapon.get_property("damage", 0)
        return attack

    def get_defense(self) -> int:
        p = cast('Player', self)
        defense = (p.runtime_state.combat.defense if p.runtime_state.combat is not None else 0) + p.get_effective_stat("dexterity") // PLAYER_DEFENSE_DEX_DIVISOR
        for item in p.equipment.values():
            if isinstance(item, Item) and item.get_property("durability", 1) > 0:
                defense += item.get_property("defense", 0)
        return defense
    
    def get_effective_attack_cooldown(self) -> float:
        p = cast('Player', self)
        base_cooldown = p.attack_cooldown
        effective_agility = p.get_effective_stat('agility')
        speed_modifier = (effective_agility - 10) * 0.01
        effective_cooldown = base_cooldown / (1 + speed_modifier)
        return max(MIN_ATTACK_COOLDOWN, effective_cooldown)

    def can_attack(self, current_time: float) -> bool:
        p = cast('Player', self)
        return p.is_alive and current_time - p.last_attack_time >= self.get_effective_attack_cooldown()
        
    def enter_combat(self, target) -> None:
        p = cast('Player', self)
        if p.runtime_state.combat is None:
            return
        if not p.is_alive: return
        if not target or not getattr(target, 'is_alive', False): return
        if target is p: return
        
        p.runtime_state.combat.in_combat = True
        p.runtime_state.combat.targets.add(target)
        
        # Bi-directional link
        target_state = getattr(target, "runtime_state", None)
        target_combatants = target_state.combat.targets if target_state is not None else getattr(target, "combat_targets", set())
        if hasattr(target, 'enter_combat') and p not in target_combatants:
             target.enter_combat(p)
             
        # Notify minions
        if p.world and p.runtime_state.magic is not None:
            for instance_ids in p.runtime_state.magic.summons.values():
                for instance_id in instance_ids:
                    summon = p.world.get_npc(instance_id)
                    if summon and summon.is_alive and hasattr(summon, 'enter_combat'): 
                        summon.enter_combat(target)

    def exit_combat(self, target: Optional[Any] = None) -> None:
        p = cast('Player', self)
        if p.runtime_state.combat is None:
            return
        if target:
            if target in p.runtime_state.combat.targets:
                p.runtime_state.combat.targets.discard(target)
                if hasattr(target, "exit_combat"):
                    target.exit_combat(p)
        else:
            target_list = list(p.runtime_state.combat.targets)
            for t in target_list:
                p.runtime_state.combat.targets.discard(t)
                if hasattr(t, "exit_combat"):
                    t.exit_combat(p)

        if not p.runtime_state.combat.targets:
            p.runtime_state.combat.in_combat = False
            p.runtime_state.combat.target = None

        if p.world and p.runtime_state.magic is not None:
            for instance_ids in p.runtime_state.magic.summons.values():
                for instance_id in instance_ids:
                    summon = p.world.get_npc(instance_id)
                    if summon and summon.is_alive and hasattr(summon, 'exit_combat'):
                        if target:
                            summon.exit_combat(target)
                        elif not p.runtime_state.combat.in_combat:
                            summon.exit_combat()

    def _add_combat_message(self, message: str) -> None:
        p = cast('Player', self)
        for line in message.strip().splitlines():
            p.combat_messages.append(line)
            while len(p.combat_messages) > p.max_combat_messages: 
                p.combat_messages.pop(0)

    def attack(self, target, world: Optional['World'] = None) -> Dict[str, Any]:
        p = cast('Player', self)
        if p.runtime_state.combat is None:
            return {"message": "Combat is not enabled for this game."}
        if not p.is_alive: return {"message": "You cannot attack while dead."}
        if p.has_effect("Stun"): return {"message": f"{FORMAT_ERROR}You are stunned and cannot attack!{FORMAT_RESET}"}
        if not target or not getattr(target, 'is_alive', False):
            p.exit_combat(target)
            return {"message": f"{FORMAT_ERROR}Your target is already dead.{FORMAT_RESET}"}
        
        equipped_weapon = p.equipment.get("main_hand")
        always_hits = isinstance(equipped_weapon, Item) and equipped_weapon.get_property("always_hit", False)
        weapon_name = equipped_weapon.name if isinstance(equipped_weapon, Item) else "bare hands"
        attack_power = p.get_attack_power()
        
        p.enter_combat(target)
        
        combat_result = CombatSystem.execute_attack(
            attacker=p, defender=target, attack_power=attack_power, 
            weapon_name=weapon_name, always_hit=always_hits, viewer=p
        )
        
        message = combat_result["message"]
        if combat_result["is_hit"] and isinstance(equipped_weapon, Weapon):
            current_durability = equipped_weapon.get_property("durability", 0)
            if current_durability > 0:
                equipped_weapon.update_property("durability", current_durability - ITEM_DURABILITY_LOSS_ON_HIT)
                if current_durability - ITEM_DURABILITY_LOSS_ON_HIT <= 0:
                     message += f"\n{FORMAT_ERROR}Your {weapon_name} breaks!{FORMAT_RESET}"

        p._add_combat_message(message)
        result_message = message

        if combat_result["target_defeated"]:
            p.exit_combat(target)
            quest_update_message = None
            if world: 
                quest_update_message = world.dispatch_event("npc_killed", {"player": p, "npc": target})
            
            gold_dropped = 0
            if hasattr(target, 'loot_table'):
                gold_data = target.loot_table.get("gold_value")
                if gold_data and isinstance(gold_data, dict):
                    if random.random() < gold_data.get("chance", 0.0):
                        qty_range = gold_data.get("quantity", [1, 1])
                        gold_dropped = random.randint(qty_range[0], qty_range[1])
            
            target_level = getattr(target, 'level', 1)
            final_xp_gained = (
                calculate_xp_gain(p.runtime_state.progression.level, target_level, getattr(target, 'max_health', 10))
                if p.runtime_state.progression is not None
                else 0
            )
            if p.runtime_state.gold is None:
                gold_dropped = 0
            current_world = world or p.world
            server = getattr(current_world, "server", None)
            use_party_routing = (
                server is not None
                and hasattr(server, "party_reward_routing_active")
                and server.party_reward_routing_active(p)
            )
            if use_party_routing and (final_xp_gained > 0 or gold_dropped > 0):
                reward_text = str(server.grant_party_rewards(p, {"xp": final_xp_gained, "gold": gold_dropped}))
                if reward_text:
                    result_message += "\n" + reward_text
            else:
                if gold_dropped > 0 and p.runtime_state.gold is not None:
                    p.runtime_state.gold += gold_dropped
                    result_message += f"\n{FORMAT_SUCCESS}You find {gold_dropped} gold.{FORMAT_RESET}"
                if final_xp_gained > 0 and p.runtime_state.progression is not None:
                    result_message += f"\n{FORMAT_SUCCESS}You gain {final_xp_gained} experience!{FORMAT_RESET}"
                    leveled_up, level_up_msg = p.gain_experience(final_xp_gained)
                    if leveled_up and level_up_msg: 
                        result_message += "\n" + level_up_msg

            loot_str = ""
            if current_world and hasattr(target, 'die'):
                 loot_str = format_loot_drop_message(p, target, target.die(current_world))
                 
            if loot_str: result_message += "\n" + loot_str
            if quest_update_message: result_message += "\n" + quest_update_message
            
            p._add_combat_message(result_message.replace(message, "").strip())

        p.last_attack_time = float(time.time()) # Ensure float
        return {"message": result_message}
    
    def take_damage(self, amount: int, damage_type: str = "physical") -> int:
        p = cast('Player', self)
        # Using super() in a mixin is tricky if not inheriting from GameObject directly in the MRO,
        # but since Player inherits from GameObject, we can assume the next class has take_damage.
        # However, type checkers might complain. We rely on the MRO of Player.
        d = super().take_damage(amount, damage_type) # type: ignore
        if p.health <= 0: p.die()
        return d
    
    def die(self, world: Optional['World'] = None) -> None:
        p = cast('Player', self)
        if not p.is_alive: return
        p.health = 0; p.is_alive = False
        if p.runtime_state.combat is not None:
            p.runtime_state.combat.in_combat = False
        
        target_world = world or p.world
        if target_world and hasattr(target_world, 'npcs'):
            for npc in target_world.npcs.values():
                if npc.in_combat and p in npc.combat_targets: npc.exit_combat(self)
        if p.runtime_state.combat is not None:
            p.runtime_state.combat.targets.clear()
        p.active_effects.clear()
        
        local_world = p.world
        if local_world and p.runtime_state.magic is not None:
            all_summon_ids = [inst_id for ids in p.runtime_state.magic.summons.values() for inst_id in ids]
            for instance_id in all_summon_ids:
                summon = local_world.get_npc(instance_id)
                if summon and hasattr(summon, 'despawn'): summon.despawn(local_world, silent=True)
                
            game = getattr(local_world, "game", None)
            if game and hasattr(game, "feature_profile") and game.feature_profile.permadeath_enabled():
                p.inventory.slots = []
                p.equipment = {slot: None for slot in p.equipment.keys()}
                if p.runtime_state.progression is not None:
                    p.runtime_state.progression.level = 1
                    p.runtime_state.progression.experience = 0
                if p.runtime_state.gold is not None:
                    p.runtime_state.gold = 0
                p._add_combat_message(f"{FORMAT_ERROR}PERMADEATH: Your inventory, equipment, and levels have been lost.{FORMAT_RESET}")
                
        if p.runtime_state.magic is not None:
            p.runtime_state.magic.summons = {}

    def respawn(self) -> None:
        p = cast('Player', self)
        p.health = p.max_health
        if p.runtime_state.magic is not None:
            p.runtime_state.magic.mana = p.runtime_state.magic.max_mana
            p.runtime_state.magic.cooldowns.clear()
            p.runtime_state.magic.summons = {}
        p.is_alive = True
        if p.runtime_state.combat is not None:
            p.runtime_state.combat.in_combat = False
            p.runtime_state.combat.targets.clear()
        p.active_effects = []
        p.current_region_id = p.respawn_region_id
        p.current_room_id = p.respawn_room_id
