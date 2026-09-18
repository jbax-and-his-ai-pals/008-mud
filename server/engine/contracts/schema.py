"""A small declarative schema language for content contracts.

The registry's job is to let content declare *what a thing is* — an item family, a
generation profile, an ability, an effect packet — and to refuse anything it
cannot describe. That refusal is the whole value: the editor renders controls
from the same schema, so a field the schema does not know is a field the editor
cannot honestly offer and the runtime cannot honestly honour.

Shape of a schema (see `CONTRACT_SCHEMAS` in `registry.py` for the real ones):

    {
      "id": {"type": "string", "required": True},
      "rank": {"type": "int", "min": 0},
      "tags": {"type": "list_of", "of": "string"},
      "tiers": {"type": "list_of", "of": {
          "fields": {"id": {"type": "string", "required": True}, "value": {"type": "float"}},
      }},
      "capabilities": {"type": "list_of", "of": "enum", "values": ("a", "b")},
    }

Rules, deliberately strict:

* **Unknown fields are errors.** Not warnings. A typo'd `generation_profil` must
  not sit in content looking live while the engine ignores it.
* **Required means required**, and an empty list/string does not satisfy it.
* **Numbers are numbers**: a quoted "3" where an int belongs is an error, because
  it means the author is guessing at the shape.
* Errors carry a JSON-ish path (`generation_profiles[2].rarity_tiers[0].weight`)
  so a validator message can be pasted straight back into the file.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Iterable, List, Sequence

# Field types the schema language understands.
SCALARS = ("string", "int", "float", "bool")
CONTAINERS = ("enum", "list_of", "object", "map")


class SchemaError(Exception):
    """Raised only for a malformed *schema*, never for malformed content."""


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, dict, set)):
        return len(value) == 0
    return False


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "list"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def validate(value: Any, schema: Dict[str, Any], path: str, issues: List[str]) -> None:
    """Validate one value against one field spec, appending any issues."""
    kind = str(schema.get("type", "")).strip()
    if not kind:
        raise SchemaError("field spec at %s has no type" % path)

    label = schema.get("label") or path
    if kind in SCALARS:
        if kind == "string" and not isinstance(value, str):
            issues.append("%s must be a string (got %s)" % (label, _type_name(value)))
            return
        if kind == "int" and (isinstance(value, bool) or not isinstance(value, int)):
            issues.append("%s must be a whole number (got %s)" % (label, _type_name(value)))
            return
        if kind == "float" and (isinstance(value, bool) or not isinstance(value, (int, float))):
            issues.append("%s must be a number (got %s)" % (label, _type_name(value)))
            return
        if kind == "bool" and not isinstance(value, bool):
            issues.append("%s must be true or false (got %s)" % (label, _type_name(value)))
            return
        if "min" in schema and isinstance(value, (int, float)) and value < schema["min"]:
            issues.append("%s must be at least %s (got %s)" % (label, schema["min"], value))
        if "max" in schema and isinstance(value, (int, float)) and value > schema["max"]:
            issues.append("%s must be at most %s (got %s)" % (label, schema["max"], value))
        if "pattern" in schema and isinstance(value, str) and not __import__("re").match(str(schema["pattern"]), value):
            issues.append("%s must match %s (got %r)" % (label, schema["pattern"], value))
        return

    if kind == "enum":
        allowed = tuple(str(v) for v in schema.get("values", ()))
        if not allowed:
            raise SchemaError("enum spec at %s has no values" % path)
        if str(value) not in allowed:
            issues.append("%s must be one of %s (got %r)" % (label, ", ".join(allowed), value))
        return

    if kind == "list_of":
        if not isinstance(value, list):
            issues.append("%s must be a list (got %s)" % (label, _type_name(value)))
            return
        item_schema = schema.get("of")
        if item_schema is None:
            raise SchemaError("list_of spec at %s has no 'of'" % path)
        if isinstance(item_schema, str):
            item_schema = {"type": item_schema}
        for index, entry in enumerate(value):
            validate(entry, item_schema, "%s[%d]" % (path, index), issues)
        return

    if kind == "object":
        if not isinstance(value, dict):
            issues.append("%s must be an object (got %s)" % (label, _type_name(value)))
            return
        validate_fields(value, schema.get("fields", {}), path, issues)
        return

    if kind == "map":
        if not isinstance(value, dict):
            issues.append("%s must be an object (got %s)" % (label, _type_name(value)))
            return
        item_schema = schema.get("of") or {"type": "string"}
        if isinstance(item_schema, str):
            item_schema = {"type": item_schema}
        for key, entry in value.items():
            validate(entry, item_schema, "%s.%s" % (path, key), issues)
        return

    raise SchemaError("unknown field type %r at %s" % (kind, path))


def validate_fields(
    payload: Dict[str, Any],
    fields: Dict[str, Any],
    path: str,
    issues: List[str],
    *,
    allow_extra: Sequence[str] = (),
) -> None:
    """Validate an object's *fields*: required present, unknown refused."""
    for name, spec in fields.items():
        label = "%s.%s" % (path, name) if path else str(name)
        spec_with_label = dict(spec)
        spec_with_label.setdefault("label", label)
        if name not in payload:
            if spec.get("required"):
                issues.append("%s is required" % label)
            continue
        value = payload[name]
        if spec.get("required") and _is_blank(value):
            issues.append("%s is required and may not be empty" % label)
            continue
        if _is_blank(value) and not spec.get("required"):
            continue
        validate(value, spec_with_label, label, issues)

    for name in payload:
        if name in fields or name.startswith("_") or name in allow_extra:
            continue
        issues.append(
            "%s is not a field this contract defines (known: %s)"
            % ("%s.%s" % (path, name) if path else name, ", ".join(sorted(fields)))
        )


def validate_list(
    entries: Any,
    fields: Dict[str, Any],
    path: str,
    issues: List[str],
    *,
    id_field: str = "id",
) -> None:
    """Validate a list of identified objects, refusing duplicate ids."""
    if entries is None:
        return
    if not isinstance(entries, list):
        issues.append("%s must be a list" % path)
        return
    seen: Dict[str, int] = {}
    for index, entry in enumerate(entries):
        where = "%s[%d]" % (path, index)
        if not isinstance(entry, dict):
            issues.append("%s must be an object" % where)
            continue
        validate_fields(entry, fields, where, issues)
        identifier = str(entry.get(id_field, "") or "").strip()
        if not identifier:
            continue
        if identifier in seen:
            issues.append(
                "%s.%s '%s' is already defined at %s[%d]"
                % (where, id_field, identifier, path, seen[identifier])
            )
            continue
        seen[identifier] = index
