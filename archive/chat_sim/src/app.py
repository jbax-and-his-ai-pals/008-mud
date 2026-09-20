import pygame
import random
import threading
from .config import *
from .ui_kit import Button, TextInput
from .models import Character, ChatMessage
from .storage import load_characters, save_characters
from .llm_client import generate_response

class App:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("AOL Sim 98 - Final Edition")
        self.font = pygame.font.SysFont("arial", 16)
        self.name_font = pygame.font.SysFont("arial", 16, bold=True)
        self.clock = pygame.time.Clock()
        self.running = True
        self.mode = "CHAT"
        
        # Data
        all_loaded = load_characters()
        self.character_pool = []
        self.active_roster = []
        
        # Assign colors cyclicly to ensure max spread in the pool
        for i, char in enumerate(all_loaded):
            char.color = NAME_COLORS[i % len(NAME_COLORS)]
            self.character_pool.append(char)
            
        self.populate_initial_roster()
        
        self.chat_history = [
            ChatMessage("SYSTEM", f"Welcome to the Chat Room! ({len(self.active_roster)} users online)")
        ]
        
        # Simulation State
        self.is_generating = False
        self.current_speaker_name = None
        self.last_turn_time = pygame.time.get_ticks()
        self.turn_delay = 3000
        self.last_roster_check = pygame.time.get_ticks()

        # UI State
        self.scroll_offset = 0  # 0 = locked to bottom. Positive = lines scrolled up.
        self.total_visual_lines = 0 # Tracked for scrollbar math
        self.visible_lines_capacity = 0

        # UI Setup
        self.setup_creator_ui()
        self.setup_chat_ui()

    def populate_initial_roster(self):
        # Try to pick people with unique colors first
        available = self.character_pool.copy()
        selected = []
        used_colors = set()
        
        while len(selected) < NUM_STARTING_CHARS and available:
            # Filter for unique colors
            unique_candidates = [c for c in available if c.color not in used_colors]
            
            if unique_candidates:
                pick = random.choice(unique_candidates)
            else:
                pick = random.choice(available) # No unique colors left, pick anyone
            
            selected.append(pick)
            available.remove(pick)
            used_colors.add(pick.color)
            
        self.active_roster = selected

    def update_roster_logic(self):
        if self.is_generating:
            return

        now = pygame.time.get_ticks()
        if now - self.last_roster_check < ROSTER_CHECK_INTERVAL:
            return

        self.last_roster_check = now
        action = random.choice(["JOIN", "LEAVE", "NOTHING"])
        
        if action == "JOIN":
            self.add_random_person()
        elif action == "LEAVE":
            if len(self.active_roster) > 2:
                leavers = [c for c in self.active_roster if c.messages_sent >= MIN_MSGS_BEFORE_LEAVE]
                if leavers:
                    person = random.choice(leavers)
                    self.active_roster.remove(person)
                    self.chat_history.append(ChatMessage("SYSTEM", f"*** {person.name} has left the room ***"))

    def bot_turn(self):
        if not self.active_roster: return
        
        last_sender = self.chat_history[-1].sender if self.chat_history else None
        candidates = [c for c in self.active_roster if c.name != last_sender]
        if not candidates: candidates = self.active_roster
        
        speaker = random.choice(candidates)
        self.current_speaker_name = speaker.name 
        self.is_generating = True

        def task():
            text = generate_response(speaker, self.chat_history[-HISTORY_LIMIT:])
            speaker.messages_sent += 1
            self.chat_history.append(ChatMessage(speaker.name, text))
            self.is_generating = False
            self.current_speaker_name = None
            
        t = threading.Thread(target=task)
        t.start()

    # (Keep setup_creator_ui, setup_chat_ui, save_character, switch methods exactly as they were)
    def setup_creator_ui(self):
        self.inp_name = TextInput(200, 100, 300, 30, "Name:")
        self.inp_prompt = TextInput(200, 180, 400, 30, "Personality Prompt:")
        self.btn_save = Button(200, 240, 100, 30, "Save", self.save_character)
        self.btn_cancel = Button(320, 240, 100, 30, "Back to Chat", self.switch_to_chat)
        self.creator_ui_elements = [self.inp_name, self.inp_prompt, self.btn_save, self.btn_cancel]

    def setup_chat_ui(self):
        self.btn_create = Button(700, 530, 300, 30, "Create person", self.switch_to_creator)        
        self.btn_add_random = Button(700, 570, 300, 30, "Add random person", self.add_random_person)
        self.chat_ui_elements = [self.btn_create, self.btn_add_random]

    def save_character(self):
        if self.inp_name.text and self.inp_prompt.text:
            new_char = Character(self.inp_name.text, self.inp_prompt.text)
            new_char.color = NAME_COLORS[len(self.character_pool) % len(NAME_COLORS)]
            self.character_pool.append(new_char)
            save_characters(self.character_pool)
            self.active_roster.append(new_char)
            self.chat_history.append(ChatMessage("SYSTEM", f"*** {new_char.name} has entered the room ***"))
            self.inp_name.text = ""
            self.inp_prompt.text = ""
            self.switch_to_chat()

    def add_random_person(self):
        available = [c for c in self.character_pool if c not in self.active_roster]
        if available:
            # COLOR LOGIC: Prefer characters whose colors aren't in the room
            current_colors = {c.color for c in self.active_roster}
            unique_candidates = [c for c in available if c.color not in current_colors]
            
            # If we have unique options, pick one. Otherwise, default to anyone.
            candidates = unique_candidates if unique_candidates else available
            
            new_person = random.choice(candidates)
            new_person.messages_sent = 0
            self.active_roster.append(new_person)
            self.chat_history.append(ChatMessage("SYSTEM", f"*** {new_person.name} has entered the room ***"))

    def switch_to_creator(self):
        self.mode = "CREATOR"
    def switch_to_chat(self):
        self.mode = "CHAT"

    def run(self):
        while self.running:
            self.clock.tick(FPS)
            current_time = pygame.time.get_ticks()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                
                # --- SCROLL WHEEL LOGIC ---
                if self.mode == "CHAT" and event.type == pygame.MOUSEWHEEL:
                    # Scroll up (positive y) -> Increase offset (look further back)
                    # Scroll down (negative y) -> Decrease offset (look closer to present)
                    self.scroll_offset += event.y 
                    
                    # Clamp: cannot scroll below 0 (newest)
                    if self.scroll_offset < 0:
                        self.scroll_offset = 0
                    
                    # Clamp: cannot scroll past the top of history
                    max_scroll = max(0, self.total_visual_lines - self.visible_lines_capacity)
                    if self.scroll_offset > max_scroll:
                        self.scroll_offset = max_scroll

                ui_list = self.creator_ui_elements if self.mode == "CREATOR" else self.chat_ui_elements
                for el in ui_list:
                    el.handle_event(event)

            if self.mode == "CHAT":
                self.update_roster_logic()
                if len(self.active_roster) > 1 and not self.is_generating:
                    if current_time - self.last_turn_time > self.turn_delay:
                        self.bot_turn()
                        self.last_turn_time = current_time
                        self.turn_delay = random.randint(2000, 5000)

            self.screen.fill(COLOR_BG)
            if self.mode == "CREATOR":
                self.draw_creator()
            else:
                self.draw_chat()
            pygame.display.flip()

    def draw_window_frame(self, x, y, w, h, title):
        pygame.draw.rect(self.screen, COLOR_WINDOW, (x, y, w, h))
        pygame.draw.rect(self.screen, (0,0,0), (x, y, w, h), 1)
        pygame.draw.rect(self.screen, COLOR_TITLE_BAR, (x+2, y+2, w-4, 20))
        lbl = self.font.render(title, True, COLOR_TITLE_TEXT)
        self.screen.blit(lbl, (x+5, y+2))

    def draw_creator(self):
        self.draw_window_frame(100, 50, 600, 400, "Character Creator v1.0")
        for el in self.creator_ui_elements:
            el.draw(self.screen, self.font)

    def draw_chat(self):
        # Coordinates
        chat_x, chat_y, chat_w, chat_h = 20, 20, 660, 500
        roster_x, roster_y, roster_w, roster_h = 700, 20, 300, 500
        
        # Draw Frames
        self.draw_window_frame(chat_x, chat_y, chat_w, chat_h, "Chat Room - Main Lobby")
        self.draw_window_frame(roster_x, roster_y, roster_w, roster_h, "Online")

        # --- Draw Roster ---
        y_off = 50
        for char in self.active_roster:
            txt = self.name_font.render(char.name, True, char.color)
            self.screen.blit(txt, (roster_x + 10, y_off))
            y_off += 20

        # --- Text Wrapping & Processing ---
        text_area_width = chat_w - 35
        line_height = 20
        # Footer space for "typing..."
        self.visible_lines_capacity = (chat_h - 40 - 30) // line_height 

        render_queue = []

        # Helper: Robust Wrapper
        # Handles newlines and allows First Line Indent (for the name)
        def process_message_text(text, font, max_width, indent=0):
            # 1. Sanitize: Remove newlines that cause overlap glitches
            clean_text = text.replace('\n', ' ').replace('\r', '')
            
            words = clean_text.split(' ')
            lines = []
            current_line = []
            
            # The first line has less space because of the Name indent
            current_width_limit = max_width - indent 
            
            for word in words:
                test_line = ' '.join(current_line + [word])
                w, h = font.size(test_line)
                
                if w < current_width_limit:
                    current_line.append(word)
                else:
                    # Finish current line
                    if current_line:
                        lines.append(' '.join(current_line))
                    else:
                        # Edge case: Word is longer than the line itself, force split
                        lines.append(word) 
                        
                    current_line = [word]
                    # Subsequent lines get full width
                    current_width_limit = max_width 
            
            if current_line: 
                lines.append(' '.join(current_line))
            return lines

        # --- Process History ---
        for msg in self.chat_history:
            if msg.sender == "SYSTEM":
                wrapped = process_message_text(msg.text, self.font, text_area_width)
                for line in wrapped:
                    render_queue.append((self.font.render(line, True, COLOR_SYSTEM), COLOR_SYSTEM))
            else:
                found = next((c for c in self.character_pool if c.name == msg.sender), None)
                sender_color = found.color if found else COLOR_TEXT
                
                # 1. Render Name (Bold)
                name_str = f"{msg.sender}:"
                name_surf = self.name_font.render(name_str, True, sender_color)
                name_w = name_surf.get_width()
                
                # 2. Wrap Message Content (Indented by Name Width)
                content_lines = process_message_text(msg.text, self.font, text_area_width, indent=name_w + 5)
                
                if not content_lines:
                    # Edge case: Empty message, just show name
                    line_surf = pygame.Surface((text_area_width, line_height), pygame.SRCALPHA)
                    line_surf.blit(name_surf, (0, 0))
                    render_queue.append((line_surf, None))
                else:
                    # 3. Construct First Line (Name + Text)
                    first_text = content_lines[0]
                    first_text_surf = self.font.render(first_text, True, COLOR_TEXT)
                    
                    line_surf = pygame.Surface((text_area_width, line_height), pygame.SRCALPHA)
                    line_surf.blit(name_surf, (0, 0))
                    line_surf.blit(first_text_surf, (name_w + 5, 0)) # +5px padding
                    
                    render_queue.append((line_surf, None))
                    
                    # 4. Construct Remaining Lines (Text Only)
                    for extra_line in content_lines[1:]:
                        render_queue.append((self.font.render(extra_line, True, COLOR_TEXT), None))

        self.total_visual_lines = len(render_queue)

        # --- Scroll & Slice ---
        max_scroll = max(0, self.total_visual_lines - self.visible_lines_capacity)
        if self.scroll_offset > max_scroll:
            self.scroll_offset = max_scroll
            
        end_idx = self.total_visual_lines - self.scroll_offset
        start_idx = max(0, end_idx - self.visible_lines_capacity)
        
        lines_to_draw = render_queue[start_idx:end_idx]

        # --- Render to Screen ---
        y_text = 40 
        for surf, _ in lines_to_draw:
            # Centering vertically in the 20px line helps if fonts vary slightly
            y_centered = y_text + (line_height - surf.get_height()) // 2
            self.screen.blit(surf, (chat_x + 10, y_centered))
            y_text += line_height

        # --- Render Scrollbar ---
        sb_x = chat_x + chat_w - 20
        sb_y = chat_y + 25
        sb_h = (self.visible_lines_capacity * line_height)
        sb_w = 15
        
        pygame.draw.rect(self.screen, COLOR_BUTTON_LIGHT, (sb_x, sb_y, sb_w, sb_h))
        pygame.draw.rect(self.screen, COLOR_BUTTON_DARK, (sb_x, sb_y, sb_w, sb_h), 1)

        if self.total_visual_lines > self.visible_lines_capacity:
            view_ratio = self.visible_lines_capacity / self.total_visual_lines
            thumb_h = max(20, sb_h * view_ratio)
            scroll_ratio = self.scroll_offset / max_scroll if max_scroll > 0 else 0
            thumb_y_offset = (sb_h - thumb_h) * (1 - scroll_ratio)
            
            thumb_rect = (sb_x + 2, sb_y + thumb_y_offset, sb_w - 4, thumb_h)
            pygame.draw.rect(self.screen, COLOR_BUTTON_DARK, thumb_rect)
            pygame.draw.rect(self.screen, COLOR_WINDOW, (sb_x+2, sb_y+thumb_y_offset, sb_w-5, thumb_h-1), 1)

        # --- Footer Area ---
        footer_y = chat_y + chat_h - 30
        pygame.draw.line(self.screen, (150,150,150), (chat_x+2, footer_y), (chat_x+chat_w-2, footer_y))
        
        if self.is_generating:
            lbl_text = f"{self.current_speaker_name} is typing..." if hasattr(self, 'current_speaker_name') and self.current_speaker_name else "Someone is typing..."
            loading = self.font.render(lbl_text, True, (0, 0, 128))
            self.screen.blit(loading, (chat_x + 10, footer_y + 5))

        for el in self.chat_ui_elements:
            el.draw(self.screen, self.font)
