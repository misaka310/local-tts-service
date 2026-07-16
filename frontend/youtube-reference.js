import path from "node:path";
import { copyFile, mkdir, readFile, rm, stat, writeFile } from "node:fs/promises";
import { execFile } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);
const YOUTUBE_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);
const SAFE_ID = /^[A-Za-z0-9_-]{1,80}$/;
let youtubeCandidateJobActive = false;

async function statIfExists(filePath) {
  try {
    return await stat(filePath);
  } catch (error) {
    if (error?.code === "ENOENT") return null;
    throw error;
  }
}

function shortId() {
  return Math.random().toString(16).slice(2, 10);
}

function timestampStem() {
  return new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0, 14);
}

export function normalizeYoutubeUrl(value) {
  const raw = String(value || "").trim();
  let parsed;
  try {
    parsed = new URL(raw);
  } catch {
    throw new Error("動画URLが正しくありません");
  }
  if (!YOUTUBE_HOSTS.has(parsed.hostname) || !["http:", "https:"].includes(parsed.protocol)) {
    throw new Error("このURLには対応していません");
  }
  let videoId = "";
  if (parsed.hostname === "youtu.be") videoId = parsed.pathname.split("/").filter(Boolean)[0] || "";
  else if (parsed.pathname === "/watch") videoId = parsed.searchParams.get("v") || "";
  else if (/^\/(shorts|live|embed)\//.test(parsed.pathname)) videoId = parsed.pathname.split("/").filter(Boolean)[1] || "";
  if (!/^[A-Za-z0-9_-]{6,20}$/.test(videoId)) throw new Error("単一の動画URLを指定してください");
  return raw;
}

function normalizeId(value, label) {
  const id = String(value || "").trim();
  if (!SAFE_ID.test(id)) throw new Error(`${label}が正しくありません`);
  return id;
}

function jobDir(rootPath, jobId) {
  return path.join(rootPath, "runtime", "youtube-reference", normalizeId(jobId, "jobId"));
}

async function readManifest(rootPath, jobId) {
  const manifestPath = path.join(jobDir(rootPath, jobId), "result.json");
  const payload = JSON.parse(await readFile(manifestPath, "utf-8"));
  if (!payload?.ok || !Array.isArray(payload.candidates)) throw new Error("動画URLから取得した候補データが壊れています");
  return payload;
}

function candidateUrl(jobId, candidateId, variant) {
  return `/api/reference-voices/youtube/jobs/${encodeURIComponent(jobId)}/audio/${encodeURIComponent(candidateId)}/${variant}`;
}

async function resolvePython(rootPath) {
  const candidates = [
    String(process.env.LOCAL_TTS_YOUTUBE_PYTHON || "").trim(),
    path.join(rootPath, ".venv", "Scripts", "python.exe"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    if ((await statIfExists(candidate))?.isFile()) return candidate;
  }
  return "python";
}

async function resolveDemucsPython(rootPath) {
  const candidates = [
    String(process.env.LOCAL_TTS_DEMUCS_PYTHON || "").trim(),
    path.join(rootPath, "runtime", "venv-demucs", "Scripts", "python.exe"),
    path.join(rootPath, "runtime", "vendor", "GPT-SoVITS", ".venv", "Scripts", "python.exe"),
  ].filter(Boolean);
  for (const candidate of candidates) {
    if ((await statIfExists(candidate))?.isFile()) return candidate;
  }
  throw new Error("BGM・伴奏除去の実行環境が見つかりません。local-tts.bat -ForceSetupを実行してください");
}

async function runDemucs(rootPath, inputPath, outputPath, workId, model = "htdemucs_ft") {
  const python = await resolveDemucsPython(rootPath);
  const workDir = path.join(rootPath, "runtime", "youtube-reference", "demucs-work", workId);
  await rm(workDir, { recursive: true, force: true });
  await mkdir(workDir, { recursive: true });
  const args = ["-m", "demucs", "--two-stems=vocals", "-n", model, "-o", workDir, inputPath];
  try {
    await execFileAsync(python, args, { cwd: rootPath, windowsHide: true, timeout: 20 * 60 * 1000, maxBuffer: 20 * 1024 * 1024 });
    const stem = path.basename(inputPath, path.extname(inputPath)).replace(/[^A-Za-z0-9_-]/g, "_");
    const vocalsPath = path.join(workDir, model, stem, "vocals.wav");
    if (!(await statIfExists(vocalsPath))?.isFile()) throw new Error("BGM・伴奏除去後の音声が見つかりません");
    await copyFile(vocalsPath, outputPath);
  } finally {
    await rm(workDir, { recursive: true, force: true });
  }
}

export async function generateYoutubeReferenceCandidates(rootPath, body) {
  if (youtubeCandidateJobActive) throw new Error("別の動画URL候補処理が実行中です。完了後に再実行してください");
  if (body?.rightsConfirmed !== true) throw new Error("音声の利用許可を確認してください");
  const url = normalizeYoutubeUrl(body?.url);
  const useDemucs = body?.useDemucs !== false;
  const requestedMaxCandidates = Number(body?.maxCandidates ?? 5);
  const maxCandidates = Number.isFinite(requestedMaxCandidates)
    ? Math.max(1, Math.min(8, Math.trunc(requestedMaxCandidates)))
    : 5;
  const language = String(body?.language || "ja").trim();
  if (!new Set(["ja", "en", "auto"]).has(language)) throw new Error("文字起こし言語が正しくありません");
  const whisperModel = String(body?.whisperModel || "small").trim();
  if (!new Set(["tiny", "base", "small", "medium", "large-v3"]).has(whisperModel)) throw new Error("Whisperモデル名が正しくありません");
  const demucsModel = String(body?.demucsModel || "htdemucs_ft").trim();
  if (!/^[A-Za-z0-9_.-]{1,80}$/.test(demucsModel) || demucsModel.startsWith("-")) {
    throw new Error("BGM・伴奏除去の設定が正しくありません");
  }
  const excludeRanges = (Array.isArray(body?.excludeRanges) ? body.excludeRanges : [])
    .slice(0, 40)
    .map((item) => ({ startSec: Number(item?.startSec), endSec: Number(item?.endSec) }))
    .filter((item) => Number.isFinite(item.startSec) && Number.isFinite(item.endSec) && item.startSec >= 0 && item.endSec > item.startSec);

  const jobId = `yt-${timestampStem()}-${shortId()}`;
  const directory = jobDir(rootPath, jobId);
  const requestPath = path.join(directory, "request.json");
  const outputPath = path.join(directory, "result.json");
  youtubeCandidateJobActive = true;
  try {
    await mkdir(directory, { recursive: true });
    await writeFile(requestPath, JSON.stringify({ repoRoot: rootPath, jobId, url, maxCandidates, language, whisperModel, excludeRanges }, null, 2), "utf-8");
    const python = await resolvePython(rootPath);
    const script = path.join(rootPath, "scripts", "youtube_reference_candidates.py");
    try {
      await execFileAsync(python, [script, "--request", requestPath, "--output", outputPath], {
        cwd: rootPath,
        windowsHide: true,
        timeout: 45 * 60 * 1000,
        maxBuffer: 20 * 1024 * 1024,
      });
    } catch (error) {
      let output = null;
      if (await statIfExists(outputPath)) {
        try {
          output = JSON.parse(await readFile(outputPath, "utf-8"));
        } catch {
          output = null;
        }
      }
      throw new Error(output?.error || String(error?.stderr || error?.message || error));
    }
    const result = JSON.parse(await readFile(outputPath, "utf-8"));
    if (!result?.ok) throw new Error(result?.error || "動画URLから候補を抽出できませんでした");
    for (const candidate of result.candidates) {
      candidate.originalAudioUrl = candidateUrl(jobId, candidate.candidate_id, "original");
      candidate.audioUrl = candidate.originalAudioUrl;
      candidate.demucsApplied = false;
      if (useDemucs) {
        const originalPath = path.join(directory, candidate.original_filename);
        const cleanedFilename = `${candidate.candidate_id}-vocals.wav`;
        try {
          await runDemucs(rootPath, originalPath, path.join(directory, cleanedFilename), `${jobId}-${candidate.candidate_id}`, demucsModel);
          candidate.cleaned_filename = cleanedFilename;
          candidate.cleanedAudioUrl = candidateUrl(jobId, candidate.candidate_id, "cleaned");
          candidate.audioUrl = candidate.cleanedAudioUrl;
          candidate.demucsApplied = true;
        } catch (error) {
          candidate.demucsError = String(error?.message || error);
        }
      }
    }
    result.useDemucs = useDemucs;
    await writeFile(outputPath, JSON.stringify(result, null, 2), "utf-8");
    return result;
  } finally {
    youtubeCandidateJobActive = false;
    await rm(requestPath, { force: true });
  }
}

export function parseYoutubeCandidateAudioRequest(pathname) {
  const match = String(pathname || "").match(/^\/api\/reference-voices\/youtube\/jobs\/([^/]+)\/audio\/([^/]+)\/(original|cleaned)$/);
  if (!match) return null;
  try {
    const jobId = decodeURIComponent(match[1]);
    const candidateId = decodeURIComponent(match[2]);
    if (!SAFE_ID.test(jobId) || !SAFE_ID.test(candidateId)) return null;
    return { jobId, candidateId, variant: match[3] };
  } catch {
    return null;
  }
}

export async function resolveYoutubeCandidateAudioPath(rootPath, request) {
  const manifest = await readManifest(rootPath, request.jobId);
  const candidateId = normalizeId(request.candidateId, "candidateId");
  const candidate = manifest.candidates.find((item) => item.candidate_id === candidateId);
  if (!candidate) throw new Error("候補音声が見つかりません");
  const filename = request.variant === "cleaned" ? candidate.cleaned_filename : candidate.original_filename;
  if (!filename || path.basename(filename) !== filename || !filename.endsWith(".wav")) throw new Error("候補音声が見つかりません");
  const candidatePath = path.join(jobDir(rootPath, request.jobId), filename);
  if (!(await statIfExists(candidatePath))?.isFile()) throw new Error("候補音声が見つかりません");
  return candidatePath;
}

export async function registerYoutubeReferenceCandidate(rootPath, body) {
  if (body?.rightsConfirmed !== true) throw new Error("音声の利用許可を確認してください");
  const voiceId = normalizeId(body?.voiceId, "参照音声名");
  const referenceText = String(body?.referenceText || "").trim();
  if (!referenceText) throw new Error("文字起こしを入力してください");
  if (referenceText.length > 5000) throw new Error("文字起こしは5000文字以内にしてください");
  const voicesDir = path.join(rootPath, "reference", "voices");
  const targetDir = path.join(voicesDir, voiceId);
  if (await statIfExists(targetDir)) throw new Error("同じ参照音声名が既にあります。別の名前を指定してください");
  const sourcePath = await resolveYoutubeCandidateAudioPath(rootPath, {
    jobId: body?.jobId,
    candidateId: body?.candidateId,
    variant: body?.useCleaned === false ? "original" : "cleaned",
  }).catch(async (error) => {
    if (body?.useCleaned === false) throw error;
    return resolveYoutubeCandidateAudioPath(rootPath, { jobId: body?.jobId, candidateId: body?.candidateId, variant: "original" });
  });
  await mkdir(voicesDir, { recursive: true });
  await mkdir(targetDir);
  try {
    await copyFile(sourcePath, path.join(targetDir, "voice.wav"));
    await writeFile(path.join(targetDir, "voice.txt"), `${referenceText}\n`, "utf-8");
  } catch (error) {
    await rm(targetDir, { recursive: true, force: true });
    throw error;
  }
  return { voiceId, referenceText, enabled: true, archived: false, hasReferenceAudio: true, hasReferenceText: true };
}
