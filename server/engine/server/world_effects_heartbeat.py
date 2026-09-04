from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple


@dataclass(frozen=True)
class WorldEffectsCellDelta:
    cell_id: str
    value: float


class WorldEffectsHeartbeat:
    """Deterministic propagation for environmental world effects."""

    def __init__(
        self,
        width: int = 8,
        height: int = 8,
        spread_factor: float = 0.22,
        decay_factor: float = 0.03,
        change_epsilon: float = 0.005,
    ) -> None:
        self.width = max(1, width)
        self.height = max(1, height)
        self.spread_factor = max(0.0, spread_factor)
        self.decay_factor = max(0.0, decay_factor)
        self.change_epsilon = max(0.0, change_epsilon)
        self.tick_index = 0
        self._cells: Dict[Tuple[int, int], float] = {}

    @staticmethod
    def _clamp(value: float) -> float:
        if value <= 0.0:
            return 0.0
        if value >= 1.0:
            return 1.0
        return float(value)

    def seed_cell(self, x: int, y: int, value: float = 1.0) -> None:
        self._cells[(int(x), int(y))] = self._clamp(value)

    def snapshot(self) -> Dict[str, float]:
        return {f"{x},{y}": value for (x, y), value in self._cells.items()}

    def load_cells(self, cells: Dict[str, float]) -> None:
        self._cells = {}
        for cell_id, value in cells.items():
            try:
                x_text, y_text = str(cell_id).split(",", 1)
                x, y = int(x_text), int(y_text)
            except (TypeError, ValueError):
                continue
            if 0 <= x < self.width and 0 <= y < self.height:
                self._cells[(x, y)] = self._clamp(float(value))

    def apply_multipliers(self, multipliers: Dict[str, float]) -> List[WorldEffectsCellDelta]:
        changed: List[WorldEffectsCellDelta] = []
        for cell_id, multiplier in multipliers.items():
            try:
                x_text, y_text = str(cell_id).split(",", 1)
                coord = (int(x_text), int(y_text))
            except (TypeError, ValueError):
                continue
            previous = self._cells.get(coord, 0.0)
            updated = self._clamp(previous * max(0.0, float(multiplier)))
            if abs(updated - previous) >= self.change_epsilon:
                self._cells[coord] = updated
                changed.append(WorldEffectsCellDelta(cell_id=cell_id, value=updated))
        return changed

    def tick(self) -> List[WorldEffectsCellDelta]:
        next_cells: Dict[Tuple[int, int], float] = {}
        changed: List[WorldEffectsCellDelta] = []
        for (x, y), value in self._cells.items():
            retained = self._clamp(value * (1.0 - self.decay_factor))
            if retained > self.change_epsilon:
                next_cells[(x, y)] = retained
            for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    spread = self._clamp(value * self.spread_factor)
                    if spread > self.change_epsilon:
                        next_cells[(nx, ny)] = max(next_cells.get((nx, ny), 0.0), spread)
        self.tick_index += 1
        for coord, value in next_cells.items():
            if abs(value - self._cells.get(coord, 0.0)) >= self.change_epsilon:
                changed.append(WorldEffectsCellDelta(cell_id=f"{coord[0]},{coord[1]}", value=value))
        self._cells = next_cells
        return changed
