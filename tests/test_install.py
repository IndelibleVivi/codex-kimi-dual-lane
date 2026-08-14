from __future__ import annotations

import datetime as dt
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
DOCTOR_SPEC = importlib.util.spec_from_file_location("dual_lane_doctor", DOCTOR)
assert DOCTOR_SPEC and DOCTOR_SPEC.loader
DOCTOR_MODULE = importlib.util.module_from_spec(DOCTOR_SPEC)
sys.modules[DOCTOR_SPEC.name] = DOCTOR_MODULE
DOCTOR_SPEC.loader.exec_module(DOCTOR_MODULE)


class InstallTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.codex_home = Path(self.temporary.name) / ".codex"
        self.kimi_code_home = Path(self.temporary.name) / ".kimi-code"
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
            [
                sys.executable,
                str(INSTALLER),
                "--codex-home",
                str(self.codex_home),
                "--kimi-code-home",
                str(self.kimi_code_home),
                *extra,
            ],
            text=True,
            capture_output=True,
            check=False,
        )

    def prepare_generated_256k_route(self) -> None:
        state = self.codex_home / "codex-router"
        (state / "litellm.yaml").write_text(
            'model_list:\n  - model_name: "kimi-oauth-k3-256k"\n',
            encoding="utf-8",
        )
        (state / "merged-models.json").write_text(
            json.dumps({"models": [{"slug": "kimi-oauth/k3-256k"}]}),
            encoding="utf-8",
        )

    def write_256k_receipt(self, provider: str, status: int) -> None:
        (self.codex_home / "codex-router" / "usage-events.jsonl").write_text(
            json.dumps(
                {
                    "at": dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z"),
                    "model": "kimi-oauth/k3-256k",
                    "provider": provider,
                    "status": status,
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def test_installs_portable_files_and_preserves_existing_overlay_models(self) -> None:
        result = self.run_installer()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PENDING: K3 256K is not live yet", result.stdout)
        self.assertTrue(
            (self.codex_home / "kimi-dual-lane" / "adapter" / "kimi-child-adapter.mjs").is_file()
        )
        self.assertTrue((self.codex_home / "skills" / "kimi-worker" / "SKILL.md").is_file())
        self.assertTrue(
            (
                self.kimi_code_home
                / "skills"
                / "codex-frontend-standards"
                / "SKILL.md"
            ).is_file()
        )
        agent = (
            self.codex_home / "agents" / "router-model-kimi-oauth-k3-256k.toml"
        ).read_text(encoding="utf-8")
        self.assertRegex(
            agent,
            r"http://127\.0\.0\.1:4213/_kimi-child/[A-Za-z0-9_-]{32,}/kimi-k3-256k/v1",
        )
        self.assertIn("Do not return an acknowledgement of starting work as final", agent)
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

    def test_skill_only_does_not_touch_router_or_agent_targets(self) -> None:
        result = self.run_installer("--skill-only")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.codex_home / "skills" / "kimi-worker" / "SKILL.md").is_file())
        self.assertTrue(
            (
                self.kimi_code_home
                / "skills"
                / "codex-frontend-standards"
                / "SKILL.md"
            ).is_file()
        )
        self.assertFalse((self.codex_home / "kimi-dual-lane").exists())
        self.assertFalse((self.codex_home / "agents").exists())

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
        self.prepare_generated_256k_route()
        self.write_256k_receipt("kimi-oauth", 200)

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

    def test_doctor_rejects_a_256k_receipt_that_fell_through_to_openai(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.prepare_generated_256k_route()
        self.write_256k_receipt("openai", 400)

        ok, required, detail = DOCTOR_MODULE.assess_256k_activation(
            self.codex_home,
            router_started_at=None,
        )

        self.assertFalse(ok)
        self.assertTrue(required)
        self.assertIn("fell through to OpenAI", detail)

    def test_doctor_rejects_a_router_process_older_than_the_256k_overlay(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.prepare_generated_256k_route()
        overlay = self.codex_home / "codex-router" / "user-models.json"

        ok, required, detail = DOCTOR_MODULE.assess_256k_activation(
            self.codex_home,
            router_started_at=overlay.stat().st_mtime - 60,
        )

        self.assertFalse(ok)
        self.assertTrue(required)
        self.assertIn("started before", detail)

    def test_doctor_accepts_a_current_kimi_oauth_256k_receipt(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.prepare_generated_256k_route()
        overlay = self.codex_home / "codex-router" / "user-models.json"
        overlay.touch()
        self.write_256k_receipt("kimi-oauth", 200)
        receipt = self.codex_home / "codex-router" / "usage-events.jsonl"
        receipt.touch()

        ok, required, detail = DOCTOR_MODULE.assess_256k_activation(
            self.codex_home,
            router_started_at=overlay.stat().st_mtime - 60,
        )

        self.assertTrue(ok)
        self.assertTrue(required)
        self.assertIn("provider kimi-oauth", detail)

    def test_rolls_back_a_replacement_when_a_later_apply_step_fails(self) -> None:
        installed = self.run_installer()
        self.assertEqual(installed.returncode, 0, installed.stderr)
        adapter = self.codex_home / "kimi-dual-lane" / "adapter" / "kimi-child-adapter.mjs"
        prior = b"local adapter that must survive\n"
        adapter.write_bytes(prior)

        args = INSTALL_MODULE.parser().parse_args(
            [
                "--codex-home",
                str(self.codex_home),
                "--kimi-code-home",
                str(self.kimi_code_home),
                "--force",
            ]
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
