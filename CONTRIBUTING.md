# Contributing

Focused issues and pull requests are welcome. Keep reports and examples
public-safe: do not include OAuth state, credentials, private prompts, account
details, personal paths, or captured Kimi Code artifacts.

## Source and verification

- Preserve the two-lane product boundary and the loopback-only adapter
  contract.
- Keep `codex-router` and Kimi OAuth/session ownership upstream; do not vendor
  credentials or upstream source.
- Run the relevant Node and Python tests described in [README.md](README.md).
- Explain changed behavior, verification, and any deliberately deferred work.

## Contribution license

By submitting a contribution, you represent that you have the right to submit
it and offer it under the license assigned to the target file by
[LICENSING.md](LICENSING.md):

- functional materials use Sustainable Use License v1.0;
- documentation uses CC BY-NC-SA 4.0; and
- third-party material must retain its original license, notices, and
  attribution.

This is not a copyright assignment. A normal contribution does not authorize
the maintainer to grant commercial rights in a contributor's work. Changes
that cross licensing surfaces should be split or identify each affected
surface explicitly.
