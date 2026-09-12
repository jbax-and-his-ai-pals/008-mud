# engine/core/knowledge_manager.py
import json
import os
import re
import uuid
from typing import Dict, Any, List, Set, Optional, Tuple, TYPE_CHECKING
from engine.config import FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_CATEGORY, FORMAT_ERROR

if TYPE_CHECKING:
    from engine.player import Player
    from engine.npcs.npc import NPC

class KnowledgeManager:
    def __init__(self, world, warning_sink=None):
        self.world = world
        self.content_root = world.content_root
        self.topics: Dict[str, Any] = {}
        # Topic ids always available to ask any NPC about, regardless of
        # conversation history. No default here -- a content set declares
        # its own via a top-level "__common_topics__" key in topics.json.
        self.common_topics: List[str] = []
        self._warning_sink = warning_sink
        self._load_topics()

    def _emit_warning(self, code: str, message: str) -> None:
        if callable(self._warning_sink):
            self._warning_sink(code, message, "content")
            return
        print(message)

    def _load_topics(self):
        path = os.path.join(self.content_root, "knowledge", "topics.json")
        if not os.path.exists(os.path.dirname(path)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            
        if os.path.exists(path):
            try:
                with open(path, 'r') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    common = data.pop("__common_topics__", None)
                    self.topics = data
                    if isinstance(common, list):
                        self.common_topics = [str(t) for t in common if isinstance(t, str)]
                else:
                    self.topics = {}
            except Exception as e:
                self._emit_warning(
                    "content.topics.load_error",
                    f"Error loading topics: {e}",
                )
                self.topics = {}
        else:
            self._emit_warning(
                "content.topics.missing",
                "Warning: topics.json not found.",
            )

    def resolve_topic_id(self, input_text: str) -> Optional[str]:
        """
        Resolves user input (e.g., 'caravan', 'missing supplies') to a Topic ID (e.g., 'missing_supplies').
        """
        raw = input_text.lower().strip()
        
        # 1. Direct ID match
        if raw in self.topics: return raw
        
        # 2. Display Name & Keyword match
        for tid, data in self.topics.items():
            if data.get("display_name", "").lower() == raw: return tid
            for kw in data.get("keywords", []):
                if kw.lower() == raw: return tid
                
        # 3. Partial match (Startswith)
        for tid, data in self.topics.items():
            if data.get("display_name", "").lower().startswith(raw): return tid
            
        return None

    def get_response(self, npc: 'NPC', topic_id: str, player: 'Player') -> Optional[str]:
        if "custom_dialog" in npc.properties and topic_id in npc.properties["custom_dialog"]:
            return npc.properties["custom_dialog"][topic_id]

        topic_data = self.topics.get(topic_id)
        if not topic_data:
            # Topic exists in code/parser but not in database
            return None

        valid_responses = []
        for resp in topic_data.get("responses", []):
            conditions = resp.get("conditions", {})
            if self._check_conditions(npc, player, conditions):
                valid_responses.append(resp)

        if not valid_responses:
            return None

        # Sort by priority
        valid_responses.sort(key=lambda x: x.get("priority", 0), reverse=True)
        chosen_response = valid_responses[0]
        
        # Process Effects
        effect_messages = self._process_response_effects(chosen_response, player)
        if effect_messages:
            return f"\"{chosen_response['text']}\"\n" + "\n".join(effect_messages)
        return f"\"{chosen_response['text']}\""

    def _check_conditions(self, npc, player, conditions: Dict) -> bool:
        for key, val in conditions.items():
            if key == "region_id" and npc.current_region_id != val: return False
            if key == "faction" and npc.faction != val: return False
            if key == "template_id" and npc.template_id != val: return False
            
            # Knowledge/Conversation State Check
            if key == "knowledge_state":
                topic = val.get("topic_id")
                state_req = val.get("state") # "known", "discussed", "revealed"
                
                if state_req == "known":
                    if not player.conversation.is_in_vocabulary(topic): return False
                elif state_req == "discussed":
                    if not player.conversation.has_discussed(npc.obj_id, topic): return False
                elif state_req == "revealed":
                    if not player.conversation.is_revealed(npc.obj_id, topic): return False

            # Campaign State Check
            if key == "campaign_state":
                if player.runtime_state.quests is None: return False
                c_id = val.get("campaign_id")
                state_req = val.get("state") # "active", "completed", "not_active"

                is_active = c_id in player.runtime_state.quests.active_campaigns
                is_completed = c_id in player.runtime_state.quests.completed_campaigns

                if state_req == "active" and not is_active: return False
                if state_req == "completed" and not is_completed: return False
                if state_req == "not_active" and (is_active or is_completed): return False

            # Campaign Outcome Check -- which END node a completed campaign
            # reached, not just whether it's completed.
            if key == "campaign_outcome":
                if player.runtime_state.quests is None: return False
                c_id = val.get("campaign_id")
                data = player.runtime_state.quests.completed_campaigns.get(c_id)
                if not data or data.get("outcome") != val.get("outcome"): return False

            # Quest State Check
            if key == "quest_state":
                if player.runtime_state.quests is None: return False
                req_state = val.get("state")
                from_this = val.get("from_this_npc", False)
                pattern = val.get("id_pattern")
                found_match = False

                logs_to_check = []
                if req_state == "active":
                    logs_to_check = [player.runtime_state.quests.active]
                elif req_state == "completed":
                    logs_to_check = [player.runtime_state.quests.completed, player.runtime_state.quests.archived]
                
                for log in logs_to_check:
                    for q_id, q_data in log.items():
                        if from_this and q_data.get("giver_instance_id") != npc.obj_id: continue
                        if pattern and pattern not in q_id: continue
                        if req_state == "active" and q_data.get("state") not in ["active", "ready_to_complete"]: continue
                        found_match = True; break
                    if found_match: break
                
                if not found_match: return False

        return True

    def parse_and_highlight(self, text: str, player: 'Player', source_npc: Optional['NPC'] = None, exclude_topic_id: Optional[str] = None) -> str:
        """
        Scans text for known topics and wraps them in clickable command tags.
        """
        if not text: return ""
        
        scannable = []
        for tid, data in self.topics.items():
            # Skip if this is the topic we are currently viewing
            if tid == exclude_topic_id:
                continue

            # Add Display Name
            scannable.append((data.get("display_name", tid), tid))
            # Add Keywords (aliases)
            for kw in data.get("keywords", []):
                scannable.append((kw, tid))
        
        # Sort by length descending to match longest phrases first
        scannable.sort(key=lambda x: len(x[0]), reverse=True)
        
        processed_text = text
        replacements = {}
        
        for phrase, topic_id in scannable:
            if len(phrase) < 3: continue 

            pattern_str = r"\b" + re.escape(phrase) + r"\b"
            pattern = re.compile(pattern_str, re.IGNORECASE)
            
            if pattern.search(processed_text):
                was_known = player.conversation.is_in_vocabulary(topic_id)
                
                if source_npc:
                    player.conversation.reveal_topic(source_npc.obj_id, topic_id)
                else:
                    player.conversation.learn_vocabulary(topic_id)
                
                color = FORMAT_HIGHLIGHT if was_known else FORMAT_CATEGORY
                
                def replace_func(match):
                    original_word = match.group(0)
                    token = f"__TOPIC_{uuid.uuid4().hex}__"
                    
                    # Use the original word for the command to maintain immersion
                    # The Resolve logic will map it back to the ID
                    topic_arg = original_word
                    
                    cmd = f"ask {topic_arg}"
                    if source_npc:
                        cmd = f"ask {source_npc.name} {topic_arg}"
                        
                    final_tag = f"[[CMD:{cmd}]]{color}{original_word}{FORMAT_RESET}[[/CMD]]"
                    replacements[token] = final_tag
                    return token
                
                processed_text = pattern.sub(replace_func, processed_text)
        
        for token, tag in replacements.items():
            processed_text = processed_text.replace(token, tag)
                
        return processed_text

    def get_topics_for_npc(self, npc: 'NPC', player: 'Player') -> Tuple[List[str], List[str]]:
        unasked = []
        asked = []
        
        available_ids = set(self.common_topics)
        if npc.obj_id in player.conversation.npc_history:
            available_ids.update(player.conversation.npc_history[npc.obj_id]["revealed"])

        for topic_id in available_ids:
            if topic_id in self.topics:
                topic_data = self.topics[topic_id]
                has_valid_response = False
                for resp in topic_data.get("responses", []):
                    if self._check_conditions(npc, player, resp.get("conditions", {})):
                        has_valid_response = True
                        break
                
                if has_valid_response:
                    if player.conversation.has_discussed(npc.obj_id, topic_id):
                        asked.append(topic_id)
                    else:
                        unasked.append(topic_id)
        
        unasked.sort(key=lambda t: self.topics[t].get("display_name", t))
        asked.sort(key=lambda t: self.topics[t].get("display_name", t))
        
        return unasked, asked

    def _apply_local_reward_bundle(self, player: 'Player', rewards: Dict[str, Any]) -> List[str]:
        messages: List[str] = []
        xp = int(rewards.get("xp", 0) or 0)
        gold = int(rewards.get("gold", 0) or 0)

        if xp > 0 and player.runtime_state.progression is not None:
            player.gain_experience(xp)
            messages.append(f"You gain {xp} XP.")
        if gold > 0 and player.runtime_state.gold is not None:
            player.runtime_state.gold += gold
            messages.append(f"You receive {gold} {self.world.currency_name().capitalize()}.")

        if "items" in rewards:
            from engine.items.item_factory import ItemFactory

            for item_data in rewards.get("items", []):
                item_id = str(item_data.get("item_id", "")).strip()
                quantity = int(item_data.get("quantity", 1) or 1)
                if item_id == "" or quantity <= 0:
                    continue
                for _ in range(quantity):
                    item = ItemFactory.create_item_from_template(item_id, self.world)
                    if item is None:
                        continue
                    player.inventory.add_item(item)
                    messages.append(f"You receive {item.name}.")

        generated_item_data = rewards.get("generated_item_data")
        if isinstance(generated_item_data, dict):
            from engine.items.item_factory import ItemFactory

            item = ItemFactory.from_dict(generated_item_data, self.world)
            if item is not None:
                player.inventory.add_item(item)
                messages.append(f"You receive {item.name}.")
        return messages

    def _process_response_effects(self, response_data: Dict, player: 'Player') -> List[str]:
        """Handles side effects defined in topics.json responses."""
        effects = response_data.get("effects", {})
        messages: List[str] = []
        server = getattr(self.world, "server", None)
        
        # 1. Start Quest
        if "start_quest" in effects:
            quest_id = effects["start_quest"]
            if self.world.quest_manager:
                self.world.quest_manager.start_quest(quest_id, player)
            
        # 2. Start Campaign
        if "start_campaign" in effects:
            campaign_id = effects["start_campaign"]
            if self.world.campaign_manager:
                self.world.campaign_manager.start_campaign(campaign_id, player)
            
        # 3. Give Item
        if "give_item" in effects:
            from engine.items.item_factory import ItemFactory

            item_id = effects["give_item"]
            item = ItemFactory.create_item_from_template(item_id, self.world)
            if item:
                recipient = player
                if server is not None and hasattr(server, "distribute_party_loot"):
                    recipient, _note = server.distribute_party_loot(player, item)
                recipient.inventory.add_item(item)
                if recipient is player:
                    messages.append(f"You receive {item.name}.")
                else:
                    messages.append(f"{recipient.name} receives {item.name}.")

        # 4. Give Gold
        if "give_gold" in effects:
            amount = int(effects.get("give_gold", 0) or 0)
            if amount > 0:
                if server is not None and hasattr(server, "grant_party_gold"):
                    routing = str(server.grant_party_gold(player, amount))
                    if routing:
                        messages.append(f"Rewards: {routing}")
                elif player.runtime_state.gold is not None:
                    player.runtime_state.gold += amount
                    messages.append(f"You receive {amount} {self.world.currency_name().capitalize()}.")

        # 5. Give Structured Rewards
        structured_rewards = effects.get("give_rewards")
        if isinstance(structured_rewards, dict):
            if server is not None and hasattr(server, "grant_party_rewards"):
                reward_text = str(server.grant_party_rewards(player, structured_rewards))
                if reward_text:
                    messages.append(reward_text)
            else:
                messages.extend(self._apply_local_reward_bundle(player, structured_rewards))

        return messages
