import pygame
from .config import *

class Button:
    def __init__(self, x, y, w, h, text, action):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = text
        self.action = action
        self.is_hovered = False

    def draw(self, surface, font):
        color = COLOR_BUTTON_LIGHT if not self.is_hovered else (200, 200, 255)
        # Draw bevel
        pygame.draw.rect(surface, COLOR_BUTTON_DARK, (self.rect.x+2, self.rect.y+2, self.rect.w, self.rect.h))
        pygame.draw.rect(surface, color, self.rect)
        pygame.draw.rect(surface, (0,0,0), self.rect, 1)
        
        txt_surf = font.render(self.text, True, COLOR_TEXT)
        txt_rect = txt_surf.get_rect(center=self.rect.center)
        surface.blit(txt_surf, txt_rect)

    def handle_event(self, event):
        if event.type == pygame.MOUSEMOTION:
            self.is_hovered = self.rect.collidepoint(event.pos)
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.is_hovered and event.button == 1:
                self.action()

class TextInput:
    def __init__(self, x, y, w, h, label=""):
        self.rect = pygame.Rect(x, y, w, h)
        self.text = ""
        self.label = label
        self.active = False

    def draw(self, surface, font):
        # Label
        if self.label:
            lbl = font.render(self.label, True, COLOR_TEXT)
            surface.blit(lbl, (self.rect.x, self.rect.y - 20))

        # Box
        color = (255, 255, 255)
        pygame.draw.rect(surface, color, self.rect)
        border = COLOR_TITLE_BAR if self.active else (100, 100, 100)
        pygame.draw.rect(surface, border, self.rect, 2)

        # Text
        # Simple clipping could be done here, but keeping it simple
        display_text = self.text + ("|" if self.active else "")
        txt_surf = font.render(display_text, True, COLOR_TEXT)
        surface.blit(txt_surf, (self.rect.x + 5, self.rect.y + 5))

    def handle_event(self, event):
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)
        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            else:
                self.text += event.unicode