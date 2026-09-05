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
    # NPC Quest Giver Interests: which quest types/tags a given NPC template
    # is willing to offer, used as a fallback when a template doesn't declare
    # its own properties.quest_interests. Content sets provide their own via
    # the "quest_generation.npc_quest_interests" ruleset section -- the
    # engine ships no default here since template ids and interest tags are
    # entirely content-defined vocabulary.
    "npc_quest_interests": {},
    "debug": True
}
