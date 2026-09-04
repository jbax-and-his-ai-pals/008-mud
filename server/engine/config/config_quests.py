# engine/config/config_quests.py
"""
Configuration for the quest system.
"""

MAX_QUESTS_ON_BOARD = 5
QUEST_TYPES_ALL = ["kill", "fetch", "deliver", "instance"]
QUEST_TYPES_NO_INSTANCE = ["kill", "fetch", "deliver"]

QUEST_SYSTEM_CONFIG = {
    "max_quests_on_board": 10,
    "min_quests_on_board": 2,
    "initial_quests_per_type": 1,
    "quest_level_range_player": 3,
    "quest_level_min": 1,
    # Reward Scaling
    "reward_base_xp": 50,
    "reward_xp_per_level": 15,
    "reward_xp_per_quantity": 5,
    "reward_base_gold": 10,
    "reward_gold_per_level": 5,
    "reward_gold_per_quantity": 2,
    # Generation Tuning
    "kill_quest_quantity_base": 3,
    "kill_quest_quantity_per_level": 0.5,
    "fetch_quest_quantity_base": 5,
    "fetch_quest_quantity_per_level": 1,
    # NPC Quest Giver Interests
    "npc_quest_interests": {
        "blacksmith": ["kill", "deliver", "fetch", "kill_nearby_threats", "fetch_materials_metal", "fetch_materials_ore", "fetch_materials_hide", "fetch_simple", "kill_pests"],
        "tavern_keeper": ["kill", "deliver", "fetch", "fetch_ingredients", "fetch_consumables", "kill_pests", "deliver_messages", "fetch_simple"],
        "merchant": ["kill", "deliver", "fetch", "fetch_trade_goods", "deliver_cargo", "kill_bandits", "fetch_materials_rare", "fetch_simple", "deliver_local"],
        "village_elder": ["kill", "deliver", "fetch", "kill_major_threats", "investigate_problems", "deliver_official", "fetch_historical", "kill_nearby_threats", "deliver_local"],
        "guard": ["kill", "deliver", "fetch", "kill_any_hostile", "patrol_area", "deliver_reports", "kill_nearby_threats"],
        "villager": ["kill", "deliver", "fetch", "fetch_simple", "kill_pests", "deliver_local", "fetch_ingredients"]
    },
    # Mapping from broad quest types to specific interests
    "quest_type_interest_map": {
        "kill": ["kill_nearby_threats", "kill_pests", "kill_major_threats", "kill_any_hostile", "kill_bandits"],
        "fetch": ["fetch_materials_metal", "fetch_materials_ore", "fetch_materials_hide", "fetch_ingredients", "fetch_consumables", "fetch_trade_goods", "fetch_materials_rare", "fetch_historical", "fetch_simple"],
        "deliver": ["deliver_messages", "deliver_cargo", "deliver_official", "deliver_local", "deliver_reports"]
    },
    "debug": True
}
