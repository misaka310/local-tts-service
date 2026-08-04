from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
RUNTIME = ROOT / "runtime"
VENV_ROOT = RUNTIME / "venvs"
VENDOR_ROOT = RUNTIME / "vendor"
MODEL_ROOT = RUNTIME / "models"
MANIFEST_ROOT = RUNTIME / "manifests"
HF_HOME = RUNTIME / "hf-cache"

TORCH_VERSION = "2.10.0"
TORCH_INDEX = "https://download.pytorch.org/whl/cu128"

CHATTERBOX_CODE_REV = "5de7a54aa4e5e2baadb0182dde554908b48b85c2"
CHATTERBOX_MODEL_REV = "5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18"
PERTH_CODE_REV = "ce86c49d029f42272c1902eccb675556b9ed2330"
COSYVOICE_CODE_REV = "074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc"
COSYVOICE_MODEL_REV = "29e01c4e8d000f4bcd70751be16fa94bf3d85a18"


def log(message: str) -> None:
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    capture: bool = False,
) -> subprocess.CompletedProcess[str]:
    log("RUN " + subprocess.list2cmdline(command))
    completed = subprocess.run(
        command,
        cwd=str(cwd or ROOT),
        env=env,
        check=False,
        capture_output=capture,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if completed.returncode != 0:
        details = (completed.stderr or completed.stdout or "").strip()
        suffix = f": {details}" if details else ""
        raise RuntimeError(
            f"command failed with exit code {completed.returncode}: "
            f"{subprocess.list2cmdline(command)}{suffix}"
        )
    return completed


def clone_pinned(name: str, url: str, revision: str, *, submodules: bool = False) -> Path:
    target = VENDOR_ROOT / name
    if not (target / ".git").is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
        command = ["git", "clone"]
        if submodules:
            command.append("--recursive")
        command.extend([url, str(target)])
        run(command)
    run(["git", "-C", str(target), "fetch", "--depth", "1", "origin", revision])
    run(["git", "-C", str(target), "checkout", "--detach", revision])
    if submodules:
        run(["git", "-C", str(target), "submodule", "update", "--init", "--recursive", "--depth", "1"])
    return target


def resolve_uv() -> str:
    discovered = shutil.which("uv")
    if discovered:
        return discovered
    for candidate in (
        Path.home() / ".local" / "bin" / "uv.exe",
        Path.home() / ".local" / "bin" / "uv",
    ):
        if candidate.is_file():
            return str(candidate)
    raise RuntimeError("uv is required. Install uv before running this setup.")


def ensure_env(key: str, *, python_version: str) -> Path:
    uv = resolve_uv()
    env_dir = VENV_ROOT / key
    python = env_dir / "Scripts" / "python.exe"
    if not python.is_file():
        env_dir.parent.mkdir(parents=True, exist_ok=True)
        run([uv, "python", "install", python_version])
        run([uv, "venv", "--python", python_version, "--seed", str(env_dir)])
    run(
        [
            uv,
            "pip",
            "install",
            "--python",
            str(python),
            f"torch=={TORCH_VERSION}",
            f"torchaudio=={TORCH_VERSION}",
            "--index-url",
            TORCH_INDEX,
        ]
    )
    return python


def uv_install(
    python: Path,
    *packages: str,
    no_deps: bool = False,
    no_build_isolation: bool = False,
) -> None:
    uv = resolve_uv()
    command = [uv, "pip", "install", "--python", str(python)]
    if no_deps:
        command.append("--no-deps")
    if no_build_isolation:
        command.append("--no-build-isolation")
    command.extend(packages)
    run(command)


def download_snapshot(
    python: Path,
    *,
    repo_id: str,
    revision: str,
    target: Path,
    allow_patterns: list[str] | None = None,
) -> None:
    target.mkdir(parents=True, exist_ok=True)
    script = (
        "from huggingface_hub import snapshot_download; "
        f"snapshot_download(repo_id={repo_id!r}, revision={revision!r}, "
        f"local_dir={str(target)!r}, allow_patterns={allow_patterns!r})"
    )
    env = {**os.environ, "HF_HOME": str(HF_HOME), "HF_HUB_DISABLE_XET": "0"}
    run([str(python), "-c", script], env=env)


def download_modelscope_snapshot(python: Path, *, model_id: str, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    script = (
        "from modelscope import snapshot_download; "
        f"print(snapshot_download(model_id={model_id!r}, local_dir={str(target)!r}))"
    )
    run([str(python), "-c", script])


def verify_runtime(python: Path) -> dict[str, object]:
    script = (
        "import json, torch; "
        "print(json.dumps({'torch':torch.__version__,'cuda':str(torch.version.cuda),"
        "'cudaAvailable':torch.cuda.is_available(),"
        "'gpu':torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'}))"
    )
    completed = run([str(python), "-c", script], capture=True)
    payload = json.loads(completed.stdout.strip().splitlines()[-1])
    log(
        "Runtime ready: "
        f"torch={payload['torch']} cuda={payload['cuda']} "
        f"cudaAvailable={payload['cudaAvailable']} gpu={payload['gpu']}"
    )
    return payload


def write_manifest(key: str, payload: dict[str, object]) -> None:
    MANIFEST_ROOT.mkdir(parents=True, exist_ok=True)
    target = MANIFEST_ROOT / f"{key}.json"
    target.write_text(
        json.dumps(
            {
                **payload,
                "installedAt": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    log(f"Wrote manifest: {target}")


def setup_chatterbox() -> None:
    log("Setting up Chatterbox Multilingual V3")
    vendor = clone_pinned(
        "chatterbox",
        "https://github.com/resemble-ai/chatterbox.git",
        CHATTERBOX_CODE_REV,
    )
    perth = clone_pinned(
        "perth",
        "https://github.com/resemble-ai/Perth.git",
        PERTH_CODE_REV,
    )
    python = ensure_env("chatterbox", python_version="3.11")
    uv_install(
        python,
        "numpy==1.26.4",
        "librosa==0.11.0",
        "s3tokenizer",
        "transformers==5.2.0",
        "diffusers==0.29.0",
        "conformer==0.3.2",
        "safetensors==0.5.3",
        "spacy-pkuseg",
        "pykakasi==2.3.0",
        "pyloudnorm",
        "omegaconf",
        "soundfile>=0.13.1",
        "huggingface-hub>=0.30.2",
    )
    uv_install(python, "-e", str(perth), no_deps=True)
    uv_install(python, "-e", str(vendor), no_deps=True)
    model_dir = MODEL_ROOT / "chatterbox"
    download_snapshot(
        python,
        repo_id="ResembleAI/chatterbox",
        revision=CHATTERBOX_MODEL_REV,
        target=model_dir,
        allow_patterns=[
            "ve.pt",
            "t3_mtl23ls_v3.safetensors",
            "s3gen.pt",
            "grapheme_mtl_merged_expanded_v1.json",
            "conds.pt",
            "Cangjie5_TC.json",
        ],
    )
    runtime = verify_runtime(python)
    run(
        [
            str(python),
            "-c",
            "from chatterbox.mtl_tts import ChatterboxMultilingualTTS; "
            "print('chatterbox import ready')",
        ]
    )
    write_manifest(
        "chatterbox",
        {
            "model": "chatterbox_multilingual_v3",
            "repository": "https://github.com/resemble-ai/chatterbox.git",
            "codeRevision": CHATTERBOX_CODE_REV,
            "modelId": "ResembleAI/chatterbox",
            "modelRevision": CHATTERBOX_MODEL_REV,
            "modelDir": str(model_dir),
            "python": str(python),
            **runtime,
        },
    )


def setup_cosyvoice() -> None:
    log("Setting up Fun-CosyVoice 3.0 0.5B")
    vendor = clone_pinned(
        "cosyvoice",
        "https://github.com/FunAudioLLM/CosyVoice.git",
        COSYVOICE_CODE_REV,
        submodules=True,
    )
    python = ensure_env("cosyvoice", python_version="3.10")
    uv_install(
        python,
        "conformer==0.3.2",
        "diffusers==0.29.0",
        "gdown==5.1.0",
        "hydra-core==1.3.2",
        "HyperPyYAML==1.2.3",
        "inflect==7.3.1",
        "librosa==0.10.2",
        "lightning==2.2.4",
        "matplotlib==3.7.5",
        "modelscope==1.20.0",
        "networkx==3.1",
        "numpy==1.26.4",
        "omegaconf==2.3.0",
        "onnx==1.16.0",
        "onnxruntime==1.20.1",
        "protobuf==4.25.8",
        "pyarrow==18.1.0",
        "pydantic==2.7.0",
        "pyworld==0.3.4",
        "rich==13.7.1",
        "soundfile==0.12.1",
        "tensorboard==2.14.0",
        "transformers==4.51.3",
        "x-transformers==2.11.24",
        "wetext==0.0.4",
        "wget==3.2",
        "tqdm>=4.66",
        "pykakasi==2.3.0",
        "huggingface-hub>=0.30.2",
    )
    uv_install(python, "setuptools==80.9.0")
    uv_install(
        python,
        "openai-whisper==20231117",
        no_build_isolation=True,
    )
    model_dir = MODEL_ROOT / "cosyvoice"
    download_snapshot(
        python,
        repo_id="FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
        revision=COSYVOICE_MODEL_REV,
        target=model_dir,
    )
    wetext_dir = MODEL_ROOT / "wetext"
    download_modelscope_snapshot(
        python,
        model_id="pengzhendong/wetext",
        target=wetext_dir,
    )
    runtime = verify_runtime(python)
    import_probe = (
        "import sys; "
        f"sys.path.insert(0, {str(vendor)!r}); "
        f"sys.path.insert(0, {str(vendor / 'third_party' / 'Matcha-TTS')!r}); "
        "from cosyvoice.cli.cosyvoice import AutoModel; "
        "print('cosyvoice import ready')"
    )
    run([str(python), "-c", import_probe])
    write_manifest(
        "cosyvoice",
        {
            "model": "fun_cosyvoice3_0_5b",
            "repository": "https://github.com/FunAudioLLM/CosyVoice.git",
            "codeRevision": COSYVOICE_CODE_REV,
            "modelId": "FunAudioLLM/Fun-CosyVoice3-0.5B-2512",
            "modelRevision": COSYVOICE_MODEL_REV,
            "modelDir": str(model_dir),
            "wetextDir": str(wetext_dir),
            "python": str(python),
            "japaneseInput": "automatic_katakana_normalization",
            **runtime,
        },
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "models",
        nargs="*",
        choices=["chatterbox", "cosyvoice"],
        default=[],
    )
    args = parser.parse_args()
    targets = args.models or ["chatterbox", "cosyvoice"]

    for directory in (VENV_ROOT, VENDOR_ROOT, MODEL_ROOT, MANIFEST_ROOT, HF_HOME):
        directory.mkdir(parents=True, exist_ok=True)

    for target in targets:
        if target == "chatterbox":
            setup_chatterbox()
        elif target == "cosyvoice":
            setup_cosyvoice()
    log("Requested local expressive TTS setup completed")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr, flush=True)
        raise
