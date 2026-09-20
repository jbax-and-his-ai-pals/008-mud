# Archive

Retired code, kept for reference and for the design intent behind it. Nothing
here is imported by the engine, built by CI, or run by any gate.

Each directory has its own README saying what it was, why it was retired, and
what it would take to bring it back. The code is unmodified apart from the import
lines that would otherwise point at modules that no longer exist — each of those
edits is marked with an `ARCHIVED:` comment so the original shape is one search
away.

| Directory | What it is | Why it is here |
|---|---|---|
| [`ai-conversation/`](ai-conversation/) | An LLM-backed ambient conversation system: a local model, a prompt set, and a threaded generator wired into the world tick | The idea is right and the models are not big enough yet. Kept so the prompt design survives; the wiring was dead in practice anyway |
| `legacy-map-viewer/` | Two pygame node-graph renderers for regions and rooms, the pre-Godot world map editor | Superseded by `mud-world-editor/`. Not in this repository — it lives on the `legacy-map-viewer` tag |

## The rule for this directory

**Archived code does not grow.** A fix, an improvement or a port is a reason to
restore the thing properly, not to edit it here. If something in the archive
starts needing maintenance, that is the signal to either delete it or revive it
into a real track.

The other rule: **`git log` is not an archive.** Code that a track cannot see is
code nobody will remember, which is why the AI prompt set is preserved as a file
rather than as a commit that scrolled off page four.
