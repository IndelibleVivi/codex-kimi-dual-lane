# Security

## Credential boundary

This project must never persist or log OAuth tokens, API keys, cookies, account exports, or request bodies. The adapter necessarily receives delegated request payloads in memory, normalizes selected tool schemas, and forwards them through the configured codex-router/Kimi data plane.

- Codex authentication remains owned by Codex.
- Kimi authentication remains owned by the official Kimi Code CLI and codex-router integration.
- The adapter forwards only allowlisted protocol headers (`content-type` and `accept`), never inbound authorization, cookie, proxy-authorization, API-key, extension, length, or transfer headers.
- Config examples contain no credentials or machine-specific route tokens.

Do not paste credentials into issues, screenshots, diagnostic bundles, prompts, or shell history. Revoke any credential that has been published.

## Listener boundary

The child adapter binds only to `127.0.0.1`, validates Host/Origin/content type, and requires an installation-specific capability token in the exact request path. The token is stored in mode-0600 installed files and is not an OAuth credential. Do not expose the adapter through a public interface, tunnel, port forward, or reverse proxy. It is not an authentication gateway.

Kimi Code artifacts may retain a complete event stream and stderr locally inside the operator-selected artifacts directory. Treat that directory as private working state and do not commit or publish it.

## Reporting

Before opening a public security report, remove private prompts, filesystem paths, route secrets, account identifiers, and raw headers. Describe the minimal synthetic reproduction instead.
