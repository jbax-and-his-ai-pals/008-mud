# engine/ui/inventory_menu.py
import pygame
from typing import Tuple, Optional, List, Any
from engine.config import (
    SCREEN_WIDTH, SCREEN_HEIGHT, BG_COLOR, TEXT_COLOR, 
    FORMAT_HIGHLIGHT, FORMAT_CATEGORY, DEFAULT_COLORS
)
from engine.ui.icons import get_item_icon, ICON_SIZE

# Configuration
PADDING = 10
SLOT_BG_COLOR = (40, 40, 50)
SLOT_BORDER_COLOR = (80, 80, 90)
HOVER_COLOR = (60, 60, 80)

class InventoryMenu:
    def __init__(self, game):
        self.game = game
        self.font = pygame.font.SysFont("arial", 16)
        self.title_font = pygame.font.SysFont("arial", 24, bold=True)
        self.mode = "hybrid" # Options: "text", "icon", "hybrid"
        self.scroll_offset = 0
        self.active_hotspots: List[Tuple[pygame.Rect, str]] = [] # (Rect, command_string)

    def render(self, screen: pygame.Surface, rect: pygame.Rect):
        """
        Draws the inventory menu within the given rect.
        """
        # Clear hotspots from previous frame
        self.active_hotspots = []
        
        # Draw Background
        pygame.draw.rect(screen, (20, 20, 25), rect)
        pygame.draw.rect(screen, (100, 100, 100), rect, 2)
        
        # Title
        title_surf = self.title_font.render(f"INVENTORY ({self.mode.upper()}) - Press 'I' to close", True, (255, 215, 0))
        screen.blit(title_surf, (rect.x + PADDING, rect.y + PADDING))
        
        # Header Info (Weight/Slots)
        player = self.game.world.resolve_reference_player() if self.game and self.game.world else None
        if not player: return
        
        inv = player.inventory
        weight_txt = f"Weight: {inv.get_total_weight():.1f}/{inv.max_weight}"
        slots_txt = f"Slots: {inv.max_slots - inv.get_empty_slots()}/{inv.max_slots}"
        
        info_surf = self.font.render(f"{weight_txt} | {slots_txt}", True, (200, 200, 200))
        screen.blit(info_surf, (rect.right - info_surf.get_width() - PADDING, rect.y + PADDING + 5))
        
        # Content Area
        content_rect = pygame.Rect(
            rect.x + PADDING, 
            rect.y + PADDING * 4, 
            rect.width - PADDING * 2, 
            rect.height - PADDING * 5
        )
        
        # Render based on mode
        if self.mode == "text":
            self._render_text_mode(screen, content_rect, inv)
        elif self.mode == "icon":
            self._render_icon_mode(screen, content_rect, inv)
        else:
            self._render_hybrid_mode(screen, content_rect, inv)

    def _render_text_mode(self, screen, rect, inv):
        y = rect.y
        line_height = 25
        
        for slot in inv.slots:
            if not slot.item: continue
            
            item = slot.item
            name = f"{item.name} (x{slot.quantity})" if slot.quantity > 1 else item.name
            
            # Draw Strip
            row_rect = pygame.Rect(rect.x, y, rect.width, line_height)
            
            # Check Hover
            mouse_pos = pygame.mouse.get_pos()
            if row_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, HOVER_COLOR, row_rect)
            
            text_surf = self.font.render(name, True, TEXT_COLOR)
            screen.blit(text_surf, (rect.x + 5, y + 2))
            
            # Add Hotspot
            self.active_hotspots.append((row_rect, f"look {item.name}"))
            
            y += line_height

    def _render_icon_mode(self, screen, rect, inv):
        cols = rect.width // (ICON_SIZE + PADDING)
        x, y = rect.x, rect.y
        
        for i, slot in enumerate(inv.slots):
            item = slot.item
            
            slot_rect = pygame.Rect(x, y, ICON_SIZE, ICON_SIZE)
            
            # Check Hover
            mouse_pos = pygame.mouse.get_pos()
            is_hovered = slot_rect.collidepoint(mouse_pos)
            
            if is_hovered:
                pygame.draw.rect(screen, HOVER_COLOR, slot_rect)
            else:
                pygame.draw.rect(screen, SLOT_BG_COLOR, slot_rect)
            pygame.draw.rect(screen, SLOT_BORDER_COLOR, slot_rect, 1)
            
            if item:
                icon = get_item_icon(item)
                screen.blit(icon, (x, y))
                
                if slot.quantity > 1:
                    qty_surf = self.font.render(str(slot.quantity), True, (255, 255, 255))
                    screen.blit(qty_surf, (x + ICON_SIZE - qty_surf.get_width(), y + ICON_SIZE - qty_surf.get_height()))
                
                # Add Hotspot
                self.active_hotspots.append((slot_rect, f"look {item.name}"))
                
                # Tooltip on hover
                if is_hovered:
                    self._draw_tooltip(screen, item, mouse_pos)
            
            x += ICON_SIZE + PADDING
            if x + ICON_SIZE > rect.right:
                x = rect.x
                y += ICON_SIZE + PADDING

    def _render_hybrid_mode(self, screen, rect, inv):
        y = rect.y
        row_height = ICON_SIZE + 4
        
        for slot in inv.slots:
            if not slot.item: continue
            
            item = slot.item
            row_rect = pygame.Rect(rect.x, y, rect.width, row_height)
            
            # Check Hover
            mouse_pos = pygame.mouse.get_pos()
            if row_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, HOVER_COLOR, row_rect)
            
            # Draw Icon
            icon = get_item_icon(item)
            screen.blit(icon, (rect.x + 2, y + 2))
            
            # Draw Text
            name_str = f"{item.name}"
            if slot.quantity > 1: name_str += f" (x{slot.quantity})"
            
            text_surf = self.font.render(name_str, True, TEXT_COLOR)
            screen.blit(text_surf, (rect.x + ICON_SIZE + 10, y + (row_height//2) - 8))
            
            # Details (Type/Weight)
            details = f"{item.__class__.__name__} | {item.weight} wt"
            detail_surf = self.font.render(details, True, (150, 150, 150))
            screen.blit(detail_surf, (rect.right - detail_surf.get_width() - 10, y + (row_height//2) - 8))

            # Add Hotspot
            self.active_hotspots.append((row_rect, f"look {item.name}"))
            
            y += row_height + 2

    def _draw_tooltip(self, screen, item, pos):
        text = f"{item.name}\n{item.__class__.__name__}\nVal: {item.value}"
        lines = text.split('\n')
        
        width = max(self.font.size(line)[0] for line in lines) + 10
        height = len(lines) * 20 + 10
        
        x, y = pos[0] + 15, pos[1] + 15
        
        # Clamp to screen
        if x + width > SCREEN_WIDTH: x -= width + 30
        
        pygame.draw.rect(screen, (10, 10, 10), (x, y, width, height))
        pygame.draw.rect(screen, (100, 100, 100), (x, y, width, height), 1)
        
        for i, line in enumerate(lines):
            surf = self.font.render(line, True, (255, 255, 255))
            screen.blit(surf, (x + 5, y + 5 + i * 20))

    def handle_click(self, pos: Tuple[int, int]) -> Optional[str]:
        """Returns the command associated with the clicked area."""
        for rect, cmd in self.active_hotspots:
            if rect.collidepoint(pos):
                return cmd
        return None
