from __future__ import annotations

from pathlib import Path

from scripts import download_qwen3_tts_model


def test_download_model_enters_background_mode_before_snapshot_download(
    monkeypatch, tmp_path: Path
) -> None:
    events: list[str] = []
    model_root = tmp_path / "qwen-model"

    monkeypatch.setattr(
        download_qwen3_tts_model,
        "_enter_windows_background_mode",
        lambda: events.append("background"),
    )
    cache_dir = tmp_path / "hf-cache"

    def fake_snapshot_download(
        *, repo_id: str, revision: str, local_dir: str, token: bool, cache_dir: str
    ) -> str:
        assert repo_id == download_qwen3_tts_model.MODEL_ID
        assert revision == download_qwen3_tts_model.MODEL_REVISION
        assert token is False
        assert Path(cache_dir) == (tmp_path / "hf-cache").resolve()
        output = Path(local_dir)
        (output / "config.json").write_text("{}", encoding="utf-8")
        (output / "model.safetensors").write_bytes(b"weights")
        events.append("download")
        return str(output)

    monkeypatch.setattr(download_qwen3_tts_model, "snapshot_download", fake_snapshot_download)

    result = download_qwen3_tts_model.download_model(model_root, cache_dir)

    assert result == model_root.resolve()
    assert events == ["background", "download"]
