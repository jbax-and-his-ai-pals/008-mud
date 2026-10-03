# engine/core/quests/closing.py
"""What a finished quest says as it closes.

A stage can end on something a character *says* (`completion_dialogue`, shown in quotes) and/or on
something that is *told* (`completion_narration`, shown plain: "The mayor takes the package, and
something in it begins to hum."). Narration used to have to be written as dialogue, and so appeared
as a quotation nobody spoke.
"""

from __future__ import annotations

from typing import Any, Dict

from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS
from engine.utils.messages import message


def final_stage_field(quest_data: Any, key: str) -> str:
    """`key` on the stage a quest is finishing on, or "" when it has none."""
    stages = quest_data.get("stages", []) if isinstance(quest_data, dict) else []
    index = quest_data.get("current_stage_index", 0) if isinstance(quest_data, dict) else 0
    if not isinstance(stages, list) or isinstance(index, bool) or not isinstance(index, int):
        return ""
    if not (0 <= index < len(stages)) or not isinstance(stages[index], dict):
        return ""
    return str(stages[index].get(key, "") or "")


def closing_text(quest_data: Any, speech: str = "") -> str:
    """The narration (plain), then the speech (quoted). `speech` is what to say when the stage names
    none of its own; with narration and no speech, nothing is quoted."""
    narration = final_stage_field(quest_data, "completion_narration")
    spoken = final_stage_field(quest_data, "completion_dialogue") or speech
    lines = []
    if narration:
        lines.append(narration)
    if spoken and not (narration and not final_stage_field(quest_data, "completion_dialogue")):
        lines.append(f'{FORMAT_HIGHLIGHT}"{spoken}"{FORMAT_RESET}')
    return "\n".join(lines)


def ready_instruction(quest_data: Any, default: str) -> str:
    """What to tell the player once a stage's objective is done: the stage's own `ready_text`, or `default`
    ("Report back to Ryn.") for a stage that names none. A stage can say it for itself when the person to
    report to is nobody the player has met."""
    return final_stage_field(quest_data, "ready_text") or default


def completion_report(title: Any, closing: str = "", rewards: Any = "", world: Any = None) -> str:
    """What handing a quest in reads like, wherever it is handed in (a conversation, `give`, `talk ... complete`):
    the title, what the stage says as it closes, then what it earned (and any level it brought) as a paragraph
    of its own, so a client can show the story slowly and the numbers at once."""
    text = f"{FORMAT_SUCCESS}{message(world, 'quest_complete', title=title)}{FORMAT_RESET}"
    if closing:
        text += "\n" + closing
    if rewards:
        text += "\n\n" + str(rewards)
    return text
