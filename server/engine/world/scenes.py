# engine/world/scenes.py
"""A scene is something the player watches: a few lines told a moment apart, with things happening between them.

Scenes live in `data/scenes/*.json` (each file an object of scenes keyed by id) and are begun by the `play_scene`
effect, so a trigger, a conversation, a quest or a campaign node can all start one:

    "ilmara_falls": {
        "beats": [
            {"text": "The doors give way, and the soldiers pour in."},
            {"after": 3, "text": "The acolytes do not run.", "pace": "slow"},
            {"after": 3, "effects": {"remove_npc": "ilmaran_acolyte"}, "text": "It is over very quickly."}
        ]
    }

A beat is `{text, after, pace, effects}`. `after` is the wait, in seconds, after the beat before it (the first
beat's wait is counted from the moment the scene begins; a beat with no `after` waits 0 for the first and 2 for
the rest). `pace` is how fast a client types the text out (utils/pacing.py). `effects` is the same vocabulary a
conversation uses (dialogue/effects.py) and happens as the beat is told, so a scene can move people, spawn a
fight, change the room or carry the player somewhere. A scene can begin another (`play_scene` in a beat).

While a scene is running its player is a spectator: commands that change the world are refused until it ends
(`"lock": false` on a scene leaves the player free). How far a scene has got is kept on the player
(`_scene.<id>`, the number of the next beat), so a restart carries on where it was instead of leaving the story
half told; `resume` picks it up. A finished scene leaves `_scene_done.<id>` behind.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

from engine.utils import pacing
from engine.utils.logger import Logger

SCENES_DIRECTORY = "scenes"
SCENE_KEYS = ("beats", "lock", "note")
BEAT_KEYS = ("text", "after", "pace", "effects")
DEFAULT_FIRST_WAIT = 0.0
DEFAULT_WAIT = 2.0
MAX_WAIT = 600

RUNNING_PREFIX = "_scene."
DONE_PREFIX = "_scene_done."


class SceneRunner:
    def __init__(self, world):
        self.world = world
        self.scenes: Dict[str, Dict[str, Any]] = {}

    # -- loading ---------------------------------------------------------------
    def add(self, scene_id: str, definition: Dict[str, Any]) -> None:
        self.scenes[str(scene_id)] = definition

    def load(self, content_root: Optional[str]) -> int:
        """Read `data/scenes/*.json`. A malformed file or scene is reported and skipped; content validation
        refuses it before the game runs, so this is the safety net."""
        self.scenes = {}
        if not content_root:
            return 0
        directory = os.path.join(str(content_root), SCENES_DIRECTORY)
        if not os.path.isdir(directory):
            return 0
        for name in sorted(os.listdir(directory)):
            if not name.endswith(".json"):
                continue
            try:
                with open(os.path.join(directory, name), encoding="utf-8") as handle:
                    payload = json.load(handle)
            except (OSError, ValueError) as error:
                Logger.warning("Scenes", "Could not read %s: %s" % (name, error))
                continue
            if not isinstance(payload, dict):
                Logger.warning("Scenes", "%s must be an object of scenes" % name)
                continue
            for scene_id, definition in payload.items():
                if str(scene_id).startswith("_") or not isinstance(definition, dict):
                    continue
                if scene_id in self.scenes:
                    Logger.warning("Scenes", "scene '%s' is defined twice; the first wins" % scene_id)
                    continue
                self.add(scene_id, definition)
        return len(self.scenes)

    # -- playing ---------------------------------------------------------------
    def play(self, player, scene_id: str) -> bool:
        """Begin `scene_id` for `player`. False when there is no such scene; a scene already running for them
        is left to run (asking twice does not tell it twice)."""
        definition = self.scenes.get(str(scene_id))
        if definition is None or player is None:
            Logger.warning("Scenes", "no scene named '%s'" % scene_id)
            return False
        flags = self._flags(player)
        key = RUNNING_PREFIX + str(scene_id)
        if key in flags:
            return True
        flags[key] = 0
        flags.pop(DONE_PREFIX + str(scene_id), None)
        self._arm(player, str(scene_id), 0)
        return True

    def resume(self, player) -> None:
        """Carry on a scene that was part told but is no longer scheduled (the server restarted)."""
        flags = getattr(player, "flags", None)
        if not isinstance(flags, dict):
            return
        for key in [k for k in flags if isinstance(k, str) and k.startswith(RUNNING_PREFIX)]:
            scene_id = key[len(RUNNING_PREFIX):]
            if scene_id not in self.scenes:
                flags.pop(key, None)   # a scene this set no longer has cannot hold the player
                continue
            if not self.world.is_scheduled(self._key(player, scene_id)):
                index = flags.get(key)
                self._arm(player, scene_id, index if isinstance(index, int) and index >= 0 else 0)

    def blocking(self, player) -> bool:
        """Whether a scene that locks its player is running for them."""
        flags = getattr(player, "flags", None)
        if not isinstance(flags, dict):
            return False
        for key in flags:
            if isinstance(key, str) and key.startswith(RUNNING_PREFIX):
                definition = self.scenes.get(key[len(RUNNING_PREFIX):])
                if definition is not None and definition.get("lock", True) is not False:
                    return True
        return False

    # -- internals -------------------------------------------------------------
    @staticmethod
    def _flags(player) -> Dict[str, Any]:
        if not isinstance(getattr(player, "flags", None), dict):
            player.flags = {}
        return player.flags

    @staticmethod
    def _key(player, scene_id: str) -> str:
        return "scene:%s:%s" % (getattr(player, "obj_id", id(player)), scene_id)

    @staticmethod
    def _wait(beat: Dict[str, Any], index: int) -> float:
        after = beat.get("after")
        if isinstance(after, (int, float)) and not isinstance(after, bool) and 0 <= after <= MAX_WAIT:
            return float(after)
        return DEFAULT_FIRST_WAIT if index == 0 else DEFAULT_WAIT

    def _beats(self, scene_id: str) -> List[Dict[str, Any]]:
        beats = self.scenes.get(scene_id, {}).get("beats")
        return [beat for beat in beats if isinstance(beat, dict)] if isinstance(beats, list) else []

    def _arm(self, player, scene_id: str, start: int) -> None:
        beats = self._beats(scene_id)
        elapsed = 0.0
        key = self._key(player, scene_id)
        if start >= len(beats):
            self._finish(player, scene_id)
            return
        for index in range(start, len(beats)):
            elapsed += self._wait(beats[index], index)
            self.world.schedule(elapsed, lambda index=index: self._tell(player, scene_id, index), key=key)

    def _tell(self, player, scene_id: str, index: int) -> None:
        flags = self._flags(player)
        if (RUNNING_PREFIX + scene_id) not in flags:
            return   # the scene was ended (or never begun for this player)
        beats = self._beats(scene_id)
        if index >= len(beats):
            self._finish(player, scene_id)
            return
        beat = beats[index]
        flags[RUNNING_PREFIX + scene_id] = index + 1   # before the effects, so a beat that carries the player away is not told twice
        lines: List[str] = []
        text = str(beat.get("text", "") or "")
        if text:
            lines.append(pacing.paced(text, beat.get("pace")))
        if beat.get("effects"):
            from engine.dialogue.effects import apply_effects

            try:
                report = apply_effects(beat["effects"], {"player": player, "world": self.world})
            except Exception as error:  # noqa: BLE001 - a broken beat must not strand the player in a scene
                Logger.warning("Scenes", "scene '%s' beat %d raised: %s" % (scene_id, index, error))
            else:
                for failure in report.failed:
                    Logger.warning("Scenes", "scene '%s' beat %d: %s" % (scene_id, index, failure))
                message = report.message()
                if message:
                    lines.append(message)
        if lines:
            self.world.notify_player(player, "\n\n".join(lines))
        if index + 1 >= len(beats):
            self._finish(player, scene_id)

    def _finish(self, player, scene_id: str) -> None:
        flags = self._flags(player)
        flags.pop(RUNNING_PREFIX + scene_id, None)
        flags[DONE_PREFIX + scene_id] = True
