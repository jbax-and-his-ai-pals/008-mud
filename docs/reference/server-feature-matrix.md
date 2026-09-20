# Server Feature Matrix

This matrix is the canonical model for server-level feature control. A server can combine:

- `feature_profile` modes (coarse runtime behavior)
- capability requirements (session role, e.g. GM)
- entitlement gates (product/package/operator access)

## Feature Layers

| Layer | Purpose | Example |
|---|---|---|
| Profile Mode | Global behavior toggle | `combat: disabled` |
| Capability | Session role/authority | `authoring.gm` |
| Entitlement | Product/package gate | `operator.world_effects.manage` |

## Common Patterns

| Server Style | Profile Modes | Capability Policy | Entitlement Policy |
|---|---|---|---|
| Static World | `world_mutation: readonly`, `authoring: disabled` | Optional GM auth | Minimal grants only |
| Social No-Combat | `combat: disabled` | Optional GM auth | No combat/operator combat gates |
| Creator Sandbox | `authoring: all`, `world_mutation: enabled` | GM for destructive ops | Broad creator/operator grants |

## Operator Action Expectations

| Operator Action | Capability Requirement | Entitlement Gate |
|---|---|---|
| `Profiles:Apply Selected` | none | `operator.profile.apply` |
| `World Effects:Use Provider` | `authoring.gm` | `operator.world_effects.manage` |
| `Authoring:*` Lock/Edit | depends on authoring mode | `creator_sdk.authoring` |
| `toggle <category> <value>` | `authoring.gm` | `operator.feature_profile.toggle` |
| `settime/setweather/teleport/genregion` | none | `operator.world.debug` |

## Design Rule

If a command or operator action can alter world/system state, it should be represented in this order:

1. Profile mode allows the system category.
2. Capability check confirms role.
3. Entitlement gate confirms licensed/granted access.
