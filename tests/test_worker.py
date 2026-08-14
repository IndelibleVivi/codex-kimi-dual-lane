from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "skills" / "kimi-worker" / "scripts" / "kimi-worker"


class WorkerArtifactTest(unittest.TestCase):
    def test_captures_final_and_exposes_a_web_visible_same_session(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            artifacts = root / "artifacts"
            kimi_home = root / ".kimi-code"
            kimi_home.mkdir()
            fake = root / "fake-kimi"
            fake.write_text(
                "#!/usr/bin/env python3\n"
                "import json, sys\n"
                "def send(value):\n"
                "    print(json.dumps(value), flush=True)\n"
                "for line in sys.stdin:\n"
                "    request = json.loads(line)\n"
                "    method = request.get('method')\n"
                "    if method == 'initialize':\n"
                "        result = {'protocolVersion': 1, 'agentCapabilities': {}}\n"
                "    elif method == 'session/new':\n"
                "        result = {'sessionId': 'session_fake'}\n"
                "    elif method in ('session/set_config_option', 'session/set_mode'):\n"
                "        result = {}\n"
                "    elif method == 'session/prompt':\n"
                "        for text in ('FINAL_', 'ONLY'):\n"
                "            send({'jsonrpc': '2.0', 'method': 'session/update', 'params': {'sessionId': 'session_fake', 'update': {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': text}}}})\n"
                "        send({'jsonrpc': '2.0', 'method': 'session/update', 'params': {'sessionId': 'session_fake', 'update': {'sessionUpdate': 'tool_call_update', 'toolCallId': 'tool-1', 'content': [{'type': 'content', 'content': {'type': 'text', 'text': 'RAW_TOOL_OUTPUT'}}]}}})\n"
                "        result = {'stopReason': 'end_turn'}\n"
                "    else:\n"
                "        result = {}\n"
                "    send({'jsonrpc': '2.0', 'id': request['id'], 'result': result})\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            environment = {
                **os.environ,
                "KIMI_WORKER_CLI": str(fake),
                "KIMI_CODE_HOME": str(kimi_home),
            }

            result = subprocess.run(
                [
                    str(WORKER),
                    "--cwd",
                    str(repo),
                    "--artifacts-dir",
                    str(artifacts),
                    "--",
                    "private synthetic prompt",
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((artifacts / "status").read_text().strip(), "complete")
            self.assertEqual((artifacts / "final.md").read_text().strip(), "FINAL_ONLY")
            self.assertEqual((artifacts / "session-id").read_text().strip(), "session_fake")
            self.assertEqual(
                (artifacts / "vis-command").read_text().strip(), "kimi vis session_fake"
            )
            self.assertIn("Watch this session: kimi vis session_fake", result.stderr)
            metadata = (artifacts / "metadata.json").read_text(encoding="utf-8")
            self.assertIn('"transport": "acp"', metadata)
            self.assertNotIn("private synthetic prompt", metadata)
            self.assertNotIn("RAW_TOOL_OUTPUT", (artifacts / "final.md").read_text())

    def test_explicit_skill_dir_uses_the_web_visible_cli_compatibility_path(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            kimi_home = root / ".kimi-code"
            kimi_home.mkdir()
            extra_skills = root / "extra-skills"
            extra_skills.mkdir()
            fake = root / "fake-kimi"
            fake.write_text(
                "#!/bin/zsh\n"
                "set -euo pipefail\n"
                "print -r -- \"${KIMI_CODE_LEGACY_FLAG:-unset}\" > \"$KIMI_CODE_HOME/legacy-flag\"\n"
                "print -r -- 'FINAL_ONLY'\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)

            result = subprocess.run(
                [
                    str(WORKER),
                    "--cwd",
                    str(repo),
                    "--skills-dir",
                    str(extra_skills),
                    "--",
                    "synthetic prompt",
                ],
                text=True,
                capture_output=True,
                env={
                    **os.environ,
                    "KIMI_WORKER_CLI": str(fake),
                    "KIMI_CODE_HOME": str(kimi_home),
                },
                check=False,
            )

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual((kimi_home / "legacy-flag").read_text().strip(), "1")


if __name__ == "__main__":
    unittest.main()
