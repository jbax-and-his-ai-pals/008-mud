# engine/ui/floating_text.py
import pygame
import random
import time
from typing import Tuple

class FloatingText:
    def __init__(self, text: str, x: int, y: int, color: Tuple[int, int, int], duration: float = 1.5):
        self.text = str(text)
        self.x = x + random.randint(-10, 10) # Jitter
        self.y = y + random.randint(-10, 10)
        self.color = color
        self.duration = duration
        self.start_time = time.time()
        self.alpha = 255
        
        # Velocity for "floating up"
        self.vy = -30.0 # Pixels per second

    def update(self, dt: float) -> bool:
        elapsed = time.time() - self.start_time
        if elapsed > self.duration:
            return False
        
        # Move up
        self.y += self.vy * dt
        
        # Fade out in last half
        if elapsed > self.duration * 0.5:
            progress = (elapsed - (self.duration * 0.5)) / (self.duration * 0.5)
            self.alpha = int(255 * (1.0 - progress))
            
        return True

    def draw(self, surface: pygame.Surface, font: pygame.font.Font):
        text_surf = font.render(self.text, True, self.color)
        
        # Handle alpha if surface supports it, otherwise just draw
        if self.alpha < 255:
            text_surf.set_alpha(self.alpha)
            
        surface.blit(text_surf, (int(self.x), int(self.y)))