# Orbital Salvage

The second reference content set, and the one that exists to prove the engine is
content-neutral rather than content-adjacent.

It is deliberately tiny: a four-room station loop, one person, one hostile
drone, one kinetic weapon, one protective vest, one salvage node that rolls
generated components, one fabrication recipe, and one ability that spends
**charge** rather than mana.

What it does *not* declare is the point. There is no magic capability, no mana
resource, no spell schools, no gems, and no fantasy vocabulary in any file here.
Its ability lives in `data/abilities/` rather than `data/magic/`, its generated
instances carry `component_*` properties rather than `gem_*`, and its pool is
called Charge because its `resources` contract says so. If a player of this set
ever reads the word "mana", something in the engine is still guessing.

```powershell
.\.conda\python.exe server\launch_content_set.py --content-set content_sets\orbital_salvage --dry-run
```

Then the same command without `--dry-run` to start the server.
