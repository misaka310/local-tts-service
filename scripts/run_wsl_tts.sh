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
if [[ "$MODEL" == "fish_s2_pro" || "$MODEL" == "indextts_2_5" ]]; then
  if [[ -n "${LOCAL_TTS_WSL_CUDA_VISIBLE_DEVICES:-}" ]]; then
    export CUDA_VISIBLE_DEVICES="$LOCAL_TTS_WSL_CUDA_VISIBLE_DEVICES"
  elif [[ -z "${CUDA_VISIBLE_DEVICES:-}" ]]; then
    BEST_GPU="$("$PYTHON" - <<'PY'
import torch
best_index = None
best_free = -1
for index in range(torch.cuda.device_count()):
    with torch.cuda.device(index):
        free_bytes, _ = torch.cuda.mem_get_info()
    if free_bytes > best_free:
        best_free = free_bytes
        best_index = index
if best_index is not None:
    print(best_index)
PY
)"
    if [[ -n "$BEST_GPU" ]]; then
      export CUDA_VISIBLE_DEVICES="$BEST_GPU"
      echo "[INFO] $MODEL selected CUDA device $BEST_GPU (most free VRAM in PyTorch order)" >&2
    fi
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