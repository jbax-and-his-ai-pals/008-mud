# Fantasy Frontier

Fantasy Frontier is the canonical reference content set for the text-game engine. It is a complete fantasy game package: the manifest selects its rules, presentation, start location, and all authored runtime data.

## Launch

From the repository root, validate the package:

```powershell
.\.conda\python.exe toolkit\content_set_validator.py content_sets\fantasy_frontier
```

Start a local TCP server with this package selected:

```powershell
Push-Location server
..\.conda\python.exe poc_server.py --content-set ..\content_sets\fantasy_frontier
Pop-Location
```

## Package layout

`content_set.manifest.json` is the package entry point. `data/` contains the authored game inputs that load at runtime:

- 14 region files, including town, coast, caves, casino, and the Obsidian Trial.
- 16 item-definition files, including equipment, consumables, quest objects, collectible items, and item sets.
- 5 NPC-template files, 3 quest files, and the Bandit Rebellion campaign.
- 7 spell files, crafting recipes, knowledge/collection content, dialogue, profiles, player defaults, combat data, and world interactions.
- `rules/ruleset.json` and `presentation/default.json` define the current gameplay and presentation intent.
- `opening/arrival_in_town.json` is the first-session brief shown after character creation.

Runtime saves never belong in this package. They are session data owned by the selected server or client profile.
Each new save records the selected content-set ID and version; it can only be restored into that same content set/version.

## Authoring boundary

For all content-set launches, this directory is the source of truth. Edits intended for Fantasy Frontier should be made here.

The package currently uses the engine's existing JSON shapes. Future migration work will make the ruleset, scenarios, and presentation contract richer without reintroducing fantasy-specific assumptions into engine code.
