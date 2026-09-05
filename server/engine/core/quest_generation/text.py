# engine/core/quest_generation/text.py
from typing import Any, Dict, Optional

# Neutral fallback wording, used only when a content set doesn't supply its
# own via the "quest_generation.text_templates" ruleset section.
DEFAULT_TEXT_TEMPLATES: Dict[str, Dict[str, str]] = {
    "kill": {
        "title": "Objective: {target_name_plural}",
        "description": "{giver_name} needs {quantity} {target_name_plural} dealt with, found in {location_description}."
    },
    "fetch": {
        "title": "Gather: {item_name_plural}",
        "description": "{giver_name} needs {quantity} {item_name_plural}. They believe {source_enemy_name_plural} in {location_description} may have them."
    },
    "deliver": {
        "title": "Delivery: {item_to_deliver_name} to {recipient_name}",
        "description": "{giver_name} asks you to deliver a {item_to_deliver_name} to {recipient_name}, who can be found in {recipient_location_description}."
    }
}


def format_quest_text(
    text_type: str, quest_instance: Dict[str, Any], giver_npc, templates: Optional[Dict[str, Dict[str, str]]] = None
) -> str:
    templates = templates if templates is not None else DEFAULT_TEXT_TEMPLATES
    q_type = quest_instance.get("type", "")
    objective = quest_instance.get("objective", {})
    template = templates.get(q_type, {}).get(text_type, "Quest")

    details = {
        "giver_name": giver_npc.name,
        "quantity": objective.get("required_quantity"),
        "target_name_plural": objective.get("target_name_plural"),
        "location_description": objective.get("location_hint"),
        "item_name_plural": objective.get("item_name_plural"),
        "source_enemy_name_plural": objective.get("source_enemy_name_plural"),
        "item_to_deliver_name": objective.get("item_to_deliver_name"),
        "recipient_name": objective.get("recipient_name"),
        "recipient_location_description": objective.get("recipient_location_description")
    }
    valid_details = {k: v for k, v in details.items() if v is not None}
    try: return template.format(**valid_details)
    except KeyError: return "Task"
