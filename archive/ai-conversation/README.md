# AI conversation (archived 2026-09-18)

## What it was

An ambient-text generator: a small local language model that took a snapshot of
the player's situation and produced a line of flavour or dialogue from it. Three
prompt targets shipped, and they are the useful artifact here:

| Prompt | What it generated |
|---|---|
| `generate_room_description` | a room description, from the room's authored data |
| `npc_ambient_dialogue` | something an NPC says, from who they are and who is present |
| `ambient_flavor_text` | an unattributed line, from the region and the weather |

`AIManager` ran on the world tick: every `AI_AMBIENT_INTERVAL_SECONDS` it built a
context stamp, spawned a worker thread to generate, and displayed the result if
the world had not moved on in the meantime. That staleness check — discard a
generated line if the player has changed room since it was requested — is a real
piece of design and is worth reading before anything is rebuilt.

## Why it was retired

**The models are not good enough yet, and the wiring was already dead.**

The second half is the part worth recording, and it is more specific than
"dependencies were missing". `LLMInterface._load_model` opens with an
unconditional `return`:

```python
def _load_model(self):
    # loading the model takes several seconds, so disabling for now until we're
    # ready to work more with ai functionality
    return
    ...
```

So the model load was switched off in code, deliberately, and everything above
it carried on as if the feature were live:

- `AI_AMBIENT_ENABLED` defaulted to `True`, so `AIManager` was constructed on
  every `GameManager`;
- it ran on every world tick and spawned a worker thread every five seconds;
- `update2()` returned at its first guard (`if not self.llm_interface or not
  self.llm_interface.pipe`) every single time, because `pipe` is only assigned
  after that `return`.

The system was *on*, doing nothing, in every test run, and no gate could see it
because nothing was broken — there was simply no path from "enabled" to "produces
a line". The one honest signal was `[AIManager] Timer elapsed. Starting new AI
generation thread.` scrolling past in the test log, which reads like progress and
was in fact the whole of the work being done.

Meanwhile the engine grew its own general answer to the same design question —
`use_text` on items, authored NPC dialogue, room descriptions — which is
content-authored, deterministic, and testable. So this is not "a feature we could
not finish". It is a feature whose implementation was switched off and whose
*idea* is still ahead of the hardware:

> The long-term goal is a model small and fast enough to take game context
> objects and generate conversation from whatever the situation is. The local
> models available today do not do the job.

## What would bring it back

1. **A model that fits the budget.** The archived interface wrapped
   `microsoft/Phi-4-mini-instruct` through a `transformers` pipeline. Anything
   restored should start by asking whether a *smaller* model with a tighter
   prompt, or a hosted one, does better — the archived prompt set is the thing
   to test that against.
2. **A general seam to hang it on, not a manager.** The archived shape put an
   `AIManager` on `GameManager` with its own thread and queue. The better shape
   now available is a **content-declared text source**: a field the engine can
   resolve from either an authored string or a generator, so content decides
   per-line whether it is fixed or generated. That keeps the engine's neutrality
   rule — it would know "this text is generated", not "this text is a language
   model".
3. **A gate that can tell generated text from broken text.** Nothing in the
   current gate suite could evaluate a generated line.

## What was removed from the engine

- `server/engine/ai/` — the whole directory.
- Three test files that covered this manager and nothing else:
  `test_ai_manager_full.py`, `test_ai_manager_validation.py` and
  `test_llm_interface.py`. The NPC AI tests (`test_ai.py`,
  `test_advanced_ai.py`, `test_npc_ai_*.py`) are a different thing and stay.
- One test inside `server/tests/singles/test_game_manager_lifecycle.py` —
  `test_ai_manager_message_is_added_to_renderer`, which patched
  `game.ai_manager.update` and asserted the tick displayed the result. A note is
  left in its place, next to a test of the same shape for a producer that still
  exists.
- `AI_AMBIENT_ENABLED`, `AI_AMBIENT_INTERVAL_SECONDS`, `AI_AMBIENT_TEXT_COLOR`
  from `server/engine/config/config_game.py`. All three were read only here.
- `from engine.ai.ai_manager import AIManager` and `self.ai_manager = AIManager(self)`
  from `server/engine/core/game_manager.py`, plus the tick call that asked it for
  a message. The tick now does the rest of its work and nothing else.

The archived test files import `engine.ai.ai_manager`, which no longer exists.
They are kept as a description of the behaviour, not as runnable code; a restore
should start from them and from the design note above. `test_llm_interface.py`'s
docstring is the most useful of the three, because it is where the unconditional
`return` in `_load_model` is written down as a deliberate choice.
