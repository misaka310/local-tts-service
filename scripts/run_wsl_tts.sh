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
  orpheus_3b_asmr) ENV_KEY="orpheus_asmr" ;;
  ming_omni_tts_0_5b) ENV_KEY="ming_omni_tts" ;;
  *) echo "unsupported WSL TTS model: $MODEL" >&2; exit 2 ;;
esac

PYTHON="$HOME/.local/share/local-tts-service/venvs/$ENV_KEY/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  echo "WSL environment is not installed for $MODEL: $PYTHON" >&2
  exit 3
fi

export PYTHONPATH="$REPO_ROOT"
exec "$PYTHON" "$CLI" --request-json "$REQUEST_JSON" --output-path "$OUTPUT_PATH"
