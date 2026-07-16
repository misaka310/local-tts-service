import path from "node:path";
import { copyFile, mkdir, rm } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { assertExistingFile, safeStemFromPath, statIfExists, truncateLog } from "../shared.js";
import { writeRvcLog } from "./artifact-store.js";

const execFileAsync = promisify(execFile);

export async function resolveDemucsPython(context, preferred) {
  const candidates = [preferred, context.defaults.demucsPython, context.defaults.fallbackDemucsPython].filter(Boolean);
  for (const candidate of candidates) if ((await statIfExists(candidate))?.isFile()) return candidate;
  throw new Error(`BGM・伴奏除去の実行環境が見つかりません: ${candidates.join(" | ")}`);
}

export async function runDemucsVocals(context, inputPath, outputPath, options, id, { exec = execFileAsync } = {}) {
  await assertExistingFile("external input audio", inputPath);
  const demucsPython = await resolveDemucsPython(context, options.demucsPython);
  const workDir = path.join(context.paths.demucsWorkDir, id);
  await rm(workDir, { recursive: true, force: true });
  await mkdir(workDir, { recursive: true });
  await mkdir(path.dirname(outputPath), { recursive: true });
  const args = ["-m", "demucs", "--two-stems=vocals", "-n", options.demucsModel, "-o", workDir, inputPath];
  const command = { command: demucsPython, args, cwd: context.repoRoot };
  const startedAt = new Date().toISOString();
  try {
    const { stdout, stderr } = await exec(command.command, command.args, { cwd: command.cwd, windowsHide: true, timeout: 20 * 60 * 1000, maxBuffer: 20 * 1024 * 1024 });
    const stemPath = path.join(workDir, options.demucsModel, safeStemFromPath(inputPath), "vocals.wav");
    await assertExistingFile("BGM・伴奏除去後の音声", stemPath);
    await copyFile(stemPath, outputPath);
    const result = { method: "demucs_vocals", command, stdout: truncateLog(stdout), stderr: truncateLog(stderr), stemPath, outputPath };
    await writeRvcLog(context, { ok: true, type: "demucs", startedAt, finishedAt: new Date().toISOString(), ...result });
    return result;
  } catch (error) {
    const stdout = truncateLog(error.stdout || ""); const stderr = truncateLog(error.stderr || error.message || "");
    await writeRvcLog(context, { ok: false, type: "demucs", startedAt, finishedAt: new Date().toISOString(), command, stdout, stderr, outputPath, error: error.message || String(error) });
    const wrapped = new Error(`BGM・伴奏除去に失敗しました: ${stderr || error.message || error}`); Object.assign(wrapped, { stdout, stderr, command }); throw wrapped;
  }
}
