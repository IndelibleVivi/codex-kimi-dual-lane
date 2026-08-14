#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import plistlib
import re
import secrets
import shutil
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ADAPTER_SOURCE = ROOT / "adapter" / "kimi-child-adapter.mjs"
SKILL_SOURCE = ROOT / "skills" / "kimi-worker"
OVERLAY_SOURCE = ROOT / "examples" / "user-models.kimi.json"
AGENT_INSTRUCTIONS = """Complete the bounded task assigned by the parent agent.
Respect repository instructions, preserve unrelated work, and keep changes coherent.
Run relevant verification and return a concise summary of changes, checks, and remaining risks."""


@dataclass(frozen=True)
class FileOperation:
    target: Path
    content: bytes
    mode: int
    allow_structured_update: bool = False


@dataclass(frozen=True)
class TreeOperation:
    source: Path
    target: Path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description="Install Codex Kimi Dual Lane files without restarting services."
    )
    result.add_argument(
        "--codex-home",
        type=Path,
        default=Path(os.environ.get("CODEX_HOME", Path.home() / ".codex")),
    )
    result.add_argument("--port", type=int, default=4213)
    result.add_argument("--control-model-256k", default="gpt-5.6-terra")
    result.add_argument("--control-model-k3", default="gpt-5.6-sol")
    result.add_argument(
        "--skip-model-overlay",
        action="store_true",
        help="Do not merge the K3 256K entry into codex-router/user-models.json.",
    )
    result.add_argument(
        "--launch-agent",
        action="store_true",
        help="Write a macOS LaunchAgent plist, but do not bootstrap or restart it.",
    )
    result.add_argument("--node", help="Absolute Node.js path for the LaunchAgent.")
    result.add_argument("--force", action="store_true", help="Back up and replace changed targets.")
    result.add_argument("--dry-run", action="store_true")
    return result


def validate(args: argparse.Namespace) -> None:
    if args.port < 1 or args.port > 65535:
        raise ValueError("--port must be between 1 and 65535")
    config = args.codex_home.expanduser() / "config.toml"
    if not config.is_file():
        raise ValueError(f"Codex config not found: {config}")
    text = config.read_text(encoding="utf-8")
    block = re.search(r"\[model_providers\.codex-router\]([\s\S]*?)(?=\n\[|$)", text)
    if not block or not re.search(r"^base_url\s*=", block.group(1), re.MULTILINE):
        raise ValueError("[model_providers.codex-router] with base_url is required")
    if args.launch_agent and sys.platform != "darwin":
        raise ValueError("--launch-agent is currently supported only on macOS")


def agent_definition(*, name: str, description: str, control_model: str, base_url: str) -> str:
    return f'''name = {json.dumps(name)}
description = {json.dumps(description)}
model_provider = "codex-router"
model = {json.dumps(control_model)}
model_providers.codex-router.name = "Codex Router Kimi child adapter"
model_providers.codex-router.base_url = {json.dumps(base_url)}
model_providers.codex-router.wire_api = "responses"

developer_instructions = """
{AGENT_INSTRUCTIONS}
"""
'''


def same_tree(source: Path, target: Path) -> bool:
    if not target.is_dir():
        return False
    source_files = {item.relative_to(source) for item in source.rglob("*") if item.is_file()}
    target_files = {item.relative_to(target) for item in target.rglob("*") if item.is_file()}
    return source_files == target_files and all(
        (target / relative).read_bytes() == (source / relative).read_bytes()
        for relative in source_files
    )


class Installer:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.codex_home = args.codex_home.expanduser().resolve()
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        self.backup_root = self.codex_home / "backups" / f"kimi-dual-lane-{stamp}"
        self.file_operations: list[FileOperation] = []
        self.tree_operations: list[TreeOperation] = []
        self.moved_targets: list[tuple[Path, Path]] = []
        self.created_targets: list[Path] = []
        self.created_directories: list[Path] = []

    def report(self, action: str, target: Path) -> None:
        prefix = "DRY-RUN" if self.args.dry_run else action
        print(f"{prefix}: {target}")

    def route_token(self) -> str:
        target = self.codex_home / "kimi-dual-lane" / "route-token"
        if target.is_file():
            value = target.read_text(encoding="utf-8").strip()
            if not re.fullmatch(r"[A-Za-z0-9_-]{32,}", value):
                raise ValueError(f"existing route token is invalid: {target}")
            return value
        return secrets.token_urlsafe(32)

    def merged_overlay(self) -> bytes:
        overlay = json.loads(OVERLAY_SOURCE.read_text(encoding="utf-8"))
        target = self.codex_home / "codex-router" / "user-models.json"
        current = (
            json.loads(target.read_text(encoding="utf-8"))
            if target.exists()
            else {"version": 1, "models": []}
        )
        if not isinstance(current, dict) or not isinstance(current.get("models"), list):
            raise ValueError(f"unsupported user-models.json shape: {target}")
        if not isinstance(overlay, dict) or len(overlay.get("models", [])) != 1:
            raise ValueError(f"unsupported overlay source shape: {OVERLAY_SOURCE}")
        replacement = overlay["models"][0]
        models = [
            model
            for model in current["models"]
            if isinstance(model, dict) and model.get("slug") != replacement["slug"]
        ]
        models.append(replacement)
        merged = {**current, "version": current.get("version", 1), "models": models}
        return (json.dumps(merged, indent=2, ensure_ascii=False) + "\n").encode()

    def launch_agent_content(self, adapter_target: Path) -> tuple[Path, bytes]:
        node = self.args.node or shutil.which("node")
        if not node or not Path(node).is_absolute() or not os.access(node, os.X_OK):
            raise ValueError("an executable absolute Node.js path is required for --launch-agent")
        log_dir = self.codex_home / "logs" / "kimi-dual-lane"
        plist_path = (
            Path.home()
            / "Library"
            / "LaunchAgents"
            / "io.github.codex-kimi-dual-lane.plist"
        )
        payload = {
            "Label": "io.github.codex-kimi-dual-lane",
            "ProgramArguments": [node, str(adapter_target)],
            "WorkingDirectory": str(adapter_target.parent),
            "EnvironmentVariables": {
                "CODEX_HOME": str(self.codex_home),
                "KIMI_CHILD_ADAPTER_PORT": str(self.args.port),
                "KIMI_CHILD_ADAPTER_TOKEN_FILE": str(
                    self.codex_home / "kimi-dual-lane" / "route-token"
                ),
            },
            "RunAtLoad": True,
            "KeepAlive": True,
            "ProcessType": "Adaptive",
            "ThrottleInterval": 10,
            "StandardOutPath": str(log_dir / "adapter.log"),
            "StandardErrorPath": str(log_dir / "adapter.log"),
        }
        return plist_path, plistlib.dumps(payload, fmt=plistlib.FMT_XML, sort_keys=False)

    def build_plan(self) -> None:
        for source in (ADAPTER_SOURCE, OVERLAY_SOURCE, SKILL_SOURCE / "SKILL.md"):
            if not source.is_file():
                raise ValueError(f"required source is missing: {source}")
        wrapper = SKILL_SOURCE / "scripts" / "kimi-worker"
        if not wrapper.is_file():
            raise ValueError(f"required worker is missing: {wrapper}")

        install_root = self.codex_home / "kimi-dual-lane"
        adapter_target = install_root / "adapter" / "kimi-child-adapter.mjs"
        token_target = install_root / "route-token"
        route_token = self.route_token()
        route_root = f"http://127.0.0.1:{self.args.port}/_kimi-child/{route_token}"

        self.file_operations = [
            FileOperation(adapter_target, ADAPTER_SOURCE.read_bytes(), 0o755),
            FileOperation(token_target, (route_token + "\n").encode(), 0o600),
            FileOperation(
                self.codex_home / "agents" / "router-model-kimi-oauth-k3-256k.toml",
                agent_definition(
                    name="router_kimi_oauth_k3_256k",
                    description="Kimi K3 256K worker through the local dual-lane adapter.",
                    control_model=self.args.control_model_256k,
                    base_url=f"{route_root}/kimi-k3-256k/v1",
                ).encode(),
                0o600,
            ),
            FileOperation(
                self.codex_home / "agents" / "router-model-kimi-oauth-k3.toml",
                agent_definition(
                    name="router_kimi_oauth_k3",
                    description="Kimi K3 worker through the local dual-lane adapter.",
                    control_model=self.args.control_model_k3,
                    base_url=f"{route_root}/kimi-k3/v1",
                ).encode(),
                0o600,
            ),
        ]
        self.tree_operations = [
            TreeOperation(SKILL_SOURCE, self.codex_home / "skills" / "kimi-worker")
        ]

        if not self.args.skip_model_overlay:
            self.file_operations.append(
                FileOperation(
                    self.codex_home / "codex-router" / "user-models.json",
                    self.merged_overlay(),
                    0o600,
                    allow_structured_update=True,
                )
            )
        if self.args.launch_agent:
            target, content = self.launch_agent_content(adapter_target)
            self.file_operations.append(FileOperation(target, content, 0o644))

    def preflight(self) -> None:
        self.build_plan()
        for operation in self.file_operations:
            target = operation.target
            if not target.exists() and not target.is_symlink():
                continue
            if target.is_file() and target.read_bytes() == operation.content:
                continue
            if not (self.args.force or operation.allow_structured_update):
                raise ValueError(f"target exists with different content; use --force: {target}")
        for operation in self.tree_operations:
            if operation.target.exists() and not same_tree(operation.source, operation.target):
                if not self.args.force:
                    raise ValueError(
                        f"target exists with different content; use --force: {operation.target}"
                    )

    def backup(self, target: Path) -> None:
        relative = target.name
        try:
            relative = str(target.relative_to(self.codex_home))
        except ValueError:
            pass
        backup = self.backup_root / relative
        self.report("BACKUP", backup)
        if self.args.dry_run:
            return
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(backup))
        self.moved_targets.append((backup, target))

    def apply_file(self, operation: FileOperation) -> None:
        target = operation.target
        if target.is_file() and target.read_bytes() == operation.content:
            self.report("UNCHANGED", target)
            return
        if target.exists() or target.is_symlink():
            self.backup(target)
        self.report("WRITE", target)
        if self.args.dry_run:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(operation.content)
            os.chmod(temporary, operation.mode)
            os.replace(temporary, target)
            self.created_targets.append(target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def apply_tree(self, operation: TreeOperation) -> None:
        if same_tree(operation.source, operation.target):
            self.report("UNCHANGED", operation.target)
            return
        if operation.target.exists() or operation.target.is_symlink():
            self.backup(operation.target)
        self.report("COPY", operation.target)
        if self.args.dry_run:
            return
        operation.target.parent.mkdir(parents=True, exist_ok=True)
        self.created_targets.append(operation.target)
        shutil.copytree(operation.source, operation.target)
        wrapper = operation.target / "scripts" / "kimi-worker"
        wrapper.chmod(0o755)

    def rollback(self) -> None:
        if self.args.dry_run:
            return
        for target in reversed(self.created_targets):
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            elif target.exists() or target.is_symlink():
                target.unlink()
        for backup, target in reversed(self.moved_targets):
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(backup), str(target))
        for directory in reversed(self.created_directories):
            try:
                directory.rmdir()
            except OSError:
                pass

    def run(self) -> None:
        self.preflight()
        try:
            for operation in self.file_operations:
                self.apply_file(operation)
            for operation in self.tree_operations:
                self.apply_tree(operation)
            if self.args.launch_agent and not self.args.dry_run:
                log_dir = self.codex_home / "logs" / "kimi-dual-lane"
                if not log_dir.exists():
                    log_dir.mkdir(parents=True)
                    self.created_directories.append(log_dir)
        except Exception:
            self.rollback()
            print(f"Rollback restored prior targets. Evidence: {self.backup_root}", file=sys.stderr)
            raise

        if self.moved_targets:
            print(f"Backups: {self.backup_root}")
        print("No service was restarted. Reload Codex/router only in a maintenance window.")


def main() -> int:
    args = parser().parse_args()
    installer = Installer(args)
    try:
        validate(args)
        installer.run()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
