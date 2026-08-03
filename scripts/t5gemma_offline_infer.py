from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any


TEXT_TOKENIZER_ALLOW_PATTERNS = (
    "tokenizer*",
    "special_tokens_map.json",
    "added_tokens.json",
    "*.model",
)


def force_torch_compile_eager(torch_module: object) -> bool:
    """Prevent T5Gemma dependencies from spawning memory-heavy Inductor workers."""

    changed = False
    compiler = getattr(torch_module, "compiler", None)
    set_stance = getattr(compiler, "set_stance", None)
    if callable(set_stance):
        set_stance("force_eager")
        changed = True

    compile_fn = getattr(torch_module, "compile", None)
    if callable(compile_fn):
        def eager_compile(model=None, *args, **kwargs):
            del args, kwargs
            if model is None:
                return lambda inner: inner
            return model

        setattr(torch_module, "compile", eager_compile)
        changed = True
    return changed


def read_dependency_ids(model_dir: Path) -> tuple[str, str | None]:
    config_path = model_dir / "config.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"T5Gemma config not found: {config_path}")
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    text_key = "text_" + "tokenizer_name"
    primary_id = str(payload.get(text_key) or payload.get("t5gemma_model_name") or "").strip()
    if not primary_id:
        raise ValueError(f"T5Gemma text dependency is missing from {config_path}")
    codec_id = str(payload.get("xcodec2_model_name") or "").strip() or None
    return primary_id, codec_id


def local_loader_proxy(base_loader: Any, *, repo_id: str, local_dir: Path):
    class LocalLoader:
        @classmethod
        def from_pretrained(cls, name, *args, **kwargs):
            del cls
            resolved = local_dir if str(name) == repo_id else name
            kwargs["local_files_only"] = True
            method = getattr(base_loader, "from_" + "pretrained")
            return method(resolved, *args, **kwargs)

    return LocalLoader


def resolve_cached_snapshot(
    repo_id: str,
    *,
    allow_patterns: tuple[str, ...] | None = None,
) -> Path:
    from huggingface_hub import snapshot_download

    download_kwargs: dict[str, Any] = {
        "repo_id": repo_id,
        "local_files_only": True,
    }
    if allow_patterns is not None:
        download_kwargs["allow_patterns"] = list(allow_patterns)
    try:
        return Path(snapshot_download(**download_kwargs)).resolve()
    except Exception as exc:
        raise RuntimeError(
            f"Required T5Gemma dependency is not cached locally: {repo_id}. "
            "Run the T5Gemma setup again while repository access is valid."
        ) from exc


def ensure_cached_dependencies(model_dir: Path) -> tuple[Path, Path]:
    primary_id, codec_id = read_dependency_ids(model_dir)
    if not codec_id:
        raise ValueError(f"T5Gemma codec dependency is missing from {model_dir / 'config.json'}")
    primary_dir = resolve_cached_snapshot(
        primary_id,
        allow_patterns=TEXT_TOKENIZER_ALLOW_PATTERNS,
    )
    codec_dir = resolve_cached_snapshot(codec_id)
    return primary_dir, codec_dir


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-cache", action="store_true")
    parser.add_argument("--vendor-dir", "--vendor_dir", dest="vendor_dir")
    parser.add_argument("--model-dir", "--model_dir", dest="model_dir", required=True)
    parser.add_argument("--target-text", "--target_text", dest="target_text")
    parser.add_argument("--reference-text", "--reference_text", dest="reference_text")
    parser.add_argument("--reference-speech", "--reference_speech", dest="reference_speech")
    parser.add_argument("--lang", default="ja")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--output-dir", "--output_dir", dest="output_dir")
    parser.add_argument("--target-duration", "--target_duration", dest="target_duration", type=float)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_dir = Path(args.model_dir).resolve()
    if not model_dir.is_dir():
        raise FileNotFoundError(f"T5Gemma model directory not found: {model_dir}")

    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    os.environ["TORCHDYNAMO_DISABLE"] = "1"
    os.environ["TORCHINDUCTOR_COMPILE_THREADS"] = "1"

    primary_id, _ = read_dependency_ids(model_dir)
    primary_dir, _ = ensure_cached_dependencies(model_dir)
    if args.check_cache:
        print(f"[OK] T5Gemma dependencies are cached: {model_dir}")
        return 0

    required_values = {
        "vendor_dir": args.vendor_dir,
        "target_text": args.target_text,
        "reference_text": args.reference_text,
        "reference_speech": args.reference_speech,
        "output_dir": args.output_dir,
    }
    missing = [name for name, value in required_values.items() if not str(value or "").strip()]
    if missing:
        raise ValueError("missing inference argument(s): " + ", ".join(missing))

    vendor_dir = Path(args.vendor_dir).resolve()
    if not vendor_dir.is_dir():
        raise FileNotFoundError(f"T5Gemma vendor directory not found: {vendor_dir}")

    import torch

    if force_torch_compile_eager(torch):
        print("[INFO] t5gemma: torch.compile forced to eager mode", file=sys.stderr, flush=True)
    sys.path.insert(0, str(vendor_dir))
    import inference_commandline_hf as vendor_inference

    loader_name = "Auto" + "Tokenizer"
    base_loader = getattr(vendor_inference, loader_name)
    if base_loader is None:
        raise ImportError("transformers text loader is unavailable in T5Gemma environment")
    setattr(
        vendor_inference,
        loader_name,
        local_loader_proxy(base_loader, repo_id=primary_id, local_dir=primary_dir),
    )

    call_args = {
        "reference_speech": args.reference_speech,
        "target_text": args.target_text,
        "model_dir": str(model_dir),
        "reference_text": args.reference_text,
        "lang": args.lang,
        "seed": args.seed,
        "output_dir": args.output_dir,
    }
    if args.target_duration is not None:
        call_args["target_duration"] = args.target_duration
    vendor_inference.run_inference(**call_args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
