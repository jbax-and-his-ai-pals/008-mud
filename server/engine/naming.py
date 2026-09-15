"""One resolver for turning player-typed words into game objects.

Before this, five separate ad-hoc matchers existed, each with different rules:

  * `Inventory.find_item_by_name` -- substring over the name, or exact `obj_id`
  * `World.find_npc_in_room` -- exact name/id, then substring
  * `Room`/container inspection -- exact name/id
  * `commands/interaction/npcs.py::_resolve_target_npc` -- longest-first
    multi-word prefix over args
  * `commands/crafting.py::craft_handler` -- substring over the recipe id or
    name, **using only `args[0]`**

That last one is why natural phrasing did not work: `craft river clay token`
searched for the literal `"river"`, which matched `press_river_token` only by
accident of dict ordering, and `craft wildflower posy` searched for
`"wildflower"` and matched nothing at all (the recipe's display name is
"Tie Wildflower Posy"). Substring matching was also order-dependent and
silently returned the first hit.

This module replaces all five. Design rules:

  * **Match the whole input**, not the first token.
  * **Score, then pick the best** -- longest, most specific match wins, so
    "rat tail" beats "tail" and an exact name beats a substring.
  * **Report ambiguity** rather than silently choosing. Callers decide whether
    to ask the player or to fall through to another strategy.
  * **Never invent a match.** A single-character query does not resolve to
    everything that contains that letter.

`Match` carries the score and how it matched, so callers can log or explain it.

**No subsequence ("fuzzy") matching, deliberately.** An earlier revision scored
a candidate when the query's letters appeared in order anywhere in the name --
intended to forgive typos. It was removed after it resolved the query `chest`
to the NPC **"Kaelan the Alchemist"**: the letters c-h-e-s-t do appear in order
across that name (*C*…*H*e…*alch*E*…alchemi*S*t…*T*he), so looking into a chest
found an alchemist instead. Subsequence matching over multi-word proper names is
far too permissive to be safe as a general fallback. Word-boundary matches
already provide the useful forgiveness ("elder" finds "Elder Thorne", "talia"
finds "Talia the Merchant") without that failure mode. If typo tolerance is ever
wanted, it belongs in an opt-in high-threshold mode for single-token queries,
not in the default path.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Iterable, List, Optional, Sequence, Tuple

# Score bands. Higher wins; ties mean genuine ambiguity.
SCORE_EXACT_ID = 1000
SCORE_EXACT_ALIAS = 950
SCORE_EXACT_NAME = 900
SCORE_NAME_PREFIX = 700          # name starts with the whole query
SCORE_NAME_WORD_PREFIX = 600     # a word in the name starts with the query
SCORE_NAME_WORD = 500            # a whole word of the name equals the query
SCORE_NAME_SUBSTRING = 300       # query appears inside the name

# A tie within this margin is treated as ambiguous rather than resolved.
AMBIGUITY_MARGIN = 0

# Minimum length for a loose (non-exact) match. Below this, only an exact name
# or id matches, so a one-letter query does not resolve to everything.
MIN_QUERY_LENGTH = 2


@dataclass(frozen=True)
class Match:
    """One candidate and how well it matched."""

    obj: Any
    score: int
    how: str


def normalize(text: str) -> str:
    """Lowercase and collapse separators so ids and prose compare equal.

    `tie_wildflower_posy`, `Tie Wildflower Posy` and `tie-wildflower-posy` all
    normalize to `tie wildflower posy`.
    """
    if not text:
        return ""
    spaced = str(text).replace("_", " ").replace("-", " ")
    return " ".join(spaced.lower().split())


def _score_against(query: str, raw_candidate: str, *, is_id: bool, is_alias: bool) -> Tuple[int, str]:
    """Score one candidate string against a normalized query."""
    candidate = normalize(raw_candidate)
    if not candidate:
        return 0, ""

    if is_id and query == candidate:
        return SCORE_EXACT_ID, "exact id"
    if is_alias and query == candidate:
        return SCORE_EXACT_ALIAS, "alias"
    if query == candidate:
        return SCORE_EXACT_NAME, "exact name"

    # A query is too short to match loosely -- otherwise "r" resolves to every
    # name containing an "r". Exact matches above are still allowed.
    if len(query) < MIN_QUERY_LENGTH:
        return 0, ""

    words = candidate.split()
    query_words = query.split()

    # Priority order is deliberate, most specific first:
    #   1. the whole name starting with the query ("wildflower" ->
    #      "Wildflower Posy") -- a strong positional signal;
    #   2. the whole name ending with a contiguous run of query tokens
    #      ("wildflower posy" -> "Tie Wildflower Posy", "a posy" -> "... Posy");
    #   3. the query naming a COMPLETE word of the name ("rat" -> "Rat Tail");
    #   4. each query token starting a word, in order ("river clay token" ->
    #      "Press River-Clay Token", "wild" -> "Wildflower Posy");
    #   5. the query appearing inside the name at all.
    if candidate.startswith(query):
        return SCORE_NAME_PREFIX, "name prefix"

    if len(query_words) > 1 and len(words) >= len(query_words):
        # Compare as substrings so hyphen/underscore forms match too. The
        # normalizer already converted separators to spaces, so an infix test is
        # enough here.
        if candidate.endswith(query):
            return SCORE_NAME_WORD, "words"

    if len(query_words) == 1 and query in words:
        return SCORE_NAME_WORD, "word"

    if all(any(word.startswith(token) for word in words) for token in query_words):
        return SCORE_NAME_WORD_PREFIX, "word prefix"

    if query in candidate:
        return SCORE_NAME_SUBSTRING, "substring"

    return 0, ""


def candidate_score(
    query: str,
    *,
    name: str = "",
    obj_id: str = "",
    aliases: Sequence[str] = (),
) -> Tuple[int, str]:
    """Best score for one candidate across its name, id, and aliases."""
    normalized_query = normalize(query)
    if not normalized_query:
        return 0, ""

    best = (0, "")
    for alias in aliases or ():
        score, how = _score_against(normalized_query, alias, is_id=False, is_alias=True)
        if score > best[0]:
            best = (score, how)
    if obj_id:
        score, how = _score_against(normalized_query, obj_id, is_id=True, is_alias=False)
        if score > best[0]:
            best = (score, how)
    if name:
        score, how = _score_against(normalized_query, name, is_id=False, is_alias=False)
        if score > best[0]:
            best = (score, how)
    return best


def _field_of(obj: Any, attribute: str, *keys: str) -> str:
    """Read one identity field from an object *or* a mapping.

    Callers hand this resolver whatever they have: NPCs, items, recipes, and
    sometimes plain dicts built on the spot. Reading only attributes meant a
    dict candidate silently scored zero -- no error, just a choice that never
    matched anything a player typed. Both shapes are cheap to support.
    """
    if isinstance(obj, dict):
        for key in keys:
            value = obj.get(key)
            if isinstance(value, str) and value.strip():
                return value
        return ""
    value = getattr(obj, attribute, None)
    return str(value) if isinstance(value, str) else ""


def _name_of(obj: Any) -> str:
    return _field_of(obj, "name", "name", "display_name", "title")


def _id_of(obj: Any) -> str:
    return _field_of(obj, "obj_id", "obj_id", "id", "template_id")


def _aliases_of(obj: Any) -> List[str]:
    """Authored alternative names for an object, if it carries any."""
    if isinstance(obj, dict):
        for key in ("aliases", "aka"):
            value = obj.get(key)
            if isinstance(value, str):
                return [value]
            if isinstance(value, (list, tuple)):
                return [str(v) for v in value if isinstance(v, (str, int))]
        return []

    for source in (getattr(obj, "properties", None), getattr(obj, "aliases", None)):
        if isinstance(source, dict):
            value = source.get("aliases") or source.get("aka")
            if isinstance(value, str):
                return [value]
            if isinstance(value, (list, tuple)):
                return [str(v) for v in value if isinstance(v, (str, int))]
        elif isinstance(source, (list, tuple)):
            return [str(v) for v in source if isinstance(v, str)]
    return []


def resolve_all(
    query: str,
    candidates: Iterable[Any],
    *,
    name_of: Optional[Callable[[Any], str]] = None,
    id_of: Optional[Callable[[Any], str]] = None,
    aliases_of: Optional[Callable[[Any], Sequence[str]]] = None,
) -> List[Match]:
    """Every candidate that matched, best first.

    Returns an empty list when nothing matched. `how` records which field won,
    which is useful for explaining a resolution in test mode.
    """
    name_of = name_of or _name_of
    id_of = id_of or _id_of
    aliases_of = aliases_of or _aliases_of

    matches: List[Match] = []
    for candidate in candidates:
        if candidate is None:
            continue
        score, how = candidate_score(
            query,
            name=name_of(candidate),
            obj_id=id_of(candidate),
            aliases=tuple(aliases_of(candidate) or ()),
        )
        if score > 0:
            matches.append(Match(candidate, score, how))

    # Ties break on the candidate's own identity, never on the order it was
    # passed in -- otherwise the same set of objects resolves differently
    # depending on how the caller happened to enumerate them.
    matches.sort(key=lambda m: (-m.score, normalize(name_of(m.obj)), id_of(m.obj)))
    return matches


def resolve_one(
    query: str,
    candidates: Iterable[Any],
    **kwargs: Any,
) -> Optional[Any]:
    """The single unambiguous best match, or None.

    Returns None when nothing matches **or** when the top two are equally good,
    so a caller does not silently act on an arbitrary one of two identical
    names. Use `resolve_all` to report the ambiguity, or `resolve_best` when a
    tie must still resolve to something.
    """
    matches = resolve_all(query, candidates, **kwargs)
    if not matches:
        return None
    if len(matches) > 1 and matches[1].score >= matches[0].score:
        return None
    return matches[0].obj


def resolve_best(
    query: str,
    candidates: Iterable[Any],
    *,
    prefer_shortest_name: bool = False,
    **kwargs: Any,
) -> Optional[Any]:
    """The best match even when it is not unique.

    For commands where acting on the closest match is better than refusing --
    and where the caller is not choosing between genuinely distinct things.
    Prefer `resolve_one` plus `ambiguity_message` when the player should be
    asked.

    `prefer_shortest_name` breaks a tie on how much of the candidate the query
    accounts for. With "Town Guard" and "Guard Captain Elara" both present, the
    query "guard" describes the guard far more completely than it describes the
    captain, so the guard should win rather than whichever sorts first.
    """
    matches = resolve_all(query, candidates, **kwargs)
    if not matches:
        return None
    if prefer_shortest_name and len(matches) > 1 and matches[1].score == matches[0].score:
        name_of = kwargs.get("name_of") or (lambda obj: str(getattr(obj, "name", "") or ""))
        tied = [m.obj for m in matches if m.score == matches[0].score]
        tied.sort(key=lambda obj: (len(normalize(name_of(obj))), normalize(name_of(obj))))
        return tied[0]
    return matches[0].obj


def resolve_exact(
    query: str,
    candidates: Iterable[Any],
    **kwargs: Any,
) -> Optional[Any]:
    """Only an exact name or id match; no prefix, word, or substring matching.

    For the first phase of a two-phase lookup, where a *loose* match must not
    shadow a later candidate. Concretely: with both a "Town Guard" and a
    "Guard Captain Elara" in the room, a loose match on "guard" finds the
    captain (the word appears in both names), so a command aimed at the guard
    reaches the wrong NPC. Restricting phase one to equality lets the guard win
    on specificity.

    Among equally exact candidates the shortest name wins, since a query that
    fully names a short name is a more complete statement of intent than one
    that is a fragment of a long name.
    """
    name_of = kwargs.get("name_of") or (lambda obj: str(getattr(obj, "name", "") or ""))
    id_of = kwargs.get("id_of") or (lambda obj: str(getattr(obj, "obj_id", "") or ""))
    aliases_of = kwargs.get("aliases_of") or _aliases_of

    wanted = normalize(query)
    if not wanted:
        return None

    exact: List[Any] = []
    for candidate in candidates:
        if candidate is None:
            continue
        if normalize(id_of(candidate)) == wanted:
            return candidate
        if normalize(name_of(candidate)) == wanted:
            exact.append(candidate)
            continue
        if any(normalize(alias) == wanted for alias in (aliases_of(candidate) or ())):
            exact.append(candidate)

    if not exact:
        return None
    exact.sort(key=lambda obj: (len(normalize(name_of(obj))), normalize(name_of(obj)), id_of(obj)))
    return exact[0]


def ambiguity_message(query: str, matches: Sequence[Match], limit: int = 4) -> str:
    """A question the player can answer, rather than a silent guess."""
    names = []
    for match in matches[:limit]:
        name = str(getattr(match.obj, "name", "") or getattr(match.obj, "obj_id", "?"))
        if name not in names:
            names.append(name)
    if not names:
        return "Which one did you mean?"
    if len(names) == 1:
        return "Did you mean %s?" % names[0]
    if len(names) == 2:
        return "Which do you mean, %s or %s?" % (names[0], names[1])
    return "Which do you mean: %s, or %s?" % (", ".join(names[:-1]), names[-1])
