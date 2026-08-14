from __future__ import annotations

import json
import os
import importlib.util
import io
import contextlib
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "install.py"
DOCTOR = ROOT / "scripts" / "doctor.py"
SPEC = importlib.util.spec_from_file_location("dual_lane_install", INSTALLER)
assert SPEC and SPEC.loader
INSTALL_MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = INSTALL_MODULE
SPEC.loader.exec_module(INSTALL_MODULE)


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temporary.name) / ".codex"
        self.codex_home.mkdir()
        (self.codex_home / "config.toml").write_text(
            '[model_providers.codex-router]\n'
            'name = "Synthetic Router"\n'
            'base_url = "http://127.0.0.1:4999/synthetic/v1"\n'
            'wire_api = "responses"\n',
            encoding="utf-8",
        )
        overlay = self.codex_home / "codex-router" / "user-models.json"
        overlay.parent.mkdir()
        overlay.write_text(
            json.dumps(
                {
                    "version": 1,
                    "models": [
                        {
                            "slug": "synthetic/existing",
                            "gatewayModel": "synthetic-existing",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def run_installer(self, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(INSTALLER), "--codex-home", str(self.codex_home), *extra],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_installs_portable_files_and_preserves_existing_overlay_models(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(
            (self.codex_home / "kimi-dual-lane" / "adapter" / "kimi-child-adapter.mjs").is_file()
        )
        self.assertTrue((self.codex_home / "skills" / "kimi-worker" / "SKILL.md").is_file())
        agent = (
            self.codex_home / "agents" / "router-model-kimi-oauth-k3-256k.toml"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            agent,
            r"http://127\.0\.0\.1:4213/_kimi-child/[A-Za-z0-9_-]{32,}/kimi-k3-256k/v1",
        )
        self.assertNotIn("/Users/", agent)
        token = self.codex_home / "kimi-dual-lane" / "route-token"
        self.assertRegex(token.read_text().strip(), r"^[A-Za-z0-9_-]{32,}$")
        self.assertEqual(token.stat().st_mode & 0o777, 0o600)
        self.assertEqual(
            (self.codex_home / "agents" / "router-model-kimi-oauth-k3-256k.toml").stat().st_mode
            & 0o777,
            0o600,
        )

        overlay = json.loads(
            (self.codex_home / "codex-router" / "user-models.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            {model["slug"] for model in overlay["models"]},
            {"synthetic/existing", "kimi-oauth/k3-256k"},
        )

        repeated = self.run_installer()
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertIn("UNCHANGED", repeated.stdout)

    def test_refuses_changed_target_without_force_and_backs_it_up_with_force(self) -> None:
        first = self.run_installer()
        self.assertEqual(first.returncode, 0, first.stderr)
        agent = self.codex_home / "agents" / "router-model-kimi-oauth-k3.toml"
        agent.write_text("local change\n", encoding="utf-8")

        refused = self.run_installer()
        self.assertEqual(refused.returncode, 2)
        self.assertIn("use --force", refused.stderr)

        forced = self.run_installer("--force")
        self.assertEqual(forced.returncode, 0, forced.stderr)
        backups = list((self.codex_home / "backups").rglob("router-model-kimi-oauth-k3.toml"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), "local change\n")

    def test_invalid_overlay_fails_preflight_before_any_install_target_is_written(self) -> None:
        overlay = self.codex_home / "codex-router" / "user-models.json"
        overlay.write_text("not-json\n", encoding="utf-8")
        result = self.run_installer()
        self.assertEqual(result.returncode, 2)
        self.assertFalse((self.codex_home / "kimi-dual-lane").exists())
        self.assertFalse((self.codex_home / "agents").exists())

    def test_doctor_reports_an_installed_but_not_running_adapter_as_a_warning(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)

        fake_bin = Path(self.temporary.name) / "bin"
        fake_bin.mkdir()
        for command in ("node", "kimi"):
            executable = fake_bin / command
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
        environment = {**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"}
        result = subprocess.run(
            [
                sys.executable,
                str(DOCTOR),
                "--codex-home",
                str(self.codex_home),
                "--port",
                "49277",
                "--json",
            ],
            text=True,
            capture_output=True,
            env=environment,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        checks = {item["name"]: item for item in json.loads(result.stdout)["checks"]}
        self.assertTrue(checks["worker skill"]["ok"])
        self.assertTrue(checks["256K model overlay"]["ok"])
        self.assertFalse(checks["adapter health"]["ok"])
        self.assertFalse(checks["adapter health"]["required"])

    def test_doctor_rejects_a_skill_without_an_executable_worker(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        worker = self.codex_home / "skills" / "kimi-worker" / "scripts" / "kimi-worker"
        worker.chmod(0o644)
        fake_bin = Path(self.temporary.name) / "doctor-bin"
        fake_bin.mkdir()
        for command in ("node", "kimi"):
            executable = fake_bin / command
            executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            executable.chmod(0o755)
        result = subprocess.run(
            [sys.executable, str(DOCTOR), "--codex-home", str(self.codex_home), "--json"],
            text=True,
            capture_output=True,
            env={**os.environ, "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}"},
            check=False,
        )
        self.assertEqual(result.returncode, 1)
        checks = {item["name"]: item for item in json.loads(result.stdout)["checks"]}
        self.assertFalse(checks["worker skill"]["ok"])

    def test_rolls_back_a_replacement_when_a_later_apply_step_fails(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        adapter = self.codex_home / "kimi-dual-lane" / "adapter" / "kimi-child-adapter.mjs"
        prior = b"local adapter that must survive\n"
        adapter.write_bytes(prior)

        args = INSTALL_MODULE.parser().parse_args(
            ["--codex-home", str(self.codex_home), "--force"]
        )
        INSTALL_MODULE.validate(args)

        class FailingInstaller(INSTALL_MODULE.Installer):
            def apply_file(self, operation):
                super().apply_file(operation)
                if operation.target.name == "kimi-child-adapter.mjs":
                    raise OSError("synthetic failure after replacement")

        installer = FailingInstaller(args)
        diagnostics = io.StringIO()
        operations = io.StringIO()
        with (
            self.assertRaisesRegex(OSError, "synthetic failure"),
            contextlib.redirect_stderr(diagnostics),
            contextlib.redirect_stdout(operations),
        ):
            installer.run()
        self.assertEqual(adapter.read_bytes(), prior)
        self.assertIn("Rollback restored prior targets", diagnostics.getvalue())


if __name__ == "__main__":
    unittest.main()
