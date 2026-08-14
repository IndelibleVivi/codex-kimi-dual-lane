# Implementation plan

## Goal and boundaries

Produce a public-ready, local-first repository that lets a Codex parent choose between a Codex-native Kimi child and the official Kimi Code CLI. Preserve upstream attribution, reuse existing OAuth sessions, avoid credential handling, and keep runtime activation separate from source installation.

Non-goals:

- replacing codex-router or Kimi Code;
- claiming Codex is Kimi's best harness;
- publishing a package, GitHub repository, release, or hosted OAuth service;
- restarting a live Router automatically.

## Implementation slices

1. Document the two-lane architecture, trust boundaries, community relationship, and lessons learned.
2. Extract a standalone loopback adapter that rewrites only the `/responses` model and normalizes Kimi-incompatible local JSON Schema references.
3. Generate inspectable Codex agent definitions and an update-surviving 256K model overlay without replacing unrelated config.
4. Package a concise `kimi-worker` skill and Kimi Code wrapper with bounded artifacts and same-session `kimi vis` observation.
5. Validate the adapter against a fake upstream, validate installation in a temporary Codex home, validate the skill schema, and run a publication audit.

## Safety and rollback

- Installation refuses to overwrite by default; `--force` creates timestamped backups.
- The installer never restarts Codex, codex-router, or LaunchAgents.
- The adapter listens on loopback only, uses a private route capability, allowlists outbound headers, and does not log request bodies or headers.
- A model overlay merge preserves unrelated models and backs up an existing file before replacement.
- Removing installed files or reloading services remains an explicit operator action.

## Acceptance

- Native requests reach a synthetic upstream with the intended Kimi model id.
- The 256K route falls back only on the exact ChatGPT-account unsupported-model error.
- Recursive object-valued `#/...` tool-schema refs are rewritten to `#/$defs/...` without mutating the input.
- A temporary installation contains the expected skill, adapter, agent definitions, and merged overlay with no absolute developer paths.
- The skill validator and bounded public audit pass, or remaining warnings are documented precisely.
