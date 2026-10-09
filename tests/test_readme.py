from pathlib import Path
import re
import stat

from scripts.audit_public_history import CONTENT_RULES


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"


def test_readme_is_a_short_first_time_user_entrypoint() -> None:
    text = README_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    assert len(lines) <= 140, f"README is too long for an entry page: {len(lines)} lines"

    for internal_heading in (
        "## フロントエンド構成",
        "## 動作確認",
        "## 公開リポ向けの注意",
        "## API",
    ):
        assert internal_heading not in text

    for internal_wording in (
        "30管理下",
        "setup-and-start-local-tts.bat",
        "start-local-tts.bat",
        "check-local-tts.bat",
    ):
        assert internal_wording not in text

    assert re.search(r"(?i)\b[A-Z]:[\\/]", text) is None

    for required_link in (
        "docs/user-guide.md",
        "docs/setup.md",
        "docs/troubleshooting.md",
        "docs/development.md",
        "docs/api.md",
        "docs/architecture.md",
    ):
        assert required_link in text

    assert "local-tts.bat" in text
    assert "-ForceSetup" in text
    assert "-Check" in text


def test_repository_root_has_only_public_entry_files() -> None:
    root_bats = sorted(path.name for path in REPO_ROOT.glob("*.bat"))
    assert root_bats == ["local-tts.bat"]

    visible_files = sorted(
        path.name
        for path in REPO_ROOT.iterdir()
        if not path.name.startswith(".") and stat.S_ISREG(path.lstat().st_mode)
    )
    assert visible_files == ["AGENTS.md", "LICENSE", "README.md", "local-tts.bat"]


def test_public_history_audit_detects_numbered_project_roots_generically() -> None:
    rule = next(pattern for name, pattern in CONTENT_RULES if name == "local-project-root")
    fake_root = chr(88) + ":" + chr(92) + "42_example" + chr(92)
    assert rule.search(fake_root) is not None
