#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import deque
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


def parse_elapsed(value: str) -> int:
    days = 0
    clock = value.strip()
    if "-" in clock:
        day_text, clock = clock.split("-", 1)
        days = int(day_text)
    parts = [int(part) for part in clock.split(":")]
    if len(parts) == 2:
        hours = 0
        minutes, seconds = parts
    elif len(parts) == 3:
        hours, minutes, seconds = parts
    else:
        raise ValueError(f"unsupported process elapsed time: {value!r}")
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def formal_router_started_at() -> float | None:
    if sys.platform != "darwin":
        return None
    launchctl = shutil.which("launchctl")
    ps = shutil.which("ps")
    if not launchctl or not ps:
        return None
    try:
        service = subprocess.run(
            [launchctl, "print", f"gui/{os.getuid()}/io.github.codex-router"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        match = re.search(r"^\s*pid\s*=\s*(\d+)\s*$", service.stdout, re.MULTILINE)
        if service.returncode != 0 or not match:
            return None
        elapsed = subprocess.run(
            [ps, "-p", match.group(1), "-o", "etime="],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        if elapsed.returncode != 0 or not elapsed.stdout.strip():
            return None
        return time.time() - parse_elapsed(elapsed.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def parse_event_time(value: object) -> float | None:
    if not isinstance(value, str):
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def latest_256k_receipt(path: Path) -> dict[str, object] | None:
    if not path.is_file():
        return None
    try:
        with path.open(encoding="utf-8") as handle:
            recent = deque(handle, maxlen=4096)
    except OSError:
        return None
    for line in reversed(recent):
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("model") == "kimi-oauth/k3-256k":
            return event
    return None


def assess_256k_activation(
    codex_home: Path,
    *,
    router_started_at: float | None,
) -> tuple[bool, bool, str]:
    state = codex_home / "codex-router"
    overlay = state / "user-models.json"
    if not overlay.is_file():
        return False, False, "model overlay is not installed"

    overlay_mtime = overlay.stat().st_mtime
    receipt = latest_256k_receipt(state / "usage-events.jsonl")
    if receipt:
        receipt_at = parse_event_time(receipt.get("at"))
        provider = receipt.get("provider")
        status = receipt.get("status")
        if provider == "kimi-oauth" and receipt_at and receipt_at >= overlay_mtime - 1:
            return (
                True,
                True,
                f"current receipt reached provider kimi-oauth with status {status}",
            )

    if router_started_at is not None and router_started_at < overlay_mtime - 1:
        return (
            False,
            True,
            "formal router started before the 256K overlay; regenerate routes and reload it in a maintenance window",
        )

    if receipt:
        receipt_at = parse_event_time(receipt.get("at"))
        provider = receipt.get("provider")
        current_process_receipt = router_started_at is None or (
            receipt_at is not None and receipt_at >= router_started_at - 1
        )
        current_overlay_receipt = receipt_at is None or receipt_at >= overlay_mtime - 1
        if provider != "kimi-oauth" and current_process_receipt and current_overlay_receipt:
            return (
                False,
                True,
                f"latest 256K request fell through to OpenAI instead of kimi-oauth (status {receipt.get('status')})",
            )

    return (
        False,
        False,
        "router files may be current, but no current kimi-oauth 256K receipt proves the live route yet",
    )


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

    if overlay_ok:
        gateway = codex_home / "codex-router" / "litellm.yaml"
        gateway_ok = gateway.is_file() and bool(
            re.search(r'^\s*-\s*model_name:\s*["\']?kimi-oauth-k3-256k["\']?\s*$', gateway.read_text(encoding="utf-8"), re.MULTILINE)
        )
        add(
            "256K generated gateway route",
            gateway_ok,
            "codex-router generated route; rerun its installer in a maintenance window if missing",
        )

        merged = codex_home / "codex-router" / "merged-models.json"
        merged_ok = False
        if merged.is_file():
            try:
                catalog = json.loads(merged.read_text(encoding="utf-8"))
                merged_ok = any(
                    model.get("slug") == "kimi-oauth/k3-256k"
                    for model in catalog.get("models", [])
                )
            except (json.JSONDecodeError, AttributeError):
                pass
        add(
            "256K generated picker catalog",
            merged_ok,
            "codex-router merged catalog entry; rerun its installer in a maintenance window if missing",
        )

        activation_ok, activation_required, activation_detail = assess_256k_activation(
            codex_home,
            router_started_at=formal_router_started_at(),
        )
        add(
            "256K live route",
            activation_ok,
            activation_detail,
            required=activation_required,
        )

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
