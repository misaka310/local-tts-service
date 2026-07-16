import path from "node:path";
import { copyFile, mkdir, readFile, readdir, rename, rm, writeFile } from "node:fs/promises";
import {
  compactTimestampStem,
  removeBom,
  shortRandomId,
  statIfExists,
} from "./shared.js";
import {
  ensureWavCopy,
  normalizeRecordingDataUrl,
  readWaveDurationSec,
  recordingExtFromMime,
} from "./audio-utils.js";

const REFERENCE_VOICE_ID_RE = /^[A-Za-z0-9_-]{1,80}$/;
const REFERENCE_VOICE_ARCHIVE_MARKER = ".archived";

function referenceVoiceError(message, statusCode = 400) {
  return Object.assign(new Error(message), { statusCode });
}

function normalizeReferenceVoiceId(voiceId) {
  const normalized = String(voiceId || "").trim();
  if (!normalized || normalized.includes("/") || normalized.includes("\\") || normalized.includes("..") || !REFERENCE_VOICE_ID_RE.test(normalized)) {
    throw referenceVoiceError("参照音声名は半角英数字・_・-のみ、80文字以内で入力してください");
  }
  return normalized;
}

export function parseReferenceVoiceAudioRequest(pathname) {
  const rawPath = String(pathname || "");
  const patterns = [
    /^\/api\/reference-voices\/([^/]+)\/audio$/,
    /^\/api\/reference-voices\/audio\/([^/]+)$/,
  ];
  for (const pattern of patterns) {
    const match = rawPath.match(pattern);
    if (!match) continue;
    try {
      return decodeURIComponent(match[1]);
    } catch {
      return null;
    }
  }
  return null;
}

export function parseReferenceVoiceTextRequest(pathname) {
  const match = String(pathname || "").match(/^\/api\/reference-voices\/([^/]+)\/text$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

export function parseReferenceVoiceArchiveRequest(pathname) {
  const match = String(pathname || "").match(/^\/api\/reference-voices\/([^/]+)\/archive$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

export function parseReferenceVoiceRenameRequest(pathname) {
  const match = String(pathname || "").match(/^\/api\/reference-voices\/([^/]+)\/rename$/);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

export function resolveReferenceVoiceDirectory(rootPath, voiceId) {
  return path.join(rootPath, "reference", "voices", normalizeReferenceVoiceId(voiceId));
}

export function resolveReferenceVoiceAudioPath(rootPath, voiceId) {
  return path.join(resolveReferenceVoiceDirectory(rootPath, voiceId), "voice.wav");
}

export function resolveReferenceVoiceTextPath(rootPath, voiceId) {
  return path.join(resolveReferenceVoiceDirectory(rootPath, voiceId), "voice.txt");
}

async function readReferenceText(directory) {
  for (const filename of ["voice.txt", "text.txt"]) {
    try {
      return removeBom(await readFile(path.join(directory, filename), "utf-8")).trim();
    } catch (error) {
      if (!error || typeof error !== "object" || error.code !== "ENOENT") throw error;
    }
  }
  return "";
}

function normalizeReferenceText(value) {
  const text = String(value || "").trim();
  if (!text) throw referenceVoiceError("音声内で実際に話している文章を入力してください");
  if (text.length > 5000) throw referenceVoiceError("音声内の文章は5000文字以内にしてください");
  return text;
}

export async function listLocalReferenceVoices(rootPath) {
  const rootDir = path.join(rootPath, "reference", "voices");
  let entries = [];
  try {
    entries = await readdir(rootDir, { withFileTypes: true });
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") return [];
    throw error;
  }

  const voices = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory() || entry.name.startsWith("_archive")) continue;
    let voiceId;
    try {
      voiceId = normalizeReferenceVoiceId(entry.name);
    } catch {
      continue;
    }
    const directory = path.join(rootDir, entry.name);
    const audioPath = path.join(directory, "voice.wav");
    const audioStat = await statIfExists(audioPath);
    const archived = Boolean(await statIfExists(path.join(directory, REFERENCE_VOICE_ARCHIVE_MARKER)));
    const referenceText = await readReferenceText(directory);
    const audioDurationSec = audioStat?.isFile() ? await readWaveDurationSec(audioPath) : null;
    voices.push({
      voiceId,
      displayName: voiceId,
      enabled: Boolean(audioStat?.isFile()) && !archived,
      archived,
      hasReferenceAudio: Boolean(audioStat?.isFile()),
      hasReferenceText: Boolean(referenceText),
      audioDurationSec,
      minReferenceDurationSec: 3,
      maxReferenceDurationSec: 10,
      errorReason: archived ? "archived" : audioStat?.isFile() ? null : "missing: voice.wav",
      referenceText,
      audioUrl: `/api/reference-voices/${encodeURIComponent(voiceId)}/audio`,
    });
  }
  return voices;
}

export async function saveReferenceVoiceText(rootPath, voiceId, referenceText) {
  const normalizedVoiceId = normalizeReferenceVoiceId(voiceId);
  const text = normalizeReferenceText(referenceText);
  const directory = resolveReferenceVoiceDirectory(rootPath, normalizedVoiceId);
  const audioStat = await statIfExists(path.join(directory, "voice.wav"));
  if (!audioStat?.isFile()) throw new Error("既存の voice.wav が見つかりません");
  await writeFile(path.join(directory, "voice.txt"), `${text}\n`, "utf-8");
  return { voiceId: normalizedVoiceId, referenceText: text };
}

export async function setReferenceVoiceArchived(rootPath, voiceId, archived) {
  const normalizedVoiceId = normalizeReferenceVoiceId(voiceId);
  const directory = resolveReferenceVoiceDirectory(rootPath, normalizedVoiceId);
  const audioStat = await statIfExists(path.join(directory, "voice.wav"));
  if (!audioStat?.isFile()) throw new Error("既存の voice.wav が見つかりません");
  const markerPath = path.join(directory, REFERENCE_VOICE_ARCHIVE_MARKER);
  if (archived) await writeFile(markerPath, "archived\n", "utf-8");
  else await rm(markerPath, { force: true });
  return { voiceId: normalizedVoiceId, archived: Boolean(archived) };
}

export async function renameReferenceVoice(rootPath, voiceId, newVoiceId) {
  const previousVoiceId = normalizeReferenceVoiceId(voiceId);
  const nextVoiceId = normalizeReferenceVoiceId(newVoiceId);
  if (previousVoiceId === nextVoiceId) return { previousVoiceId, voiceId: nextVoiceId };

  const previousDirectory = resolveReferenceVoiceDirectory(rootPath, previousVoiceId);
  const nextDirectory = resolveReferenceVoiceDirectory(rootPath, nextVoiceId);
  const audioStat = await statIfExists(path.join(previousDirectory, "voice.wav"));
  if (!audioStat?.isFile()) throw referenceVoiceError("変更元の参照音声が見つかりません", 404);
  if (await statIfExists(nextDirectory)) throw referenceVoiceError("同じ登録ID名が既にあります。別の名前を指定してください", 409);

  try {
    await rename(previousDirectory, nextDirectory);
  } catch (error) {
    if (error?.code === "EEXIST") throw referenceVoiceError("同じ登録ID名が既にあります。別の名前を指定してください", 409);
    throw referenceVoiceError(`登録ID名を変更できませんでした。詳細: ${error?.message || error}`, 500);
  }
  return { previousVoiceId, voiceId: nextVoiceId };
}

export async function saveReferenceVoiceRecording(rootPath, body) {
  const voiceId = normalizeReferenceVoiceId(body?.voiceId);
  const referenceText = normalizeReferenceText(body?.referenceText);
  const directory = resolveReferenceVoiceDirectory(rootPath, voiceId);
  if (await statIfExists(directory)) {
    throw referenceVoiceError("同じ参照音声名が既にあります。別の名前を指定してください", 409);
  }

  let normalizedData;
  try {
    normalizedData = normalizeRecordingDataUrl(body);
  } catch (error) {
    const message = String(error?.message || error);
    if (/empty/i.test(message)) throw referenceVoiceError("音声ファイルが空です。別のファイルを選んでください");
    if (/too large/i.test(message)) throw referenceVoiceError("音声ファイルが大きすぎます。50MB以下のファイルを選んでください");
    throw referenceVoiceError("音声データを読み込めませんでした。ファイルを選び直してください");
  }

  const { buffer, mimeType } = normalizedData;
  const uploadDir = path.join(rootPath, "runtime", "outputs", "reference-voices");
  const uploadId = `reference-${compactTimestampStem()}-${shortRandomId()}`;
  const rawExt = recordingExtFromMime(mimeType);
  const rawPath = path.join(uploadDir, `${uploadId}-source${rawExt}`);
  const wavPath = path.join(uploadDir, `${uploadId}-normalized.wav`);
  let directoryCreated = false;
  try {
    await mkdir(uploadDir, { recursive: true });
    await writeFile(rawPath, buffer);
    try {
      await ensureWavCopy(rootPath, rawPath, wavPath, "参照音声");
    } catch (error) {
      throw referenceVoiceError(`音声をWAVへ変換できませんでした。壊れていない対応形式の音声を選んでください。詳細: ${error.message || error}`);
    }

    const audioDurationSec = await readWaveDurationSec(wavPath);
    if (!Number.isFinite(audioDurationSec) || audioDurationSec <= 0) {
      throw referenceVoiceError("音声の長さを確認できませんでした。壊れていない音声ファイルを選んでください");
    }

    await mkdir(path.dirname(directory), { recursive: true });
    await mkdir(directory);
    directoryCreated = true;
    await copyFile(wavPath, path.join(directory, "voice.wav"));
    await writeFile(path.join(directory, "voice.txt"), `${referenceText}\n`, "utf-8");

    return {
      voiceId,
      displayName: voiceId,
      enabled: true,
      archived: false,
      hasReferenceAudio: true,
      hasReferenceText: true,
      audioDurationSec,
      minReferenceDurationSec: 3,
      maxReferenceDurationSec: 10,
      errorReason: null,
      referenceText,
      audioUrl: `/api/reference-voices/${encodeURIComponent(voiceId)}/audio`,
    };
  } catch (error) {
    if (directoryCreated) await rm(directory, { recursive: true, force: true }).catch(() => {});
    if (error?.code === "EEXIST") throw referenceVoiceError("同じ参照音声名が既にあります。別の名前を指定してください", 409);
    if (Number.isInteger(error?.statusCode)) throw error;
    throw referenceVoiceError(`参照音声を保存できませんでした。保存先の権限と空き容量を確認してください。詳細: ${error?.message || error}`, 500);
  } finally {
    await Promise.allSettled([
      rm(rawPath, { force: true }),
      rm(wavPath, { force: true }),
    ]);
  }
}

const IMPORT_EXTENSIONS = new Set([".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"]);

export async function importReferenceVoiceFile(rootPath, body) {
  const originalName = String(body?.fileName || "").trim();
  const extension = path.extname(originalName).toLowerCase();
  if (!IMPORT_EXTENSIONS.has(extension)) {
    throw referenceVoiceError("対応形式は wav・mp3・m4a・flac・ogg・aac です。音声ファイルを選び直してください");
  }
  const mimeByExtension = { ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4", ".flac": "audio/flac", ".ogg": "audio/ogg", ".aac": "audio/aac" };
  const mimeType = mimeByExtension[extension];
  return saveReferenceVoiceRecording(rootPath, {
    ...body,
    mimeType,
    dataUrl: body?.dataUrl,
  });
}
