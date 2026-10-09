import path from "node:path";
import { copyFile, mkdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { assertExistingDirectory, assertExistingFile, safeStemFromPath, statIfExists, truncateLog } from "../shared.js";
import { writeRvcLog } from "./artifact-store.js";

const execFileAsync = promisify(execFile);

export function buildRvcCommand(settings, params, inputPath, outputPath) {
  return { command: settings.pythonPath, args: [".\\tools\\infer_cli.py", "--input_path", inputPath, "--opt_path", outputPath, "--model_name", path.basename(params.modelPath), "--index_path", params.indexPath, "--index_rate", String(params.indexRate), "--f0method", params.f0method, "--f0up_key", String(params.f0upKey), "--filter_radius", String(params.filterRadius), "--resample_sr", String(params.resampleSr), "--rms_mix_rate", String(params.rmsMixRate), "--protect", String(params.protect)], cwd: settings.cwd };
}

export async function stageRvcModelForRuntime(context, modelPath) {
  const sourcePath = path.resolve(modelPath);
  const weightsDir = path.join(context.defaults.cwd, "assets", "weights");
  const currentWeightsDir = path.resolve(path.dirname(sourcePath));
  if (currentWeightsDir.toLowerCase() === path.resolve(weightsDir).toLowerCase()) return sourcePath;

  await mkdir(weightsDir, { recursive: true });
  const parentStem = safeStemFromPath(path.dirname(sourcePath));
  const targetName = `${parentStem}-${path.basename(sourcePath)}`;
  const targetPath = path.join(weightsDir, targetName);
  const sourceStat = await statIfExists(sourcePath);
  const targetStat = await statIfExists(targetPath);
  if (!sourceStat?.isFile()) throw new Error(`RVC model not found: ${sourcePath}`);
  if (!targetStat?.isFile() || targetStat.size !== sourceStat.size || targetStat.mtimeMs < sourceStat.mtimeMs) {
    await copyFile(sourcePath, targetPath);
  }
  return targetPath;
}

export async function runRvcConvert(context, params, inputPath, outputPath, { exec = execFileAsync } = {}) {
  await assertExistingFile("RVC python", context.defaults.pythonPath);
  await assertExistingDirectory("RVC cwd", context.defaults.cwd);
  await assertExistingFile("RVC model", params.modelPath);
  await assertExistingFile("RVC index", params.indexPath);
  await assertExistingFile("RVC input", inputPath);
  const runtimeModelPath = await stageRvcModelForRuntime(context, params.modelPath);
  const command = buildRvcCommand(context.defaults, { ...params, modelPath: runtimeModelPath }, inputPath, outputPath);
  const startedAt = new Date().toISOString();
  try {
    const { stdout, stderr } = await exec(command.command, command.args, { cwd: command.cwd, windowsHide: true, timeout: context.defaults.timeoutMs, maxBuffer: 20 * 1024 * 1024 });
    await assertExistingFile("RVC output", outputPath);
    const result = { command, stdout: truncateLog(stdout), stderr: truncateLog(stderr) };
    await writeRvcLog(context, { ok: true, startedAt, finishedAt: new Date().toISOString(), ...result, outputPath }); return result;
  } catch (error) {
    const stdout = truncateLog(error.stdout || ""); const stderr = truncateLog(error.stderr || error.message || "");
    await writeRvcLog(context, { ok: false, startedAt, finishedAt: new Date().toISOString(), command, stdout, stderr, outputPath, error: error.message || String(error) });
    const wrapped = new Error(`RVC変換に失敗しました: ${stderr || error.message || error}`); Object.assign(wrapped, { stdout, stderr, command }); throw wrapped;
  }
}
