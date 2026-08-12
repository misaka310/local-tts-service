from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
from typing import Any


def no_console_python_executable(executable: str) -> str:
    """Prefer pythonw.exe on Windows so helper probes/workers stay windowless."""

    resolved = Path(executable).resolve()
    if os.name == "nt" and resolved.name.lower() == "python.exe":
        pythonw = resolved.with_name("pythonw.exe")
        if pythonw.is_file():
            return str(pythonw)
    return str(resolved)


def terminate_process(process: subprocess.Popen[Any], *, timeout: float = 5.0) -> None:
    """Gracefully stop one process, then kill it if it does not exit in time."""

    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def terminate_process_tree(process: subprocess.Popen[Any]) -> None:
    """Force-stop a process and descendants after a command timeout."""

    if process.poll() is not None:
        return
    if os.name == "nt":
        completed = subprocess.run(
            ["taskkill.exe", "/PID", str(process.pid), "/T", "/F"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)),
        )
        if completed.returncode == 0:
            return
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
            return
        except (OSError, ProcessLookupError):
            pass
    if process.poll() is None:
        process.kill()
