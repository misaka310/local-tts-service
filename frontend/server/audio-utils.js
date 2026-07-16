import path from "node:path";
import { copyFile, mkdir, readFile, readdir } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { assertExistingFile, statIfExists, truncateLog } from "./shared.js";

const execFileAsync = promisify(execFile);

export async function readWaveDurationSec(filePath) {
  const fileStat = await statIfExists(filePath);
  if (!fileStat) return null;
  const buffer = await readFile(filePath);
  if (buffer.length < 12 || buffer.toString("ascii", 0, 4) !== "RIFF" || buffer.toString("ascii", 8, 12) !== "WAVE") return null;

  let offset = 12;
  let byteRate = null;
  let dataSize = null;
  while (offset + 8 <= buffer.length) {
    const chunkId = buffer.toString("ascii", offset, offset + 4);
    const chunkSize = buffer.readUInt32LE(offset + 4);
    const chunkDataStart = offset + 8;
    const nextOffset = chunkDataStart + chunkSize + (chunkSize % 2);
    if (chunkId === "fmt " && chunkSize >= 16 && chunkDataStart + 16 <= buffer.length) byteRate = buffer.readUInt32LE(chunkDataStart + 8);
    if (chunkId === "data") dataSize = chunkSize;
    if (byteRate && dataSize !== null) break;
    offset = nextOffset;
  }
  if (!byteRate || dataSize === null || byteRate <= 0) return null;
  return Number((dataSize / byteRate).toFixed(3));
}

export function normalizeRecordingDataUrl(body) {
  const dataUrl = String(body?.dataUrl || "").trim();
  const mimeType = String(body?.mimeType || "").trim().toLowerCase();
  const match = dataUrl.match(/^data:([^;,]+)?(;[^,]*)?,(.*)$/s);
  if (!match) throw new Error("recording dataUrl is required");
  const detectedMime = String(match[1] || mimeType || "application/octet-stream").toLowerCase();
  const meta = String(match[2] || "");
  if (!meta.includes(";base64")) throw new Error("recording dataUrl must be base64");
  const buffer = Buffer.from(match[3], "base64");
  if (!buffer.length) throw new Error("recording data is empty");
  if (buffer.length > 50 * 1024 * 1024) throw new Error("recording data is too large");
  return { buffer, mimeType: detectedMime };
}

export function recordingExtFromMime(mimeType) {
  if (mimeType.includes("wav") || mimeType.includes("wave")) return ".wav";
  if (mimeType.includes("webm")) return ".webm";
  if (mimeType.includes("ogg")) return ".ogg";
  if (mimeType.includes("mpeg") || mimeType.includes("mp3")) return ".mp3";
  if (mimeType.includes("flac")) return ".flac";
  if (mimeType.includes("aac")) return ".aac";
  if (mimeType.includes("mp4") || mimeType.includes("m4a")) return ".m4a";
  return ".webm";
}

async function findFileByName(rootDir, filename, maxDepth = 5) {
  if (maxDepth < 0) return "";
  let entries;
  try {
    entries = await readdir(rootDir, { withFileTypes: true });
  } catch {
    return "";
  }
  for (const entry of entries) {
    const fullPath = path.join(rootDir, entry.name);
    if (entry.isFile() && entry.name.toLowerCase() === filename.toLowerCase()) return fullPath;
  }
  for (const entry of entries) {
    if (!entry.isDirectory()) continue;
    const found = await findFileByName(path.join(rootDir, entry.name), filename, maxDepth - 1);
    if (found) return found;
  }
  return "";
}

export async function resolveFfmpegPath(repoRoot) {
  const candidates = [
    process.env.FFMPEG_PATH,
    path.join(repoRoot, "runtime", "vendor", "ffmpeg", "bin", "ffmpeg.exe")
  ].filter(Boolean);
  for (const candidate of candidates) {
    const fileStat = await statIfExists(candidate);
    if (fileStat?.isFile()) return candidate;
  }
  const bundled = await findFileByName(path.join(repoRoot, "runtime", "vendor", "ffmpeg"), "ffmpeg.exe", 5);
  return bundled || "ffmpeg";
}

export function shouldConvertAudioInputToWav(filePath) {
  return path.extname(String(filePath || "")).toLowerCase() !== ".wav";
}

export function buildFfmpegWavArgs(inputPath, outputPath) {
  return ["-hide_banner", "-loglevel", "error", "-y", "-i", inputPath, "-ac", "1", "-ar", "40000", outputPath];
}

export function buildFfmpegVoiceDenoiseArgs(inputPath, outputPath) {
  return [
    "-hide_banner", "-loglevel", "error", "-y", "-i", inputPath,
    "-af", "highpass=f=70,lowpass=f=16000,afftdn=nr=8:nf=-50:tn=1",
    "-ac", "1", "-ar", "40000", outputPath,
  ];
}

export async function denoiseVoiceFile(repoRoot, inputPath, outputPath, label = "RVC音声") {
  await mkdir(path.dirname(outputPath), { recursive: true });
  const ffmpegPath = await resolveFfmpegPath(repoRoot);
  const args = buildFfmpegVoiceDenoiseArgs(inputPath, outputPath);
  try {
    const { stdout, stderr } = await execFileAsync(ffmpegPath, args, {
      cwd: repoRoot,
      windowsHide: true,
      timeout: 90 * 1000,
      maxBuffer: 10 * 1024 * 1024
    });
    await assertExistingFile(`${label} denoised wav`, outputPath);
    return { command: { command: ffmpegPath, args, cwd: repoRoot }, stdout: truncateLog(stdout), stderr: truncateLog(stderr) };
  } catch (error) {
    const stderr = truncateLog(error.stderr || error.message || "");
    const wrapped = new Error(`${label}のノイズ除去に失敗しました: ${stderr || error.message || error}`);
    wrapped.stdout = truncateLog(error.stdout || "");
    wrapped.stderr = stderr;
    wrapped.command = { command: ffmpegPath, args, cwd: repoRoot };
    throw wrapped;
  }
}

export async function convertAudioFileToWav(repoRoot, rawPath, wavPath, label = "音声") {
  await mkdir(path.dirname(wavPath), { recursive: true });
  const ffmpegPath = await resolveFfmpegPath(repoRoot);
  const args = buildFfmpegWavArgs(rawPath, wavPath);
  try {
    const { stdout, stderr } = await execFileAsync(ffmpegPath, args, {
      cwd: repoRoot,
      windowsHide: true,
      timeout: 90 * 1000,
      maxBuffer: 10 * 1024 * 1024
    });
    await assertExistingFile(`${label} wav`, wavPath);
    return { command: { command: ffmpegPath, args, cwd: repoRoot }, stdout: truncateLog(stdout), stderr: truncateLog(stderr) };
  } catch (error) {
    const stderr = truncateLog(error.stderr || error.message || "");
    const wrapped = new Error(`${label}のwav変換に失敗しました: ${stderr || error.message || error}`);
    wrapped.stdout = truncateLog(error.stdout || "");
    wrapped.stderr = stderr;
    wrapped.command = { command: ffmpegPath, args, cwd: repoRoot };
    throw wrapped;
  }
}

export async function ensureWavCopy(repoRoot, sourcePath, targetPath, label = "音声") {
  if (shouldConvertAudioInputToWav(sourcePath)) return convertAudioFileToWav(repoRoot, sourcePath, targetPath, label);
  await mkdir(path.dirname(targetPath), { recursive: true });
  await copyFile(sourcePath, targetPath);
  return { command: null, stdout: "", stderr: "" };
}
