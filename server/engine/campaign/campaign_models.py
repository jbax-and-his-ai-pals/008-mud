# engine/campaign/campaign_models.py
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Any

# The node types CampaignManager._trigger_node acts on: a QUEST node starts its
# quest, whose completion advances the campaign; an END node records the
# outcome. Any other type is reached and then nothing happens, so the campaign
# stays active forever.
CAMPAIGN_NODE_TYPES = ("QUEST", "END")
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
                    conditions=t.get("conditions", {}),
                    chance=t.get("chance", 1.0)
                ))
            
            nodes_dict[nid] = CampaignNode(
                node_id=nid,
                description=ndata.get("description", ""),
                quest_template_id=ndata.get("quest_template_id"),
                node_type=ndata.get("type", "QUEST"),
                transitions=transitions,
                outcome=ndata.get("outcome")
            )
            
        return cls(
            campaign_id=data["campaign_id"],
            name=data["name"],
            description=data["description"],
            start_node_id=data["start_node_id"],
            nodes=nodes_dict
        )