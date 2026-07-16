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
SARASHINA_MODEL_REV="8d30bd523b1fa217ab0b4cd32c9275d4f222fbcd"
FIRERED_MODEL_REV="4af3f5cc4963373b86b52d750220d4de85261f05"
T5GEMMA_MODEL_REV="e548f8358891975e61d2107e3d7ccc47b1b7294e"
FISH_MODEL_REV="f4b445029346701e082b60bb63fcc2d1bb17a0e2"

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

install_torch_28() {
  local python="$1"
  uv pip install --python "$python" \
    torch==2.8.0 torchaudio==2.8.0 torchvision==0.23.0 \
    --index-url https://download.pytorch.org/whl/cu128
}

download_model() {
  local repo_id="$1" revision="$2" target="$3"
  mkdir -p "$target"
  log "Downloading $repo_id at $revision"
  HF_HUB_DISABLE_XET=1 hf download "$repo_id" --revision "$revision" --local-dir "$target"
}

write_manifest() {
  local key="$1" repo="$2" code_revision="$3" model_id="$4" model_revision="$5" model_dir="$6" python="$7"
  local torch_version
  torch_version="$($python -c 'import torch; print(torch.__version__)')"
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

if want sarashina; then setup_sarashina; fi
if want fireredtts2; then setup_firered; fi
if want t5gemma; then setup_t5gemma; fi
if want fish_s1_mini; then setup_fish; fi

log "Requested WSL TTS model setup completed"
