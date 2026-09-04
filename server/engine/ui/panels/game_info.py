# engine/ui/panels/game_info.py
import pygame
from typing import TYPE_CHECKING
from engine.config import TEXT_COLOR

if TYPE_CHECKING:
    from engine.ui.renderer import Renderer
    from engine.world.world import World

def draw_time_bar(renderer: 'Renderer', time_data: dict):
    time_str = time_data.get("time_str", "??:??")
    date_str = time_data.get("date_str", "Unknown Date")
    time_period = time_data.get("time_period", "unknown")
    
    weather_str = ""
    if renderer.game and renderer.game.weather_manager:
        weather = renderer.game.weather_manager.current_weather
        intensity = renderer.game.weather_manager.current_intensity
        weather_str = f"Weather: {weather.capitalize()} ({intensity.capitalize()})"

    pygame.draw.rect(renderer.screen, (40, 40, 60), (0, 0, renderer.layout["screen_width"], renderer.layout["time_bar"]["height"]))

    time_color_map = {
        "dawn": (255, 165, 0),
        "morning": (200, 200, 100),
        "afternoon": (255, 255, 150),
        "dusk": (255, 100, 100),
        "night": (100, 100, 255)
    }
    time_color = time_color_map.get(time_period, TEXT_COLOR)
    time_surface = renderer.font.render(time_str, True, time_color)
    renderer.screen.blit(time_surface, (10, 5))

    period_surface = renderer.font.render(time_period.capitalize(), True, time_color)
    period_x = renderer.layout["screen_width"] - period_surface.get_width() - 10
    renderer.screen.blit(period_surface, (period_x, 5))

    date_surface = renderer.font.render(date_str, True, TEXT_COLOR)
    weather_surface = renderer.font.render(weather_str, True, TEXT_COLOR)
    
    total_center_width = date_surface.get_width() + weather_surface.get_width() + 20 
    center_start_x = (renderer.layout["screen_width"] - total_center_width) // 2
    
    date_x = center_start_x
    weather_x = date_x + date_surface.get_width() + 20
    
    renderer.screen.blit(date_surface, (date_x, 5))
    renderer.screen.blit(weather_surface, (weather_x, 5))

    pygame.draw.line(renderer.screen, (80, 80, 100), (0, renderer.layout["time_bar"]["height"]), (renderer.layout["screen_width"], renderer.layout["time_bar"]["height"]), 1)

def draw_room_info_panel(renderer: 'Renderer', world: 'World'):
    panel_layout = renderer.layout.get("room_info_panel")
    if not panel_layout: return
    
    panel_rect = pygame.Rect(panel_layout["x"], panel_layout["y"], panel_layout["width"], panel_layout["height"])
    pygame.draw.rect(renderer.screen, (15, 15, 15), panel_rect)
    pygame.draw.rect(renderer.screen, (70, 70, 70), panel_rect, 1)
    
    padding = 5
    current_y = panel_rect.y + padding
    max_y = panel_rect.bottom - padding
    
    room_description_text = world.get_room_description_for_display()
    
    original_width = renderer.text_formatter.screen_width
    renderer.text_formatter.update_screen_width(panel_rect.width)

    try:
        renderer.text_formatter.render(renderer.screen, room_description_text, (panel_rect.x + padding, current_y), max_height=max_y - current_y)
        
        # Capture hotspots for the single big render block
        renderer._static_hotspots.extend(renderer.text_formatter.last_hotspots)
    finally:
        renderer.text_formatter.update_screen_width(original_width)