---
name: codex-frontend-standards
description: Reuse compatible installed Codex React, Next.js, and shadcn engineering standards from native Kimi Code.
---

# Codex frontend standards

Treat the installed Codex skill files as the canonical, automatically updated rule sources. Resolve the Codex home as `$CODEX_HOME` when set, otherwise `~/.codex`.

For React or Next.js work, locate the newest matching copy under:

`<codex-home>/plugins/cache/openai-curated-remote/build-web-apps/*/skills/react-best-practices/`

Read its `SKILL.md` completely and resolve relative references from that directory.

For a project with `components.json`, shadcn/ui, or a shadcn request, also locate the newest matching `shadcn-best-practices/` directory beside it, read `SKILL.md` completely, and resolve its relative references.

Apply only rules relevant to the current repository and requested change. Preserve the repository's existing framework, package manager, design system, and user changes.

This bridge does not provide Codex-only tools. If a canonical skill requires Codex ImageGen, Browser, MCP, plugin, or app tools that are unavailable in Kimi Code, do not fabricate them. Continue with Kimi-native capabilities when they satisfy the same contract; otherwise report the missing capability to the orchestrating Codex agent.

Before completion, inspect the exact diff and run the narrowest relevant lint, typecheck, test, build, or rendered-UI check supported by the repository.
