from __future__ import annotations

import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


LOG_PATH = ROOT_DIR / "runtime" / "logs" / "qwen3_tts_clone_0_6b_diag.log"
MODEL_PATH = ROOT_DIR / "runtime" / "vendor" / "qwen3-tts" / "Qwen3-TTS-12Hz-0.6B-Base"
REFERENCE_DIR = ROOT_DIR / "reference" / "voices" / "sample_neutral"
OUTPUT_PATH = ROOT_DIR / "runtime" / "audio" / "qwen3_tts_probe" / "qwen3_tts_clone_0_6b__sample_neutral__seed1001.wav"
TEXT = "どうも、ドチタオです"
LANGUAGE = "Japanese"
SEED = 1001


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="milliseconds")


def log(message: str) -> None:
    line = f"[{now_iso()}] {message}"
    print(line, flush=True)
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with LOG_PATH.open("a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def sync_cuda(torch_module) -> None:  # type: ignore[no-untyped-def]
    if torch_module.cuda.is_available():
        torch_module.cuda.synchronize()


def main() -> int:
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("", encoding="utf-8")

    t0 = time.perf_counter()
    log("start import")
    import soundfile as sf  # noqa: PLC0415
    import torch  # noqa: PLC0415
    from qwen_tts import Qwen3TTSModel  # noqa: PLC0415

    log(
        "done import "
        f"elapsed={time.perf_counter() - t0:.3f}s "
        f"torch={torch.__version__} "
        f"cuda_available={torch.cuda.is_available()} "
        f"torch_cuda={torch.version.cuda}"
    )
    if torch.cuda.is_available():
        log(f"gpu_name={torch.cuda.get_device_name(0)}")

    if not MODEL_PATH.is_dir():
        log(f"missing model path: {MODEL_PATH}")
        return 1

    ref_audio = REFERENCE_DIR / "voice.wav"
    ref_text = REFERENCE_DIR / "voice.txt"
    if not ref_audio.is_file():
        log(f"missing reference audio: {ref_audio}")
        return 1
    if not ref_text.is_file():
        log(f"missing reference text: {ref_text}")
        return 1

    load_t0 = time.perf_counter()
    log("start load model")
    model = Qwen3TTSModel.from_pretrained(
        str(MODEL_PATH),
        device_map="cuda:0" if torch.cuda.is_available() else "cpu",
        dtype=torch.bfloat16 if torch.cuda.is_available() else torch.float32,
    )
    sync_cuda(torch)
    model_device = getattr(model, "device", None)
    model_dtype = getattr(getattr(model, "model", None), "dtype", None)
    log(
        "done load model "
        f"elapsed={time.perf_counter() - load_t0:.3f}s "
        f"model_device={model_device} "
        f"model_dtype={model_dtype}"
    )

    ref_t0 = time.perf_counter()
    log("start load reference")
    ref_text_value = ref_text.read_text(encoding="utf-8-sig").strip()
    prompt = model.create_voice_clone_prompt(
        ref_audio=str(ref_audio),
        ref_text=ref_text_value,
        x_vector_only_mode=False,
    )
    sync_cuda(torch)
    log(
        "done load reference "
        f"elapsed={time.perf_counter() - ref_t0:.3f}s "
        f"prompt_items={len(prompt)}"
    )

    gen_t0 = time.perf_counter()
    log("start generate")
    wavs, sample_rate = model.generate_voice_clone(
        text=TEXT,
        language=LANGUAGE,
        voice_clone_prompt=prompt,
        seed=SEED,
        non_streaming_mode=True,
    )
    sync_cuda(torch)
    log(
        "done generate "
        f"elapsed={time.perf_counter() - gen_t0:.3f}s "
        f"sample_rate={sample_rate} "
        f"num_wavs={len(wavs)} "
        f"samples={len(wavs[0]) if wavs else 0}"
    )

    save_t0 = time.perf_counter()
    log("start save wav")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    sf.write(OUTPUT_PATH, wavs[0], sample_rate)
    log(
        "done save wav "
        f"elapsed={time.perf_counter() - save_t0:.3f}s "
        f"output={OUTPUT_PATH} "
        f"bytes={OUTPUT_PATH.stat().st_size}"
    )
    log(f"total_elapsed={time.perf_counter() - t0:.3f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
