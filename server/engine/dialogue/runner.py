"""Driving a conversation: open it, offer the replies, resolve what was typed.

Split out of `commands/interaction/npcs.py` deliberately. The command module
should decide *when* a conversation happens (is anyone here hostile? did the
player mean a topic or a reply?); this module decides *what* happens, and can be
unit-tested without a command context.

Two kinds of conversation end up here and share one presentation path:

* **Authored graphs** -- `data/dialogue/*.json`, chosen by the NPC template.
* **Quest negotiation** -- a node built from a quest's `negotiate` objective,
  so a negotiation is played as a conversation (you choose an approach, the
  skill check resolves it) instead of being a dice roll behind the word
  "complete". This is what "absorb the quest-negotiation path" means in
  practice: one presentation, one place that applies outcomes.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from engine.config import (
    FORMAT_CATEGORY, FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS,
)
from engine.core.skill_system import SkillSystem
from engine.dialogue.manager import DialogueManager, DialogueSession
from engine.presentation import show_internals


def manager_for(world) -> Optional[DialogueManager]:
    manager = getattr(world, "dialogue_manager", None)
    if manager is not None:
        return manager
    server = getattr(world, "server", None)
    return getattr(server, "dialogue_manager", None) if server is not None else None


def pending_negotiation(player, npc) -> Optional[Tuple[str, Dict[str, Any]]]:
    """The (quest_id, objective) this NPC is waiting to negotiate, if any.

    A hostile-faction NPC will still hear you out when a quest stage is
    specifically waiting on a negotiation with them -- which is why `talk`
    consults this *before* its generic hostile refusal.
    """
    quests = getattr(getattr(player, "runtime_state", None), "quests", None)
    if quests is None or npc is None:
        return None
    for quest_id, quest_data in (getattr(quests, "active", {}) or {}).items():
        if not isinstance(quest_data, dict):
            continue
        stages = quest_data.get("stages", [])
        index = quest_data.get("current_stage_index", 0)
        if not isinstance(stages, list) or not (0 <= index < len(stages)):
            continue
        objective = (stages[index] or {}).get("objective", {}) or {}
        if objective.get("type") != "negotiate":
            continue
        target_id = str(objective.get("target_npc_id", "") or "")
        if target_id and target_id in (
            str(getattr(npc, "template_id", "") or ""), str(getattr(npc, "obj_id", "") or "")
        ):
            return str(quest_id), objective
    return None


def has_pending_negotiation(player, npc) -> bool:
    return pending_negotiation(player, npc) is not None


def _quest_title(player, quest_id: str) -> str:
    quests = getattr(getattr(player, "runtime_state", None), "quests", None)
    entry = (getattr(quests, "active", {}) or {}).get(quest_id)
    if isinstance(entry, dict):
        return str(entry.get("title", "") or "")
    return ""


def start(world, player, npc) -> Optional[str]:
    """Open a conversation with `npc`, or return None if they have nothing to say.

    Negotiation wins over an authored graph: if a quest stage is waiting on a
    negotiation with this NPC, that is the conversation.
    """
    manager = manager_for(world)
    if manager is None or npc is None:
        return None

    negotiation = pending_negotiation(player, npc)
    if negotiation is not None:
        quest_id, objective = negotiation
        node = manager.negotiation_node(player, npc, objective, _quest_title(player, quest_id))
        manager.open_synthetic(player, npc, node, quest_id=quest_id)
        return manager.render_node(player, npc, node, manager.current(player))

    graph = manager.graph_for_npc(npc)
    if graph is None:
        return None
    node = manager.open(player, npc, graph)
    return manager.render_node(player, npc, node, manager.current(player))


def respond(world, player, npc, query: str) -> Optional[str]:
    """Resolve what the player typed against the open conversation.

    Returns None when there is no open conversation *or* when what was typed is
    not one of the offered replies -- the caller may have a topic in mind
    instead, and `talk grenda patterns` should reach her flat `dialog` dict
    rather than being told it misunderstood.
    """
    manager = manager_for(world)
    if manager is None or npc is None:
        return None
    session = manager.current(player)
    if session is None or session.npc_id != str(getattr(npc, "obj_id", "") or ""):
        return None

    node = manager.node_for_session(session)
    if node is None:
        manager.end(player)
        return None

    choices = manager.offered_choices(player, node)
    labels = [choice.label for choice in choices]
    index = manager.match_choice(query, labels, [list(choice.aliases) for choice in choices])
    if index is None:
        return None
    choice = choices[index]

    if choice.check:
        return _resolve_check(world, player, npc, manager, session, node, choice)

    outcome_lines: List[str] = []
    report = manager.apply(player, npc, choice.effects, quest_id=session.quest_id)
    message = report.message()
    if message:
        outcome_lines.append(message)

    if choice.ends_conversation or (not choice.next_node and not choice.effects):
        manager.end(player)
        closing = "\n".join(outcome_lines)
        return closing or "%sYou say your piece and the conversation ends.%s" % (FORMAT_CATEGORY, FORMAT_RESET)

    if not choice.next_node:
        # Effects on a reply that do not move anywhere: stay put, showing the
        # same node, so a one-off line does not strand the player.
        body = manager.render_node(player, npc, node, session)
        return "\n".join([line for line in [body, outcome_lines and "\n".join(outcome_lines)] if line])

    graph = manager.get(session.graph_id)
    next_node = graph.node(choice.next_node) if graph else None
    if next_node is None:
        manager.end(player)
        return "%sThe conversation trails off.%s" % (FORMAT_ERROR, FORMAT_RESET)

    session.node_id = next_node.node_id
    # Node entry effects fire on arrival, once per visit.
    entry_report = manager.apply(player, npc, next_node.effects, quest_id=session.quest_id)
    entry_message = entry_report.message()
    if entry_message:
        outcome_lines.append(entry_message)
    body = manager.render_node(player, npc, next_node, session)
    return "\n".join([line for line in [body, "\n".join(outcome_lines)] if line])


def _resolve_check(world, player, npc, manager, session, node, choice) -> str:
    """A reply that comes down to a skill: roll it, then follow the branch."""
    check = choice.check or {}
    skill = str(check.get("skill", "") or "").strip()
    try:
        difficulty = int(check.get("difficulty", 10) or 10)
    except (TypeError, ValueError):
        difficulty = 10
    # practice_check trains on the attempt as well as testing it, so a
    # negotiation is practice (ROADMAP P4: no check against a skill that
    # cannot be raised).
    success, message = SkillSystem.practice_check(player, skill, difficulty)
    branch_key = "success_node" if success else "fail_node"
    branch_node_id = str(check.get(branch_key, "") or "").strip()
    outcome = "success" if success else "fail"

    if session.quest_id:
        return _resolve_negotiation(world, player, npc, manager, session, choice, outcome, message, skill)

    effects = check.get("%s_effects" % outcome)
    report = manager.apply(player, npc, effects, quest_id=session.quest_id)
    lines: List[str] = []
    colour = FORMAT_SUCCESS if success else FORMAT_ERROR
    lines.append("%s[%s %s]%s %s" % (colour, skill.capitalize(), outcome.upper(), FORMAT_RESET, message))
    message_text = report.message()
    if message_text:
        lines.append(message_text)

    graph = manager.get(session.graph_id)
    next_node = graph.node(branch_node_id) if graph else None
    if next_node is None:
        manager.end(player)
        return "\n".join(lines)
    session.node_id = next_node.node_id
    lines.append(manager.render_node(player, npc, next_node, session))
    return "\n".join(line for line in lines if line)


def _resolve_negotiation(world, player, npc, manager, session, choice, outcome, check_message, skill) -> str:
    """Outcome of a quest negotiation, applied through the quest manager.

    Kept here rather than in the quest module because it is the *result of a
    conversation*: the quest authors the stakes, the dialogue system asks the
    question and reports the answer.
    """
    quest_manager = getattr(world, "quest_manager", None)
    quest_id = session.quest_id
    objective: Dict[str, Any] = {}
    quests = getattr(getattr(player, "runtime_state", None), "quests", None)
    entry = (getattr(quests, "active", {}) or {}).get(quest_id)
    if isinstance(entry, dict):
        stages = entry.get("stages", [])
        index = entry.get("current_stage_index", 0)
        if isinstance(stages, list) and 0 <= index < len(stages):
            objective = (stages[index] or {}).get("objective", {}) or {}

    if quest_manager is None:
        manager.end(player)
        return "%sThere is nothing to negotiate after all.%s" % (FORMAT_ERROR, FORMAT_RESET)

    branches = objective.get("choices", {}) if isinstance(objective.get("choices"), dict) else {}
    branch = branches.get(outcome) if isinstance(branches.get(outcome), dict) else {}
    manager.end(player)

    dialogue = quest_manager.advance_quest_stage(player, quest_id, choice_id=outcome)
    colour = FORMAT_SUCCESS if outcome == "success" else FORMAT_ERROR
    header = "%s[%s %s]%s %s" % (colour, skill.capitalize(), outcome.upper(), FORMAT_RESET, check_message)

    if dialogue == "QUEST_COMPLETE":
        resolution = "PEACEFUL_SUCCESS" if outcome == "success" else "VIOLENT_SUCCESS"
        title = _quest_title(player, quest_id) or quest_id
        rewards = quest_manager.complete_quest(player, quest_id, resolution=resolution)
        closing = str(
            branch.get("dialogue")
            or branch.get("closing")
            or (objective.get("closing") if isinstance(objective.get("closing"), dict) else "")
            or "Negotiation concluded."
        )
        lines = [
            header,
            "%s[Quest Complete] %s%s" % (FORMAT_SUCCESS, title, FORMAT_RESET),
            '%s"%s"%s' % (FORMAT_HIGHLIGHT, closing, FORMAT_RESET),
        ]
        description = str(branch.get("description", "") or "")
        if description:
            lines.append("%s(%s)%s" % (FORMAT_CATEGORY, description, FORMAT_RESET))
        if rewards:
            lines.append(str(rewards))
        return "\n".join(lines)

    lines = [header]
    if dialogue:
        lines.append('%s"%s"%s' % (FORMAT_HIGHLIGHT, dialogue, FORMAT_RESET))
    description = str(branch.get("description", "") or "")
    if description:
        lines.append("%s(%s)%s" % (FORMAT_CATEGORY, description, FORMAT_RESET))
    next_objective = _current_stage_description(player, quest_id)
    if next_objective:
        lines.append("%sNew Objective:%s %s" % (FORMAT_CATEGORY, FORMAT_RESET, next_objective))
    return "\n".join(lines)


def _current_stage_description(player, quest_id: str) -> str:
    """The stage the player is on now, so a negotiation that went sideways
    still tells them what happens next."""
    quests = getattr(getattr(player, "runtime_state", None), "quests", None)
    entry = (getattr(quests, "active", {}) or {}).get(quest_id)
    if not isinstance(entry, dict):
        return ""
    stages = entry.get("stages", [])
    index = entry.get("current_stage_index", 0)
    if not isinstance(stages, list) or not (0 <= index < len(stages)):
        return ""
    stage = stages[index]
    return str(stage.get("description", "") or "") if isinstance(stage, dict) else ""


def continue_or_report(world, player, npc, query: str) -> str:
    """`respond`, with a helpful message when nothing matches."""
    manager = manager_for(world)
    if manager is None:
        return "%sThis world has no conversations to continue.%s" % (FORMAT_ERROR, FORMAT_RESET)
    session = manager.current(player)
    if session is None:
        negotiation = pending_negotiation(player, npc)
        if negotiation is not None and npc is not None:
            opened = start(world, player, npc)
            if opened:
                return opened
        suggestion = ""
        last = getattr(player, "last_talked_to", None)
        if last:
            for candidate in getattr(world, "npcs", {}).values():
                if str(getattr(candidate, "obj_id", "")) == str(last):
                    suggestion = " Try 'talk %s'." % getattr(candidate, "name", "them")
                    break
        return "%sYou are not in the middle of a conversation.%s%s" % (
            FORMAT_ERROR, suggestion, FORMAT_RESET,
        )
    if npc is None:
        npc = _npc_from_session(world, player, session)
    if npc is None:
        manager.end(player)
        return "%sWhoever you were talking to has gone.%s" % (FORMAT_ERROR, FORMAT_RESET)
    response = respond(world, player, npc, query)
    if response is not None:
        return response

    # Nothing matched a reply. Say so, and show the replies again -- the player
    # is still in the conversation, and repeating the list is cheaper than
    # making them ask for it.
    node = manager.node_for_session(session)
    hint = "%s did not understand that. Reply with a number, or the words of a reply." % (
        getattr(npc, "name", "They")
    )
    listing = manager.format_choices(player, node) if node is not None else ""
    return "%s%s%s%s" % (FORMAT_ERROR, hint, FORMAT_RESET, ("\n\n" + listing) if listing else "")


def _npc_from_session(world, player, session: DialogueSession):
    for npc in getattr(world, "npcs", {}).values():
        if str(getattr(npc, "obj_id", "")) == session.npc_id:
            return npc
    return None


def debug_state(world, player) -> str:
    """Test-mode view of the open conversation, if any."""
    manager = manager_for(world)
    if manager is None:
        return "no dialogue manager"
    if not show_internals({"world": world, "player": player}):
        return ""
    session = manager.current(player)
    if session is None:
        return "dialogue: closed"
    return "dialogue: %s @ %s (npc %s)" % (
        session.graph_id or "negotiation", session.node_id, session.npc_id or "-"
    )
