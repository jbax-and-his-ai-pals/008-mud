# engine/campaign/campaign_models.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

# The node types CampaignManager._trigger_node acts on: a QUEST node starts its
# quest, whose completion advances the campaign; a CUTSCENE node applies its
# `effects` and moves straight on; a DIALOGUE node applies its `effects` and
# waits for an `advance_campaign` effect (a conversation, a trigger); an END node
# records the outcome. Any other type is reached and then nothing happens, so the
# campaign stays active forever.
CAMPAIGN_NODE_TYPES = ("QUEST", "DIALOGUE", "CUTSCENE", "END")
# How many nodes one advance may pass through without a quest or a conversation
# between them; a loop of cutscenes stops here instead of hanging the server.
MAX_CHAIN = 20
# The resolutions a quest completion reports (quests/manager.py complete_quest,
# commands/interaction/npcs.py, dialogue/runner.py). A transition's trigger is
# matched against one; "SUCCESS" also matches both variants. Nothing reports a
# failure, so a "FAILURE" trigger never fires.
CAMPAIGN_TRIGGERS = ("SUCCESS", "PEACEFUL_SUCCESS", "VIOLENT_SUCCESS")

@dataclass
class CampaignTransition:
    trigger: str  # e.g., "VIOLENT_SUCCESS", "SUCCESS", "FAILURE"
    target_node_id: str
    narrative_text: str = ""
    pace: Any = None   # how fast a client reveals `narrative_text` (a name or characters per second)
    conditions: Dict[str, Any] = field(default_factory=dict) # e.g. {"reputation_min": 50}
    chance: float = 1.0 # 1.0 = 100% chance (for RNG twists)

@dataclass
class CampaignNode:
    node_id: str
    description: str
    # If type is "QUEST", this ID is used to generate the actual gameplay object
    quest_template_id: Optional[str] = None
    node_type: str = "QUEST" # QUEST, DIALOGUE, CUTSCENE, END
    transitions: List[CampaignTransition] = field(default_factory=list)
    outcome: Optional[str] = None # For END nodes
    # Applied on reaching a CUTSCENE or DIALOGUE node, by the same vocabulary a
    # conversation uses (dialogue/effects.py).
    effects: Dict[str, Any] = field(default_factory=dict)

@dataclass
class CampaignDefinition:
    campaign_id: str
    name: str
    description: str
    start_node_id: str
    nodes: Dict[str, CampaignNode] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CampaignDefinition':
        nodes_dict = {}
        for nid, ndata in data.get("nodes", {}).items():
            transitions = []
            for t in ndata.get("transitions", []):
                transitions.append(CampaignTransition(
                    trigger=t.get("trigger", "SUCCESS"),
                    target_node_id=t.get("target_node_id"),
                    narrative_text=t.get("narrative_text", ""),
                    pace=t.get("pace"),
                    conditions=t.get("conditions", {}),
                    chance=t.get("chance", 1.0)
                ))
            
            nodes_dict[nid] = CampaignNode(
                node_id=nid,
                description=ndata.get("description", ""),
                quest_template_id=ndata.get("quest_template_id"),
                node_type=ndata.get("type", "QUEST"),
                transitions=transitions,
                outcome=ndata.get("outcome"),
                effects=ndata.get("effects") if isinstance(ndata.get("effects"), dict) else {}
            )
            
        return cls(
            campaign_id=data["campaign_id"],
            name=data["name"],
            description=data["description"],
            start_node_id=data["start_node_id"],
            nodes=nodes_dict
        )