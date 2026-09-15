"""Loading dialogue graphs, and running one conversation at a time.

`DialogueManager` owns three things:

1. **Loading** `data/dialogue/*.json` into `DialogueGraph` objects, reporting
   structural problems (a root that does not exist, a `next_node` pointing at
   nothing) rather than discovering them mid-sentence.
2. **Sessions** -- which node a player is currently looking at, and with whom.
   State is in memory, keyed by player id: a conversation does not survive a
   disconnect, which is the honest behaviour for something that is happening
   *now*.
3. **Presentation** -- rendering a node and its choices, in player mode or test
   mode, and matching what the player typed to the choice they meant.

Choice matching goes through the shared resolver (`engine/naming.py`), so a
player may type the number, the whole line, or enough of it to be unambiguous.
That is the same rule the rest of the game follows: players type what they see.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from engine import presentation
from engine.conditions import Evaluation, evaluate, explain
from engine.config import (
    FORMAT_CATEGORY, FORMAT_ERROR, FORMAT_HIGHLIGHT, FORMAT_RESET, FORMAT_SUCCESS,
    FORMAT_TITLE,
)
from engine.dialogue import effects as dialogue_effects
from engine.dialogue.graph import DialogueChoice, DialogueGraph, DialogueNode
from engine.naming import resolve_all, resolve_best
from engine.utils.logger import Logger

DIALOGUE_DIRECTORY = "dialogue"

# An NPC template points at a graph with this key (in `properties`).
NPC_GRAPH_KEY = "dialogue"


def parse_graph(payload: Any, graph_id: str, source: str = "") -> Tuple[Optional[DialogueGraph], List[str]]:
    """Build a `DialogueGraph`. Returns (graph, issues); graph is None if unusable."""
    issues: List[str] = []
    if not isinstance(payload, dict):
        return None, ["%s: dialogue graph must be an object" % (source or graph_id)]

    nodes_payload = payload.get("nodes")
    if not isinstance(nodes_payload, dict) or not nodes_payload:
        return None, ["%s: dialogue graph '%s' has no nodes" % (source or graph_id, graph_id)]

    nodes: Dict[str, DialogueNode] = {}
    for raw_id, raw_node in nodes_payload.items():
        node_id = str(raw_id).strip()
        if isinstance(raw_node, str):
            # `"greeting": "Hello."` -- a one-line node with no choices. Worth
            # supporting: it is how most conversations actually end.
            nodes[node_id] = DialogueNode(node_id=node_id, text=raw_node)
            continue
        if not isinstance(raw_node, dict):
            issues.append("%s: node '%s' must be an object or a string" % (source or graph_id, node_id))
            continue
        choices: List[DialogueChoice] = []
        raw_choices = raw_node.get("choices") or []
        if not isinstance(raw_choices, list):
            issues.append("%s: node '%s'.choices must be an array" % (source or graph_id, node_id))
            raw_choices = []
        for index, raw_choice in enumerate(raw_choices):
            label = "%s: node '%s'.choices[%d]" % (source or graph_id, node_id, index)
            if isinstance(raw_choice, str):
                choices.append(DialogueChoice(
                    text=raw_choice, node_id=node_id, index=index,
                    ends_conversation=True, raw={"text": raw_choice},
                ))
                continue
            if not isinstance(raw_choice, dict):
                issues.append("%s must be an object or a string" % label)
                continue
            text = str(raw_choice.get("text", "") or "").strip()
            if not text:
                issues.append("%s requires text" % label)
                continue
            check = raw_choice.get("check")
            if check is not None and not isinstance(check, dict):
                issues.append("%s.check must be an object" % label)
                check = None
            effect_block = raw_choice.get("effects") or {}
            if not isinstance(effect_block, dict):
                issues.append("%s.effects must be an object" % label)
                effect_block = {}
            choices.append(DialogueChoice(
                text=text,
                node_id=node_id,
                index=index,
                next_node=str(raw_choice.get("next_node", "") or "").strip(),
                condition=raw_choice.get("condition"),
                effects=effect_block,
                check=check,
                ends_conversation=bool(raw_choice.get("end", False)),
                aliases=[
                    str(alias).strip()
                    for alias in (raw_choice.get("aliases") or [])
                    if isinstance(alias, (str, int)) and str(alias).strip()
                ] if isinstance(raw_choice.get("aliases") or [], list) else [],
                raw=raw_choice,
            ))

        node_effects = raw_node.get("effects") or {}
        if not isinstance(node_effects, dict):
            issues.append("%s: node '%s'.effects must be an object" % (source or graph_id, node_id))
            node_effects = {}
        text = raw_node.get("text", "")
        if not isinstance(text, (str, dict)):
            issues.append("%s: node '%s'.text must be a string or a mode mapping" % (source or graph_id, node_id))
            text = str(text)
        nodes[node_id] = DialogueNode(
            node_id=node_id, text=text, choices=choices, effects=node_effects, raw=raw_node,
        )

    root = str(payload.get("root", "") or "").strip()
    if not root:
        root = "root" if "root" in nodes else (sorted(nodes)[0] if nodes else "")
        issues.append(
            "%s: dialogue graph '%s' does not declare 'root'; assuming '%s'"
            % (source or graph_id, graph_id, root)
        )
    if root not in nodes:
        issues.append("%s: dialogue graph '%s' root '%s' is not a node" % (source or graph_id, graph_id, root))

    graph = DialogueGraph(graph_id=graph_id, root=root, nodes=nodes, source=source)
    issues.extend(structural_issues(graph))
    return graph, issues


def structural_issues(graph: DialogueGraph) -> List[str]:
    """Problems visible from inside the graph alone."""
    issues: List[str] = []
    if graph.root not in graph.nodes:
        issues.append("graph '%s': root '%s' is not a node" % (graph.graph_id, graph.root))
    for node_id, kind, target in graph.references():
        if target not in graph.nodes:
            issues.append(
                "graph '%s': node '%s' %s '%s' is not a node"
                % (graph.graph_id, node_id, kind, target)
            )
    for node in graph.nodes.values():
        for choice in node.choices:
            has_destination = bool(choice.next_node) or choice.ends_conversation or bool(choice.check)
            if not has_destination and not choice.effects:
                issues.append(
                    "graph '%s': node '%s' choice '%s' goes nowhere "
                    "(needs next_node, end, check, or effects)"
                    % (graph.graph_id, node.node_id, choice.text)
                )
            if choice.check:
                check = choice.check
                if not str(check.get("skill", "") or "").strip():
                    issues.append(
                        "graph '%s': node '%s' choice '%s' check has no skill"
                        % (graph.graph_id, node.node_id, choice.text)
                    )
                for key in ("success_node", "fail_node"):
                    if not str(check.get(key, "") or "").strip():
                        issues.append(
                            "graph '%s': node '%s' choice '%s' check has no %s"
                            % (graph.graph_id, node.node_id, choice.text, key)
                        )
            for key in sorted(choice.effects):
                if key not in dialogue_effects.KNOWN_EFFECTS:
                    issues.append(
                        "graph '%s': node '%s' choice '%s' has unknown effect '%s'"
                        % (graph.graph_id, node.node_id, choice.text, key)
                    )
        for key in sorted(node.effects):
            if key not in dialogue_effects.KNOWN_EFFECTS:
                issues.append(
                    "graph '%s': node '%s' has unknown effect '%s'"
                    % (graph.graph_id, node.node_id, key)
                )
    return issues


@dataclass
class DialogueSession:
    """Where one player is in one conversation."""

    graph_id: str
    node_id: str
    npc_id: str = ""
    quest_id: str = ""
    synthetic: Optional[DialogueNode] = None


class DialogueManager:
    def __init__(self, world):
        self.world = world
        self.content_root = getattr(world, "content_root", None)
        self.graphs: Dict[str, DialogueGraph] = {}
        self.issues: List[str] = []
        self._sessions: Dict[str, DialogueSession] = {}
        self._load()

    # -- loading ---------------------------------------------------------

    def _load(self) -> None:
        if not self.content_root:
            return
        directory = os.path.join(str(self.content_root), DIALOGUE_DIRECTORY)
        if not os.path.isdir(directory):
            return
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".json"):
                continue
            path = os.path.join(directory, filename)
            graph_id = filename[: -len(".json")]
            try:
                with open(path, "r", encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, json.JSONDecodeError) as error:
                self.issues.append("%s: could not read dialogue graph: %s" % (filename, error))
                continue
            if isinstance(payload, dict) and payload.get("id"):
                graph_id = str(payload["id"]).strip()
            graph, issues = parse_graph(payload, graph_id, filename)
            self.issues.extend(issues)
            if graph is None:
                continue
            if graph_id in self.graphs:
                self.issues.append("%s: duplicate dialogue graph id '%s'" % (filename, graph_id))
                continue
            self.graphs[graph_id] = graph
            if self.issues:
                for issue in issues:
                    Logger.warning("Dialogue", issue)

    # -- lookup ----------------------------------------------------------

    def get(self, graph_id: str) -> Optional[DialogueGraph]:
        return self.graphs.get(str(graph_id or "").strip())

    def graph_for_npc(self, npc) -> Optional[DialogueGraph]:
        if npc is None:
            return None
        properties = getattr(npc, "properties", None)
        graph_id = ""
        if isinstance(properties, dict):
            graph_id = str(properties.get(NPC_GRAPH_KEY, "") or "").strip()
        return self.get(graph_id) if graph_id else None

    def has_graph(self, npc) -> bool:
        return self.graph_for_npc(npc) is not None

    # -- session ---------------------------------------------------------

    def current(self, player) -> Optional[DialogueSession]:
        return self._sessions.get(str(getattr(player, "obj_id", "")))

    def open(self, player, npc, graph: DialogueGraph, node_id: str = "", quest_id: str = "") -> DialogueNode:
        node = graph.node(node_id or graph.root) or graph.node(graph.root)
        assert node is not None  # parse_graph guarantees a root node exists
        self._sessions[str(player.obj_id)] = DialogueSession(
            graph_id=graph.graph_id, node_id=node.node_id,
            npc_id=str(getattr(npc, "obj_id", "") or ""), quest_id=quest_id,
        )
        return node

    def open_synthetic(self, player, npc, node: DialogueNode, quest_id: str = "") -> DialogueNode:
        """Run a node the engine built rather than content authored.

        Used for quest negotiation, which is a conversation whose shape comes
        from the quest (`objective.choices`) but which must be *presented* like
        any other: numbered replies, mode-aware annotations, the shared
        resolver matching what the player typed.
        """
        self._sessions[str(player.obj_id)] = DialogueSession(
            graph_id="", node_id=node.node_id,
            npc_id=str(getattr(npc, "obj_id", "") or ""), quest_id=quest_id,
            synthetic=node,
        )
        return node

    def end(self, player) -> None:
        self._sessions.pop(str(getattr(player, "obj_id", "")), None)

    def node_for_session(self, session: DialogueSession) -> Optional[DialogueNode]:
        if session.synthetic is not None:
            return session.synthetic
        graph = self.get(session.graph_id)
        return graph.node(session.node_id) if graph else None

    # -- presentation ----------------------------------------------------

    def presentation_context(self, player) -> Dict[str, Any]:
        return {"world": getattr(player, "world", None), "player": player}

    def evaluate_choice(self, player, choice: DialogueChoice) -> Evaluation:
        return evaluate(choice.condition, player)

    def available_choices(self, player, node: DialogueNode) -> List[Tuple[DialogueChoice, Evaluation, bool]]:
        """Every choice, with its evaluation and whether it is offered.

        Hidden choices are returned too -- test mode lists them *because* they
        are hidden, and a player never sees the annotation that says so.
        """
        rows: List[Tuple[DialogueChoice, Evaluation, bool]] = []
        for choice in node.choices:
            result = self.evaluate_choice(player, choice)
            rows.append((choice, result, bool(result.satisfied)))
        return rows

    def format_choices(self, player, node: DialogueNode) -> str:
        """The numbered reply list, annotated for whoever is reading it."""
        context = self.presentation_context(player)
        show_internals = presentation.show_internals(context)
        rows = self.available_choices(player, node)
        lines: List[str] = []
        number = 0
        for choice, result, ok in rows:
            if ok:
                number += 1
                line = "%s%d.%s %s" % (FORMAT_HIGHLIGHT, number, FORMAT_RESET, choice.label)
            elif not show_internals:
                continue
            else:
                # Unavailable lines deliberately take no number: numbering them
                # made a hidden reply and a real one share "3", and a player who
                # typed 3 got whichever the loop reached first.
                line = "%s- %s %s(unavailable: %s)%s" % (
                    FORMAT_ERROR, choice.label,
                    FORMAT_CATEGORY, explain(choice.condition, player), FORMAT_RESET,
                )
            if show_internals:
                annotations = self._choice_annotations(choice)
                if annotations:
                    line += " %s[%s]%s" % (FORMAT_CATEGORY, annotations, FORMAT_RESET)
            lines.append(line)
        return "\n".join(lines)

    def _choice_annotations(self, choice: DialogueChoice) -> str:
        parts: List[str] = []
        effect_text = dialogue_effects.describe_effects(choice.effects)
        if effect_text:
            parts.append("effects: %s" % effect_text)
        if choice.check:
            check = choice.check
            parts.append(
                "check %s %s -> %s/%s"
                % (check.get("skill", "?"), check.get("difficulty", "?"),
                   check.get("success_node", "?"), check.get("fail_node", "?"))
            )
        if choice.next_node:
            parts.append("-> %s" % choice.next_node)
        if choice.ends_conversation:
            parts.append("ends conversation")
        return "; ".join(parts)

    def render_node(self, player, npc, node: DialogueNode, session: Optional[DialogueSession] = None) -> str:
        context = self.presentation_context(player)
        show_internals = presentation.show_internals(context)
        speaker = getattr(npc, "name", "") or "Someone"
        text = presentation.variant(node.text, context)
        header = "%sCONVERSATION WITH %s%s" % (FORMAT_TITLE, str(speaker).upper(), FORMAT_RESET)
        body = '%s"%s"%s' % (FORMAT_HIGHLIGHT, text, FORMAT_RESET)
        chunks = [header, "", body]
        if show_internals:
            node_effects = dialogue_effects.describe_effects(node.effects)
            if node_effects:
                chunks.append("%s[node effects: %s]%s" % (FORMAT_CATEGORY, node_effects, FORMAT_RESET))
            if session is not None:
                origin = session.graph_id or "negotiation"
                chunks.append("%s[node %s of %s]%s" % (FORMAT_CATEGORY, node.node_id, origin, FORMAT_RESET))
        choices = self.format_choices(player, node)
        if choices:
            chunks.append("")
            chunks.append(choices)
        elif not show_internals:
            chunks.append("")
            chunks.append("%s(That seems to be all.)%s" % (FORMAT_CATEGORY, FORMAT_RESET))
        return "\n".join(chunks)

    # -- choice matching -------------------------------------------------

    def match_choice(self, query: str, labels: List[str], aliases: Optional[List[List[str]]] = None) -> Optional[int]:
        """Index into `labels` for what the player typed, or None.

        Numbers are accepted directly; anything else goes through the shared
        resolver, which means "what are you working on" finds "What are you
        working on?". A choice may also author `aliases` -- a player who wants
        to say "show me the pattern" should not have to guess that the author
        wrote "Show me how to make one" instead.

        An ambiguous fragment resolves to nothing rather than to the wrong
        reply: saying the wrong thing to an NPC is worse than being asked again.
        """
        text = str(query or "").strip()
        if not text:
            return None
        if text.isdigit():
            index = int(text) - 1
            return index if 0 <= index < len(labels) else None

        candidates: List[Dict[str, Any]] = []
        for index, label in enumerate(labels):
            entry: Dict[str, Any] = {"name": label, "obj_id": label, "index": index}
            if aliases and index < len(aliases) and aliases[index]:
                entry["aliases"] = list(aliases[index])
            candidates.append(entry)

        matches = resolve_all(text, candidates)
        if not matches:
            return None
        # A tie means the player's words fit two replies equally well. Saying the
        # wrong thing to an NPC is worse than being asked to repeat yourself, so
        # ambiguous input resolves to nothing -- the same rule `resolve_one`
        # applies to items, applied here where the stakes are a conversation.
        if len(matches) > 1 and matches[1].score >= matches[0].score:
            return None
        matched = matches[0].obj
        if not isinstance(matched, dict):
            return None
        index = matched.get("index")
        return index if isinstance(index, int) and 0 <= index < len(labels) else None

    def offered_labels(self, player, node: DialogueNode) -> List[str]:
        return [choice.label for choice, _result, ok in self.available_choices(player, node) if ok]

    def offered_choices(self, player, node: DialogueNode) -> List[DialogueChoice]:
        return [choice for choice, _result, ok in self.available_choices(player, node) if ok]

    # -- effects ---------------------------------------------------------

    def apply(self, player, npc, effect_block: Any, quest_id: str = "") -> dialogue_effects.EffectReport:
        return dialogue_effects.apply_effects(effect_block, {
            "player": player,
            "world": getattr(player, "world", None),
            "npc": npc,
            "quest_id": quest_id,
        })

    # -- negotiation -----------------------------------------------------

    def negotiation_node(self, player, npc, objective: Dict[str, Any], quest_title: str = "") -> DialogueNode:
        """A conversation built from a quest's `negotiate` objective.

        The quest authors the stakes (`prompt`, `choices`) and the skill check;
        this turns that into an ordinary node so negotiation is presented and
        played like any other conversation instead of being a dice roll behind
        the word "complete".
        """
        objective = objective or {}
        skill = str(objective.get("skill", "diplomacy") or "diplomacy")
        try:
            difficulty = int(objective.get("difficulty", 10) or 10)
        except (TypeError, ValueError):
            difficulty = 10
        prompt = str(objective.get("prompt", "") or "").strip()
        if not prompt:
            greeting = ""
            dialog = getattr(npc, "dialog", None)
            if isinstance(dialog, dict):
                greeting = str(dialog.get("greeting", "") or "")
            if not greeting:
                # `talk()` on an NPC with nothing authored formats its
                # `default_dialog` template; reading that attribute raw left a
                # literal "{name}" in front of the player.
                talk = getattr(npc, "talk", None)
                greeting = str(talk() if callable(talk) else "")
            prompt = greeting.strip() or "They wait for you to speak."

        approach = str(objective.get("approach", "") or "").strip()
        if not approach:
            approach_text = objective.get("approach_text")
            if isinstance(approach_text, dict):
                approach = str(presentation.variant(approach_text, self.presentation_context(player)) or "")
            else:
                approach = "Make your case."
            for outcome in ("success", "fail"):
                authored = (objective.get("choices", {}) or {}).get(outcome, {})
                if isinstance(authored, dict) and authored.get("text"):
                    approach = str(authored["text"])
                    break

        outcomes = objective.get("choices", {}) if isinstance(objective.get("choices"), dict) else {}
        success = outcomes.get("success", {}) if isinstance(outcomes.get("success"), dict) else {}
        fail = outcomes.get("fail", {}) if isinstance(outcomes.get("fail"), dict) else {}

        node = DialogueNode(
            node_id="negotiation",
            text=prompt,
            choices=[
                DialogueChoice(
                    text=approach,
                    node_id="negotiation",
                    index=0,
                    check={
                        "skill": skill,
                        "difficulty": difficulty,
                        "success_node": "__negotiation_success",
                        "fail_node": "__negotiation_fail",
                    },
                ),
                DialogueChoice(
                    text="Say nothing more.",
                    node_id="negotiation",
                    index=1,
                    ends_conversation=True,
                ),
            ],
            raw={"negotiation": True, "quest_title": quest_title},
        )
        node.raw["outcomes"] = {"success": success, "fail": fail}
        return node
