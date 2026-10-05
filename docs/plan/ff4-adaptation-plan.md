# The ff4 adaptation: story order, and what each stretch needs

`content_sets/ff4_slice` is being built out in the order the original story plays, with small regions (a proof of concept to be broadened
later: larger areas to explore, treasure, side content such as the sylph cave and the land of summoned monsters). Everything is renamed: the
story uses its own names. Party changes (people leaving and joining) are scenes for now, not a roster feature. The engine holds every
system; the set is data only (`docs/design/adaptation_slices.md`).

## Where the story is

Done in content, in play order: the raid on Ilmara and the crystal, the flight and the king, the courier run and the Fog Drake, the burned
village and the Colossus, the guards at the inn, Ryn joins, Dunhallow and Rosalind's fever, Belaric and the camp, the Brineway and the Brinecoil,
Ashmere under siege and Mirelle's death, Lucan joins as a bard, the royal skimmer across the sand sea, the Sandmaw and the pearl.

## What the engine now has for the rest

| Story beat (original order) | What it needs | Engine support |
|---|---|---|
| Rosalind cured and joins as healer | a companion that heals and revives the party | `companions.falls_when_defeated`, `revive` (spell effect, consumable, inn), `perform_companion_support` (heal, revive, cure stone) |
| Fabul: the crystal stolen, a duel the hero loses | a fight the story ends | trigger event `health_below`, effect `end_fight`, `set_faction` for the brainwashed friend |
| The sea voyage, the Leviathan | a ship | `data/vehicles`, `embark`/`disembark`, exit requirement `vehicle`, `place_vehicle`/`board_vehicle`, `aboard` |
| Mysidia, the twins, the Paladin trial on the mountain | the trial's shadow; the conversion; the twins | `mirrors_player`; conversion = `raise` + `teach_spell` + `forget_spell` + title; `requires_ally` (twin spell); `petrify` and a cleanse |
| Belaric's Meteor | a spell that costs everything | `sacrifice` |
| Eblan, the ninja prince | throwing, stealing, a jump | `throwing` (carried `target_damage` items), `steal` effect and `steal_items`, `windup` (Jump) |
| The four lieutenants and their gimmicks | absorb an element, shed a cloak at half, a share of health | resistances to 200 (absorb), phase `resistances`, `percent_damage`, `percent_immune` |
| The airship, Baron, the Underworld | an airship; a second world | vehicles with `lands_in_biomes`; regions and hazards are content |
| The moon and the last fight | a multi-form boss | phases, `counter`, `health_below` |
| Every fight, with a full party | a readable fight | `combat.pacing`, `combat full|normal|brief` |

## What is still not built

* The ship, the airship and the Lunar Whale as content (the system is there; each needs its map layer authored).
* A counter-attack for a companion (the monk): a phase `counter` exists for creatures only.
* A dual-wield or off-hand blow, smoke (a fight-escape ability) and per-item "only this character may use it" for companion gear.
* A timed "doom" status (a countdown that kills).
* Party swapping beyond the story scenes, and a party size above the ruleset's `companions.max` (ff4_slice sets 3; five fighters need 4).

Each is small once the story reaches it; none blocks the order above.
