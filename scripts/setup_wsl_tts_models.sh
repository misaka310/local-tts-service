#!/usr/bin/env bash
set -euo pipefail

BASE="${LOCAL_TTS_WSL_HOME:-$HOME/.local/share/local-tts-service}"
VENV_ROOT="$BASE/venvs"
VENDOR_ROOT="$BASE/vendors"
MODEL_ROOT="$BASE/models"
LOG_ROOT="$BASE/logs"
MANIFEST_ROOT="$BASE/manifests"
TARGETS=("${@:-all}")

SARASHINA_REV="e0ac9c99160ea4bf8dde46892892c945e66fcc13"
FIRERED_REV="404f3f61d25bb4804859b588a6a734bf8468090c"
T5GEMMA_REV="c8722b37e1aca0e21f85185188755e164c316828"
FISH_REV="23a4beb06952a6cc29813851309184ec1c498cac"
ORPHEUS_CPP_REV="ed126bea531ea9d53ef7564b00e8bc23f8f9aebe"
MING_REV="200a1562e33492e786c23174985bb14f8e012cc6"
SARASHINA_MODEL_REV="8d30bd523b1fa217ab0b4cd32c9275d4f222fbcd"
FIRERED_MODEL_REV="4af3f5cc4963373b86b52d750220d4de85261f05"
T5GEMMA_MODEL_REV="e548f8358891975e61d2107e3d7ccc47b1b7294e"
FISH_MODEL_REV="f4b445029346701e082b60bb63fcc2d1bb17a0e2"
ORPHEUS_MODEL_REV="22892bc82fc22d5db827b005db658e778dcf7847"
ORPHEUS_MODEL_REPO="HummingbirdCake/Orpheus-3B-ASMR-Q4_K_M-GGUF"
ORPHEUS_MODEL_FILE="orpheus-3b-asmr-q4_k_m.gguf"
ORPHEUS_SNAC_REV="e0b0016bc39c9d144e51aba2f275f59b7a6874d6"
ORPHEUS_SNAC_REPO="onnx-community/snac_24khz-ONNX"
ORPHEUS_SNAC_FILE="onnx/decoder_model.onnx"
MING_MODEL_REV="9154772e7fbc585907b6237e3190790676f28975"

mkdir -p "$VENV_ROOT" "$VENDOR_ROOT" "$MODEL_ROOT" "$LOG_ROOT" "$MANIFEST_ROOT"
export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

log() { printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*"; }
want() {
  local key="$1"
  local target
  for target in "${TARGETS[@]}"; do
    [[ "$target" == "all" || "$target" == "$key" ]] && return 0
  done
  return 1
}
want_asmr() {
  local key="$1"
  local target
  for target in "${TARGETS[@]}"; do
    [[ "$target" == "asmr" || "$target" == "$key" ]] && return 0
  done
  return 1
}

if ! command -v hf >/dev/null 2>&1; then
  echo "Hugging Face CLI is missing. Run: curl -LsSf https://hf.co/cli/install.sh | bash" >&2
  exit 2
fi
if ! hf auth whoami >/dev/null 2>&1; then
  echo "Hugging Face login is missing. Run: hf auth login" >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  log "Installing uv in the WSL user account"
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi
uv python install 3.11

clone_pinned() {
  local name="$1" url="$2" revision="$3"
  local target="$VENDOR_ROOT/$name"
  if [[ ! -d "$target/.git" ]]; then
    log "Cloning $name"
    git clone "$url" "$target"
  fi
  git -C "$target" fetch --depth 1 origin "$revision"
  git -C "$target" checkout --detach "$revision"
}

create_env() {
  local key="$1"
  local env_dir="$VENV_ROOT/$key"
  if [[ ! -x "$env_dir/bin/python" ]]; then
    log "Creating Python 3.11 environment: $key" >&2
    uv venv --python 3.11 --seed "$env_dir" >&2
  fi
  printf '%s' "$env_dir/bin/python"
}

create_env_for_python() {
  local key="$1" version="$2"
  local env_dir="$VENV_ROOT/$key"
  if [[ -x "$env_dir/bin/python" ]]; then
    local current_version
    current_version="$($env_dir/bin/python -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    if [[ "$current_version" != "$version" ]]; then
      log "Recreating $key for Python $version (was $current_version)" >&2
      rm -rf "$env_dir"
    fi
  fi
  if [[ ! -x "$env_dir/bin/python" ]]; then
    log "Creating Python $version environment: $key" >&2
    uv venv --python "$version" --seed "$env_dir" >&2
  fi
  printf '%s' "$env_dir/bin/python"
}

install_torch_28() {
  local python="$1"
  uv pip install --python "$python" \
    torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 \
    --index-url https://download.pytorch.org/whl/cu128
}

install_ming_dependencies() {
  local python="$1" vendor="$2"
  local filtered
  filtered="$(mktemp)"
  "$python" - "$vendor/requirements.txt" "$filtered" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text(encoding="utf-8").splitlines()
blocked = ("torch==", "torchaudio==", "torchvision==", "grouped_gemm==")
kept = [line for line in source if line.strip() and not line.strip().startswith(blocked)]
Path(sys.argv[2]).write_text("\n".join(kept) + "\n", encoding="utf-8")
PY
  install_torch_28 "$python"
  uv pip install --python "$python" --no-build-isolation -r "$filtered"
  uv pip install --python "$python" inflect onnxruntime-gpu loguru
  rm -f "$filtered"
}

download_model() {
  local repo_id="$1" revision="$2" target="$3"
  mkdir -p "$target"
  log "Downloading $repo_id at $revision"
  HF_HUB_DISABLE_XET=1 hf download "$repo_id" --revision "$revision" --local-dir "$target"
}

cache_t5gemma_dependencies() {
  local python="$1" model_dir="$2"
  local config_path="$model_dir/config.json"
  [[ -f "$config_path" ]] || { echo "T5Gemma config is missing: $config_path" >&2; return 1; }
  local dependencies=()
  mapfile -t dependencies < <("$python" - "$config_path" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
text_key = "text_" + "tokenizer_name"
text_repo = str(payload.get(text_key) or payload.get("t5gemma_model_name") or "").strip()
codec_repo = str(payload.get("xcodec2_model_name") or "").strip()
if not text_repo or not codec_repo:
    raise SystemExit("T5Gemma dependency ids are missing from config.json")
print(text_repo)
print(codec_repo)
PY
  )
  [[ ${#dependencies[@]} -eq 2 ]] || { echo "T5Gemma dependency ids could not be resolved" >&2; return 1; }
  local text_dependency="${dependencies[0]}" codec_dependency="${dependencies[1]}"
  log "Caching T5Gemma text tokenizer dependency: $text_dependency"
  HF_HUB_DISABLE_XET=1 hf download "$text_dependency" \
    --include 'tokenizer*' 'special_tokens_map.json' 'added_tokens.json' '*.model'
  log "Caching T5Gemma codec dependency: $codec_dependency"
  HF_HUB_DISABLE_XET=1 hf download "$codec_dependency"
}

write_manifest() {
  local key="$1" repo="$2" code_revision="$3" model_id="$4" model_revision="$5" model_dir="$6" python="$7"
  local torch_version
  torch_version="$($python - <<'PY'
import importlib.util
if importlib.util.find_spec("torch") is None:
    print("not-installed")
else:
    import torch
    print(torch.__version__)
PY
)"
  cat > "$MANIFEST_ROOT/$key.json" <<EOF
{
  "model": "$key",
  "repository": "$repo",
  "codeRevision": "$code_revision",
  "modelId": "$model_id",
  "modelRevision": "$model_revision",
  "modelDir": "$model_dir",
  "python": "$($python --version 2>&1)",
  "torch": "$torch_version",
  "installedAt": "$(date --iso-8601=seconds)"
}
EOF
}

setup_sarashina() {
  local key="sarashina" vendor="$VENDOR_ROOT/sarashina" model="$MODEL_ROOT/sarashina"
  clone_pinned "$key" "https://github.com/sbintuitions/sarashina2.2-tts.git" "$SARASHINA_REV"
  local python; python="$(create_env "$key")"
  install_torch_28 "$python"
  uv pip install --python "$python" -e "$vendor"
  download_model "sbintuitions/sarashina2.2-tts" "$SARASHINA_MODEL_REV" "$model"
  write_manifest "$key" "https://github.com/sbintuitions/sarashina2.2-tts.git" "$SARASHINA_REV" "sbintuitions/sarashina2.2-tts" "$SARASHINA_MODEL_REV" "$model" "$python"
}

setup_firered() {
  local key="fireredtts2" vendor="$VENDOR_ROOT/fireredtts2" model="$MODEL_ROOT/fireredtts2"
  clone_pinned "$key" "https://github.com/FireRedTeam/FireRedTTS2.git" "$FIRERED_REV"
  local python; python="$(create_env "$key")"
  install_torch_28 "$python"
  uv pip install --python "$python" -e "$vendor"
  uv pip install --python "$python" -r "$vendor/requirements.txt"
  uv pip install --python "$python" transformers==4.57.3 'huggingface_hub<1.0'
  download_model "FireRedTeam/FireRedTTS2" "$FIRERED_MODEL_REV" "$model"
  write_manifest "$key" "https://github.com/FireRedTeam/FireRedTTS2.git" "$FIRERED_REV" "FireRedTeam/FireRedTTS2" "$FIRERED_MODEL_REV" "$model" "$python"
}

setup_t5gemma() {
  local key="t5gemma" vendor="$VENDOR_ROOT/t5gemma" model="$MODEL_ROOT/t5gemma"
  clone_pinned "$key" "https://github.com/Aratako/T5Gemma-TTS.git" "$T5GEMMA_REV"
  local python; python="$(create_env "$key")"
  install_torch_28 "$python"
  uv pip install --python "$python" -r "$vendor/requirements.txt"
  download_model "Aratako/T5Gemma-TTS-2b-2b" "$T5GEMMA_MODEL_REV" "$model"
  cache_t5gemma_dependencies "$python" "$model"
  write_manifest "$key" "https://github.com/Aratako/T5Gemma-TTS.git" "$T5GEMMA_REV" "Aratako/T5Gemma-TTS-2b-2b" "$T5GEMMA_MODEL_REV" "$model" "$python"
}

setup_fish() {
  local key="fish_s1_mini" vendor="$VENDOR_ROOT/fish_s1_mini" model="$MODEL_ROOT/fish_s1_mini"
  clone_pinned "$key" "https://github.com/fishaudio/fish-speech.git" "$FISH_REV"
  local python; python="$(create_env "$key")"
  install_torch_28 "$python"
  uv pip install --python "$python" \
    'numpy<=1.26.4' 'transformers>=4.45.2,<4.58' datasets==2.18.0 'lightning>=2.1.0' 'hydra-core>=1.3.2' \
    natsort einops librosa rich loguru loralib pyrootutils 'vector_quantize_pytorch==1.14.24' resampy 'einx[torch]==0.2.2' \
    zstandard pydub ormsgpack 'tiktoken>=0.8.0' pydantic==2.9.2 cachetools click safetensors soundfile
  uv pip install --python "$python" --no-deps -e "$vendor"
  download_model "fishaudio/s1-mini" "$FISH_MODEL_REV" "$model"
  write_manifest "$key" "https://github.com/fishaudio/fish-speech.git" "$FISH_REV" "fishaudio/s1-mini" "$FISH_MODEL_REV" "$model" "$python"
}

setup_orpheus_asmr() {
  local key="orpheus_asmr" vendor="$VENDOR_ROOT/orpheus_asmr" model="$MODEL_ROOT/orpheus_asmr"
  local repo="https://github.com/freddyaboulton/orpheus-cpp.git"
  if [[ -d "$vendor/.git" ]]; then
    local current_origin
    current_origin="$(git -C "$vendor" remote get-url origin 2>/dev/null || true)"
    if [[ "$current_origin" != "$repo" ]]; then
      log "Replacing legacy Orpheus vendor: ${current_origin:-unknown}"
      rm -rf "$vendor"
    fi
  fi
  clone_pinned "$key" "$repo" "$ORPHEUS_CPP_REV"
  local python; python="$(create_env_for_python "$key" 3.11)"
  uv pip install --python "$python" -e "$vendor"
  uv pip install --python "$python" llama-cpp-python \
    --extra-index-url https://abetlen.github.io/llama-cpp-python/whl/cpu
  if [[ -d "$model" && ! -f "$model/$ORPHEUS_MODEL_FILE" ]]; then
    log "Replacing legacy Orpheus model directory with GGUF runtime files"
    rm -rf "$model"
  fi
  mkdir -p "$model"
  log "Downloading $ORPHEUS_MODEL_REPO at $ORPHEUS_MODEL_REV"
  HF_HUB_DISABLE_XET=1 hf download "$ORPHEUS_MODEL_REPO" "$ORPHEUS_MODEL_FILE" \
    --revision "$ORPHEUS_MODEL_REV" --local-dir "$model"
  log "Downloading $ORPHEUS_SNAC_REPO at $ORPHEUS_SNAC_REV"
  local snac_source
  snac_source="$(HF_HUB_DISABLE_XET=1 hf download "$ORPHEUS_SNAC_REPO" "$ORPHEUS_SNAC_FILE" --revision "$ORPHEUS_SNAC_REV" --quiet)"
  cp "$snac_source" "$model/snac-decoder_model.onnx"
  write_manifest "$key" "$repo" "$ORPHEUS_CPP_REV" "$ORPHEUS_MODEL_REPO" "$ORPHEUS_MODEL_REV" "$model" "$python"
}

setup_ming_omni_tts() {
  local key="ming_omni_tts" vendor="$VENDOR_ROOT/ming_omni_tts" model="$MODEL_ROOT/ming_omni_tts"
  clone_pinned "$key" "https://github.com/inclusionAI/Ming-omni-tts.git" "$MING_REV"
  local python; python="$(create_env "$key")"
  install_ming_dependencies "$python" "$vendor"
  download_model "inclusionAI/Ming-omni-tts-0.5B" "$MING_MODEL_REV" "$model"
  write_manifest "$key" "https://github.com/inclusionAI/Ming-omni-tts.git" "$MING_REV" "inclusionAI/Ming-omni-tts-0.5B" "$MING_MODEL_REV" "$model" "$python"
}

if want sarashina; then setup_sarashina; fi
if want fireredtts2; then setup_firered; fi
if want t5gemma; then setup_t5gemma; fi
if want fish_s1_mini; then setup_fish; fi
if want_asmr orpheus_asmr; then setup_orpheus_asmr; fi
if want_asmr ming_omni_tts; then setup_ming_omni_tts; fi

log "Requested WSL TTS model setup completed"
