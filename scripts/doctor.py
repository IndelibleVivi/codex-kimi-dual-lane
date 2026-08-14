#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Inspect a Codex Kimi Dual Lane installation.")
    result.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
    )
    result.add_argument("--port", type=int, default=4213)
    result.add_argument("--json", action="store_true")
    result.add_argument("--require-running", action="store_true")
    return result


def probe(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as response:
            payload = json.loads(response.read().decode())
            return response.status == 200 and payload.get("ok") is True
    except (OSError, ValueError, urllib.error.URLError):
        return False


def main() -> int:
    args = parser().parse_args()
    codex_home = args.codex_home.expanduser().resolve()
    checks: list[dict[str, str | bool]] = []

    def add(name: str, ok: bool, detail: str, required: bool = True) -> None:
        checks.append({"name": name, "ok": ok, "detail": detail, "required": required})

    config = codex_home / "config.toml"
    provider = False
    if config.is_file():
        text = config.read_text(encoding="utf-8")
        block = re.search(r"\[model_providers\.codex-router\]([\s\S]*?)(?=\n\[|$)", text)
        provider = bool(block and re.search(r"^base_url\s*=", block.group(1), re.MULTILINE))
    add("codex-router config", provider, "provider block with base_url")

    add("Node.js", shutil.which("node") is not None, "node executable on PATH")
    add("Kimi Code CLI", shutil.which("kimi") is not None, "kimi executable on PATH")
    add(
        "adapter source",
        (codex_home / "kimi-dual-lane" / "adapter" / "kimi-child-adapter.mjs").is_file(),
        "installed adapter file",
    )
    add(
        "worker skill",
        (
            (codex_home / "skills" / "kimi-worker" / "SKILL.md").is_file()
            and (codex_home / "skills" / "kimi-worker" / "scripts" / "kimi-worker").is_file()
            and os.access(
                codex_home / "skills" / "kimi-worker" / "scripts" / "kimi-worker",
                os.X_OK,
            )
        ),
        "SKILL.md plus executable launcher",
    )
    token_path = codex_home / "kimi-dual-lane" / "route-token"
    token_ok = False
    if token_path.is_file():
        token_ok = bool(re.fullmatch(r"[A-Za-z0-9_-]{32,}", token_path.read_text().strip()))
    add("route capability", token_ok, "private installation route token")
    for slug in ("kimi-oauth-k3-256k", "kimi-oauth-k3"):
        agent_path = codex_home / "agents" / f"router-model-{slug}.toml"
        agent_ok = agent_path.is_file() and token_ok
        if agent_ok:
            agent_ok = f"/_kimi-child/{token_path.read_text().strip()}/" in agent_path.read_text(
                encoding="utf-8"
            )
        add(
            f"agent {slug}",
            agent_ok,
            "native agent definition bound to route capability",
        )

    overlay_path = codex_home / "codex-router" / "user-models.json"
    overlay_ok = False
    if overlay_path.is_file():
        try:
            overlay = json.loads(overlay_path.read_text(encoding="utf-8"))
            overlay_ok = any(
                model.get("slug") == "kimi-oauth/k3-256k"
                for model in overlay.get("models", [])
            )
        except (json.JSONDecodeError, AttributeError):
            pass
    add("256K model overlay", overlay_ok, "update-surviving user model entry", required=False)

    running = probe(f"http://127.0.0.1:{args.port}/health")
    add("adapter health", running, "loopback /health", required=args.require_running)

    if args.json:
        print(json.dumps({"checks": checks}, indent=2))
    else:
        for check in checks:
            if check["ok"]:
                state = "OK"
            elif check["required"]:
                state = "FAIL"
            else:
                state = "WARN"
            print(f"{state:4} {check['name']}: {check['detail']}")

    return 1 if any(not check["ok"] and check["required"] for check in checks) else 0


if __name__ == "__main__":
    raise SystemExit(main())
