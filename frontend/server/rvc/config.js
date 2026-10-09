import path from "node:path";
import { fileURLToPath } from "node:url";

const moduleDir = path.dirname(fileURLToPath(import.meta.url));
export const defaultRepoRoot = path.resolve(moduleDir, "..", "..", "..");

export function createRvcContext({ repoRoot = defaultRepoRoot, env = process.env, outputDir } = {}) {
  const root = path.resolve(repoRoot);
  const resolvedOutputDir = path.resolve(outputDir || path.join(root, "runtime", "outputs", "rvc"));
  const rvcRoot = String(env.LOCAL_TTS_RVC_ROOT || "").trim();
  const paths = {
    outputDir: resolvedOutputDir,
    inputDir: path.join(resolvedOutputDir, "inputs"),
    intermediateDir: path.join(resolvedOutputDir, "intermediate"),
    convertedDir: path.join(resolvedOutputDir, "converted"),
    inputCleanDir: path.join(resolvedOutputDir, "input_cleaned"),
    demucsWorkDir: path.join(resolvedOutputDir, "demucs_work"),
    logPath: path.join(root, "runtime", "logs", "rvc-convert.log"),
  };
  return {
    repoRoot: root,
    paths,
    defaults: {
      pythonPath: String(env.LOCAL_TTS_RVC_PYTHON || (rvcRoot ? path.join(rvcRoot, ".venv", "Scripts", "python.exe") : "")).trim(),
      cwd: String(env.LOCAL_TTS_RVC_CWD || (rvcRoot ? path.join(rvcRoot, "vendor", "rvc") : "")).trim(),
      modelPath: String(env.LOCAL_TTS_RVC_MODEL_PATH || "").trim(),
      indexPath: String(env.LOCAL_TTS_RVC_INDEX_PATH || "").trim(),
      indexRate: 0.35,
      f0method: "rmvpe",
      f0upKey: 0,
      filterRadius: 3,
      resampleSr: 0,
      rmsMixRate: 1,
      protect: 0.33,
      timeoutMs: 10 * 60 * 1000,
      inputSource: "mic",
      externalAudioPath: String(env.LOCAL_TTS_RVC_EXTERNAL_AUDIO_PATH || "").trim(),
      cleanExternalAudio: false,
      demucsPython: path.join(root, "runtime", "venv-demucs", "Scripts", "python.exe"),
      fallbackDemucsPython: path.join(root, "runtime", "vendor", "GPT-SoVITS", ".venv", "Scripts", "python.exe"),
      demucsModel: "htdemucs_ft",
    },
  };
}
