"""Validate that authored `.format()`-style text templates render cleanly.

Two distinct risks this checks for, both found live in fantasy_frontier
while designing this validator:

1. A field the engine never runs through `.format()` at all (most NPC
   `dialog` keys besides `trade`) must not contain a `{placeholder}` --
   any brace there is guaranteed to leak to the player verbatim the
   moment anything reads that field.
2. A field the engine does format with a fixed, known key set (spell
   messages, quest procedural text, procedural item names, affix name
   patterns) must not reference a key the engine won't actually supply --
   several of these call sites already swallow the resulting `KeyError`
   and silently substitute a generic fallback line, so a typo here means
   an author's custom text silently never appears with zero signal.

Deliberately out of scope: campaign/saga stage `description` templates
that draw on a dynamically-accumulated `saga_context`
(`engine/core/quest_generation/generator.py`) -- validating those
correctly means replicating that function's stateful, order-dependent
control flow outside of it. Also out of scope: procedural region
`dynamic_themes.json` name/description templates -- flavor-only,
procedurally generated, not part of any authored vertical slice.
"""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable


@dataclass
class TemplateIssue:
    severity: str
    path: str
    message: str


# The one dialog key the engine actually formats (mercantile.py's vendor
# trade/greeting line, with `{name}`). Every other dialog key is returned
# verbatim by NPC.talk() and must contain no brace at all.
_FORMATTED_DIALOG_KEYS: Dict[str, Dict[str, str]] = {
    "trade": {"name": "Sample Vendor"},
}

# Top-level NPC template field (not inside "dialog") that IS formatted.
_DEFAULT_DIALOG_SUBSTITUTIONS = {"name": "Sample Creature"}
_GREETING_EXTENDED_SUBSTITUTIONS = {"entry_location_desc": "the old mill"}

_SPELL_MESSAGE_SUBSTITUTIONS: Dict[str, Dict[str, Any]] = {
    "cast_message": {"caster_name": "Sample Caster", "spell_name": "Sample Spell"},
    "hit_message": {
        "caster_name": "Sample Caster", "target_name": "Sample Target",
        "spell_name": "Sample Spell", "value": 5, "damage_type": "fire",
    },
    "heal_message": {
        "caster_name": "Sample Caster", "target_name": "Sample Target",
        "spell_name": "Sample Spell", "value": 5,
    },
    "self_heal_message": {"value": 5},
    "remove_curse_item_message": {"target_name": "Sample Target"},
    "remove_curse_equipment_message": {"target_name": "Sample Target", "value": 1},
}

_PROCEDURAL_ITEM_SUBSTITUTIONS = {"spell_name": "Sample Spell"}
_AFFIX_NAME_PATTERN_SUBSTITUTIONS = {"item_name": "Sample Item"}

# Mirrors engine/core/quest_generation/text.py's format_quest_text() details.
_QUEST_TEXT_SUBSTITUTIONS = {
    "giver_name": "Sample Giver",
    "quantity": 3,
    "target_name_plural": "sample foes",
    "location_description": "the sample woods",
    "item_name_plural": "sample items",
    "source_enemy_name_plural": "sample creatures",
    "item_to_deliver_name": "a sample item",
    "recipient_name": "Sample Recipient",
    "recipient_location_description": "the sample market",
}


def _load_json(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _try_format(template: str, substitutions: Dict[str, Any]) -> str | None:
    """Return an error message if `template` doesn't format cleanly, else None."""
    try:
        template.format(**substitutions)
    except (KeyError, IndexError) as exc:
        return f"references unknown placeholder {exc} (known: {sorted(substitutions)})"
    return None


def _check_npc_templates(npc_files: Iterable[Path], issues: list[TemplateIssue]) -> None:
    for path in npc_files:
        try:
            payload = _load_json(path)
        except Exception as exc:
            issues.append(TemplateIssue("error", str(path), f"failed to parse JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            continue
        for template_id, template in payload.items():
            if not isinstance(template, dict):
                continue
            default_dialog = template.get("default_dialog")
            if isinstance(default_dialog, str) and "{" in default_dialog:
                error = _try_format(default_dialog, _DEFAULT_DIALOG_SUBSTITUTIONS)
                if error:
                    issues.append(TemplateIssue("error", f"{path}:{template_id}.default_dialog", error))

            dialog = template.get("dialog")
            if not isinstance(dialog, dict):
                continue
            for key, value in dialog.items():
                if not isinstance(value, str) or "{" not in value:
                    continue
                if key == "greeting_extended":
                    error = _try_format(value, _GREETING_EXTENDED_SUBSTITUTIONS)
                    if error:
                        issues.append(TemplateIssue("error", f"{path}:{template_id}.dialog.{key}", error))
                elif key in _FORMATTED_DIALOG_KEYS:
                    error = _try_format(value, _FORMATTED_DIALOG_KEYS[key])
                    if error:
                        issues.append(TemplateIssue("error", f"{path}:{template_id}.dialog.{key}", error))
                else:
                    issues.append(TemplateIssue(
                        "error", f"{path}:{template_id}.dialog.{key}",
                        f"contains a placeholder but this dialog field is never formatted -- "
                        f"it will be shown verbatim: {value!r}",
                    ))


def _check_spell_files(magic_files: Iterable[Path], issues: list[TemplateIssue]) -> None:
    for path in magic_files:
        try:
            payload = _load_json(path)
        except Exception as exc:
            issues.append(TemplateIssue("error", str(path), f"failed to parse JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            continue
        for spell_id, spell in payload.items():
            if not isinstance(spell, dict):
                continue
            for field, substitutions in _SPELL_MESSAGE_SUBSTITUTIONS.items():
                value = spell.get(field)
                if not isinstance(value, str) or "{" not in value:
                    continue
                error = _try_format(value, substitutions)
                if error:
                    issues.append(TemplateIssue("error", f"{path}:{spell_id}.{field}", error))


def _check_item_files(item_files: Iterable[Path], issues: list[TemplateIssue]) -> None:
    for path in item_files:
        try:
            payload = _load_json(path)
        except Exception as exc:
            issues.append(TemplateIssue("error", str(path), f"failed to parse JSON: {exc}"))
            continue
        if not isinstance(payload, dict):
            continue
        for item_id, item in payload.items():
            if not isinstance(item, dict):
                continue
            properties = item.get("properties", {})
            if isinstance(properties, dict) and properties.get("is_procedural"):
                for field in ("name", "description"):
                    value = item.get(field)
                    if not isinstance(value, str) or "{" not in value:
                        continue
                    error = _try_format(value, _PROCEDURAL_ITEM_SUBSTITUTIONS)
                    if error:
                        issues.append(TemplateIssue("error", f"{path}:{item_id}.{field}", error))

            pattern = item.get("generated_effect_name_pattern")
            if isinstance(pattern, str) and "{" in pattern:
                error = _try_format(pattern, _AFFIX_NAME_PATTERN_SUBSTITUTIONS)
                if error:
                    issues.append(TemplateIssue("error", f"{path}:{item_id}.generated_effect_name_pattern", error))


def _check_quest_text_templates(templates: Any, source: str, issues: list[TemplateIssue]) -> None:
    if not isinstance(templates, dict):
        return
    for quest_type, by_text_type in templates.items():
        if not isinstance(by_text_type, dict):
            continue
        for text_type, template in by_text_type.items():
            if not isinstance(template, str) or "{" not in template:
                continue
            error = _try_format(template, _QUEST_TEXT_SUBSTITUTIONS)
            if error:
                issues.append(TemplateIssue("error", f"{source}:{quest_type}.{text_type}", error))


def validate_content_set(root: Path) -> list[TemplateIssue]:
    """`root` is a content-set root (e.g. content_sets/fantasy_frontier),
    not just its data/ subdirectory -- this needs both data/ and
    rules/ruleset.json."""
    issues: list[TemplateIssue] = []
    data_root = root / "data"

    npc_dir = data_root / "npcs"
    if npc_dir.is_dir():
        _check_npc_templates(sorted(npc_dir.glob("*.json")), issues)

    magic_dir = data_root / "magic"
    if magic_dir.is_dir():
        _check_spell_files(sorted(magic_dir.glob("*.json")), issues)

    items_dir = data_root / "items"
    if items_dir.is_dir():
        _check_item_files(sorted(items_dir.glob("*.json")), issues)

    ruleset_path = root / "rules" / "ruleset.json"
    if ruleset_path.is_file():
        try:
            ruleset = _load_json(ruleset_path)
        except Exception as exc:
            issues.append(TemplateIssue("error", str(ruleset_path), f"failed to parse JSON: {exc}"))
        else:
            if isinstance(ruleset, dict):
                overrides = ruleset.get("quest_generation", {}).get("text_templates")
                if overrides:
                    _check_quest_text_templates(overrides, str(ruleset_path), issues)

    return issues


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Validate that authored dialogue/spell/item/quest text templates render without a leftover placeholder."
    )
    parser.add_argument("root", nargs="?", default="content_sets/fantasy_frontier", help="Path to a content-set root (not its data/ subdirectory).")
    args = parser.parse_args()

    root = Path(args.root)
    if not root.exists() or not root.is_dir():
        print(f"[ERROR] Root directory not found: {root}")
        raise SystemExit(2)

    issues = validate_content_set(root)
    error_count = 0
    for issue in issues:
        if issue.severity == "error":
            error_count += 1
            print(f"[ERROR] {issue.path} - {issue.message}")
        else:
            print(f"[WARN]  {issue.path} - {issue.message}")
    print(f"Template issues: {len(issues)} (errors: {error_count})")
    raise SystemExit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()
