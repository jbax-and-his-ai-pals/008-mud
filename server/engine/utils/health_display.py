# engine/utils/health_display.py
"""`ruleset.world.health_per_heart`: a set that counts health in hearts shows it so, half and quarter hearts included."""
from typing import Any, Optional

_FRACTIONS = {0.25: "¼", 0.5: "½", 0.75: "¾"}


def health_per_heart(world: Optional[Any]) -> int:
    """Points of health in one heart, or 0 for a set that shows plain numbers."""
    if world is None:
        return 0
    try:
        section = world.ruleset_section("world")
    except Exception:  # noqa: BLE001 - a world without rules shows numbers
        return 0
    unit = section.get("health_per_heart") if isinstance(section, dict) else None
    return unit if isinstance(unit, int) and not isinstance(unit, bool) and unit > 0 else 0


def hearts(points: float, unit: int) -> str:
    """`points` of health as hearts: 11 points at two to a heart is "5½"; a heart is never rounded up."""
    whole, rest = divmod(max(0.0, float(points)), unit)
    fraction = _FRACTIONS.get(round(rest / unit * 4) / 4) if rest else None
    if fraction is None and rest:
        return "%g" % (round(max(0.0, float(points)) / unit, 2))
    return "%d%s" % (whole, fraction or "")


def format_health(world: Optional[Any], health: float, max_health: float) -> str:
    """"5½/6 hearts" in a set that counts hearts, otherwise "11/12"."""
    unit = health_per_heart(world)
    if unit:
        return "%s/%s hearts" % (hearts(health, unit), hearts(max_health, unit))
    return "%d/%d" % (int(health), int(max_health))
