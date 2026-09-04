# Documentation Information Architecture (Draft)

## Objective

Give each audience a fast path from "new" to "effective" without digging through source code.

## Top-Level Structure

1. Getting Started
- Product overview
- Install/run quickstarts
- "First server in 30 minutes"

2. Player Docs
- Client setup and controls
- Accessibility and mobile usage
- Common troubleshooting

3. Operator Docs
- Server master config guide
- Profiles, toggles, and entitlement policy
- Security and operational runbooks

4. GM/Moderator Docs
- GM auth lifecycle
- Operator actions and policy interpretation
- Moderation/safety controls

5. Creator Docs
- Worldbuilding paths:
  - editor path (`mud-world-editor`)
  - live authoring path (`@dig` / `@edit`)
- Content validation and export

6. Developer/Integrator Docs
- Protocol/event reference
- Data schemas and compatibility contracts
- Mod/plugin extension APIs

7. Commercialization Docs
- Steam packaging/release tracks
- Support and incident workflows
- Launch checklist and readiness gates

## Initial Priority Order

1. Operator docs (master-config-first) and setup wizard docs.
2. Creator docs for editor/export/validation flow.
3. Protocol + schema references.
4. Player-facing docs and guided tutorials.

## Ownership Proposal

1. Runtime team:
- operator, protocol, schema docs.

2. Client/tooling team:
- player, accessibility, editor, wizard docs.

3. Release/ops:
- packaging, support, launch runbooks.
