"""Content-authored dialogue graphs: the data model.

A conversation is a small directed graph. Nodes are what an NPC says; choices
are what the player can say back. Content authors the whole thing in
`data/dialogue/*.json`, and an NPC template points at a graph with
`properties.dialogue: "<graph_id>"`.

Shape (one graph per file; `id` defaults to the filename stem):

    {
      "id": "grenda_forge",
      "root": "greeting",
      "nodes": {
        "greeting": {
          "text": "Well met. The forge is hot, but my supplies are low.",
          "choices": [
            {
              "text": "What are you making?",
              "next_node": "making"
            },
            {
              "text": "About that shipment -- I found your ore.",
              "condition": {"kind": "has_item", "item_id": "item_iron_ingot", "quantity": 2},
              "effects": {"adjust_relationship": {"amount": 5}},
              "next_node": "thanks"
            },
            {"text": "Goodbye.", "end": true}
          ]
        },
        "making": {
          "text": "Horseshoes, mostly. Without good iron I cannot forge weapons.",
          "choices": [
            {"text": "Show me how you work the metal.", "next_node": "lesson"},
            {"text": "I see.", "next_node": "greeting"}
          ]
        },
        "lesson": {
          "text": "Watch closely. You will need two bars, and a hot fire.",
          "effects": {"grant_recipe": "forge_iron_dagger"},
          "choices": [{"text": "Thank you.", "end": true}]
        }
      }
    }

Why a graph and not a keyword dict
----------------------------------
The flat `dialog` keyword dict on NPC templates is *kept* -- it is the right
weight for the twenty-six villagers who have one line and no secrets, and
`ask <npc> <topic>` still reads it. What it cannot express is a conversation
where what you may say depends on what you have done: a choice gated on an item,
a reply that teaches a recipe, a negotiation that can go two ways. That is what
this is for.

Conditions are not a new language: they are `engine/conditions.py`, the same
evaluator that gates titles and quest availability (ROADMAP P4 built it once,
for exactly this). Effects are `engine/dialogue/effects.py`.

Mode awareness
--------------
`text` may be a plain string, or a mapping of presentation mode to string
(`{"player": "...", "test": "..."}`) which `presentation.variant` resolves. Test
mode additionally annotates every choice with its condition, check, and effects,
because that is the authoring surface; a player never sees them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class DialogueChoice:
    """One thing the player can say."""

    text: str
    node_id: str = ""
    index: int = 0
    next_node: str = ""
    condition: Any = None
    effects: Dict[str, Any] = field(default_factory=dict)
    check: Optional[Dict[str, Any]] = None
    ends_conversation: bool = False
    aliases: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def label(self) -> str:
        return str(self.text or "").strip()


@dataclass
class DialogueNode:
    """One thing an NPC says, and the replies it offers."""

    node_id: str
    text: Any = ""
    choices: List[DialogueChoice] = field(default_factory=list)
    effects: Dict[str, Any] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)

    def choice(self, index: int) -> Optional[DialogueChoice]:
        if 0 <= index < len(self.choices):
            return self.choices[index]
        return None


@dataclass
class DialogueGraph:
    """A whole conversation, loaded from one content file."""

    graph_id: str
    root: str
    nodes: Dict[str, DialogueNode] = field(default_factory=dict)
    source: str = ""

    def node(self, node_id: str) -> Optional[DialogueNode]:
        return self.nodes.get(str(node_id))

    def node_ids(self) -> List[str]:
        return sorted(self.nodes)

    def references(self) -> List[tuple[str, str, str]]:
        """(node_id, kind, target) for every node-to-node link in the graph.

        Used by content validation to find a `next_node` that does not exist
        before anyone walks into it mid-conversation.
        """
        found: List[tuple[str, str, str]] = []
        for node in self.nodes.values():
            for choice in node.choices:
                if choice.next_node:
                    found.append((node.node_id, "next_node", choice.next_node))
                check = choice.check or {}
                for key in ("success_node", "fail_node"):
                    target = str(check.get(key, "") or "").strip()
                    if target:
                        found.append((node.node_id, key, target))
        return found
