from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from uuid import uuid4


def main() -> int:
    parser = argparse.ArgumentParser(description="Start one no-window detached child process on Windows.")
    parser.add_argument("--file", required=True)
    parser.add_argument("--working-directory", required=True)
    parser.add_argument("--stdout", type=Path, required=True)
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("args", nargs=argparse.REMAINDER)
    parsed = parser.parse_args()

    if sys.platform != "win32":
        raise SystemExit("start_detached_process.py is Windows-only")

    executable = Path(parsed.file).resolve()
    working_directory = Path(parsed.working_directory).resolve()
    if not executable.is_file():
        raise SystemExit(f"executable not found: {executable}")
    if not working_directory.is_dir():
        raise SystemExit(f"working directory not found: {working_directory}")

    parsed.stdout.parent.mkdir(parents=True, exist_ok=True)
    parsed.stderr.parent.mkdir(parents=True, exist_ok=True)
    launch_id = uuid4().hex
    creationflags = subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP

    with parsed.stdout.open("ab", buffering=0) as stdout_handle, parsed.stderr.open(
        "ab", buffering=0
    ) as stderr_handle:
        process = subprocess.Popen(
            [str(executable), *parsed.args],
            cwd=str(working_directory),
            stdin=subprocess.DEVNULL,
            stdout=stdout_handle,
            stderr=stderr_handle,
            close_fds=True,
            creationflags=creationflags,
        )

    print(
        json.dumps(
            {
                "started": True,
                "launchId": launch_id,
                "childProcessId": process.pid,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
