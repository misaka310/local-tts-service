from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

EXPECTED = {
    "chatterbox": {
        "model": "chatterbox_multilingual_v3",
        "code_revision": "5de7a54aa4e5e2baadb0182dde554908b48b85c2",
        "model_revision": "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18",
        "module": "chatterbox.mtl_tts",
        "required_files": (
            "ve.pt",
            "s3gen.pt",
            "t3_mtl23ls_v3.safetensors",
            "grapheme_mtl_merged_expanded_v1.json",
        ),
    },
    "cosyvoice": {
        "model": "fun_cosyvoice3_0_5b",
        "code_revision": "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc",
        "model_revision": "29e01c4e8d000f4bcd70751be16fa94bf3d85a18",
        "module": "cosyvoice.cli.cosyvoice",
        "required_files": (
            "cosyvoice3.yaml",
            "llm.pt",
            "flow.pt",
            "hift.pt",
            "speech_tokenizer_v3.onnx",
            "campplus.onnx",
        ),
    },
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=sorted(EXPECTED), required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    args = parser.parse_args()

    root = args.repo_root.resolve()
    expected = EXPECTED[args.model]
    vendor = root / "runtime" / "vendor" / args.model
    model_dir = root / "runtime" / "models" / args.model
    manifest_path = root / "runtime" / "manifests" / f"{args.model}.json"

    if not (vendor / ".git").is_dir():
        raise FileNotFoundError(f"Official source checkout is missing: {vendor}")
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Pinned installation manifest is missing: {manifest_path}")
    for relative in expected["required_files"]:
        required = model_dir / str(relative)
        if not required.is_file():
            raise FileNotFoundError(f"Required model file is missing: {required}")
    if args.model == "cosyvoice":
        wetext_dir = root / "runtime" / "models" / "wetext"
        for relative in (
            "en/tn/tagger.fst",
            "en/tn/verbalizer.fst",
            "zh/tn/tagger.fst",
            "zh/tn/verbalizer.fst",
        ):
            required = wetext_dir / relative
            if not required.is_file():
                raise FileNotFoundError(f"Required WeText file is missing: {required}")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    if manifest.get("codeRevision") != expected["code_revision"]:
        raise RuntimeError(
            "Source revision mismatch: "
            f"expected={expected['code_revision']} actual={manifest.get('codeRevision')}"
        )
    if manifest.get("modelRevision") != expected["model_revision"]:
        raise RuntimeError(
            "Model revision mismatch: "
            f"expected={expected['model_revision']} actual={manifest.get('modelRevision')}"
        )

    if args.model == "cosyvoice":
        sys.path.insert(0, str(vendor / "third_party" / "Matcha-TTS"))
        sys.path.insert(0, str(vendor))
    importlib.import_module(str(expected["module"]))

    import torch

    print(
        json.dumps(
            {
                "available": True,
                "model": expected["model"],
                "codeRevision": expected["code_revision"],
                "modelRevision": expected["model_revision"],
                "python": sys.executable,
                "torch": torch.__version__,
                "cuda": str(torch.version.cuda),
                "cudaAvailable": torch.cuda.is_available(),
                "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu",
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
