from pathlib import Path


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
        "C:\\00_dev\\",
        "setup-and-start-local-tts.bat",
        "start-local-tts.bat",
        "check-local-tts.bat",
    ):
        assert internal_wording not in text

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
        path.name for path in REPO_ROOT.iterdir() if path.is_file() and not path.name.startswith(".")
    )
    assert visible_files == ["AGENTS.md", "LICENSE", "README.md", "local-tts.bat"]
