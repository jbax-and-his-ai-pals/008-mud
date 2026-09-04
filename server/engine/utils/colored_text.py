# engine/utils/colored_text.py
import pygame
from typing import List, Tuple, Dict, Optional

class ColoredText:
    def __init__(self, font, format_colors: Dict[str, Tuple[int, int, int]]):
        self.font = font
        self.format_colors = format_colors
        self.default_color = (255, 255, 255)

    def render(self, surface, text: str, position: Tuple[int, int], default_color=None) -> None:
        if default_color is None:
            default_color = self.default_color
        x_orig, y = position  # Keep track of original x position for newlines
        x = x_orig
        lines = text.split('\n')
        line_height = self.font.get_linesize()        
        for line_idx, line in enumerate(lines):
            x = x_orig
            if not line:
                y += line_height
                continue
            segments = self._split_by_format_codes(line)
            current_color = default_color
            for segment in segments:
                if segment in self.format_colors:
                    current_color = self.format_colors[segment]
                else:
                    if segment and any(ord(c) >= 32 for c in segment):
                        cleaned_segment = ''.join(c if ord(c) >= 32 else ' ' for c in segment)
                        if cleaned_segment:  # Only render non-empty segments
                            text_surface = self.font.render(cleaned_segment, True, current_color)
                            surface.blit(text_surface, (x, y))
                            x += text_surface.get_width()
            y += line_height    
    
    def remove_format_codes(self, text: str) -> str:
        if not text:
            return ""
        result = text
        for code in self.format_colors.keys():
            result = result.replace(code, "")
        result = result.replace('\r\n', '\n').replace('\r', '\n')
        result = ''.join(c if c == '\n' or ord(c) >= 32 else ' ' for c in result)
        while '\n\n\n' in result:
            result = result.replace('\n\n\n', '\n\n')
        return result
    
    def _split_by_format_codes(self, text: str) -> List[str]:
        result = []
        current_text = text
        while current_text:
            earliest_pos = len(current_text)
            earliest_code = None
            for code in self.format_colors.keys():
                pos = current_text.find(code)
                if pos != -1 and pos < earliest_pos:
                    earliest_pos = pos
                    earliest_code = code
            if earliest_code is None:
                result.append(current_text)
                break
            if earliest_pos > 0:
                result.append(current_text[:earliest_pos])
            result.append(earliest_code)
            current_text = current_text[earliest_pos + len(earliest_code):]
        return result