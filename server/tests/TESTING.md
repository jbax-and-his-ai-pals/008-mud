## CORE MECHANICS

* tests/test_mechanics.py

[TestMechanics]
test_movement
test_inventory_add_remove
test_combat_damage
test_command_processor

* tests/test_command_parsing.py

[TestCommandParsing]
test_aliases
test_case_insensitivity
test_unknown_command

* tests/test_player_stats.py

[TestPlayerStats]
test_health_regeneration
test_mana_regeneration
test_xp_rollover
test_stat_caps

* tests/test_persistence.py

[TestPersistence]
test_save_load_roundtrip

* tests/test_persistence_extended.py

[TestPersistenceExtended]
test_skills_save_load

## COMBAT SYSTEM

* tests/test_combat.py

[TestCombat]
test_physical_damage_math
test_magic_resistance
test_dot_tick
test_stat_buff_application

* tests/test_combat_extended.py

[TestCombatExtended]
test_physical_damage_math
test_magic_resistance
test_dot_tick
test_stat_buff_application

* tests/test_combat_advanced.py

[TestCombatAdvanced]
test_level_up_mechanics
test_equipment_bonuses
test_death_and_respawn_cycle

* tests/test_combat_mechanics.py

[TestCombatMechanics]
test_attack_cooldown
test_combat_state_exit
test_friendly_fire_prevention

* tests/test_magic.py

[TestMagic]
test_learn_and_forget_spell
test_cast_requirements
test_cooldowns

* tests/test_magic_effects.py

[TestMagicEffects]
test_summon_cap
test_buff_duration
test_debuff_application

* tests/test_magic_resistance.py

[TestMagicResistance]
test_magic_resist_mitigation
test_elemental_resistance_percent

* tests/test_status_effects.py

[TestStatusEffects]
test_stat_buff_application_and_expiration
test_dot_application
ITEMS & INVENTORY

* tests/test_inventory_extended.py

[TestInventoryExtended]
test_encumbrance_limit
test_stack_merging
test_stack_splitting

* tests/test_containers.py

[TestContainers]
test_locked_container
test_put_get_container

* tests/test_consumables.py

[TestConsumables]
test_healing_potion
test_multi_use_item
test_durability_loss

* tests/test_world_item_persistence.py

[TestWorldItemPersistence]
test_dropped_items_persist
AI & NPCs

* tests/test_ai.py

[TestAI]
test_hostile_aggression
test_healer_behavior
test_wander_movement

* tests/test_advanced_ai.py

[TestAdvancedAI]
test_npc_fleeing
test_minion_following
test_minion_combat_assist

* tests/test_npc_schedules.py

[TestNPCSchedules]
test_schedule_transition

* tests/test_interaction.py

[TestInteraction]
test_merchant_buy
test_merchant_sell
test_dialogue_ask

* tests/test_knowledge_logic.py

[TestKnowledgeLogic]
test_conditional_response
WORLD & ENVIRONMENT

* tests/test_environment.py

[TestEnvironment]
test_time_flow
test_weather_command

* tests/test_navigation.py

[TestNavigation]
test_pathfinding_astar
test_locked_room_entry

* tests/test_world_generation.py

[TestWorldGeneration]
test_generate_region_structure
test_invalid_theme

* tests/test_spawner.py

[TestSpawner]
test_spawn_caps_and_cooldowns
QUESTS & PROGRESSION

* tests/test_quests.py

[TestQuests]
test_quest_lifecycle_kill
test_quest_fetch_mechanics
test_quest_deliver_mechanics

* tests/test_quest_instances.py

[TestQuestInstances]
test_instantiation_and_cleanup

* tests/test_collections.py

[TestCollections]
test_turn_in_and_completion

* tests/test_skill_system.py

[TestSkillSystem]
test_xp_curve
test_player_skill_progression
test_skill_check_math
test_lockpicking_mechanics
test_crafting_skill_check

## ECONOMY & CRAFTING

* tests/test_crafting.py

[TestCrafting]
test_crafting_station_logic
test_repair_mechanic

* tests/test_economy_repair.py

[TestEconomyRepair]
test_repair_costs_and_logic
test_repair_too_poor

* tests/test_mercantile_logic.py

[TestMercantileLogic]
test_vendor_rejects_invalid_type
test_vendor_buys_valid_type

* tests/test_gambling.py

[TestGambling]
test_blackjack_math
test_betting_flow
test_blackjack_state
