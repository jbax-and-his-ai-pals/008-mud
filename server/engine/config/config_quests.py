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
    # Word pools + patterns for naming procedurally-generated "fetch" quest
    # items (QuestGenerator._instantiate_quest_logic's "fetch_procedural"
    # objective). No default pools are shipped -- when empty, the generator
    # uses the base item template's own authored name instead of inventing
    # one. Content sets provide their own via "quest_generation.procedural_naming".
    "procedural_naming": {
        "adjectives": [],
        "nouns": [],
        "default_name_pattern": "{Noun}",
        "default_base_template_id": "",
    },
    # Text/behavior for the auto-generated entry point and title/description
    # of instance quests (QuestGenerator.generate_instance_quest). No default
    # theme/flavor is shipped; content sets provide their own via
    # "quest_generation.instance_quest".
    "instance_quest": {
        "entry_exit_command": "enter",
        "entry_description_when_visible": "Something unusual has appeared here.",
        "title_pattern": "Quest: {creature_name}",
        "description_pattern": "Deal with the {creature_name}.",
        "default_procedural_theme": "",
    },
    "debug": True
}
