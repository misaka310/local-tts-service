import path from "node:path";
import { appendFile, copyFile, mkdir, writeFile } from "node:fs/promises";
import { compactTimestampStem, shortRandomId, statIfExists, assertExistingFile } from "../shared.js";
import { convertAudioFileToWav, denoiseVoiceFile, normalizeRecordingDataUrl, readWaveDurationSec, recordingExtFromMime } from "../audio-utils.js";

export function ensureSafeRvcFilename(filename) {
  const safe = String(filename || "").trim();
  if (!safe || safe.includes("/") || safe.includes("\\") || safe.includes("..") || !safe.toLowerCase().endsWith(".wav")) throw new Error("invalid rvc audio filename");
  return safe;
}

export function resolveRvcAudioPath(context, kind, filename) {
  const safe = ensureSafeRvcFilename(filename);
  if (kind === "inputs") return path.join(context.paths.inputDir, safe);
  if (kind === "intermediate") return path.join(context.paths.intermediateDir, safe);
  if (kind === "converted") return path.join(context.paths.convertedDir, safe);
  throw new Error("invalid rvc audio kind");
}

export function rvcAudioUrl(kind, filename) {
  return `/api/rvc/audio/${kind}/${encodeURIComponent(filename)}`;
}

export async function writeRvcLog(context, entry) {
  await mkdir(path.dirname(context.paths.logPath), { recursive: true });
  await appendFile(context.paths.logPath, `${JSON.stringify(entry, null, 2)}\n`, "utf-8");
}

export async function createConversionArtifacts(context, id, paramStem) {
  const intermediateFilename = `rvc-intermediate-${id}.wav`;
  const convertedFilename = `rvc-converted-${id}-${paramStem}.wav`;
  await Promise.all([context.paths.intermediateDir, context.paths.convertedDir, context.paths.inputCleanDir].map((dir) => mkdir(dir, { recursive: true })));
  return {
    intermediateFilename, convertedFilename,
    intermediatePath: path.join(context.paths.intermediateDir, intermediateFilename),
    convertedPath: path.join(context.paths.convertedDir, convertedFilename),
  };
}

export async function denoiseRvcOutput(context, body) {
  const filename = ensureSafeRvcFilename(body?.filename);
  if (!filename.startsWith("rvc-converted-") || filename.endsWith("-denoised.wav")) throw new Error("RVC変換後の元wavを指定してください。");
  const inputPath = resolveRvcAudioPath(context, "converted", filename);
  await assertExistingFile("RVC converted audio", inputPath);
  const outputFilename = `${path.basename(filename, ".wav")}-denoised.wav`;
  const outputPath = resolveRvcAudioPath(context, "converted", outputFilename);
  const processing = await denoiseVoiceFile(context.repoRoot, inputPath, outputPath, "RVC変換後音声");
  await writeRvcLog(context, { ok: true, type: "post-denoise", inputPath, outputPath, command: processing.command, stdout: processing.stdout, stderr: processing.stderr, finishedAt: new Date().toISOString() });
  return { original: { filename, path: inputPath, url: rvcAudioUrl("converted", filename) }, denoised: { filename: outputFilename, path: outputPath, url: rvcAudioUrl("converted", outputFilename) }, processing };
}

export async function saveRvcRecording(context, body) {
  const { buffer, mimeType } = normalizeRecordingDataUrl(body);
  const scriptText = String(body?.scriptText || "").trim().slice(0, 1000);
  const id = `mic-${compactTimestampStem()}-${shortRandomId()}`;
  const rawExt = recordingExtFromMime(mimeType);
  const rawPath = path.join(context.paths.inputDir, `${id}${rawExt}`);
  const wavFilename = `${id}.wav`;
  const wavPath = path.join(context.paths.inputDir, wavFilename);
  await mkdir(context.paths.inputDir, { recursive: true });
  await writeFile(rawPath, buffer);
  const isAlreadyWav = rawExt === ".wav" && buffer.toString("ascii", 0, 4) === "RIFF";
  const conversion = isAlreadyWav ? (rawPath === wavPath ? { command: null, stdout: "", stderr: "" } : (await copyFile(rawPath, wavPath), { command: null, stdout: "", stderr: "" })) : await convertAudioFileToWav(context.repoRoot, rawPath, wavPath, "録音音声");
  const fileStat = await statIfExists(wavPath);
  const result = { filename: wavFilename, path: wavPath, url: rvcAudioUrl("inputs", wavFilename), rawPath, rawMimeType: mimeType, durationSec: await readWaveDurationSec(wavPath), sizeBytes: fileStat?.size || 0, scriptText, createdAt: new Date().toISOString(), conversion };
  await writeRvcLog(context, { ok: true, type: "mic-recording", ...result });
  return result;
}
