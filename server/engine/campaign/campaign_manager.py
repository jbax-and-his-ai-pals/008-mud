# engine/campaign/campaign_manager.py
import os
import json
import random
import time
from typing import Dict, List, Optional, TYPE_CHECKING, Any
from engine.utils.logger import Logger
from .campaign_models import MAX_CHAIN, CampaignDefinition, CampaignNode

if TYPE_CHECKING:
    from engine.world.world import World
    from engine.player.core import Player

class CampaignManager:
    def __init__(self, world: 'World'):
        self.world = world
        self.content_root = world.content_root
        self.definitions: Dict[str, CampaignDefinition] = {}
        self._load_definitions()

    def _load_definitions(self):
        path = os.path.join(self.content_root, "campaigns")
        if not os.path.exists(path):
            return

        for fname in os.listdir(path):
            if fname.endswith(".json"):
                try:
                    with open(os.path.join(path, fname), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        defn = CampaignDefinition.from_dict(data)
                        self.definitions[defn.campaign_id] = defn
                except Exception as e:
                    Logger.error("CampaignManager", f"Failed to load {fname}: {e}")

    def start_campaign(self, campaign_id: str, player: 'Player', narration: Optional[List[str]] = None) -> bool:
        """`narration`, when given, collects what a cutscene at the start says."""
        if campaign_id not in self.definitions: return False
        
        # Check if already active or completed
        if campaign_id in player.runtime_state.quests.active_campaigns or campaign_id in player.runtime_state.quests.completed_campaigns:
            return False 
            
        definition = self.definitions[campaign_id]
        start_node = definition.nodes.get(definition.start_node_id)
        
        if not start_node: return False
        
        # Initialize State
        player.runtime_state.quests.active_campaigns[campaign_id] = {
            "current_node": definition.start_node_id,
            "history": [],
            "variables": {}
        }
        finite_state = player.runtime_state.quests.finite_adventure
        finite_state.update(
            {
                "campaign_id": campaign_id,
                "status": "active",
                "current_node": definition.start_node_id,
                "started_at": time.time(),
                "completed_at": None,
                "outcome": "",
            }
        )
        
        Logger.info("CampaignManager", f"Started campaign '{definition.name}'")
        
        # Trigger the first node
        lines = self._trigger_node(campaign_id, start_node, player)
        if narration is not None:
            narration.extend(lines)
        return True

    def handle_quest_completion(self, campaign_id: str, node_id: str, resolution: str, player: 'Player') -> str:
        """
        Called by QuestManager when a quest linked to a campaign node completes.
        Calculates the next node based on resolution.
        """
        lines: List[str] = []
        text = self._advance(campaign_id, node_id, resolution, player, lines)
        return "\n".join(([text] if text else []) + lines)

    def advance_from_dialogue(self, campaign_id: str, player: 'Player', narration: Optional[List[str]] = None) -> bool:
        """The `advance_campaign` effect: the player's campaign sits on a DIALOGUE node
        and moves on. Anything else (no such campaign, not active, waiting on a quest)
        does nothing and reports False, so a stray effect cannot skip a quest."""
        definition = self.definitions.get(campaign_id)
        state = player.runtime_state.quests.active_campaigns.get(campaign_id)
        if definition is None or not state:
            return False
        node = definition.nodes.get(state.get("current_node"))
        if node is None or node.node_type != "DIALOGUE":
            return False
        lines: List[str] = []
        text = self._advance(campaign_id, node.node_id, "SUCCESS", player, lines)
        if narration is not None:
            narration.extend([text] if text else [])
            narration.extend(lines)
        return True

    def _advance(self, campaign_id: str, node_id: str, resolution: str, player: 'Player',
                 lines: List[str], depth: int = 0) -> str:
        definition = self.definitions.get(campaign_id)
        if not definition: return ""
        
        current_node = definition.nodes.get(node_id)
        if not current_node: return ""
        
        # Record History
        player_state = player.runtime_state.quests.active_campaigns.get(campaign_id)
        if player_state:
            player_state["history"].append({"node_id": node_id, "resolution": resolution})
        
        # Find Next Node
        next_node_id = None
        transition_text = ""
        
        for transition in current_node.transitions:
            # 1. Check Trigger
            matches = False
            if transition.trigger == resolution:
                matches = True
            elif transition.trigger == "SUCCESS" and "SUCCESS" in resolution:
                matches = True
            elif transition.trigger == "FAILURE" and "FAILURE" in resolution:
                matches = True
                
            if matches:
                # 2. Check RNG (Twists)
                if transition.chance < 1.0 and random.random() > transition.chance:
                    continue 
                    
                next_node_id = transition.target_node_id
                transition_text = transition.narrative_text
                break
        
        if next_node_id:
            # Advance
            if player_state:
                player_state["current_node"] = next_node_id
            finite_state = player.runtime_state.quests.finite_adventure
            finite_state["current_node"] = next_node_id
                
            next_node = definition.nodes.get(next_node_id)
            if next_node:
                lines.extend(self._trigger_node(campaign_id, next_node, player, depth + 1))
                if transition_text:
                    return f"{transition_text}"
                return ""
        
        return "The campaign path ends here."

    def _apply_node_effects(self, node: CampaignNode, player: 'Player') -> List[str]:
        if not node.effects:
            return []
        from engine.dialogue.effects import apply_effects

        report = apply_effects(node.effects, {"player": player, "world": self.world})
        for problem in list(report.failed) + list(report.unknown):
            Logger.warning("CampaignManager", f"node '{node.node_id}' effect did not apply: {problem}")
        return [str(m) for m in report.messages]

    def _trigger_node(self, campaign_id: str, node: CampaignNode, player: 'Player', depth: int = 0) -> List[str]:
        """Acts on reaching `node`; returns any narration its effects produced."""
        lines: List[str] = []
        if node.node_type in ("CUTSCENE", "DIALOGUE"):
            lines.extend(self._apply_node_effects(node, player))
            if node.node_type == "CUTSCENE":
                if depth >= MAX_CHAIN:
                    Logger.error("CampaignManager", f"campaign '{campaign_id}' passed {MAX_CHAIN} nodes without a quest or conversation; stopped at '{node.node_id}'")
                else:
                    text = self._advance(campaign_id, node.node_id, "SUCCESS", player, lines, depth)
                    if text and text != "The campaign path ends here.":
                        lines.append(text)
            return lines
        if node.node_type == "QUEST" and node.quest_template_id:
            # Context allows the quest to report back upon completion
            context = {"campaign_id": campaign_id, "node_id": node.node_id}
            
            # Start the Quest
            self.world.quest_manager.start_quest(node.quest_template_id, player, campaign_context=context)
            
        elif node.node_type == "END":
            Logger.info("CampaignManager", f"Campaign {campaign_id} ended: {node.outcome}")
            completed_at = time.time()
            
            # Move to completed
            if campaign_id in player.runtime_state.quests.active_campaigns:
                data = player.runtime_state.quests.active_campaigns.pop(campaign_id)
                data["outcome"] = node.outcome
                data["end_time"] = completed_at
                player.runtime_state.quests.completed_campaigns[campaign_id] = data
            finite_state = player.runtime_state.quests.finite_adventure
            finite_state.update(
                {
                    "campaign_id": campaign_id,
                    "status": "completed",
                    "current_node": node.node_id,
                    "completed_at": completed_at,
                    "outcome": str(node.outcome or ""),
                }
            )
            server_ref = getattr(self.world, "server", None)
            if server_ref is not None and hasattr(server_ref, "record_finite_adventure_summary"):
                finite_state["last_summary"] = server_ref.record_finite_adventure_summary(
                    player,
                    campaign_id=campaign_id,
                    status="completed",
                    outcome=str(node.outcome or ""),
                    final_node=node.node_id,
                    completed_at=completed_at,
                )
        return lines
