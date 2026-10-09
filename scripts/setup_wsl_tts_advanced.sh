#!/usr/bin/env bash
set -euo pipefail
# Optional heavy models: never installed by the default 'all' setup.
KEY="${1:?usage: setup_wsl_tts_advanced.sh fish_s2_pro|indextts_2_5}"
BASE="${LOCAL_TTS_WSL_HOME:-$HOME/.local/share/local-tts-service}"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
mkdir -p "$BASE/venvs" "$BASE/vendors" "$BASE/models" "$BASE/manifests"
command -v uv >/dev/null || { echo "uv is missing" >&2; exit 2; }
command -v hf >/dev/null || { echo "Hugging Face CLI is missing" >&2; exit 2; }
# Optional heavy downloads and CUDA operations may not overlap.
LOCK_FILE="${LOCAL_AI_GPU_LOCK_FILE:-$HOME/.local/share/local-ai-gpu-workload.lock}"
mkdir -p "$(dirname "$LOCK_FILE")"
exec 9>"$LOCK_FILE"
flock -w 600 9 || {
    echo "Another guarded GPU setup/inference is active: $LOCK_FILE" >&2
    exit 5
}

case "$KEY" in
 fish_s2_pro)
    REPO="https://github.com/fishaudio/fish-speech.git"
    CODE_REV="214da3cd841bda85da2496b96cd3c4d7edb1337e"
    MODEL_ID="fishaudio/s2-pro"
    MODEL_REV="1de9996b6be38b745688de084d87a5633f714e4e"
    PYTHON_VERSION="3.12"
    ;;
 indextts_2_5)
    REPO="https://github.com/index-tts/index-tts.git"
    CODE_REV="ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c"
    MODEL_ID="IndexTeam/IndexTTS-2.5"
    MODEL_REV="c39ce5ba981572cb187443877ff559dfb246ce63"
    PYTHON_VERSION="3.11"
    ;;
 *) echo "Unknown optional TTS model: $KEY" >&2; exit 2 ;;
esac

VENDOR="$BASE/vendors/$KEY"
MODEL="$BASE/models/$KEY"
ENV="$BASE/venvs/$KEY"
MANIFEST="$BASE/manifests/$KEY.json"
if [[ ! -d "$VENDOR/.git" ]]; then
    git clone "$REPO" "$VENDOR"
fi
git -C "$VENDOR" fetch --depth 1 origin "$CODE_REV"
git -C "$VENDOR" checkout --detach "$CODE_REV"
uv python install "$PYTHON_VERSION"
# Never modify the already working Fish S1 or other model environments.
export UV_PROJECT_ENVIRONMENT="$ENV"
if [[ "$KEY" == "fish_s2_pro" ]]; then
    if [[ ! -f /usr/include/portaudio.h ]]; then
        echo "Fish S2 Pro needs WSL PortAudio/SoX/ffmpeg: install portaudio19-dev libsox-dev ffmpeg as root first" >&2
        exit 3
    fi
    (cd "$VENDOR" && uv sync --python "$PYTHON_VERSION" --extra cu128)
else
    (cd "$VENDOR" && uv sync --python "$PYTHON_VERSION" --frozen)
fi
mkdir -p "$MODEL"
HF_HUB_DISABLE_XET=1 hf download "$MODEL_ID" --revision "$MODEL_REV" --local-dir "$MODEL"
if [[ "$KEY" == "indextts_2_5" ]]; then
    "$ENV/bin/python" - "$VENDOR" "$MODEL" <<'PY'
import os, sys
vendor, model_dir = sys.argv[1:]
os.chdir(vendor)
sys.path.insert(0, vendor)
from indextts.utils.model_download import ensure_models_available
ensure_models_available(model_dir)
print("IndexTTS 2.5 auxiliary encoders and vocoder cached", flush=True)
PY
    for item in hf_cache/w2v-bert-2.0/config.json \
        hf_cache/semantic_codec_model.safetensors \
        hf_cache/campplus_cn_common.bin \
        hf_cache/bigvgan/config.json \
        hf_cache/bigvgan/bigvgan_generator.pt; do
        [[ -s "$MODEL/$item" ]] || { echo "IndexTTS auxiliary checkpoint missing: $item" >&2; exit 6; }
    done
else
    for item in codec.pth config.json model.safetensors.index.json; do
        [[ -s "$MODEL/$item" ]] || { echo "Fish S2 checkpoint missing: $item" >&2; exit 6; }
    done
fi
"$ENV/bin/python" - "$MANIFEST" "$KEY" "$REPO" "$CODE_REV" "$MODEL_ID" "$MODEL_REV" "$MODEL" <<'PY'
import datetime, json, pathlib, sys, torch
dst, key, repo, code, model_id, model_rev, model_dir = sys.argv[1:]
data = {
    "model": key, "repository": repo, "codeRevision": code,
    "modelId": model_id, "modelRevision": model_rev,
    "modelDir": model_dir, "python": sys.version.split()[0],
    "torch": torch.__version__,
    "installedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
}
pathlib.Path(dst).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
PY
echo "[DONE] $KEY ready at $MODEL"
