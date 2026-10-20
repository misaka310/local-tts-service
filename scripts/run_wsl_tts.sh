#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 5 ]]; then
  echo "usage: run_wsl_tts.sh MODEL REPO_ROOT CLI REQUEST_JSON OUTPUT_PATH" >&2
  exit 2
fi

MODEL="$1"
REPO_ROOT="$2"
CLI="$3"
REQUEST_JSON="$4"
OUTPUT_PATH="$5"

case "$MODEL" in
  sarashina2_2_tts) ENV_KEY="sarashina" ;;
  fireredtts2) ENV_KEY="fireredtts2" ;;
  t5gemma_tts_2b_2b) ENV_KEY="t5gemma" ;;
  fish_s1_mini) ENV_KEY="fish_s1_mini" ;;
  fish_s2_pro) ENV_KEY="fish_s2_pro" ;;
  indextts_2_5) ENV_KEY="indextts_2_5" ;;
  orpheus_3b_asmr) ENV_KEY="orpheus_asmr" ;;
  ming_omni_tts_0_5b) ENV_KEY="ming_omni_tts" ;;
  *) echo "unsupported WSL TTS model: $MODEL" >&2; exit 2 ;;
esac

if [[ "$MODEL" == "fish_s2_pro" || "$MODEL" == "indextts_2_5" ]]; then
  LOCK_FILE="${LOCAL_AI_GPU_LOCK_FILE:-$HOME/.local/share/local-ai-gpu-workload.lock}"
  mkdir -p "$(dirname "$LOCK_FILE")"
  exec 9>"$LOCK_FILE"
  flock -n 9 || {
    echo "Another guarded GPU setup/inference is active: $LOCK_FILE" >&2
    exit 5
  }
fi
PYTHON="$HOME/.local/share/local-tts-service/venvs/$ENV_KEY/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "WSL environment is not installed for $MODEL: $PYTHON" >&2
  exit 3
fi

export PYTHONPATH="$REPO_ROOT"
if [[ "$MODEL" == "orpheus_3b_asmr" ]]; then
  unset CUDA_VISIBLE_DEVICES
  echo "[INFO] $MODEL uses its CPU-only llama.cpp runtime; CUDA selection is skipped" >&2
elif [[ -n "${LOCAL_TTS_WSL_CUDA_VISIBLE_DEVICES:-}" ]]; then
  export CUDA_VISIBLE_DEVICES="${LOCAL_TTS_WSL_CUDA_VISIBLE_DEVICES}"
elif [[ -n "${CUDA_VISIBLE_DEVICES:-}" ]]; then
  echo "[INFO] $MODEL preserves inherited CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES" >&2
else
  BEST_GPU="$("$PYTHON" - <<'PY'
import torch
best_index = None
best_ratio = -1.0
for index in range(torch.cuda.device_count()):
    with torch.cuda.device(index):
        free_bytes, total_bytes = torch.cuda.mem_get_info()
    ratio = free_bytes / total_bytes if total_bytes > 0 else -1.0
    if ratio > best_ratio:
        best_ratio = ratio
        best_index = index
if best_index is not None:
    print(f"{best_index},{best_ratio:.4f}")
PY
)"
  if [[ -n "$BEST_GPU" ]]; then
    BEST_GPU_INDEX="${BEST_GPU%%,*}"
    BEST_GPU_RATIO="${BEST_GPU#*,}"
    export CUDA_VISIBLE_DEVICES="$BEST_GPU_INDEX"
    echo "[INFO] $MODEL selected CUDA device $BEST_GPU_INDEX (highest free-VRAM ratio: $BEST_GPU_RATIO)" >&2
  fi
fi
set +e
"$PYTHON" "$CLI" --request-json "$REQUEST_JSON" --output-path "$OUTPUT_PATH"
STATUS=$?
set -e
if [[ "$STATUS" -ne 0 ]]; then
  echo "[ERROR] $MODEL python exited with status $STATUS" >&2
fi
exit "$STATUS"
