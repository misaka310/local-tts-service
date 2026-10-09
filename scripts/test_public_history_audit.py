from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
AUDIT_SCRIPT = SCRIPT_DIR / "audit_public_history.py"


def run(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(
            f"command failed ({result.returncode}): {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
    return result


def git(repo: Path, *args: str) -> None:
    run(["git", "-C", str(repo), *args])


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="local-tts-history-audit-test-") as temp_dir:
        repo = Path(temp_dir)
        git(repo, "init")
        git(repo, "config", "user.email", "audit-test@example.invalid")
        git(repo, "config", "user.name", "Audit Test")

        (repo / "safe.txt").write_text("safe content\n", encoding="utf-8")
        public_reference_dir = repo / "reference"
        public_reference_dir.mkdir(parents=True)
        (public_reference_dir / "README.md").write_text("public reference instructions\n", encoding="utf-8")
        workflow_dir = public_reference_dir / "workflows"
        workflow_dir.mkdir()
        (workflow_dir / "example.json").write_text("{}\n", encoding="utf-8")
        git(repo, "add", "safe.txt", "reference/README.md", "reference/workflows/example.json")
        git(repo, "commit", "-m", "safe")

        reference_dir = repo / "reference"
        reference_dir.mkdir(parents=True, exist_ok=True)
        (reference_dir / "private.wav").write_bytes(bytes((1, 2, 3, 4)))
        local_path = "C:" + "\\Users\\" + "alice\\private"
        token = "hf_" + "abcdefghijklmnopqrstuvwxyz123456"
        (repo / "notes.txt").write_text(
            f"local path: {local_path}\ntoken: {token}\n",
            encoding="utf-8",
        )
        git(repo, "add", "reference/private.wav", "notes.txt")
        git(repo, "commit", "-m", "unsafe history")

        (reference_dir / "private.wav").unlink()
        (repo / "notes.txt").unlink()
        git(repo, "add", "-A")
        git(repo, "commit", "-m", "remove unsafe files")

        output_path = repo / "audit.json"
        run(
            [
                sys.executable,
                str(AUDIT_SCRIPT),
                "--repo-root",
                str(repo),
                "--output",
                str(output_path),
            ]
        )
        audit = json.loads(output_path.read_text(encoding="utf-8"))

        history_paths = audit["history"]["pathFindings"]
        history_content = audit["history"]["contentFindings"]
        assert any(item["path"] == "reference/private.wav" for item in history_paths), history_paths
        assert any(item["type"] == "local-user-path" for item in history_content), history_content
        assert any(item["type"] == "huggingface-token" for item in history_content), history_content
        assert audit["workingTreeVerdict"] == "PASS", audit["workingTree"]
        assert audit["historyVerdict"] == "FAIL", audit["history"]

    print("[OK] public history audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
