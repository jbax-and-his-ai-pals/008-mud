# engine/ui/ui_element.py
import pygame
from typing import Callable, Any, Optional, List
from engine.utils.text_formatter import ClickableZone

# UI Colors
PANEL_BG_COLOR = (30, 30, 35)
PANEL_BORDER_COLOR = (100, 100, 110) # Slightly lighter border for visibility
HEADER_BG_COLOR = (60, 60, 80)       # Lighter header background to contrast with black
HEADER_TEXT_COLOR = (255, 255, 255)  # Pure white text
HEADER_HEIGHT = 24

# Renderer signature: (surface, context, hotspots_list) -> None
ContentRenderer = Callable[[pygame.Surface, Any, List[ClickableZone]], None]

class UIPanel:
    def __init__(self, 
                 panel_id: str,
                 height: int, 
                 title: str,
                 content_renderer: ContentRenderer):
        
        self.panel_id = panel_id
        self.target_height = height 
        self.rect = pygame.Rect(0, 0, 100, height) 
        self.title = title
        self.content_renderer = content_renderer
        
        # Fallback to default font if arial not found
        try:
            self.font = pygame.font.SysFont("arial", 14, bold=True)
        except:
            self.font = pygame.font.Font(None, 20)
        
        self.surface: Optional[pygame.Surface] = None
        self.content_surface: Optional[pygame.Surface] = None
        
        self.hotspots: List[ClickableZone] = []
        self.is_collapsed = False

    @property
    def current_height(self) -> int:
        """Returns the height the panel effectively takes up in the dock."""
        return HEADER_HEIGHT if self.is_collapsed else self.target_height

    def resize(self, width: int, height: int):
        """
        Resizes internal surfaces.
        """
        width = max(1, width)
        height = max(1, height)

        if self.surface and self.rect.width == width and self.rect.height == height:
            return
            
        self.rect.width = width
        self.rect.height = height
        self.surface = pygame.Surface((width, height))
        
        content_h = max(1, height - HEADER_HEIGHT)
        self.content_surface = pygame.Surface((width, content_h))

    def update(self, context_data: Any):
        if not self.surface or not self.content_surface: return

        # 1. Draw Frame (Border) - This clears the surface with the border color
        self.surface.fill(PANEL_BORDER_COLOR) 
        
        # 2. Draw Header
        # Explicitly fill header area to ensure no black background bleed-through
        header_rect = pygame.Rect(1, 1, self.rect.width - 2, HEADER_HEIGHT - 1)
        pygame.draw.rect(self.surface, HEADER_BG_COLOR, header_rect)
        
        # Collapse Indicator & Title
        indicator = "[+]" if self.is_collapsed else "[-]"
        title_text = f"{indicator} {self.title}"
        title_surf = self.font.render(title_text, True, HEADER_TEXT_COLOR)
        
        # Center vertically in header
        text_y = (HEADER_HEIGHT - title_surf.get_height()) // 2 + 1
        self.surface.blit(title_surf, (5, text_y))

        # 3. Render Content (Only if expanded)
        if not self.is_collapsed:
            # Draw Content Background
            bg_rect = pygame.Rect(1, HEADER_HEIGHT, self.rect.width - 2, self.rect.height - HEADER_HEIGHT - 1)
            pygame.draw.rect(self.surface, PANEL_BG_COLOR, bg_rect)
            
            # Update Content Surface
            self.content_surface.fill(PANEL_BG_COLOR)
            self.hotspots = []
            self.content_renderer(self.content_surface, context_data, self.hotspots)
            
            # Blit Content onto Main Surface
            self.surface.blit(self.content_surface, (0, HEADER_HEIGHT))
        else:
            self.hotspots = []

    def draw(self, screen: pygame.Surface, x: int, y: int):
        """Draws the panel. If collapsed, only draws the header portion."""
        self.rect.x = x
        self.rect.y = y
        
        if self.surface:
            if self.is_collapsed:
                # Only draw the top strip using the 'area' argument
                header_area = pygame.Rect(0, 0, self.rect.width, HEADER_HEIGHT)
                screen.blit(self.surface, (x, y), header_area)
            else:
                screen.blit(self.surface, (x, y))