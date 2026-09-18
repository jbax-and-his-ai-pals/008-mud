# engine/ui/icons.py
import pygame
from typing import Tuple, Dict
from engine.items.item import Item

# Cache for generated icons to save CPU
_ICON_CACHE: Dict[str, pygame.Surface] = {}
ICON_SIZE = 32

# Colors for item types (R, G, B)
# Made brighter for visibility
TYPE_COLORS = {
    "Weapon": (220, 60, 60),      # Bright Red
    "Armor": (120, 120, 180),     # Blue-Grey
    "Consumable": (80, 220, 80),  # Bright Green
    "Key": (240, 240, 60),        # Bright Gold
    "Treasure": (220, 60, 220),   # Bright Purple
    "Junk": (160, 160, 140),      # Grey
    "Container": (160, 100, 50),  # Brown
    "Gem": (60, 240, 240),        # Cyan
    "Lockpick": (220, 220, 220)   # White/Silver
}

def get_item_icon(item: Item) -> pygame.Surface:
    """
    Generates or retrieves a cached icon surface for an item.
    """
    cache_key = f"{item.__class__.__name__}_{item.name}"
    if cache_key in _ICON_CACHE:
        return _ICON_CACHE[cache_key]
    
    # Create new surface - use standard RGB for opacity, or Alpha if you want transparency
    surface = pygame.Surface((ICON_SIZE, ICON_SIZE)) 
    
    # 1. Fill Background with a solid dark color (so it stands out against menu)
    surface.fill((20, 20, 20)) 
    
    # 2. Draw Border
    rect = pygame.Rect(0, 0, ICON_SIZE, ICON_SIZE)
    pygame.draw.rect(surface, (100, 100, 100), rect, 1)

    # 3. Get Item Color and drawing style.
    #
    # Style comes from the item's family contract when content declares one, so
    # a content set decides how its things look; the class name is the fallback
    # for items from families that declare nothing, which is also how every item
    # behaved before styles existed.
    item_type = item.__class__.__name__
    color = TYPE_COLORS.get(item_type, (200, 200, 200))
    style = _style_for(item, item_type)
    
    # 4. Draw Symbol
    center = (ICON_SIZE // 2, ICON_SIZE // 2)
    
    if style == "blade":
        pygame.draw.line(surface, color, (6, 26), (26, 6), 3) # Blade
        pygame.draw.line(surface, (150, 150, 150), (6, 26), (12, 20), 5) # Hilt handle
        pygame.draw.line(surface, (100, 100, 100), (8, 24), (14, 18), 2) # Crossguard
        
    elif style == "shield":
        shield_rect = pygame.Rect(8, 8, 16, 16)
        pygame.draw.rect(surface, color, shield_rect)
        pygame.draw.rect(surface, (255, 255, 255), shield_rect, 1)

    elif style == "bottle":
        pygame.draw.circle(surface, color, (16, 20), 7) # Bottle
        pygame.draw.rect(surface, (150, 150, 150), (14, 10, 4, 4)) # Neck

    elif style == "key":
        pygame.draw.circle(surface, color, (12, 12), 5, 2) # Bow
        pygame.draw.line(surface, color, (16, 16), (24, 24), 2) # Shaft
        
    elif style == "gem":
        pygame.draw.polygon(surface, color, [(16, 6), (26, 16), (16, 26), (6, 16)])
        
    elif style == "pick":
        pygame.draw.line(surface, color, (8, 24), (24, 8), 1)
        pygame.draw.line(surface, color, (24, 8), (20, 6), 1) # Hook

    else:
        # Generic Box
        box_rect = pygame.Rect(10, 10, 12, 12)
        pygame.draw.rect(surface, color, box_rect)
        pygame.draw.line(surface, (0,0,0), (10, 10), (22, 22), 1)

    _ICON_CACHE[cache_key] = surface
    return surface


# Class name -> style, for items whose family declares no icon_style. This is
# the whole of the old behaviour, kept as data rather than as branches.
LEGACY_STYLES = {
    "Weapon": "blade",
    "Armor": "shield",
    "Consumable": "bottle",
    "Key": "key",
    "Gem": "gem",
    "Lockpick": "pick",
}


def _style_for(item: Item, item_type: str) -> str:
    declared = ""
    getter = getattr(item, "get_property", None)
    if callable(getter):
        declared = str(getter("icon_style", "") or "")
    return declared or LEGACY_STYLES.get(item_type, "box")
