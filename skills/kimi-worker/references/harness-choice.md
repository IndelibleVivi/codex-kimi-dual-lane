# Harness choice

## Decision table

| Requirement | Codex-native child | Kimi Code CLI |
|---|---:|---:|
| Codex collaboration UI | Best fit | Separate session |
| Codex plugins, MCP, Browser, or installed skills | Best fit | Parent must mediate Codex-only tools |
| Kimi-native tool behavior | Adapted through Codex | Best fit |
| Durable Kimi session, Kimi Web history, and `kimi vis` | No | Best fit |
| Bounded final output without parent trace growth | Yes | Yes with `--artifacts-dir` |
| Human watches the exact worker session | Codex collaboration surface | `kimi vis <session-id>` |
| Router/control-plane compatibility risk | Higher | Lower |
| Tool-loop completion evidence | Must be verified from tool calls or artifacts | Native harness; verify artifacts normally |

## Selection rules

Choose the native Codex child when the worker must use Codex-owned capabilities or when one collaboration surface materially improves coordination. A native child receives the current Codex environment, but do not assume every provider will handle every tool schema equally; keep the task bounded and verify the provider receipt.

A provider receipt does not prove that the native child continued through its tool loop. If a tool-requiring task ends with only an acknowledgement or statement of intent, require actual tool/artifact evidence. One same-child follow-up may confirm the failure; a repeated false finish moves the work package to the Kimi Code lane instead of launching more native retries.

Choose Kimi Code when Kimi's own harness is part of the advantage: frontend implementation rhythm, native tool loop, OAuth session, resumability, ACP/MCP support configured in Kimi, or human-visible session inspection.

Use either lane for an independent opinion when no edits are needed. Prefer the lane that requires less context duplication and fewer unavailable tools.

## Parent behavior

The parent should:

1. define the contract;
2. dispatch one coherent package;
3. continue non-overlapping work or sleep once;
4. inspect the worker's final response and exact diff;
5. run or check the relevant verification;
6. accept, revise, or reject the contribution explicitly.

Do not use Kimi as a ritual reviewer. Do not keep the parent awake by importing unchanged progress. Do not equate a different model with an automatically correct answer.
