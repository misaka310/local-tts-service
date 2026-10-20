from __future__ import annotations

import importlib
import os
import runpy
import sys
from pathlib import Path
from typing import Sequence


LANG_SEGMENTER_MODULE = "GPT_SoVITS.text.LangSegmenter.langsegmenter"


def _uses_vendor_cache(config) -> bool:
    parts = [part.casefold() for part in Path(config.cache_dir).parts]
    return any(
        parts[index : index + 2] == ["pretrained_models", "fast_langdetect"]
        for index in range(len(parts) - 1)
    )


def configure_language_detector():
    """Redirect GPT-SoVITS language-detection cache outside its read-only vendor."""
    runtime_root_value = os.environ.get("LOCAL_TTS_RUNTIME_ROOT")
    if not runtime_root_value:
        raise RuntimeError("LOCAL_TTS_RUNTIME_ROOT is required for the GPT-SoVITS API")

    cache_dir = Path(runtime_root_value) / "gpt-sovits" / "fast-langdetect"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ["FTLANG_CACHE"] = str(cache_dir)

    fast_detect = importlib.import_module("fast_langdetect.infer")
    original_init = fast_detect.LangDetector.__init__
    if getattr(original_init, "_local_tts_cache_redirect", False):
        return cache_dir

    def init_with_runtime_cache(self, config=None):
        if config is not None and _uses_vendor_cache(config):
            config.cache_dir = str(cache_dir)
            config.model = "lite"
        original_init(self, config)

    init_with_runtime_cache._local_tts_cache_redirect = True
    fast_detect.LangDetector.__init__ = init_with_runtime_cache
    return cache_dir


def main(arguments: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if arguments is None else arguments)
    if not args:
        raise SystemExit("usage: gpt_sovits_api_bootstrap.py <api_v2.py> [api arguments]")

    api_script = Path(args[0]).resolve()
    if not api_script.is_file():
        raise SystemExit(f"GPT-SoVITS API script not found: {api_script}")

    # Leave import ordering and path setup to the upstream API entrypoint.
    configure_language_detector()
    sys.argv = [str(api_script), *args[1:]]
    runpy.run_path(str(api_script), run_name="__main__")


if __name__ == "__main__":
    main()