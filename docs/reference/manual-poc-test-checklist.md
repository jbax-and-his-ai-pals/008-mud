# Manual POC Test Checklist (Server + Client)

Use this checklist for personal end-to-end testing against the latest refreshed fixture.

## A. Preflight

- [ ] Run content checks:
  - `powershell -ExecutionPolicy Bypass -File run_content_checks.ps1`
- [ ] Confirm fixture selection:
  - `python server/launch_from_latest_fixture.py --transport tcp --dry-run`
  - Verify the selected content-set identity in output JSON.

## B. TCP Session

- [ ] Launch TCP server:
  - `python server/launch_from_latest_fixture.py --transport tcp`
- [ ] Connect client and confirm initial events:
  - `hello`
  - `auth_state`
  - `lock_state`
- [ ] Run core commands:
  - `look`
  - movement (`n/s/e/w`)
  - `inventory`
  - `status`
  - `help`
- [ ] Confirm no command parser or envelope errors in normal play.

## C. WS Session

- [ ] Launch WS server:
  - `python server/launch_from_latest_fixture.py --transport ws`
- [ ] Connect client and verify command roundtrip behavior.
- [ ] If available, test reconnect/resume flow.

## D. Policy + Auth

- [ ] Run policy/operator probes:
  - `server policy`
  - `profile list`
  - `effects status`
- [ ] Validate GM auth path:
  - `gm status`
  - `gm auth <token>` (if configured)
  - `gm deauth`
- [ ] Verify GM-gated actions deny before auth and allow after auth where expected.

## E. Content/World Sanity

- [ ] Visit core town/vendor/NPC areas.
- [ ] Open trade with key vendors where available.
- [ ] Confirm no fatal template-reference failures; warnings should be non-fatal.

## F. Finite Adventure Scenario

- [ ] Switch server/profile to a `finite_adventure` world-mode target if this session is intended to exercise the story-run path.
- [ ] Connect the Godot client shell and create a character if prompted.
- [ ] Confirm the client loads adventure campaign choices:
  - use the `List` button in the adventure row if they do not appear automatically,
  - verify the picker shows at least one campaign and marks the default where applicable.
- [ ] Start a finite-adventure run from the client:
  - use the selected catalog entry, or
  - type a specific campaign id in the campaign field.
- [ ] Verify run-state feedback updates in both places:
  - adventure panel state line,
  - client log lifecycle cues.
- [ ] Verify the adventure panel also shows:
  - selected campaign detail from the catalog,
  - a current objective block once the run quest payload arrives.
- [ ] Verify objective/journal sync stays immediate when using:
  - `Start`
  - `Restore`
  - `Abandon`
  - `Reset`
  - `Replay`
- [ ] During the run, exercise:
  - `Checkpoint`
  - `Restore`
  - `Status`
- [ ] End the run using either gameplay completion or `Abandon`.
- [ ] Request summary exports from the client:
  - `Summary TXT`
  - `Summary MD`
  - `Summary JSON`
- [ ] Verify the report preview updates and remains readable for markdown/json payloads.
- [ ] Exercise `Reset` and `Replay` after the run ends and confirm the run can be started cleanly again.

## G. Abuse/Guardrails

- [ ] Send burst commands quickly and verify graceful rate-limit errors.
- [ ] If client supports it, send oversized input and verify graceful rejection.
- [ ] If possible, test protocol version mismatch handling and degraded-continue behavior.

## H. Post-Run

- [ ] Re-run content checks:
  - `powershell -ExecutionPolicy Bypass -File run_content_checks.ps1`
- [ ] Record findings:
  - blocking bugs
  - warnings seen
  - UX rough edges
  - protocol or state-sync anomalies
