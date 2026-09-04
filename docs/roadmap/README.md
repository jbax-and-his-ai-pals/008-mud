# Content Engine Roadmap

The project is building a reusable engine for authored text-first games. A **content set** defines a complete game—its world, rules, structure, scenarios, and presentation. The first canonical content set is a substantial fantasy game; later sets may explore modern, western, space, or other genres.

## Active roadmap

Read and maintain [Content Engine Roadmap](content-engine-roadmap.md). It defines the product charter, content-set boundary, canonical game sequence, delivery milestones, and current priorities.

## Current priority

Make the content-engine boundary real before expanding feature breadth:

1. Establish a reproducible runtime, content validation, and test baseline.
2. Define the versioned content-set manifest and loader.
3. Extract the existing fantasy world as `fantasy_frontier`.
4. Deliver a reliable first-session player loop for Fantasy Frontier.
5. Build a small modern content set to prove that the engine is not fantasy-bound.

Persistent multiplayer, broad modding, storefront work, and additional genres remain valuable, but follow the proven content-set package boundary rather than lead it.

## Historical material

The documents below record prior platform work and remain useful as implementation references. They are not the active phase order or source of priority.

- [Previous phase documents](phases/)
- [Historical next-session log](next-session.md)
- [Platform architecture notes](platform-architecture.md)
- [World-editor track](world-editor-track.md)
- [Content and mod publishing guidance](content-authoring-and-mod-publishing-guidelines.md)
- [Accessibility track](accessibility-track.md)
- [ADR template](adr/0000-template.md)

When prior documents conflict with the active roadmap, the Content Engine Roadmap wins.
