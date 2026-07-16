from __future__ import annotations

import argparse
from collections import Counter
import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Iterable

MAX_TEXT_BLOB_BYTES = 2 * 1024 * 1024

SENSITIVE_EXTENSIONS = {
    ".wav",
    ".mp3",
    ".flac",
    ".ogg",
    ".m4a",
    ".aac",
    ".webm",
    ".mp4",
    ".mov",
    ".pth",
    ".pt",
    ".ckpt",
    ".safetensors",
    ".onnx",
    ".index",
    ".zip",
    ".7z",
    ".tar",
    ".gz",
}

TEXT_EXTENSIONS = {
    "",
    ".txt",
    ".md",
    ".json",
    ".jsonl",
    ".csv",
    ".tsv",
    ".py",
    ".ps1",
    ".psm1",
    ".bat",
    ".cmd",
    ".js",
    ".mjs",
    ".cjs",
    ".ts",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".cfg",
    ".conf",
    ".xml",
    ".env",
    ".gitignore",
    ".gitattributes",
    ".properties",
}

IDENTITY_TERMS = (
    "dochi" + "tao",
    "haru" + "hi",
    "asu" + "ka",
    "sugu" + "ha",
    "j" + "kv",
    "naki" + "_dochi",
    "yoso" + "_dochi",
    "futsu" + "_dochi",
    "oko" + "_dochi",
    "pani" + "_dochi",
)
IDENTITY_PATTERN = re.compile("|".join(re.escape(term) for term in IDENTITY_TERMS), re.IGNORECASE)

CONTENT_RULES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("huggingface-token", re.compile(r"(?<![A-Za-z0-9])hf_[A-Za-z0-9]{20,}")),
    ("openai-token", re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9]{20,}")),
    ("github-token", re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}")),
    ("aws-access-key", re.compile(r"(?<![A-Z0-9])AKIA[0-9A-Z]{16}(?![A-Z0-9])")),
    ("private-key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
    ("bearer-token", re.compile(r"Bearer\s+[A-Za-z0-9._~+/-]{20,}={0,2}", re.IGNORECASE)),
    ("local-user-path", re.compile(r"[A-Z]:\\Users\\[^\r\n\"']+", re.IGNORECASE)),
    ("local-dev-path", re.compile(r"C:\\00_dev\\", re.IGNORECASE)),
    ("machine-name", re.compile(r"DESKTOP-[A-Z0-9-]+", re.IGNORECASE)),
    ("project-specific-identity", IDENTITY_PATTERN),
)

CONTENT_SCAN_EXCLUSIONS = {
    "scripts/audit_public_history.py",
    "scripts/test_public_history_audit.py",
}


@dataclass(frozen=True)
class PathFinding:
    type: str
    path: str
    objectId: str = ""


@dataclass(frozen=True)
class ContentFinding:
    type: str
    path: str
    line: int
    objectId: str = ""


class AuditError(RuntimeError):
    pass


def resolve_git() -> str:
    candidate = shutil.which("git")
    if candidate:
        return candidate
    windows_candidates = [
        Path("C:/Program Files/Git/cmd/git.exe"),
        Path("C:/Program Files/Git/mingw64/bin/git.exe"),
        Path(os.environ.get("ProgramFiles", "")) / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Git" / "mingw64" / "bin" / "git.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Git" / "mingw64" / "bin" / "git.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "cmd" / "git.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Git" / "mingw64" / "bin" / "git.exe",
    ]
    for path in windows_candidates:
        if path.is_file():
            return str(path)
    raise AuditError("git executable was not found")


def run_git(repo_root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
    command = [resolve_git(), "-C", str(repo_root), *args]
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=text,
        encoding="utf-8" if text else None,
        errors="replace" if text else None,
        check=False,
    )
    if result.returncode != 0:
        stderr = result.stderr.strip() if isinstance(result.stderr, str) else result.stderr.decode("utf-8", "replace").strip()
        raise AuditError(f"git command failed ({' '.join(args)}): {stderr}")
    return result


def git_lines(repo_root: Path, *args: str) -> list[str]:
    result = run_git(repo_root, *args)
    assert isinstance(result.stdout, str)
    return [line for line in result.stdout.splitlines() if line]


def normalize_path(raw_path: str) -> str:
    return raw_path.replace("\\", "/").lstrip("./")


def path_finding_types(raw_path: str) -> list[str]:
    path = normalize_path(raw_path)
    lower = path.lower()
    types: list[str] = []
    if PurePosixPath(lower).suffix in SENSITIVE_EXTENSIONS:
        types.append("media-model-or-archive")
    if (
        lower in {"config.local.json", "config/config.local.json"}
        or lower == ".env"
        or lower.startswith(".env.")
        or lower.startswith("runtime/")
        or (
            lower.startswith("reference/")
            and lower not in {"reference/readme.md", "reference/workflows"}
            and not lower.startswith("reference/workflows/")
        )
        or lower.startswith("data/source_audio/")
    ):
        types.append("local-or-private-path")
    if IDENTITY_PATTERN.search(lower):
        types.append("project-specific-identity")
    return types


def is_text_candidate(raw_path: str) -> bool:
    path = PurePosixPath(normalize_path(raw_path))
    if path.name.lower() in {"readme", "license", "dockerfile", "makefile"}:
        return True
    return path.suffix.lower() in TEXT_EXTENSIONS


def find_content_issues(text: str, path: str, object_id: str = "") -> list[ContentFinding]:
    normalized = normalize_path(path)
    if normalized in CONTENT_SCAN_EXCLUSIONS:
        return []
    findings: list[ContentFinding] = []
    for finding_type, pattern in CONTENT_RULES:
        match = pattern.search(text)
        if not match:
            continue
        line = text.count("\n", 0, match.start()) + 1
        findings.append(ContentFinding(finding_type, normalized, line, object_id))
    return findings


def unique_findings(findings: Iterable[PathFinding | ContentFinding]) -> list[PathFinding | ContentFinding]:
    result: list[PathFinding | ContentFinding] = []
    seen: set[tuple[object, ...]] = set()
    for finding in findings:
        if isinstance(finding, ContentFinding):
            key = (finding.type, finding.path, finding.objectId, finding.line)
        else:
            key = (finding.type, finding.path, finding.objectId)
        if key in seen:
            continue
        seen.add(key)
        result.append(finding)
    return result


def list_working_files(repo_root: Path) -> list[str]:
    return sorted(set(git_lines(repo_root, "ls-files", "--cached", "--others", "--exclude-standard")))


def scan_working_tree(repo_root: Path) -> tuple[list[PathFinding], list[ContentFinding], int]:
    path_findings: list[PathFinding] = []
    content_findings: list[ContentFinding] = []
    files = list_working_files(repo_root)
    for raw_path in files:
        path = normalize_path(raw_path)
        full_path = repo_root / Path(path)
        if not full_path.is_file():
            continue
        path_findings.extend(PathFinding(kind, path) for kind in path_finding_types(path))
        if not is_text_candidate(path) or full_path.stat().st_size > MAX_TEXT_BLOB_BYTES:
            continue
        try:
            text = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        content_findings.extend(find_content_issues(text, path))
    return (
        [finding for finding in unique_findings(path_findings) if isinstance(finding, PathFinding)],
        [finding for finding in unique_findings(content_findings) if isinstance(finding, ContentFinding)],
        len(files),
    )


def scan_history(repo_root: Path) -> tuple[list[PathFinding], list[ContentFinding], int]:
    path_findings: list[PathFinding] = []
    content_findings: list[ContentFinding] = []
    scanned_blobs: set[str] = set()
    object_path_count = 0

    for line in git_lines(repo_root, "rev-list", "--objects", "--all"):
        object_id, separator, raw_path = line.partition(" ")
        if not separator or not raw_path:
            continue
        path = normalize_path(raw_path)
        object_path_count += 1
        path_findings.extend(PathFinding(kind, path, object_id) for kind in path_finding_types(path))

        if object_id in scanned_blobs or not is_text_candidate(path):
            continue
        scanned_blobs.add(object_id)
        object_type = run_git(repo_root, "cat-file", "-t", object_id).stdout
        if not isinstance(object_type, str) or object_type.strip() != "blob":
            continue
        object_size_text = run_git(repo_root, "cat-file", "-s", object_id).stdout
        if not isinstance(object_size_text, str):
            continue
        try:
            object_size = int(object_size_text.strip())
        except ValueError:
            continue
        if object_size > MAX_TEXT_BLOB_BYTES:
            continue
        blob_result = run_git(repo_root, "cat-file", "-p", object_id, text=False)
        assert isinstance(blob_result.stdout, bytes)
        text = blob_result.stdout.decode("utf-8", errors="replace")
        content_findings.extend(find_content_issues(text, path, object_id))

    return (
        [finding for finding in unique_findings(path_findings) if isinstance(finding, PathFinding)],
        [finding for finding in unique_findings(content_findings) if isinstance(finding, ContentFinding)],
        object_path_count,
    )


def serialize_findings(findings: Iterable[PathFinding | ContentFinding]) -> list[dict[str, object]]:
    return [asdict(finding) for finding in findings]


def summarize_findings(findings: Iterable[PathFinding | ContentFinding]) -> dict[str, object]:
    materialized = list(findings)
    counts = Counter(finding.type for finding in materialized)
    sample_paths: dict[str, list[str]] = {}
    for finding_type in sorted(counts):
        paths: list[str] = []
        for finding in materialized:
            if finding.type != finding_type or finding.path in paths:
                continue
            paths.append(finding.path)
            if len(paths) >= 5:
                break
        sample_paths[finding_type] = paths
    return {
        "countsByType": dict(sorted(counts.items())),
        "samplePathsByType": sample_paths,
    }


def audit(repo_root: Path) -> dict[str, object]:
    inside = git_lines(repo_root, "rev-parse", "--is-inside-work-tree")
    if not inside or inside[0] != "true":
        raise AuditError(f"not a Git work tree: {repo_root}")

    working_paths, working_content, working_file_count = scan_working_tree(repo_root)
    history_paths, history_content, history_object_path_count = scan_history(repo_root)
    working_findings = [*working_paths, *working_content]
    history_findings = [*history_paths, *history_content]
    working_count = len(working_findings)
    history_count = len(history_findings)
    total_count = working_count + history_count

    return {
        "schemaVersion": 1,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "repoRoot": str(repo_root),
        "verdict": "FAIL" if total_count else "PASS",
        "workingTreeVerdict": "FAIL" if working_count else "PASS",
        "historyVerdict": "FAIL" if history_count else "PASS",
        "summary": {
            "workingFileCount": working_file_count,
            "historyObjectPathCount": history_object_path_count,
            "workingTreeFindings": working_count,
            "historyFindings": history_count,
            "totalFindings": total_count,
            "workingTreeBreakdown": summarize_findings(working_findings),
            "historyBreakdown": summarize_findings(history_findings),
        },
        "workingTree": {
            "pathFindings": serialize_findings(working_paths),
            "contentFindings": serialize_findings(working_content),
        },
        "history": {
            "pathFindings": serialize_findings(history_paths),
            "contentFindings": serialize_findings(history_content),
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit current files and all reachable Git history before public release.")
    parser.add_argument("--repo-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--output", default="runtime/audits/public-history-audit.json")
    parser.add_argument("--fail-on-findings", action="store_true")
    parser.add_argument("--fail-on-working-tree-findings", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo_root).resolve()
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = repo_root / output_path
    try:
        result = audit(repo_root)
    except AuditError as exc:
        print(f"[AUDIT ERROR] {exc}", file=sys.stderr)
        return 2

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = result["summary"]
    assert isinstance(summary, dict)
    print(
        "[AUDIT] "
        f"verdict={result['verdict']} "
        f"working={result['workingTreeVerdict']} "
        f"history={result['historyVerdict']} "
        f"working_files={summary['workingFileCount']} "
        f"history_paths={summary['historyObjectPathCount']} "
        f"findings={summary['totalFindings']}"
    )
    print(f"[AUDIT] output={output_path}")

    if args.fail_on_findings and result["verdict"] == "FAIL":
        return 1
    if args.fail_on_working_tree_findings and result["workingTreeVerdict"] == "FAIL":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
