# toolkit/engine_vocabulary_dump.py
"""The engine's own vocabularies, as JSON, for the editor's parity check.

The editor's `DialogueSchema` and `QuestSchema` hold *copies* of the engine's
condition kinds, effect keys and objective types. They have to: the editor needs
field types to choose widgets, and it cannot import Python. But a copy drifts, and
the drift is silent in the worst way -- an author picks a kind the engine does not
know and the only symptom is that the gate never fires.

So the copies are checked against the source. This is the source: it imports the
engine's own sets rather than re-declaring them, which is the point. A hand-written
list here would be a third copy.

Printed as one JSON object, matching the convention `toolkit/editor_validate.py`
set: the editor makes one subprocess call and parses the last balanced object.

Exit codes: 0 always, unless the engine cannot be imported at all (2).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_SERVER_ROOT = _REPO_ROOT / "server"
for _path in (_REPO_ROOT, _SERVER_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))


def _content_set_module():
    """`engine/server/content_set.py`, loaded without its package.

    `import engine.server.content_set` executes `engine/server/__init__.py`, which
    pulls in the whole headless runtime -- and that imports the command modules,
    whose startup logging lands on stdout ahead of this dump's JSON. The module
    itself imports nothing but the standard library, so loading it by path reads
    the same constants with none of the noise. Anything the editor consumes here is
    a string or a tuple, so a package-level import would gain nothing.
    """
    import importlib.util

    path = _SERVER_ROOT / "engine" / "server" / "content_set.py"
    spec = importlib.util.spec_from_file_location("_engine_content_set", path)
    module = importlib.util.module_from_spec(spec)
    # Registered before execution because `@dataclass` resolves its own module
    # through `sys.modules` while the class body is being processed.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main() -> int:
    try:
        from engine.conditions import KNOWN_KINDS
        from engine.dialogue.effects import KNOWN_EFFECTS
        from engine.core.knowledge_manager import (
            CAMPAIGN_STATES, KNOWLEDGE_CONDITION_KINDS, KNOWLEDGE_STATES, QUEST_STATES,
        )
        from engine.core.quests import tracker  # noqa: F401 - imported to prove it exists
        from engine.utils.utils import DIRECTION_OPPOSITES
        from engine.config import (
            FACTIONS,
            FACTION_DISPOSITIONS,
            FACTION_DEFAULT_DISPOSITIONS,
            NPC_BEHAVIOR_TYPES,
        )

        cs = _content_set_module()
    except Exception as error:  # noqa: BLE001 - report, do not traceback at the caller
        print(json.dumps({"error": str(error)}))
        return 2

    # The objective types the engine dispatches on. Read from the modules that
    # route them rather than from a list: `tracker` handles the event-driven ones,
    # `npcs` and `manager` the conversation-driven ones, and the generator builds
    # the procedural variant. A type nothing routes is a type that does nothing.
    objective_types = sorted(
        name for name in _objective_type_names() if name
    )

    print(json.dumps({
        "condition_kinds": sorted(KNOWN_KINDS),
        "effect_keys": sorted(KNOWN_EFFECTS),
        "objective_types": objective_types,
        # Exits are game contracts too. In particular, `climb` reciprocates with
        # `descend`, while `dive` reciprocates with `surface`; treating either as
        # an interchangeable vertical pair lets the editor write misleading links.
        "direction_opposites": dict(sorted(DIRECTION_OPPOSITES.items())),
        # The field names each effect's object shape must use, read from the
        # readers. Only the effects whose value is an object are listed: the rest
        # take a bare id or number, which is what the editor's "kind" already says.
        "effect_fields": _effect_fields(),
        # The two engine-owned words an NPC template names directly (see
        # `content_set.py::_validate_npc_faction_and_behavior`). `NPCVocabulary.gd`
        # is the editor's copy; `schema_parity_smoke.gd` checks it against this.
        "factions": {
            "built_in": sorted(FACTIONS),
            "dispositions": sorted(FACTION_DISPOSITIONS),
            "default_dispositions": dict(sorted(FACTION_DEFAULT_DISPOSITIONS.items())),
        },
        "npc_behavior_types": sorted(NPC_BEHAVIOR_TYPES),
        # What an affix's `allowed_types` is compared with: the generated item's
        # class name. `AffixInspector.gd` offers these plus "All".
        "item_classes": _item_classes(),
        # A topic response's own condition vocabulary (not `condition_kinds`
        # above, which is dialogue's). `KnowledgeInspector.gd` holds the copy.
        "knowledge_conditions": {
            "kinds": sorted(KNOWLEDGE_CONDITION_KINDS),
            "knowledge_states": sorted(KNOWLEDGE_STATES),
            "campaign_states": sorted(CAMPAIGN_STATES),
            "quest_states": sorted(QUEST_STATES),
        },
        # The manifest's shape, for the editor's create-set flow. `content_set.py`
        # is what refuses a set, so it owns these; the editor keeps a copy only
        # because writing a manifest needs field *names* to build a form with, and
        # this is what keeps the copy equal.
        "manifest": {
            "filename": cs.CONTENT_SET_MANIFEST_NAME,
            "schema_version": cs.CONTENT_SET_SCHEMA_VERSION,
            "runtime_api_version": cs.RUNTIME_API_VERSION,
            "id_pattern": cs._CONTENT_SET_ID_PATTERN.pattern,
            "required_strings": sorted(cs.REQUIRED_MANIFEST_STRINGS),
            "required_paths": sorted(cs.REQUIRED_MANIFEST_PATHS),
            "optional_paths": sorted(cs.OPTIONAL_MANIFEST_PATHS),
            "required_start_fields": sorted(cs.REQUIRED_START_FIELDS),
            "required_data_directories": sorted(cs._REQUIRED_DATA_DIRECTORIES),
            "capabilities": sorted(cs._CAPABILITY_SYSTEMS),
        },
    }, indent=2, sort_keys=True))
    return 0


def _item_classes() -> list:
    from engine.items.item_factory import ITEM_CLASS_MAP

    return sorted({cls.__name__ for cls in ITEM_CLASS_MAP.values()})


def _objective_type_names() -> set:
    """Objective type literals the engine compares against `objective["type"]`."""
    import re

    names: set = set()
    for path in (_SERVER_ROOT / "engine").rglob("*.py"):
        source = path.read_text(encoding="utf-8", errors="replace")
        names.update(re.findall(r'objective(?:_type|\["type"\]|\.get\("type"\))?\s*==\s*"([a-z_0-9]+)"', source))
        names.update(re.findall(r'obj_type\s*(?:==|in)\s*[\[(]?"?([a-z_0-9]+)"?', source))
        names.update(re.findall(r'objective_type\s+in\s+\[([^\]]+)\]', source))
    # The last pattern captures a list literal, so split those apart.
    expanded: set = set()
    for name in names:
        for part in re.findall(r'"([a-z_0-9]+)"', name) or [name]:
            expanded.add(part)
    return {name for name in expanded if name and name != "type"}


def _effect_fields() -> dict:
    """`{effect: [required field names]}` for the object-shaped effects.

    Read from the readers' own `raw.get("...")` calls, so this cannot disagree with
    what the engine does -- which is the failure the hints drifted into.
    """
    import re

    source = (_SERVER_ROOT / "engine" / "dialogue" / "effects.py").read_text(encoding="utf-8")
    fields: dict = {}
    for effect, reader in (
        ("adjust_relationship", "_apply_relationship_effects"),
        ("move_npc", "_apply_move_npc_effect"),
        ("reveal_exit", "_apply_exit_effect"),
        ("give_rewards", "_apply_reward_effect"),
    ):
        start = source.find("def %s(" % reader)
        if start == -1:
            continue
        # Up to the next top-level def, so one reader cannot borrow another's keys.
        end = source.find("\ndef ", start + 1)
        body = source[start:end if end != -1 else len(source)]
        keys = set(re.findall(r'(?:raw|rewards|effects\[[^\]]+\])\.get\(\s*"([a-z_]+)"', body))
        keys.update(re.findall(r'raw\.get\(\s*"([a-z_]+)"', body))
        fields[effect] = sorted(keys)
    return fields


if __name__ == "__main__":
    raise SystemExit(main())
