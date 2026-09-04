# engine/core/conversation_history.py
from typing import Dict, Set, List, Any, Optional

class ConversationHistory:
    """
    Manages the player's knowledge base and interaction history with NPCs.
    """
    def __init__(self):
        # Global Vocabulary: Topics the player recognizes (controls Highlighting: Blue vs Yellow)
        self.vocabulary: Set[str] = set(["job", "rumors"])
        
        # Per-NPC state
        # Key: npc_id
        # Value: { "discussed": Set[str], "revealed": Set[str] }
        self.npc_history: Dict[str, Dict[str, Set[str]]] = {}

    def learn_vocabulary(self, topic_id: str) -> bool:
        """Adds a topic to global vocabulary. Returns True if new."""
        if topic_id not in self.vocabulary:
            self.vocabulary.add(topic_id)
            return True
        return False

    def is_in_vocabulary(self, topic_id: str) -> bool:
        return topic_id in self.vocabulary

    def reveal_topic(self, npc_id: str, topic_id: str):
        """The NPC has mentioned this topic. It is now available in their UI list."""
        self._ensure_npc_entry(npc_id)
        self.npc_history[npc_id]["revealed"].add(topic_id)
        self.learn_vocabulary(topic_id) # Revealing implicitly adds to vocabulary

    def mark_discussed(self, npc_id: str, topic_id: str):
        """The player has actively asked about this topic."""
        self._ensure_npc_entry(npc_id)
        self.npc_history[npc_id]["discussed"].add(topic_id)
        # Discussing implicitly reveals it (e.g. if manually typed) and adds to vocab
        self.npc_history[npc_id]["revealed"].add(topic_id) 
        self.learn_vocabulary(topic_id)

    def has_discussed(self, npc_id: str, topic_id: str) -> bool:
        if npc_id not in self.npc_history: return False
        return topic_id in self.npc_history[npc_id]["discussed"]

    def is_revealed(self, npc_id: str, topic_id: str) -> bool:
        if npc_id not in self.npc_history: return False
        return topic_id in self.npc_history[npc_id]["revealed"]

    def _ensure_npc_entry(self, npc_id: str):
        if npc_id not in self.npc_history:
            self.npc_history[npc_id] = {"discussed": set(), "revealed": set()}

    def to_dict(self) -> Dict[str, Any]:
        serializable_npc_history = {}
        for npc_id, data in self.npc_history.items():
            serializable_npc_history[npc_id] = {
                "discussed": list(data["discussed"]),
                "revealed": list(data["revealed"])
            }
            
        return {
            "vocabulary": list(self.vocabulary),
            "npc_history": serializable_npc_history
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationHistory':
        history = cls()
        history.vocabulary = set(data.get("vocabulary", ["job", "rumors"]))
        
        raw_npc_history = data.get("npc_history", {})
        for npc_id, npc_data in raw_npc_history.items():
            history.npc_history[npc_id] = {
                "discussed": set(npc_data.get("discussed", [])),
                "revealed": set(npc_data.get("revealed", []))
            }
        
        return history
