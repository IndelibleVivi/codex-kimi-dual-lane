# Architecture and trust boundaries

## The three planes

The integration separates three things that are easy to conflate:

1. **Catalog plane** — whether a model appears in Codex Desktop's picker.
2. **Child control plane** — whether Codex accepts an agent's configured model when creating a native subagent under the current account harness.
3. **Data plane** — which provider and model actually receive the `/responses` request.

Picker visibility proves only the first plane. A successful native `spawn_agent` plus a Router receipt is needed to prove the second and third.

## Native Codex lane

The generated agent uses a Codex-supported control-model id and a per-agent custom provider base URL pointing at the loopback adapter. The adapter:

1. accepts only two exact capability-token-gated `POST .../responses` paths, with loopback Host, absent Origin, and JSON content-type checks;
2. parses the JSON request and replaces only `model`;
3. normalizes resolvable object-valued `#/...` JSON Schema references into `$defs` for Kimi compatibility, while leaving root and boolean-schema references unchanged;
4. forwards to the already-authenticated codex-router endpoint found in the user's Codex config;
5. retries the 256K request as K3 only when the upstream JSON envelope contains exactly the one known `detail` value for the ChatGPT-account unsupported-model boundary;
6. streams the upstream response back without buffering successful output;
7. forwards only `content-type` and `accept`, and logs no prompts, headers, credentials, or response bodies.

This is a compatibility bridge, not an authentication service. Both listener and upstream are required to remain on loopback. The path capability prevents unrelated local callers from invoking a route they cannot name; it does not make the service safe to expose publicly.

## Kimi Code lane

The worker unsets Platform API override variables so the official Kimi Code OAuth session remains authoritative. Normal runs use Kimi Code's ACP stdio server; an explicit extra `--skills-dir` uses the CLI compatibility transport because ACP 0.23 cannot carry that override. Both launch one durable session and separate its outputs:

For Kimi Code 0.36, ACP `session/prompt` goes through the same prompt-metadata service used by interactive and Web submission. The session therefore remains visible in Kimi Web while the Codex parent reads only bounded artifacts. The installer also places the portable frontend bridge in Kimi's normal user skill root so ACP sessions discover it without a per-run override.

```text
run directory/
├── events.log       complete mixed stream; diagnose only
├── stderr.log       CLI diagnostics
├── final.md         last assistant response
├── status           running, complete, or failed:<code>
├── session-id       durable Kimi session id
├── vis-command      kimi vis <same-session-id>
├── pid              worker process id
└── metadata.json    cwd, model, effort, transport, start time; no prompt
```

The parent model should do other non-overlapping work or one long tool-owned wait. Repeatedly importing progress events into the parent context adds cost without improving supervision.

## Ownership

| Surface | Authority |
|---|---|
| Codex login, skills, plugins, MCP, sandbox | Codex |
| Kimi OAuth, native session, `kimi vis` | Kimi Code |
| external-model routing and route receipts | codex-router |
| adapter route rewrite | this project |
| final diff review, tests, merge decision | parent Codex agent and user |
