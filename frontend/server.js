import http from "node:http";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  generateYoutubeReferenceCandidates,
  parseYoutubeCandidateAudioRequest,
  registerYoutubeReferenceCandidate,
  resolveYoutubeCandidateAudioPath,
} from "./youtube-reference.js";
import { normalizeBaseUrl, readJsonIfExists, truncateLog } from "./server/shared.js";
import {
  callTtsJson,
  isAllowedLocalBrowserOrigin,
  readRequestBody,
  sendJson,
  serveDirectoryFile,
  serveFile,
} from "./server/http-utils.js";
import {
  listLocalReferenceVoices,
  importReferenceVoiceFile,
  parseReferenceVoiceArchiveRequest,
  parseReferenceVoiceAudioRequest,
  parseReferenceVoiceRenameRequest,
  parseReferenceVoiceTextRequest,
  resolveReferenceVoiceAudioPath,
  saveReferenceVoiceRecording,
  saveReferenceVoiceText,
  renameReferenceVoice,
  setReferenceVoiceArchived,
} from "./server/reference-voices.js";
import {
  buildFfmpegWavArgs,
  buildRvcCommand,
  createRvcContext,
  defaultRvcSettings,
  denoiseRvcOutput,
  getRvcPaths,
  listRvcModels,
  normalizeRvcParams,
  normalizeSpeakChunking,
  resolveRvcAudioPath,
  rvcParamStem,
  saveRvcRecording,
  shouldConvertAudioInputToWav,
  synthesizeAndConvertRvc,
} from "./server/rvc-service.js";
import { normalizeTtsRequest } from "./server/tts-request.js";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "..");
const publicDir = path.join(__dirname, "public");
const referenceVoicesDir = path.join(repoRoot, "reference", "voices");

function isQwenCloneModel(model) {
  return model === "qwen3_tts_clone_0_6b" || model === "qwen3_tts_clone_1_7b";
}

async function readAppConfig() {
  const candidates = [
    "config/config.local.json",
    "config.local.json",
    "config/config.qwen3.example.json",
    "config/config.irodori.example.json",
    "config/config.example.json",
  ].map((filename) => path.join(repoRoot, filename));
  const configs = await Promise.all(candidates.map(readJsonIfExists));
  const rootConfig = configs.find(Boolean) || {};
  const frontend = rootConfig.frontend || {};
  const ttsHost = String(rootConfig.host || "127.0.0.1").trim() || "127.0.0.1";
  const ttsPort = Number(rootConfig.port || 8730);
  return {
    host: String(process.env.TTS_FRONT_HOST || frontend.host || "127.0.0.1").trim() || "127.0.0.1",
    port: Number(process.env.TTS_FRONT_PORT || frontend.port || 5177),
    ttsBaseUrl: normalizeBaseUrl(process.env.TTS_API_BASE_URL || frontend.ttsBaseUrl, `http://${ttsHost}:${ttsPort}`),
  };
}

function normalizeSpeakRequest(body) {
  const normalized = normalizeTtsRequest(body);
  const { model, voiceId } = normalized;

  if (isQwenCloneModel(model) && !voiceId) throw Object.assign(new Error("voiceId is required for Qwen3-TTS Voice Clone"), { statusCode: 400 });
  return normalized;
}

async function handleReferenceVoices(req, res, url, config) {
  const rootPath = path.resolve(config.referenceVoicesRoot || repoRoot);
  if (req.method === "GET" && url.pathname === "/api/reference-voices") {
    const localVoices = await listLocalReferenceVoices(rootPath);
    let upstream = { ok: false, body: {}, rawText: "" };
    try {
      upstream = await callTtsJson(config.ttsBaseUrl, "GET", "/v1/reference-voices");
    } catch {
      // TTS API停止中でもローカル参照音声の管理は継続する。
    }
    const merged = new Map();
    const upstreamVoices = Array.isArray(upstream.body?.voices) ? upstream.body.voices : [];
    upstreamVoices.forEach((voice) => merged.set(voice.voiceId, voice));
    localVoices.forEach((voice) => merged.set(voice.voiceId, { ...(merged.get(voice.voiceId) || {}), ...voice }));
    sendJson(res, 200, {
      ok: true,
      backendAvailable: upstream.ok,
      defaultReferenceVoice: upstream.body.defaultReferenceVoice || null,
      referenceVoicesDir: upstream.body.referenceVoicesDir || referenceVoicesDir,
      voices: Array.from(merged.values()),
      raw: upstream.body,
    });
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/reference-voices/import") {
    const voice = await importReferenceVoiceFile(rootPath, await readRequestBody(req));
    sendJson(res, 200, { ok: true, voice });
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/reference-voices") {
    const voice = await saveReferenceVoiceRecording(rootPath, await readRequestBody(req));
    sendJson(res, 200, { ok: true, voice });
    return true;
  }

  const textVoiceId = parseReferenceVoiceTextRequest(url.pathname);
  if (req.method === "POST" && textVoiceId) {
    const body = await readRequestBody(req);
    sendJson(res, 200, { ok: true, ...await saveReferenceVoiceText(rootPath, textVoiceId, body.referenceText) });
    return true;
  }

  const archiveVoiceId = parseReferenceVoiceArchiveRequest(url.pathname);
  if (req.method === "POST" && archiveVoiceId) {
    const body = await readRequestBody(req);
    sendJson(res, 200, { ok: true, ...await setReferenceVoiceArchived(rootPath, archiveVoiceId, Boolean(body.archived)) });
    return true;
  }

  const renameVoiceId = parseReferenceVoiceRenameRequest(url.pathname);
  if (req.method === "POST" && renameVoiceId) {
    const body = await readRequestBody(req);
    sendJson(res, 200, { ok: true, ...await renameReferenceVoice(rootPath, renameVoiceId, body.newVoiceId) });
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/reference-voices/youtube/candidates") {
    sendJson(res, 200, { ok: true, ...await generateYoutubeReferenceCandidates(rootPath, await readRequestBody(req)) });
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/reference-voices/youtube/register") {
    const voice = await registerYoutubeReferenceCandidate(rootPath, await readRequestBody(req));
    sendJson(res, 200, { ok: true, voice });
    return true;
  }

  const youtubeAudioRequest = parseYoutubeCandidateAudioRequest(url.pathname);
  if (req.method === "GET" && youtubeAudioRequest) {
    try {
      serveFile(res, await resolveYoutubeCandidateAudioPath(rootPath, youtubeAudioRequest), "audio/wav", req.headers.range);
    } catch (error) {
      sendJson(res, 404, { ok: false, error: error.message || "候補音声が見つかりません" });
    }
    return true;
  }

  const previewVoiceId = parseReferenceVoiceAudioRequest(url.pathname);
  if (req.method === "GET" && previewVoiceId) {
    try {
      serveFile(res, resolveReferenceVoiceAudioPath(rootPath, previewVoiceId), "audio/wav", req.headers.range);
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error.message || "invalid voiceId" });
    }
    return true;
  }
  return false;
}

async function handleRvc(req, res, url, config) {
  const rvcPaths = getRvcPaths(config.rvcContext);
  if (req.method === "GET" && url.pathname === "/api/rvc/defaults") {
    const catalog = await listRvcModels(config.rvcContext);
    sendJson(res, 200, {
      ok: true,
      defaults: defaultRvcSettings(config.rvcContext),
      ...catalog,
      outputDir: rvcPaths.outputDir,
      intermediateDir: rvcPaths.intermediateDir,
      inputDir: rvcPaths.inputDir,
      convertedDir: rvcPaths.convertedDir,
      logPath: rvcPaths.logPath,
    });
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/rvc/recording") {
    sendJson(res, 200, { ok: true, recording: await saveRvcRecording(await readRequestBody(req), config.rvcContext) });
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/rvc/convert") {
    try {
      sendJson(res, 200, { ok: true, result: await synthesizeAndConvertRvc(config, await readRequestBody(req)) });
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        error: error.message || "RVC変換に失敗しました。",
        errorMessage: error.message || "RVC変換に失敗しました。",
        stdout: truncateLog(error.stdout || ""),
        stderr: truncateLog(error.stderr || ""),
        command: error.command || null,
        partialResult: error.partialResult || null,
      });
    }
    return true;
  }

  if (req.method === "POST" && url.pathname === "/api/rvc/denoise") {
    try {
      sendJson(res, 200, { ok: true, result: await denoiseRvcOutput(await readRequestBody(req), config.rvcContext) });
    } catch (error) {
      sendJson(res, 500, {
        ok: false,
        error: error.message || "RVC変換後音声のノイズ除去に失敗しました。",
        errorMessage: error.message || "RVC変換後音声のノイズ除去に失敗しました。",
        stdout: truncateLog(error.stdout || ""),
        stderr: truncateLog(error.stderr || ""),
        command: error.command || null,
      });
    }
    return true;
  }

  if (req.method === "GET" && url.pathname.startsWith("/api/rvc/audio/")) {
    const [kind, encodedFilename] = url.pathname.replace("/api/rvc/audio/", "").split("/");
    try {
      serveFile(res, resolveRvcAudioPath(kind, decodeURIComponent(encodedFilename || ""), config.rvcContext), "audio/wav", req.headers.range);
    } catch (error) {
      sendJson(res, 400, { ok: false, error: error.message || "invalid rvc audio request" });
    }
    return true;
  }
  return false;
}

async function route(req, res, config) {
  const browserOrigin = String(req.headers.origin || "").trim();
  if (browserOrigin && !isAllowedLocalBrowserOrigin(browserOrigin)) {
    sendJson(res, 403, { ok: false, error: "external browser origins are not allowed" });
    return;
  }
  if (req.method === "OPTIONS") {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    });
    res.end();
    return;
  }

  const url = new URL(req.url || "/", "http://localhost");
  try {
    if (req.method === "GET" && url.pathname === "/api/health") {
      const health = await callTtsJson(config.ttsBaseUrl, "GET", "/health");
      sendJson(res, health.ok ? 200 : 502, { ok: health.ok, ttsBaseUrl: config.ttsBaseUrl, health: health.body, raw: health.rawText });
      return;
    }

    if (req.method === "GET" && url.pathname === "/api/models") {
      const health = await callTtsJson(config.ttsBaseUrl, "GET", "/health");
      const models = Array.isArray(health.body.availableModelInfo) ? health.body.availableModelInfo : [];
      sendJson(res, health.ok ? 200 : 502, {
        ok: health.ok,
        models,
        raw: health.body,
      });
      return;
    }

    if (await handleReferenceVoices(req, res, url, config)) return;

    if (req.method === "POST" && url.pathname === "/api/speak") {
      let requestBody;
      try {
        requestBody = normalizeSpeakRequest(await readRequestBody(req));
      } catch (error) {
        sendJson(res, error.statusCode || 400, { ok: false, error: error.message });
        return;
      }
      const speak = await callTtsJson(config.ttsBaseUrl, "POST", "/v1/speak", requestBody);
      if (!speak.ok) {
        const message = speak.body.errorMessage || speak.body.error || "音声生成に失敗しました。";
        sendJson(res, speak.status >= 400 && speak.status < 600 ? speak.status : 502, {
          ok: false,
          error: message,
          errorMessage: message,
          model: speak.body.model || requestBody.model,
          runtime: speak.body.runtime || "",
          voiceId: speak.body.voiceId || requestBody.voiceId || "",
          unavailableReason: speak.body.unavailableReason || "",
          ttsStatus: speak.status,
          raw: speak.body,
        });
        return;
      }
      sendJson(res, 200, { ok: true, result: speak.body });
      return;
    }

    if (await handleRvc(req, res, url, config)) return;

    if (req.method === "GET") {
      serveDirectoryFile(res, publicDir, url.pathname);
      return;
    }
    sendJson(res, 404, { ok: false, error: "not found" });
  } catch (error) {
    const statusCode = Number(error?.statusCode);
    sendJson(res, statusCode >= 400 && statusCode < 600 ? statusCode : 500, { ok: false, error: error.message || "internal error" });
  }
}

export function createServer(config) {
  return http.createServer((req, res) => route(req, res, config));
}

export {
  buildFfmpegWavArgs,
  buildRvcCommand,
  createRvcContext,
  isAllowedLocalBrowserOrigin,
  listLocalReferenceVoices,
  importReferenceVoiceFile,
  normalizeRvcParams,
  normalizeSpeakChunking,
  parseReferenceVoiceArchiveRequest,
  parseReferenceVoiceAudioRequest,
  parseReferenceVoiceRenameRequest,
  parseReferenceVoiceTextRequest,
  resolveReferenceVoiceAudioPath,
  resolveRvcAudioPath,
  rvcParamStem,
  saveReferenceVoiceRecording,
  saveReferenceVoiceText,
  renameReferenceVoice,
  setReferenceVoiceArchived,
  shouldConvertAudioInputToWav,
};
export { normalizeTtsRequest } from "./server/tts-request.js";

if (process.argv[1] && path.resolve(process.argv[1]) === __filename) {
  const appConfig = await readAppConfig();
  const server = createServer(appConfig);
  server.listen(appConfig.port, appConfig.host, () => {
    console.log(`tts frontend: http://${appConfig.host}:${appConfig.port}`);
    console.log(`tts api: ${appConfig.ttsBaseUrl}`);
  });
}
