"""Content-neutral helpers for installed item attachments.

Hosts declare a list of slot names and attachment tokens declare one slot plus
numeric modifiers.  Installed data lives on the host item so normal item-save
overrides preserve it without a bespoke save format.
"""

from typing import Any


def installed_attachments(item: Any) -> list[dict[str, Any]]:
    raw = item.get_property("attachments", []) if item is not None else []
    return [entry for entry in raw if isinstance(entry, dict)] if isinstance(raw, list) else []


def attachment_modifier(item: Any, modifier_name: str) -> int:
    total = 0
    for entry in installed_attachments(item):
        modifiers = entry.get("modifiers", {})
        if isinstance(modifiers, dict):
            value = modifiers.get(modifier_name, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += int(value)
    return total


def attachment_stat_modifier(item: Any, stat_name: str) -> int:
    total = 0
    for entry in installed_attachments(item):
        modifiers = entry.get("modifiers", {})
        stats = modifiers.get("stats", {}) if isinstance(modifiers, dict) else {}
        if isinstance(stats, dict):
            value = stats.get(stat_name, 0)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += int(value)
    return total
