# engine/ai/ai_manager.py
import time
import threading
import queue
from typing import TYPE_CHECKING, Dict, Any
from engine.config import AI_AMBIENT_ENABLED, AI_AMBIENT_INTERVAL_SECONDS, AI_AMBIENT_TEXT_COLOR, FORMAT_RESET
from engine.ai.llm_interface import LLMInterface

if TYPE_CHECKING:
    from engine.core.game_manager import GameManager

class AIManager:
    def __init__(self, game: 'GameManager'):
        self.game = game
        self.llm_interface = LLMInterface() if AI_AMBIENT_ENABLED else None
        self.result_queue = queue.Queue()
        self.generation_thread = None
        self.interval = AI_AMBIENT_INTERVAL_SECONDS
        self.last_ambient_event_time = time.time() - self.interval

    def _worker_generate_text(self, prompt_key: str, replacements: Dict[str, str], context_stamp: Dict[str, Any]):
        """
        Worker function (runs in a separate thread).
        Generates text and includes timing and context information in the result.
        """
        if self.llm_interface:
            # --- DEBUG: Start timer ---
            start_time = time.time()

            generated_text = self.llm_interface.generate(
                prompt_key=prompt_key,
                replacements=replacements
            )

            # --- DEBUG: End timer and calculate duration ---
            end_time = time.time()
            duration = end_time - start_time

            result_package = {
                "text": generated_text,
                "context_stamp": context_stamp,
                "duration": duration,  # Add duration to the package
                "full_context": replacements.get("context_string", "CONTEXT NOT FOUND") # Pass context for logging
            }
            self.result_queue.put(result_package)

    def update(self) -> str | None:
            return None
    def update2(self) -> str | None:
        """
        The main non-blocking update loop with context validation and debug logging.
        """
        if not self.llm_interface or not self.llm_interface.pipe:
            return None

        try:
            result_package = self.result_queue.get_nowait()
            generated_text = result_package["text"]
            original_context_stamp = result_package["context_stamp"]
            duration = result_package.get("duration", -1.0)
            full_context = result_package.get("full_context", "CONTEXT NOT FOUND")
            
            # --- DEBUG: Print the generation time and context ---
            print("\n" + "="*50)
            print(f"[AI DEBUG] Generation task finished in {duration:.2f} seconds.")
            print("[AI DEBUG] Context used for this generation:")
            print("-" * 20)
            print(full_context)
            print("="*50 + "\n")

            current_context_stamp = self._create_context_stamp()

            if original_context_stamp == current_context_stamp:
                print("[AIManager] Context is valid. Displaying text.")
                if "Error:" not in generated_text:
                    clean_text = generated_text.replace('"', '')
                    return f"{AI_AMBIENT_TEXT_COLOR}{clean_text}{FORMAT_RESET}"
                else:
                    print(f"[AIManager] Worker returned an error: {generated_text}")
            else:
                print("[AIManager] Context has changed. Discarding stale generated text.")

        except queue.Empty:
            pass

        current_time = time.time()
        is_thread_running = self.generation_thread and self.generation_thread.is_alive()

        if not is_thread_running and (current_time - self.last_ambient_event_time > self.interval):
            self.last_ambient_event_time = current_time
            
            print("[AIManager] Timer elapsed. Starting new AI generation thread.")
            
            context_string_for_llm = self._gather_context_for_llm()
            context_stamp_for_validation = self._create_context_stamp()

            self.generation_thread = threading.Thread(
                target=self._worker_generate_text,
                args=("ambient_flavor_text", {"context_string": context_string_for_llm}, context_stamp_for_validation)
            )
            self.generation_thread.start()
        
        return None

    def _create_context_stamp(self) -> Dict[str, Any]:
        """
        Creates a lightweight, comparable snapshot of the critical game state.
        This is used for validation.
        """
        world = self.game.world
        player = world.resolve_reference_player()
        if not player: return {}

        npcs_in_room = world.get_current_room_npcs(player)
        
        stamp = {
            "location": (player.current_region_id, player.current_room_id),
            "time_period": self.game.time_manager.time_data.get('time_period'),
            "weather": self.game.weather_manager.current_weather,
            "in_combat": player.runtime_state.combat.in_combat,
            "npcs_present": tuple(sorted([npc.obj_id for npc in npcs_in_room]))
        }
        return stamp

    def _gather_context_for_llm(self) -> str:
        """
        Collects detailed, human-readable game state information into a string
        to be sent to the LLM.
        """
        world = self.game.world
        player = world.resolve_reference_player()
        room = world.get_current_room(player)
        region = world.get_current_region(player)
        if not player or not room or not region: return "Error."

        if not all([player, room, region]):
            return "Context Error: Game state is incomplete."

        location = f"Location: {room.name} ({region.name})"
        is_outdoors = world.is_location_outdoors(region.obj_id, room.obj_id)
        env_type = "Outdoors" if is_outdoors else "Indoors"
        is_safe = "Safe Zone" if world.is_location_safe(region.obj_id) else "Dangerous Area"

        time_data = self.game.time_manager.time_data
        time_str = f"Time: {time_data.get('time_str', '??:??')} ({time_data.get('time_period', 'Unknown').capitalize()})"
        weather_str = f"Weather: {self.game.weather_manager.current_weather.capitalize()}" if is_outdoors else "Weather: (Indoors)"

        npcs_in_room = world.get_current_room_npcs(player)
        npc_list = [f"{npc.name} ({npc.ai_state.get('current_activity', 'idle')})" for npc in npcs_in_room] if npcs_in_room else ["None"]
        npcs_str = f"NPCs Present: {', '.join(npc_list)}"

        health_percent = (player.health / player.max_health) * 100
        health_status = "Healthy"
        if health_percent < 30: health_status = "Critically Injured"
        elif health_percent < 70: health_status = "Injured"
        player_str = f"Player Status: {health_status}"
        
        combat_str = "Player is in combat." if player.runtime_state.combat.in_combat else "Player is not in combat."

        context_parts = [
            location, f"Environment: {env_type}, {is_safe}", time_str,
            weather_str, npcs_str, player_str, combat_str
        ]
        return "\n".join(context_parts)
