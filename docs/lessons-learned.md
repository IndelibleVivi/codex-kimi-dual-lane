# Lessons learned

This project came from a real integration that took several wrong turns. The mistakes are part of the reusable result.

## 1. A visible picker entry is not a completed route

Codex Desktop can display a merged external model while native collaboration still rejects the same model id before any request reaches the local Router. Verify catalog, child creation, and provider receipt independently.

## 2. Do not globally replace Codex's provider

Keeping the root Codex session on its normal OpenAI/ChatGPT login preserves native behavior. Route Kimi by model id or per-agent provider config instead of switching the whole installation and risking the primary login.

## 3. Disk config and live registry are different facts

Writing a 256K overlay and passing a catalog doctor does not prove that an already-running Router loaded it. A compatibility adapter can fall back safely, but the real 256K route is proved only by a completed request receipt. A doctor must reject a formal Router process older than the overlay and any 256K receipt attributed to `provider=openai`; otherwise picker visibility can impersonate runtime readiness. Reload only in a maintenance window: restarting a loopback service can sever an in-flight stream.

## 4. Provider tool schemas are part of compatibility

The model may answer simple prompts yet reject Codex's full tool list. One observed failure came from valid object-valued local JSON Schema references outside `#/$defs/`; Kimi rejected the entire tools payload. The adapter rewrites the supported `#/...` subset and leaves already-supported, root, boolean-schema, and unresolved refs unchanged.

## 5. Codex is useful, not universally optimal

The Codex harness is valuable when its plugins, MCP servers, skills, collaboration UI, or review loop matter. Kimi Code is often the more natural harness for Kimi's own tool behavior, frontend implementation rhythm, OAuth session, and human-visible session UI. There is no need to force every task through one shell.

## 6. Delegation should be bounded by coherence, not an arbitrary count

“At most one finding” reduces a second model to a timid ritual. Give it one coherent work package with owned files, constraints, and acceptance evidence; allow the mutually consistent changes needed for that package without padding the change count.

## 7. Watching and supervising are not the same as streaming everything

The human can watch the same Kimi session through `kimi vis`. The parent agent does not need the entire event trace in its context. On success, final response plus exact diff and tests are the high-signal review surface.

### A durable session can still be hidden by Kimi Web

In Kimi Code 0.36, the v2 print runner calls the prompt queue directly. It persists the session, messages, tools, and result but skips the prompt-metadata update used by interactive/Web submission. Kimi Web requests `exclude_empty=true`, so a real delegated session with no `last_prompt` is absent from its history list. The worker instead uses official ACP `session/prompt`, which reaches the metadata update without requiring a Web bearer token; session authority remains Kimi Code, while Codex still receives only bounded artifacts. Explicit extra skill-directory overrides retain a CLI compatibility path because ACP 0.23 cannot express them.

## 8. The collaboration policy must remain revisable

Frontend skill is a useful prior, not a permanent routing law. Harness capabilities, quota economics, model behavior, and project needs change. Record observed strengths and failures, then update the decision rule from evidence.

## 9. A route receipt is not an agent-loop receipt

A native child can reach Kimi successfully and still return an acknowledgement as its final answer before making any required tool call. Accept tool-requiring work only from tool, artifact, diff, or test evidence. One same-child follow-up is enough to distinguish a transient continuation miss; a repeated false finish is a harness failure and should move the coherent work package to the Kimi Code lane.
