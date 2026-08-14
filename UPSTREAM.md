# Provenance and upstream relationship

## Primary dependency

This project integrates with [`duolahypercho/codex-router`](https://github.com/duolahypercho/codex-router), distributed under the MIT License. The first validated development baseline was:

```text
repository: https://github.com/duolahypercho/codex-router.git
version: 0.4.0-beta.3
commit: 4976020befcd530410f740e68b6a11ca0821871d
```

`codex-router` owns the merged model catalog, external-provider routing, Kimi OAuth transport, and its service lifecycle. This repository does not claim authorship of those components and does not vendor the upstream source.

The original contribution here is the dual-lane orchestration, the loopback child compatibility adapter, portable installation/config generation, bounded Kimi Code artifact capture, human-visible same-session workflow, and the documented harness-selection contract.

This repository's MIT license covers its original code and documentation. It does not alter the licenses or ownership of any dependency or referenced project.

## Other community references

- [`wangsiyi7/Codexkimi`](https://github.com/wangsiyi7/Codexkimi), MIT: Codex-led Kimi frontend workers and secure credential routing across macOS and Windows.
- [`boringmarketer/kimi-first`](https://github.com/boringmarketer/kimi-first), MIT: frozen work-order delegation and parent-side adversarial review.
- [`shinpr/sub-agents-skills`](https://github.com/shinpr/sub-agents-skills), MIT: portable cross-CLI subagent definitions and backend selection.
- [`MoonshotAI/kimi-code`](https://github.com/MoonshotAI/kimi-code): the official Kimi Code CLI used by the native lane.

These projects informed comparison and terminology. Their source is not copied into this repository.

## Product names

Codex, OpenAI, Kimi, Moonshot AI, Claude, and GitHub are names or marks of their respective owners. This project is unofficial and independent.
