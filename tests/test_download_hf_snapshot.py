from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace


def test_snapshot_download_explicitly_disables_implicit_auth(tmp_path, monkeypatch) -> None:
    script = Path(__file__).parents[1] / "scripts" / "download_hf_snapshot.py"
    spec = importlib.util.spec_from_file_location("local_tts_download_hf_snapshot", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured: dict[str, object] = {}

    def fake_snapshot_download(**kwargs):  # noqa: ANN003
        captured.update(kwargs)
        return str(tmp_path / "models")

    monkeypatch.setitem(
        sys.modules,
        "huggingface_hub",
        SimpleNamespace(snapshot_download=fake_snapshot_download),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            str(script),
            "--repo-id",
            "public/example",
            "--local-dir",
            str(tmp_path / "models"),
        ],
    )

    assert module.main() == 0
    assert captured["token"] is False
