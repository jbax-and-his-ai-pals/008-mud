# engine/core/quest_generation/rewards.py
from typing import Dict

def calculate_rewards(quest_type: str, objective_data: Dict, config: Dict) -> Dict[str, int]:
    difficulty = objective_data.get("difficulty_level", 1)
    quantity = objective_data.get("required_quantity", 1)
    
    xp = config.get("reward_base_xp", 50) + (difficulty * config.get("reward_xp_per_level", 15))
    gold = config.get("reward_base_gold", 10) + (difficulty * config.get("reward_gold_per_level", 5))
    
    if quest_type in ["kill", "fetch"]:
        xp += quantity * config.get("reward_xp_per_quantity", 5)
        gold += quantity * config.get("reward_gold_per_quantity", 2)
        
    return {"xp": int(xp), "gold": int(gold)}
