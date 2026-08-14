from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / "skills" / "kimi-worker" / "scripts" / "kimi-worker"


class WorkerArtifactTest(unittest.TestCase):
    def test_captures_final_and_exposes_the_same_session_without_prompt_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            repo.mkdir()
            artifacts = root / "artifacts"
            kimi_home = root / ".kimi-code"
            kimi_home.mkdir()
            fake = root / "fake-kimi"
            fake.write_text(
                "#!/bin/zsh\n"
                "set -euo pipefail\n"
                "print -r -- \"{\\\"workDir\\\":\\\"$PWD\\\",\\\"sessionId\\\":\\\"session_fake\\\"}\" >> \"$KIMI_CODE_HOME/session_index.jsonl\"\n"
                "print -r -- '{\"role\":\"assistant\",\"content\":\"INTERMEDIATE\"}'\n"
                "print -r -- '{\"type\":\"tool\",\"content\":\"RAW_TOOL_OUTPUT\"}'\n"
                "print -r -- '{\"role\":\"assistant\",\"content\":\"FINAL_ONLY\"}'\n",
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
            self.assertNotIn("private synthetic prompt", metadata)
            self.assertNotIn("RAW_TOOL_OUTPUT", (artifacts / "final.md").read_text())


if __name__ == "__main__":
    unittest.main()
