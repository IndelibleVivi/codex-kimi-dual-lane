---
name: kimi-worker
description: Delegate bounded coding, frontend, repository-analysis, debugging-hypothesis, or independent-review work to Kimi K3 through either a Codex-native child or the official Kimi Code CLI. Use when the user asks for Kimi/K3, when frontend judgment or implementation benefits from Kimi, or when a genuinely independent second perspective can materially improve architecture, difficult debugging, consequential refactoring, or review confidence.
---

# Kimi Worker

Choose the harness from the task instead of assuming one universal winner. Read [references/harness-choice.md](references/harness-choice.md) when the lane is not obvious or when tools, privacy, session visibility, or concurrent edits affect the choice.

## Choose a lane

- Prefer native Codex collaboration with `router_kimi_oauth_k3_256k` when Codex tools, plugins, MCP, installed skills, collaboration UI, or sandbox ownership matter. Use `router_kimi_oauth_k3` only when the operator deliberately selects the non-256K route for the capabilities and quota of the active Kimi plan; do not infer its context size from the local alias.
- Prefer `scripts/kimi-worker` when Kimi's native tool loop, frontend implementation behavior, durable Kimi session, or human-visible `kimi vis` session matters more.
- Skip delegation for trivial lookups, mechanical edits, or answers already supported by high-confidence local evidence.

Codex is useful but is not assumed to be Kimi's best harness for every task. Treat lane selection as an evidence-driven policy that may change as both products evolve.

## Scope the work

Give Kimi one coherent, bounded work package with:

- the exact outcome and owned paths;
- relevant repository instructions and constraints;
- explicit read-only or edit authority;
- acceptance checks and expected return shape;
- private or unrelated paths excluded.

Do not impose an arbitrary “at most one finding/change” limit. Allow the mutually consistent changes required by the work package, but do not manufacture extra changes to reach a count.

Avoid concurrent overlapping edits. The parent Codex agent owns final judgment, diff review, tests, and any commit or publication decision.

## Run the Kimi Code lane

Create a fresh private artifacts directory and dispatch from the target repository:

```bash
artifacts_dir="$(mktemp -d /tmp/kimi-worker.XXXXXX)"
worker="${CODEX_HOME:-$HOME/.codex}/skills/kimi-worker/scripts/kimi-worker"
"$worker" \
  --cwd /absolute/repo/path \
  --artifacts-dir "$artifacts_dir" \
  -- "<self-contained work order>"
```

The wrapper reuses the official Kimi Code OAuth session and unsets Platform API overrides. It does not copy Codex OAuth or Kimi credentials.

While Kimi works, continue useful non-overlapping parent work. If no independent work remains, use one tool-owned long wait rather than repeated short polling. Never stream the complete progress trace into the parent model context.

When the session id appears, give the user the one-line command stored in `vis-command` if they want to watch. It opens the same durable session and does not create a duplicate request.

On completion, inspect only:

1. `status`;
2. `final.md`;
3. the exact repository diff and relevant tests.

Open `events.log` or `stderr.log` only to diagnose a failure.

## Resume deliberately

- Use `--session ID` when a specific Kimi session owns the work.
- Use `--continue` only when the repository has no competing Kimi session that could be selected accidentally.
- Wait on the original process or session. Never start a duplicate merely because it is quiet.

## Safety

- Never place OAuth tokens, API keys, cookies, private chats, account exports, or unrelated files in prompts, artifacts, logs, or the repository.
- Native Kimi Code does not automatically inherit Codex-only plugins or MCP tools. Pass only compatible skill directories and let the Codex parent perform Codex-only actions.
- Preserve unrelated user changes and inspect the exact diff before accepting Kimi's work.
- Treat a worker's completion claim as advisory until the parent verifies the actual artifact and tests.

## Launcher

```text
kimi-worker [--cwd PATH] [--model MODEL] [--effort low|high|max]
            [--continue | --session ID] [--skills-dir PATH]
            [--add-dir PATH] [--json] [--artifacts-dir PATH] -- PROMPT
```
