"""Content-authored conversations (ROADMAP P5).

`data/dialogue/*.json` holds graphs; NPC templates point at one with
`properties.dialogue`. Conditions come from `engine/conditions.py` and effects
from `engine/dialogue/effects.py`, so a conversation can ask the same questions
and do the same things as titles, quests, and topic responses.

The flat `dialog` keyword dict on NPC templates is deliberately still here and
still works -- see `engine/dialogue/graph.py` for why both exist.
"""

from engine.dialogue.graph import DialogueChoice, DialogueGraph, DialogueNode
from engine.dialogue.manager import (
    DIALOGUE_DIRECTORY,
    NPC_GRAPH_KEY,
    DialogueManager,
    DialogueSession,
    parse_graph,
    structural_issues,
)

__all__ = [
    "DIALOGUE_DIRECTORY",
    "NPC_GRAPH_KEY",
    "DialogueChoice",
    "DialogueGraph",
    "DialogueManager",
    "DialogueNode",
    "DialogueSession",
    "parse_graph",
    "structural_issues",
]
