# ADR 0002: GMCP Package Contract

- Status: Accepted
- Date: 2026-05-01
- Owners: Server runtime team
- Related Phase: Phase 1 – Runtime Foundation

---

## Context

The platform supports two client paths:

| Path | Transport | Encoding |
|------|-----------|----------|
| Rich client (Godot) | WebSocket / TCP | JSON or MessagePack |
| Legacy client (Telnet, Mudlet, etc.) | Raw TCP | ANSI text + GMCP side-channel |

GMCP (Generic MUD Communication Protocol) is a Telnet sub-negotiation extension
(option byte `0xC9` / `201`) that lets a server attach structured JSON metadata
alongside plain-text output.  Legacy clients that support GMCP can consume
rich structured data without breaking plain-text clients that ignore it.

This ADR pins the exact package names, payload shapes, and negotiation sequence
so that the server implementation and any conforming client implementation have
a single source of truth.

---

## Decision

### 1. Negotiation Sequence

```
Server → Client:   IAC WILL GMCP          (server announces GMCP support)
Client → Server:   IAC DO   GMCP          (client opts in)
Server → Client:   Core.Supports.Set [...]  (server's package advertisement)
Client → Server:   Core.Supports.Set [...]  (client's package declaration, optional)
```

If the client sends `IAC DONT GMCP`, the server stops sending GMCP subneg
frames and falls back to plain-text-only output for that session.

Plain-text alternative: clients that do not implement IAC parsing can type
`GMCP ON` / `GMCP OFF` to toggle a simulated text-mode side-channel.

---

### 2. Server → Client Packages

All server-originated events are mapped to a GMCP package.  Payload is always
a JSON value (object, string, or null) transmitted inside a
`IAC SB GMCP <package> <payload> IAC SE` subnegotiation.

#### Core lifecycle

| Package | Trigger event | Payload shape |
|---------|--------------|---------------|
| `Core.Hello` | Session connected | `{"message": "connected", "session_id": str}` |
| `Core.Goodbye` | Session disconnected | `"disconnected"` |
| `Core.Error` | Server-side error | `str` (human-readable message) |
| `Core.Command` | Command echo (server echoes what it received) | `str` (command text) |

#### Text output

| Package | Trigger event | Payload shape |
|---------|--------------|---------------|
| `Comm.Text` | Any textual game output | `str` **or** `{"text": str, "fx": {"blight": float, ...}}` |

`fx` is optional.  Clients that do not support atmospheric effects should render
the `text` field and ignore `fx`.

#### SVG / authored assets

| Package | Trigger event | Payload shape |
|---------|--------------|---------------|
| `Asset.SVG` | Asset created or updated | `{asset_type, asset_id, revision, checksum_sha256, byte_length, svg, alt_text}` |
| `Asset.Update.Accepted` | Asset update accepted | `{"asset_id": str, "revision": int}` |
| `Asset.Update.Rejected` | Asset update rejected | `{"asset_id": str, "reason": str, ...}` |

`Asset.SVG` payload fields:

| Field | Type | Description |
|-------|------|-------------|
| `asset_type` | str | Always `"svg_1bit"` for v1 assets |
| `asset_id` | str | Stable identifier for this asset |
| `revision` | int | Monotonically increasing; starts at 1 |
| `checksum_sha256` | str | Hex SHA-256 of the UTF-8 SVG string |
| `byte_length` | int | Byte length of the UTF-8 SVG string |
| `svg` | str | Full SVG markup (sanitized; max 16 KiB) |
| `alt_text` | str | Accessibility description |

#### Asset OCC lock protocol

Optimistic concurrency control: a session acquires a lock before editing an
asset, preventing overwrite collisions.  Locks are ephemeral (not persisted
across server restarts) and expire automatically after the lease period.

| Package | Trigger event | Payload shape |
|---------|--------------|---------------|
| `Asset.Lock.State` | Sent on session connect | `{"locks_ephemeral": bool, "active_locks": [{asset_id, owner_session_id, expires_at}]}` |
| `Asset.Lock.StateDelta` | Any lock state change | `{"asset_id": str, "owner_session_id": str\|null, "expires_at": float, "state": "acquired"\|"released"\|"renewed"}` |
| `Asset.Lock.Acquired` | Lock granted to this session | `{"asset_id": str, "expires_at": float}` |
| `Asset.Lock.Released` | Lock released | `{"asset_id": str, "released": bool}` |
| `Asset.Lock.Denied` | Lock request denied | `{"asset_id": str, "reason": str, "owner_session_id": str}` |
| `Asset.Lock.Renewed` | Lock lease extended | `{"asset_id": str, "expires_at": float}` |

`Asset.Lock.StateDelta` is **always broadcast to all connected sessions** (not
just the session that triggered the change) so every client can maintain an
accurate lock state view.

---

### 3. Client → Server Packages

These are sent by the client inside `IAC SB GMCP` subneg frames.

| Package | Purpose | Expected payload |
|---------|---------|-----------------|
| `Core.Supports.Get` | Request server's package list | *(no payload)* |
| `Core.Supports.Set` | Declare client's supported packages | `["PackageName version", ...]` e.g. `["Core 1", "Comm.Text 1"]` |

All game commands are sent as **plain text lines** (not GMCP).  GMCP is a
metadata side-channel only.

---

### 4. Package Version Advertisement

`Core.Supports.Set` uses the format `"PackageName N"` where `N` is an integer
version.  Current server advertisement (`default_server_supports()`):

```
Core 1
Core.Hello 1
Core.Supports.Set 1
Core.Supports.Get 1
Core.Command 1
Core.Error 1
Core.Goodbye 1
Comm.Text 1
Asset.SVG 1
Asset.Update.Accepted 1
Asset.Update.Rejected 1
Asset.Lock.State 1
Asset.Lock.StateDelta 1
Asset.Lock.Acquired 1
Asset.Lock.Released 1
Asset.Lock.Denied 1
Asset.Lock.Renewed 1
```

A client that does not declare support for a package may still receive it
(compatibility default before declaration). After `Core.Supports.Set`, the
server filters GMCP emission per session:
- Exact package match is allowed (e.g. `Comm.Text`).
- Namespace wildcard via top-level package name is allowed (e.g. `Core` allows
  `Core.*`).
- Undeclared packages are suppressed for that session.

---

### 5. Catch-all Behaviour

Events with no explicit mapping in `_EVENT_TO_GMCP_PACKAGE` fall back to
`Core.Event` with payload `{"type": event_type, "payload": ...}`.  The
presence of a `Core.Event` frame in a session is a signal that
`_EVENT_TO_GMCP_PACKAGE` needs a new entry; it is not an intended production
package.

---

### 6. Relationship to the Rich-Client Protocol

GMCP is the **legacy path only**.  The rich client (Godot over WebSocket) does
not use GMCP; it consumes the same underlying event types in JSON or
MessagePack envelopes as defined in `engine/server/protocol.py`.  The event
type names (`hello`, `text`, `asset`, `lock_state`, etc.) are the canonical
identifiers; GMCP package names are a translation layer on top of them.

---

## Consequences

- **Positive:** Legacy MUD clients (Mudlet, TinTin++, BlowTorch) gain access
  to structured asset and lock data without requiring a protocol upgrade.
- **Positive:** The package table in `legacy_protocol.py` is the single source
  of truth; this doc derives from it.
- **Negative:** Every new server event type requires a corresponding entry in
  `_EVENT_TO_GMCP_PACKAGE`.  The catch-all `Core.Event` makes this easy to
  miss; consider adding a CI lint check.
- **Risk:** Package name collisions with standard MUD GMCP conventions (e.g.,
  `Comm.Channel.Text` used by IRE games).  Our names diverge intentionally
  since we are not targeting IRE-client compatibility.

---

## Alternatives Considered

1. **Use IRE-standard package names** (`Char.Status`, `Room.Info`, etc.).
   Rejected: IRE packages carry IRE payload shapes; we would need shim logic
   and the client ecosystem we target (Godot) doesn't benefit from
   IRE-compatibility.

2. **GMCP for rich client as well.**  Rejected: GMCP is line-delimited and
   adds Telnet framing overhead on top of WebSocket which already frames
   messages.  Binary codecs (MessagePack) are incompatible with GMCP's
   UTF-8 text payload requirement.

3. **No GMCP at all; rich-only protocol.**  Rejected: a meaningful portion of
   the MUD player base uses Mudlet and similar clients.  GMCP support is a
   low-cost way to keep that audience reachable.

---

## Rollout Plan

1. `engine/server/legacy_protocol.py` – `_EVENT_TO_GMCP_PACKAGE` dict and
   updated `default_server_supports()` — **done**.
2. Add CI lint step that asserts `Core.Event` never appears in a production
   event trace (i.e., all event types have an explicit mapping). â€” **done**
   via `tests/singles/test_gmcp_package_coverage.py`.
3. Enforce per-client package filtering from `Core.Supports.Set`. â€” **done**
   in `poc_legacy_server.py` with coverage in
   `tests/singles/test_poc_legacy_server.py`.
4. Write Mudlet script examples in `docs/mudlet/` demonstrating each package.

---

## Validation

- Unit test: `test_server_protocol.py` — envelope field validation.
- Integration test: `test_poc_legacy_server.py` — IAC negotiation, GMCP
  subneg framing, `Core.Supports.Set` round-trip.
- New: add `test_gmcp_package_coverage.py` asserting that every known event
  type from `protocol.py` has a non-`Core.Event` entry in
  `_EVENT_TO_GMCP_PACKAGE`.
