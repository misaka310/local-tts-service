from __future__ import annotations

import os
from pathlib import Path
import subprocess

from local_tts_service.runtimes import process_utils


def test_no_console_python_executable_prefers_pythonw_on_windows(tmp_path: Path) -> None:
    python = tmp_path / "python.exe"
    pythonw = tmp_path / "pythonw.exe"
    python.write_bytes(b"")
    pythonw.write_bytes(b"")
    resolved = process_utils.no_console_python_executable(str(python))
    expected = pythonw if os.name == "nt" else python
    assert Path(resolved) == expected.resolve()


def test_terminate_process_escalates_after_timeout() -> None:
    calls: list[tuple[str, float | None]] = []

    class FakeProcess:
        def poll(self):
            return None

        def terminate(self) -> None:
            calls.append(("terminate", None))

        def wait(self, timeout=None):
            calls.append(("wait", timeout))
            if len([call for call in calls if call[0] == "wait"]) == 1:
                raise subprocess.TimeoutExpired(["fake"], timeout)
            return -9

        def kill(self) -> None:
            calls.append(("kill", None))

    process_utils.terminate_process(FakeProcess(), timeout=2)  # type: ignore[arg-type]
    assert calls == [("terminate", None), ("wait", 2), ("kill", None), ("wait", 2)]
