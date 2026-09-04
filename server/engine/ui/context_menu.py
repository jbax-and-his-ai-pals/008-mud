# engine/ui/context_menu.py
import pygame
from typing import List, Tuple, Callable

# Colors
MENU_BG_COLOR = (40, 40, 45)
MENU_BORDER_COLOR = (150, 150, 150)
MENU_TEXT_COLOR = (240, 240, 240)
MENU_HOVER_COLOR = (60, 60, 80)
MENU_PADDING = 5
ITEM_HEIGHT = 24

class ContextMenu:
    def __init__(self, x: int, y: int, options: List[Tuple[str, str]]):
        """
        options: List of (Label, CommandString)
        """
        self.x = x
        self.y = y
        self.options = options
        
        self.font = pygame.font.SysFont("arial", 14)
        
        # Calculate dimensions
        max_width = 100
        for label, cmd in options:
            w = self.font.size(label)[0]
            if w > max_width: max_width = w
            
        self.width = max_width + (MENU_PADDING * 2) + 10
        self.height = (len(options) * ITEM_HEIGHT) + (MENU_PADDING * 2)
        
        self.rect = pygame.Rect(x, y, self.width, self.height)
        
        # Keep on screen
        surface = pygame.display.get_surface()
        if surface is None: return None

        display_info = surface.get_rect()
        if self.rect.right > display_info.width:
            self.rect.x -= self.width
        if self.rect.bottom > display_info.height:
            self.rect.y -= self.height

    def handle_event(self, event: pygame.event.Event) -> str | None:
        """
        Returns the command string if an option is clicked, None otherwise.
        Returns "CLOSE_MENU" if clicked outside.
        """
        if event.type == pygame.MOUSEBUTTONDOWN:
            if event.button == 1: # Left Click
                if self.rect.collidepoint(event.pos):
                    # Check which item
                    relative_y = event.pos[1] - self.rect.y - MENU_PADDING
                    index = relative_y // ITEM_HEIGHT
                    
                    if 0 <= index < len(self.options):
                        return self.options[index][1] # Return command
                else:
                    return "CLOSE_MENU" # Clicked outside
            elif event.button == 3: # Right Click outside
                if not self.rect.collidepoint(event.pos):
                    return "CLOSE_MENU"

        return None

    def draw(self, screen: pygame.Surface):
        # Shadow
        shadow_rect = self.rect.copy()
        shadow_rect.x += 4
        shadow_rect.y += 4
        s = pygame.Surface((shadow_rect.width, shadow_rect.height), pygame.SRCALPHA)
        s.fill((0, 0, 0, 100))
        screen.blit(s, shadow_rect)

        # Background
        pygame.draw.rect(screen, MENU_BG_COLOR, self.rect)
        pygame.draw.rect(screen, MENU_BORDER_COLOR, self.rect, 1)
        
        mouse_pos = pygame.mouse.get_pos()
        
        # Items
        for i, (label, cmd) in enumerate(self.options):
            item_rect = pygame.Rect(
                self.rect.x + 1, 
                self.rect.y + MENU_PADDING + (i * ITEM_HEIGHT), 
                self.rect.width - 2, 
                ITEM_HEIGHT
            )
            
            if item_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, MENU_HOVER_COLOR, item_rect)
            
            text_surf = self.font.render(label, True, MENU_TEXT_COLOR)
            screen.blit(text_surf, (self.rect.x + MENU_PADDING + 5, item_rect.y + 4))