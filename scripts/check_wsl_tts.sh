#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ $# -ne 1 ]]; then
  echo "usage: check_wsl_tts.sh MODEL" >&2
  exit 2
fi

MODEL="$1"
BASE="${LOCAL_TTS_WSL_HOME:-$HOME/.local/share/local-tts-service}"
REQUIRE_TORCH="1"
REQUIRED_MODEL_EXTRA=""
IMPORT_MODULE_EXTRA=""

case "$MODEL" in
  sarashina2_2_tts)
    ENV_KEY="sarashina"
    CODE_REV="e0ac9c99160ea4bf8dde46892892c945e66fcc13"
    MODEL_REV="8d30bd523b1fa217ab0b4cd32c9275d4f222fbcd"
    REQUIRED_VENDOR="sarashina_tts/generate/generate.py"
    REQUIRED_MODEL="model.safetensors"
    IMPORT_MODULE="sarashina_tts"
    ;;
  fireredtts2)
    ENV_KEY="fireredtts2"
    CODE_REV="404f3f61d25bb4804859b588a6a734bf8468090c"
    MODEL_REV="4af3f5cc4963373b86b52d750220d4de85261f05"
    REQUIRED_VENDOR="fireredtts2/fireredtts2.py"
    REQUIRED_MODEL="llm_posttrain.pt"
    IMPORT_MODULE="fireredtts2"
    ;;
  t5gemma_tts_2b_2b)
    ENV_KEY="t5gemma"
    CODE_REV="c8722b37e1aca0e21f85185188755e164c316828"
    MODEL_REV="e548f8358891975e61d2107e3d7ccc47b1b7294e"
    REQUIRED_VENDOR="inference_commandline_hf.py"
    REQUIRED_MODEL="model.safetensors.index.json"
    IMPORT_MODULE="transformers"
    ;;
  fish_s1_mini)
    ENV_KEY="fish_s1_mini"
    CODE_REV="23a4beb06952a6cc29813851309184ec1c498cac"
    MODEL_REV="f4b445029346701e082b60bb63fcc2d1bb17a0e2"
    REQUIRED_VENDOR="fish_speech/models/text2semantic/inference.py"
    REQUIRED_MODEL="model.pth"
    IMPORT_MODULE="fish_speech"
    ;;
  orpheus_3b_asmr)
    ENV_KEY="orpheus_asmr"
    CODE_REV="ed126bea531ea9d53ef7564b00e8bc23f8f9aebe"
    MODEL_REV="22892bc82fc22d5db827b005db658e778dcf7847"
    REQUIRED_VENDOR="src/orpheus_cpp/model.py"
    REQUIRED_MODEL="orpheus-3b-asmr-q4_k_m.gguf"
    REQUIRED_MODEL_EXTRA="snac-decoder_model.onnx"
    IMPORT_MODULE="orpheus_cpp"
    IMPORT_MODULE_EXTRA="llama_cpp onnxruntime"
    REQUIRE_TORCH="0"
    ;;
  ming_omni_tts_0_5b)
    ENV_KEY="ming_omni_tts"
    CODE_REV="200a1562e33492e786c23174985bb14f8e012cc6"
    MODEL_REV="9154772e7fbc585907b6237e3190790676f28975"
    REQUIRED_VENDOR="cookbooks/test.py"
    REQUIRED_MODEL="model.safetensors"
    IMPORT_MODULE="transformers"
    ;;
  *)
    echo "未対応のWSL TTSモデルです: $MODEL" >&2
    exit 2
    ;;
esac

PYTHON="$BASE/venvs/$ENV_KEY/bin/python"
VENDOR="$BASE/vendors/$ENV_KEY"
MODEL_DIR="$BASE/models/$ENV_KEY"
MANIFEST="$BASE/manifests/$ENV_KEY.json"

[[ -x "$PYTHON" ]] || { echo "WSLの専用Python環境が未導入です: $PYTHON" >&2; exit 3; }
[[ -f "$VENDOR/$REQUIRED_VENDOR" ]] || { echo "公式コードの実行入口がありません: $VENDOR/$REQUIRED_VENDOR" >&2; exit 4; }
[[ -f "$MODEL_DIR/$REQUIRED_MODEL" ]] || { echo "モデル重みがありません: $MODEL_DIR/$REQUIRED_MODEL" >&2; exit 5; }
if [[ -n "$REQUIRED_MODEL_EXTRA" && ! -f "$MODEL_DIR/$REQUIRED_MODEL_EXTRA" ]]; then
  echo "モデル依存ファイルがありません: $MODEL_DIR/$REQUIRED_MODEL_EXTRA" >&2
  exit 5
fi
[[ -f "$MANIFEST" ]] || { echo "固定revisionの導入記録がありません: $MANIFEST" >&2; exit 6; }

ACTUAL_CODE_REV="$(git -C "$VENDOR" rev-parse HEAD 2>/dev/null || true)"
[[ "$ACTUAL_CODE_REV" == "$CODE_REV" ]] || {
  echo "公式コードrevisionが不一致です: expected=$CODE_REV actual=${ACTUAL_CODE_REV:-unknown}" >&2
  exit 7
}

"$PYTHON" - "$MANIFEST" "$MODEL_REV" "$IMPORT_MODULE" "$REQUIRE_TORCH" "$IMPORT_MODULE_EXTRA" <<'PY'
import importlib.util
import json
from pathlib import Path
import sys

manifest_path = Path(sys.argv[1])
expected_model_revision = sys.argv[2]
module_name = sys.argv[3]
require_torch = sys.argv[4] == "1"
extra_module_names = sys.argv[5].split()
payload = json.loads(manifest_path.read_text(encoding="utf-8"))
actual_model_revision = str(payload.get("modelRevision") or "")
if actual_model_revision != expected_model_revision:
    raise SystemExit(
        f"モデルrevisionが不一致です: expected={expected_model_revision} actual={actual_model_revision or '未記録'}"
    )
if require_torch and importlib.util.find_spec("torch") is None:
    raise SystemExit("専用Python環境にtorchがありません")
for required_module in [module_name, *extra_module_names]:
    if importlib.util.find_spec(required_module) is None:
        raise SystemExit(f"専用Python環境に必要なモジュールがありません: {required_module}")
PY

if [[ "$MODEL" == "t5gemma_tts_2b_2b" ]]; then
  "$PYTHON" "$SCRIPT_DIR/t5gemma_offline_infer.py" --check-cache --model-dir "$MODEL_DIR"
fi

printf '利用可能: %s (%s)\n' "$MODEL" "$ENV_KEY"
