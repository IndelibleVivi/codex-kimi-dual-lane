# Codex Kimi Dual Lane Agent Instructions

This repository provides two experimental local-first orchestration lanes for
using Kimi K3 from Codex. It modifies local Codex/Kimi/codex-router integration
files and may reload a loopback routing control plane. Preserve credential
custody, inspectable installation, route isolation, bounded worker artifacts,
and Codex-owned final acceptance.

Read `README.md`, `README.zh-CN.md`, `SECURITY.md`, `UPSTREAM.md`,
`docs/architecture.md`, and `docs/lessons-learned.md` before changing behavior.
Global Faye/Cove collaboration style and private continuity live outside this
repository.

## Two-Lane Contract

### Codex-native lane

- A Kimi worker runs inside Codex collaboration.
- Codex owns orchestration, parent instructions, tools, installed Skills/plugins,
  final review, and acceptance.
- The loopback child adapter rewrites only the exact supported outgoing model
  path under the installation-specific capability gate.
- A route receipt proves routing, not a completed agent loop. Tool-requiring work
  needs the expected tool call, artifact, diff, or test evidence.
- A final response that only acknowledges starting is failed work. Permit one
  bounded same-child confirmation, then move the package to the Kimi-native lane
  instead of looping retries.

### Kimi-native lane

- Dispatch through the official Kimi Code CLI/ACP using the user's existing Kimi
  OAuth session.
- Preserve a real durable Kimi session and normal Web-history metadata.
- `kimi vis` attaches to the same session. It must not create a second request.
- Parent consumption is bounded to `status`, `final.md`, `session-id`,
  `vis-command`, and the exact repository diff. Keep the full event stream for
  local failure diagnosis only.

The harness choice is task-specific. Do not freeze one lane as universally
superior or delegate tiny obvious edits.

## Credential Custody

- Codex keeps its normal OpenAI/ChatGPT login.
- Kimi Code keeps its official OAuth session.
- codex-router keeps its configured Kimi OAuth provider.
- Do not extract, copy, inject, log, serialize, or commit OAuth tokens or API
  keys.
- The wrapper/adapter must not receive more credential material than the owning
  client already uses through its normal boundary.
- Never place credentials in agent definitions, Skills, prompts, fixtures,
  config examples, artifacts, route receipts, or debug logs.
- Request bodies and model output are sensitive. Do not persist them beyond the
  explicitly bounded local worker artifacts/logs.

## Adapter And Routing Boundary

- The adapter exists for the exact native-child compatibility gap documented in
  the architecture. Do not turn it into a generic proxy, model router, or public
  service.
- Bind only to loopback and require the installation-specific capability token
  for the exact allowed model paths.
- Preserve exact-envelope fallback from `kimi-oauth/k3-256k` to
  `kimi-oauth/k3` only under the reviewed compatibility rule.
- Reject unexpected paths, methods, model IDs, missing/invalid capability,
  malformed payloads, and unsupported streaming behavior.
- Do not log request bodies, Authorization headers, credentials, prompts, or raw
  response content.
- A receipt must prove the selected provider/model route without leaking private
  payloads.
- A 256K overlay present on disk is `PENDING` until the generated gateway route,
  picker catalog, formal router process age, and a current Kimi route receipt
  prove it live.
- If a request falls through to OpenAI, fail the Kimi-route check. Do not label it
  a Kimi success because a model returned text.

## Installer Contract

- `scripts/install.py --dry-run` must show the complete intended local change.
- Apply preflights every target before mutation.
- Preserve user-owned config and unrelated TOML tables.
- Use private modes for generated route capability/config files.
- Roll back all changes owned by the failed apply step when installation cannot
  complete coherently.
- The installer does not restart Codex or codex-router. Keep activation explicit.
- `--skill-only` must not touch router or agent definitions.
- Do not overwrite a user-modified target without the current force/ownership
  contract and a restorable backup/receipt.
- Local installed files, LaunchAgent plist, generated overlay, live router, and
  Codex metadata are separate states.

## Router Maintenance Window

- Router lifecycle commands are an independent control plane.
- Never reload, disable, replace, or reinstall the router from the task whose
  active response still uses that route.
- Stop/finish every active routed task, then use a separate Terminal/control
  session and the router's supported commands.
- Existing Codex tasks may retain an old endpoint after route change; fully quit
  and reopen Codex when the documented flow requires it.
- `disable` isolates the managed route; it does not guarantee the native OpenAI
  path is reachable through the machine's network.
- Preserve a private backup of `~/.codex/config.toml` around router versions with
  known user-table preservation risk. Do not commit the backup.
- Treat a restart that temporarily clears HTTP/2 session poisoning as diagnostic
  evidence unless the underlying version contains the reviewed fix.

## Kimi Worker Artifacts

- Use a caller-provided or secure temporary artifacts directory.
- Keep final output bounded and deterministic enough for the parent to inspect.
- `events.log` may contain sensitive work context; it remains local and is read
  only for failure diagnosis.
- Do not stage worker artifacts, session metadata, OAuth state, or private diffs.
- Preserve timeout/cancel/exit status and do not report completion when the
  worker only opened a session or emitted an acknowledgement.
- Resume/attach must reuse the session ID. Do not duplicate a request while
  diagnosing visibility.

## Skill And Agent Definitions

- Keep the `kimi-worker` Skill portable and thin. Put detailed mechanics in its
  scripts/references.
- Preserve the Kimi user-skill bridge to the currently installed Codex
  React/Next.js and shadcn standards without copying secrets or machine-specific
  paths into the repository.
- Agent roles must make Codex the acceptance/review owner and state the evidence
  expected from a Kimi worker.
- Do not imply that a provider route grants Codex plugins/MCP/tools inside the
  Kimi-native lane.
- Validate generated Skill frontmatter and agent/config syntax before install.

## Tests

Run:

```bash
node --test tests/*.test.mjs
python3 -m unittest discover -s tests -p 'test_*.py'
uv run --with pyyaml python \
  ~/.codex/skills/.system/skill-creator/scripts/quick_validate.py \
  skills/kimi-worker
```

- The third command is an optional contributor check when the Codex system
  `skill-creator` exists; it does not create a runtime PyYAML dependency.
- Use synthetic adapters, fake router catalogs/process state, temporary Codex
  roots, and fake Kimi sessions.
- Never aim tests at live OAuth, real `~/.codex`, the active codex-router, or a
  user's Kimi history.
- Real route activation, Desktop picker reload, LaunchAgent, OAuth, `kimi vis`,
  and live model calls are explicit manual tests with account/runtime impact.
- Report route, worker-loop, artifact, diff, and test evidence separately.

## Documentation Closure

- Keep `README.md` and `README.zh-CN.md` as semantic peers.
- Update `SECURITY.md` for credential, adapter, route, artifact, or installation
  boundary changes.
- Update `UPSTREAM.md` when dependency/provenance/patch relationships change.
- Update architecture/lessons docs when the reason for a lane or compatibility
  path changes.
- Update this file when authority, installer, router window, testing, or
  credential behavior changes.
- Keep source-only/unofficial/community wording accurate.

Private continuity lives outside Git in the external private-continuity root
governed by the user-level working contract.

## Git And External Actions

- Inspect `git status --short`, stage explicit paths, review the staged diff, and
  run `git diff --cached --check`.
- Do not commit OAuth data, config backups, capability tokens, route receipts
  containing private data, events logs, worker artifacts, installed files, or
  continuity notes.
- Source changes do not authorize local installation, LaunchAgent changes,
  router install/reload, Codex restart, Kimi login, or model calls.
- Report source commit/push, local installation, route activation, and live lane
  behavior as distinct facts.
