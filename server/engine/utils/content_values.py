# engine/utils/content_values.py
"""Reading a number out of authored content without guessing what it meant.

Content is JSON, and JSON has one number type plus strings. The engine, though,
means specific things: `min_crafts` is a count, `weight` is a quantity that may
be fractional, `required_score` is an integer. When an authored value is not what
the field means, there are three possible behaviours and only one of them is
good:

* **silently drop it.** `Recipe` used to keep a quality tier only if
  `isinstance(tier["min_crafts"], int)`, so a float there removed the tier. No
  exception, no log, no tier. The same shape appears wherever a loader filters a
  list with `isinstance`, and it is the worst option: the content looks loaded.
* **silently default it.** `.get("cost", 0)` covering a key that is *present but
  wrong* turns a typo into a free purchase.
* **say what is wrong, in the file's own terms.** This module.

The refusal names the field the way the file spells it -- `recipes.tie_posy.
quality_tiers[1].min_crafts` -- so the message can be pasted back into the JSON
without a search. `world/housing_manager.py` has done this by hand in three
places since before this module existed; this is that pattern, shared.

What it deliberately does **not** do:

* It does not accept a quoted number. `"2"` for a count is a mistake in the file,
  and the engine's other readers reject it too -- `int("2")` succeeds, but
  `"2" * 3` is `"222"`, which is how a quoted `result_quantity` used to overshoot
  a craft by string multiplication.
* It does not treat a whole float as a fraction. `2.0` for a count is what a JSON
  writer with one number type produces (see `toolkit/normalize_content_numbers.py`)
  and is read as 2; `2.5` is refused, because truncating it invents a value the
  author did not write.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence


class ContentValueError(ValueError):
    """An authored value is not what the engine reads that field as.

    Carries the pieces separately as well as in the message, so a caller can
    report them without parsing prose.
    """

    def __init__(self, path: str, expected: str, value: Any) -> None:
        self.path = path
        self.expected = expected
        self.value = value
        super().__init__("%s must be %s (got %s)" % (path, expected, _render(value)))


def _render(value: Any) -> str:
    if isinstance(value, str):
        return repr(value)
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return "%d.0" % int(value)
    return "%s (%s)" % (value, type(value).__name__)


def _is_missing(value: Any) -> bool:
    """Whether a field was not authored at all.

    A present `null` is not missing: JSON can say `"min_crafts": null`, and that
    is an author writing something the engine cannot read, not an absent field.
    """
    return value is _ABSENT


class _Absent:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<absent>"


_ABSENT = _Absent()


def present(mapping: Any, key: str) -> Any:
    """The value of `key`, or the `_ABSENT` sentinel when it is not there."""
    if isinstance(mapping, Mapping) and key in mapping:
        return mapping[key]
    return _ABSENT


def absent(value: Any) -> bool:
    """Whether a value came back from `present` because the field is absent.

    A present `null` is not absent: JSON can say `"min_crafts": null`, and that
    is an author writing something the engine cannot read.
    """
    return value is _ABSENT


def optional_text(mapping: Any, key: str, path: str, *, default: Optional[str] = None) -> Optional[str]:
    """A string field the content may leave out, but may not get wrong."""
    value = present(mapping, key)
    if value is _ABSENT or value is None:
        return default
    return as_text(value, "%s.%s" % (path, key))


def optional_bool(mapping: Any, key: str, path: str, *, default: bool = False) -> bool:
    """A switch the content may leave out, but may not get wrong."""
    value = present(mapping, key)
    if value is _ABSENT or value is None:
        return default
    return as_bool(value, "%s.%s" % (path, key))


def required_int(
    mapping: Any,
    key: str,
    path: str,
    *,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> int:
    """An integer field that the content must have authored."""
    value = present(mapping, key)
    if value is _ABSENT:
        raise ContentValueError("%s.%s" % (path, key), "an integer", None)
    return as_int(value, "%s.%s" % (path, key), minimum=minimum, maximum=maximum)


def optional_int(
    mapping: Any,
    key: str,
    path: str,
    *,
    default: Optional[int] = None,
    minimum: Optional[int] = None,
    maximum: Optional[int] = None,
) -> Optional[int]:
    """An integer the content may leave out.

    Which is not the same as an integer the content may get wrong: an authored
    value that is not an integer raises, and `default` only covers absence.
    """
    value = present(mapping, key)
    if value is _ABSENT:
        return default
    return as_int(value, "%s.%s" % (path, key), minimum=minimum, maximum=maximum)


def as_int(value: Any, path: str, *, minimum: Optional[int] = None, maximum: Optional[int] = None) -> int:
    """A value the engine reads as a whole number.

    A whole float is what a JSON writer with one number type produces, so it is
    read as that integer; a fractional one is refused rather than truncated.
    """
    if isinstance(value, bool):
        raise ContentValueError(path, "an integer", value)
    if isinstance(value, int):
        result = value
    elif isinstance(value, float):
        if not value.is_integer():
            raise ContentValueError(path, "an integer", value)
        result = int(value)
    else:
        raise ContentValueError(path, "an integer", value)

    if minimum is not None and result < minimum:
        raise ContentValueError(path, "an integer of at least %d" % minimum, value)
    if maximum is not None and result > maximum:
        raise ContentValueError(path, "an integer of at most %d" % maximum, value)
    return result


def as_number(value: Any, path: str, *, minimum: Optional[float] = None) -> float:
    """A value the engine reads as a number that may be fractional."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ContentValueError(path, "a number", value)
    result = float(value)
    if minimum is not None and result < minimum:
        raise ContentValueError(path, "a number of at least %s" % minimum, value)
    return result


def as_bool(value: Any, path: str) -> bool:
    """A value the engine reads as a switch.

    `bool("false")` is True, which is how a content set ends up with a recipe it
    can never learn. A string is not a boolean, however convincing it looks.
    """
    if not isinstance(value, bool):
        raise ContentValueError(path, "true or false", value)
    return value


def as_text(value: Any, path: str, *, allow_empty: bool = True) -> str:
    """A value the engine reads as a string."""
    if not isinstance(value, str):
        raise ContentValueError(path, "a string", value)
    if not allow_empty and not value.strip():
        raise ContentValueError(path, "a non-empty string", value)
    return value


def as_sequence(value: Any, path: str, *, of: str = "a list") -> Sequence[Any]:
    """A value the engine reads as a list.

    Which is a field a loader used to accept and then iterate wrongly -- an
    object where a list was meant iterates its keys, and the entries are simply
    not there.
    """
    if not isinstance(value, (list, tuple)):
        raise ContentValueError(path, of, value)
    return value


def optional_sequence(mapping: Any, key: str, path: str) -> Sequence[Any]:
    """A list field the content may leave out, but may not get wrong."""
    value = present(mapping, key)
    if value is _ABSENT:
        return ()
    return as_sequence(value, "%s.%s" % (path, key))


def list_of_objects(value: Any, path: str) -> Sequence[Mapping[str, Any]]:
    """A list whose entries the engine reads as objects.

    Returns only the well-formed entries; a non-object entry raises, because a
    list that quietly drops half its members is the `min_crafts` bug again in a
    different place.
    """
    entries = as_sequence(value, path)
    for index, entry in enumerate(entries):
        if not isinstance(entry, Mapping):
            raise ContentValueError("%s[%d]" % (path, index), "an object", entry)
    return entries
