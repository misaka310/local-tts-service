import assert from "node:assert/strict";
import test from "node:test";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { existsSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { spawnSync } from "node:child_process";

import {
  buildFfmpegWavArgs,
  buildRvcCommand,
  createRvcContext,
  createServer,
  isAllowedLocalBrowserOrigin,
  normalizeRvcParams,
  normalizeTtsRequest,
  normalizeSpeakChunking,
  parseReferenceVoiceArchiveRequest,
  parseReferenceVoiceAudioRequest,
  parseReferenceVoiceRenameRequest,
  parseReferenceVoiceTextRequest,
  listLocalReferenceVoices,
  importReferenceVoiceFile,
  saveReferenceVoiceRecording,
  saveReferenceVoiceText,
  renameReferenceVoice,
  setReferenceVoiceArchived,
  resolveReferenceVoiceAudioPath,
  resolveRvcAudioPath,
  rvcParamStem,
  shouldConvertAudioInputToWav
} from "./server.js";
import { buildFfmpegVoiceDenoiseArgs, readWaveDurationSec, resolveFfmpegPath } from "./server/audio-utils.js";
import { resolveRvcAudioPath as resolveInjectedRvcAudioPath } from "./server/rvc/artifact-store.js";
import { listRvcModels } from "./server/rvc/model-catalog.js";
import { buildRvcCommand as buildInjectedRvcCommand, stageRvcModelForRuntime } from "./server/rvc/rvc-runner.js";
import { synthesizeAndConvertRvc as convertWithDependencies } from "./server/rvc/conversion-service.js";
import {
  normalizeYoutubeUrl,
  parseYoutubeCandidateAudioRequest,
  registerYoutubeReferenceCandidate,
  resolveYoutubeCandidateAudioPath,
} from "./youtube-reference.js";

function makeWavBuffer(durationSec = 3, sampleRate = 16000) {
  const samples = Math.max(1, Math.floor(durationSec * sampleRate));
  const dataSize = samples * 2;
  const buffer = Buffer.alloc(44 + dataSize);
  buffer.write("RIFF", 0);
  buffer.writeUInt32LE(36 + dataSize, 4);
  buffer.write("WAVE", 8);
  buffer.write("fmt ", 12);
  buffer.writeUInt32LE(16, 16);
  buffer.writeUInt16LE(1, 20);
  buffer.writeUInt16LE(1, 22);
  buffer.writeUInt32LE(sampleRate, 24);
  buffer.writeUInt32LE(sampleRate * 2, 28);
  buffer.writeUInt16LE(2, 32);
  buffer.writeUInt16LE(16, 34);
  buffer.write("data", 36);
  buffer.writeUInt32LE(dataSize, 40);
  return buffer;
}

test("frontend model catalog uses lightweight health metadata instead of waiting for deep model probes", async () => {
  const backendCalls = [];
  const backend = http.createServer((req, res) => {
    backendCalls.push(req.url);
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    if (req.url === "/health") {
      res.end(JSON.stringify({
        ok: true,
        availableModelInfo: [{
          id: "irodori_v3_voicedesign",
          model: "irodori_v3_voicedesign",
          label: "Irodori v3 VoiceDesign",
          available: true,
          enabled: true,
          supportsSpeedControl: true,
          supportsStyleStrength: true,
        }],
      }));
      return;
    }
    if (req.url === "/v1/models") {
      setTimeout(() => res.end(JSON.stringify({ ok: true, models: [] })), 1200);
      return;
    }
    res.statusCode = 404;
    res.end(JSON.stringify({ ok: false }));
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const backendAddress = backend.address();
  const frontend = createServer({
    host: "127.0.0.1",
    port: 0,
    ttsBaseUrl: `http://127.0.0.1:${backendAddress.port}`,
  });
  await new Promise((resolve) => frontend.listen(0, "127.0.0.1", resolve));
  const frontendAddress = frontend.address();

  try {
    const startedAt = Date.now();
    const response = await fetch(`http://127.0.0.1:${frontendAddress.port}/api/models`);
    const payload = await response.json();
    const elapsedMs = Date.now() - startedAt;

    assert.equal(response.status, 200);
    assert.ok(elapsedMs < 500, `model catalog took ${elapsedMs}ms`);
    assert.deepEqual(backendCalls, ["/health"]);
    assert.equal(payload.models[0].supportsSpeedControl, true);
    assert.equal(payload.models[0].supportsStyleStrength, true);
  } finally {
    await new Promise((resolve) => frontend.close(resolve));
    await new Promise((resolve) => backend.close(resolve));
  }
});

test("frontend speak proxy preserves independent speed and style controls", async () => {
  let upstreamBody = null;
  const backend = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    upstreamBody = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.end(JSON.stringify({
      ok: true,
      requestId: "proxy-controls",
      model: upstreamBody.model,
      runtime: "mock",
      audioUrl: "http://127.0.0.1/audio/mock.wav",
      audioPath: "C:/mock.wav",
    }));
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const backendAddress = backend.address();
  const frontend = createServer({
    host: "127.0.0.1",
    port: 0,
    ttsBaseUrl: `http://127.0.0.1:${backendAddress.port}`,
  });
  await new Promise((resolve) => frontend.listen(0, "127.0.0.1", resolve));
  const frontendAddress = frontend.address();

  try {
    const response = await fetch(`http://127.0.0.1:${frontendAddress.port}/api/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "確認します。",
        model: "irodori_v3_voicedesign",
        voiceId: "sample_voice",
        instruction: "明るく話す。",
        speedScale: 0.85,
        styleStrength: 5,
      }),
    });

    assert.equal(response.status, 200);
    assert.equal(upstreamBody.speedScale, 0.85);
    assert.equal(upstreamBody.styleStrength, 5);
  } finally {
    await new Promise((resolve) => frontend.close(resolve));
    await new Promise((resolve) => backend.close(resolve));
  }
});

test("frontend does not require a reference voice for Irodori models that declare it optional", async () => {
  let upstreamBody = null;
  const backend = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    upstreamBody = JSON.parse(Buffer.concat(chunks).toString("utf-8"));
    res.setHeader("Content-Type", "application/json; charset=utf-8");
    res.end(JSON.stringify({
      ok: true,
      requestId: "irodori-no-voice",
      model: upstreamBody.model,
      runtime: "irodori_voicedesign_direct",
      audioUrl: "http://127.0.0.1/audio/mock.wav",
      audioPath: "C:/mock.wav",
    }));
  });
  await new Promise((resolve) => backend.listen(0, "127.0.0.1", resolve));
  const backendAddress = backend.address();
  const frontend = createServer({
    host: "127.0.0.1",
    port: 0,
    ttsBaseUrl: `http://127.0.0.1:${backendAddress.port}`,
  });
  await new Promise((resolve) => frontend.listen(0, "127.0.0.1", resolve));
  const frontendAddress = frontend.address();

  try {
    const response = await fetch(`http://127.0.0.1:${frontendAddress.port}/api/speak`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: "参照音声なしで確認します。", model: "irodori_v3" }),
    });

    assert.equal(response.status, 200);
    assert.equal(upstreamBody.model, "irodori_v3");
    assert.equal(upstreamBody.voiceId, undefined);
  } finally {
    await new Promise((resolve) => frontend.close(resolve));
    await new Promise((resolve) => backend.close(resolve));
  }
});

test("parseReferenceVoiceAudioRequest supports both preview route styles", () => {
  assert.equal(parseReferenceVoiceAudioRequest("/api/reference-voices/sample/audio"), "sample");
  assert.equal(parseReferenceVoiceAudioRequest("/api/reference-voices/audio/sample"), "sample");
  assert.equal(parseReferenceVoiceAudioRequest("/api/reference-voices"), null);
});

test("resolveReferenceVoiceAudioPath returns voice.wav for a safe voice id", () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-ref-"));
  try {
    const voiceDir = path.join(tempRoot, "reference", "voices", "sample_voice");
    mkdirSync(voiceDir, { recursive: true });
    writeFileSync(path.join(voiceDir, "voice.wav"), "RIFF");

    assert.equal(
      resolveReferenceVoiceAudioPath(tempRoot, "sample_voice"),
      path.join(voiceDir, "voice.wav")
    );
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("resolveReferenceVoiceAudioPath rejects traversal and invalid ids", () => {
  assert.throws(() => resolveReferenceVoiceAudioPath("C:\\repo", "../bad"), /参照音声名/);
  assert.throws(() => resolveReferenceVoiceAudioPath("C:\\repo", "bad/name"), /参照音声名/);
});

test("parseReferenceVoiceTextRequest accepts only the text update route", () => {
  assert.equal(parseReferenceVoiceTextRequest("/api/reference-voices/sample_voice/text"), "sample_voice");
  assert.equal(parseReferenceVoiceTextRequest("/api/reference-voices/sample_voice/audio"), null);
  assert.equal(parseReferenceVoiceTextRequest("/api/reference-voices"), null);
});

test("parseReferenceVoiceArchiveRequest accepts only the archive route", () => {
  assert.equal(parseReferenceVoiceArchiveRequest("/api/reference-voices/sample_voice/archive"), "sample_voice");
  assert.equal(parseReferenceVoiceArchiveRequest("/api/reference-voices/sample_voice/text"), null);
  assert.equal(parseReferenceVoiceArchiveRequest("/api/reference-voices"), null);
});

test("parseReferenceVoiceRenameRequest accepts only the rename route", () => {
  assert.equal(parseReferenceVoiceRenameRequest("/api/reference-voices/sample_voice/rename"), "sample_voice");
  assert.equal(parseReferenceVoiceRenameRequest("/api/reference-voices/sample_voice/text"), null);
  assert.equal(parseReferenceVoiceRenameRequest("/api/reference-voices"), null);
});

test("local reference voices expose and update voice.txt", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-ref-manage-"));
  try {
    const voiceDir = path.join(tempRoot, "reference", "voices", "sample_voice");
    mkdirSync(voiceDir, { recursive: true });
    writeFileSync(path.join(voiceDir, "voice.wav"), makeWavBuffer(3.2));
    writeFileSync(path.join(voiceDir, "voice.txt"), "元の文章\n", "utf-8");

    const initial = await listLocalReferenceVoices(tempRoot);
    assert.equal(initial.length, 1);
    assert.equal(initial[0].voiceId, "sample_voice");
    assert.equal(initial[0].referenceText, "元の文章");
    assert.equal(initial[0].hasReferenceText, true);
    assert.ok(initial[0].audioDurationSec >= 3);

    await saveReferenceVoiceText(tempRoot, "sample_voice", "修正後の文章");
    assert.equal(readFileSync(path.join(voiceDir, "voice.txt"), "utf-8"), "修正後の文章\n");
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("reference voice archive keeps files but disables UI selection until restored", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-ref-archive-"));
  try {
    const voiceDir = path.join(tempRoot, "reference", "voices", "sample_voice");
    mkdirSync(voiceDir, { recursive: true });
    writeFileSync(path.join(voiceDir, "voice.wav"), makeWavBuffer(3.2));
    writeFileSync(path.join(voiceDir, "voice.txt"), "保存する文章\n", "utf-8");

    await setReferenceVoiceArchived(tempRoot, "sample_voice", true);
    assert.ok(existsSync(path.join(voiceDir, "voice.wav")));
    assert.ok(existsSync(path.join(voiceDir, "voice.txt")));
    assert.ok(existsSync(path.join(voiceDir, ".archived")));
    let listed = await listLocalReferenceVoices(tempRoot);
    assert.equal(listed[0].archived, true);
    assert.equal(listed[0].enabled, false);
    assert.equal(listed[0].referenceText, "保存する文章");

    await setReferenceVoiceArchived(tempRoot, "sample_voice", false);
    assert.equal(existsSync(path.join(voiceDir, ".archived")), false);
    listed = await listLocalReferenceVoices(tempRoot);
    assert.equal(listed[0].archived, false);
    assert.equal(listed[0].enabled, true);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("reference voice registration ID can be renamed without losing audio, text, or archive state", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-ref-rename-"));
  try {
    const previousDir = path.join(tempRoot, "reference", "voices", "before_voice");
    const collisionDir = path.join(tempRoot, "reference", "voices", "existing_voice");
    mkdirSync(previousDir, { recursive: true });
    mkdirSync(collisionDir, { recursive: true });
    writeFileSync(path.join(previousDir, "voice.wav"), makeWavBuffer(3.2));
    writeFileSync(path.join(previousDir, "voice.txt"), "変更前の文章\n", "utf-8");
    writeFileSync(path.join(previousDir, ".archived"), "archived\n", "utf-8");
    writeFileSync(path.join(collisionDir, "voice.wav"), makeWavBuffer(3.1));

    const renamed = await renameReferenceVoice(tempRoot, "before_voice", "after_voice");
    const nextDir = path.join(tempRoot, "reference", "voices", "after_voice");
    assert.deepEqual(renamed, { previousVoiceId: "before_voice", voiceId: "after_voice" });
    assert.equal(existsSync(previousDir), false);
    assert.ok(existsSync(path.join(nextDir, "voice.wav")));
    assert.equal(readFileSync(path.join(nextDir, "voice.txt"), "utf-8"), "変更前の文章\n");
    assert.ok(existsSync(path.join(nextDir, ".archived")));
    const listed = await listLocalReferenceVoices(tempRoot);
    assert.equal(listed.find((voice) => voice.voiceId === "after_voice")?.archived, true);
    await assert.rejects(renameReferenceVoice(tempRoot, "after_voice", "existing_voice"), /同じ登録ID名/);
    await assert.rejects(renameReferenceVoice(tempRoot, "after_voice", "../bad"), /半角英数字/);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("reference voice recording saves reusable voice.wav and voice.txt", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-ref-record-"));
  try {
    const wav = makeWavBuffer(4.1);
    const voice = await saveReferenceVoiceRecording(tempRoot, {
      voiceId: "new_voice",
      referenceText: "録音で実際に読んだ文章です。",
      mimeType: "audio/wav",
      dataUrl: `data:audio/wav;base64,${wav.toString("base64")}`
    });
    const voiceDir = path.join(tempRoot, "reference", "voices", "new_voice");
    assert.equal(voice.voiceId, "new_voice");
    assert.equal(voice.referenceText, "録音で実際に読んだ文章です。");
    assert.ok(existsSync(path.join(voiceDir, "voice.wav")));
    assert.equal(readFileSync(path.join(voiceDir, "voice.txt"), "utf-8"), "録音で実際に読んだ文章です。\n");
    await assert.rejects(
      saveReferenceVoiceRecording(tempRoot, {
        voiceId: "new_voice",
        referenceText: "上書きしようとした文章です。",
        mimeType: "audio/wav",
        dataUrl: `data:audio/wav;base64,${wav.toString("base64")}`
      }),
      /同じ参照音声名/
    );

    const listed = await listLocalReferenceVoices(tempRoot);
    assert.equal(listed[0].voiceId, "new_voice");
    assert.equal(listed[0].referenceText, "録音で実際に読んだ文章です。");
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("reference voice file import accepts WAV and rejects unsupported files", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-reference-import-"));
  try {
    const wav = makeWavBuffer(4.2);
    const voice = await importReferenceVoiceFile(tempRoot, {
      voiceId: "file_voice",
      referenceText: "音声ファイルで実際に話している文章です。",
      fileName: "sample.wav",
      mimeType: "audio/wav",
      dataUrl: `data:audio/wav;base64,${wav.toString("base64")}`,
    });
    assert.equal(voice.voiceId, "file_voice");
    assert.ok(existsSync(path.join(tempRoot, "reference", "voices", "file_voice", "voice.wav")));
    assert.equal(readFileSync(path.join(tempRoot, "reference", "voices", "file_voice", "voice.txt"), "utf-8").trim(), "音声ファイルで実際に話している文章です。");
    await assert.rejects(importReferenceVoiceFile(tempRoot, { voiceId: "bad", referenceText: "本文", fileName: "bad.exe", dataUrl: "data:application/octet-stream;base64,WA==" }), /対応形式/);
    await assert.rejects(importReferenceVoiceFile(tempRoot, { voiceId: "bad/name", referenceText: "本文", fileName: "sample.wav", dataUrl: `data:audio/wav;base64,${wav.toString("base64")}` }), /参照音声名/);
    await assert.rejects(importReferenceVoiceFile(tempRoot, { voiceId: "missing_text", referenceText: "", fileName: "sample.wav", dataUrl: `data:audio/wav;base64,${wav.toString("base64")}` }), /実際に話している文章/);
    await assert.rejects(importReferenceVoiceFile(tempRoot, { voiceId: "empty_file", referenceText: "本文", fileName: "sample.wav", dataUrl: "data:audio/wav;base64," }), /空です|読み込めません/);
  } finally { rmSync(tempRoot, { recursive: true, force: true }); }
});

test("reference voice file import rejects corrupt audio without leaving a partial voice", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-reference-corrupt-"));
  try {
    const corruptWav = Buffer.from("RIFF this is not a valid WAVE file", "utf-8");
    await assert.rejects(
      importReferenceVoiceFile(tempRoot, {
        voiceId: "corrupt_voice",
        referenceText: "壊れた音声の文章です。",
        fileName: "broken.wav",
        mimeType: "audio/wav",
        dataUrl: `data:audio/wav;base64,${corruptWav.toString("base64")}`,
      }),
      /音声|WAV|wav|変換/
    );
    assert.equal(existsSync(path.join(tempRoot, "reference", "voices", "corrupt_voice")), false);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("reference voice file import converts MP3 and M4A into usable WAV files", async (t) => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-reference-formats-"));
  const previousFfmpegPath = process.env.FFMPEG_PATH;
  try {
    const repoRoot = path.resolve(process.cwd(), "..");
    const ffmpegPath = await resolveFfmpegPath(repoRoot);
    process.env.FFMPEG_PATH = ffmpegPath;
    const sourceWav = path.join(tempRoot, "source.wav");
    writeFileSync(sourceWav, makeWavBuffer(4.4));

    for (const extension of ["mp3", "m4a"]) {
      const sourcePath = path.join(tempRoot, `source.${extension}`);
      const encoded = spawnSync(ffmpegPath, ["-hide_banner", "-loglevel", "error", "-y", "-i", sourceWav, sourcePath], {
        cwd: tempRoot,
        windowsHide: true,
        encoding: "utf-8",
      });
      if (encoded.status !== 0 || !existsSync(sourcePath)) {
        t.skip(`FFmpegで${extension}のテスト音声を作れませんでした: ${encoded.stderr || encoded.error || "unknown error"}`);
        return;
      }
      const imported = await importReferenceVoiceFile(tempRoot, {
        voiceId: `format_${extension}`,
        referenceText: `${extension}で実際に話している文章です。`,
        fileName: `sample.${extension}`,
        mimeType: extension === "mp3" ? "audio/mpeg" : "audio/mp4",
        dataUrl: `data:${extension === "mp3" ? "audio/mpeg" : "audio/mp4"};base64,${readFileSync(sourcePath).toString("base64")}`,
      });
      const savedWav = path.join(tempRoot, "reference", "voices", imported.voiceId, "voice.wav");
      assert.ok(existsSync(savedWav));
      assert.ok(Number(await readWaveDurationSec(savedWav)) > 4);
    }
  } finally {
    if (previousFfmpegPath === undefined) delete process.env.FFMPEG_PATH;
    else process.env.FFMPEG_PATH = previousFfmpegPath;
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("reference voice API can use an isolated voice root", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-reference-api-root-"));
  const voiceDir = path.join(tempRoot, "reference", "voices", "isolated_voice");
  mkdirSync(voiceDir, { recursive: true });
  writeFileSync(path.join(voiceDir, "voice.wav"), makeWavBuffer(4));
  writeFileSync(path.join(voiceDir, "voice.txt"), "隔離された参照音声です。\n", "utf-8");
  const server = createServer({ host: "127.0.0.1", port: 0, ttsBaseUrl: "http://127.0.0.1:1", referenceVoicesRoot: tempRoot });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  try {
    const response = await fetch(`http://127.0.0.1:${address.port}/api/reference-voices`);
    const payload = await response.json();
    assert.equal(response.status, 200);
    assert.ok(payload.voices.some((voice) => voice.voiceId === "isolated_voice"));

    const importResponse = await fetch(`http://127.0.0.1:${address.port}/api/reference-voices/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        voiceId: "api_imported_voice",
        referenceText: "APIで登録した参照音声です。",
        fileName: "sample.wav",
        mimeType: "audio/wav",
        dataUrl: `data:audio/wav;base64,${makeWavBuffer(4).toString("base64")}`,
      }),
    });
    const importPayload = await importResponse.json();
    assert.equal(importResponse.status, 200);
    assert.equal(importPayload.voice.voiceId, "api_imported_voice");
    assert.ok(existsSync(path.join(tempRoot, "reference", "voices", "api_imported_voice", "voice.wav")));
    assert.ok(existsSync(path.join(tempRoot, "reference", "voices", "api_imported_voice", "voice.txt")));

    const duplicateResponse = await fetch(`http://127.0.0.1:${address.port}/api/reference-voices/import`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        voiceId: "api_imported_voice",
        referenceText: "重複登録です。",
        fileName: "sample.wav",
        mimeType: "audio/wav",
        dataUrl: `data:audio/wav;base64,${makeWavBuffer(4).toString("base64")}`,
      }),
    });
    assert.equal(duplicateResponse.status, 409);
    assert.match((await duplicateResponse.json()).error, /同じ参照音声名/);

    const renameResponse = await fetch(`http://127.0.0.1:${address.port}/api/reference-voices/api_imported_voice/rename`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ newVoiceId: "api_renamed_voice" }),
    });
    const renamePayload = await renameResponse.json();
    assert.equal(renameResponse.status, 200);
    assert.deepEqual(renamePayload, { ok: true, previousVoiceId: "api_imported_voice", voiceId: "api_renamed_voice" });
    assert.equal(existsSync(path.join(tempRoot, "reference", "voices", "api_imported_voice")), false);
    assert.ok(existsSync(path.join(tempRoot, "reference", "voices", "api_renamed_voice", "voice.wav")));
    assert.ok(existsSync(path.join(tempRoot, "reference", "voices", "api_renamed_voice", "voice.txt")));
  } finally {
    await new Promise((resolve) => server.close(resolve));
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("browser-origin guard accepts localhost and rejects public websites", () => {
  assert.equal(isAllowedLocalBrowserOrigin(""), true);
  assert.equal(isAllowedLocalBrowserOrigin("http://127.0.0.1:5177"), true);
  assert.equal(isAllowedLocalBrowserOrigin("http://localhost:5173"), true);
  assert.equal(isAllowedLocalBrowserOrigin("https://example.com"), false);
  assert.equal(isAllowedLocalBrowserOrigin("null"), false);
});

test("YouTube reference URL and candidate audio routes are restricted", () => {
  assert.equal(normalizeYoutubeUrl("https://youtu.be/dQw4w9WgXcQ"), "https://youtu.be/dQw4w9WgXcQ");
  assert.throws(() => normalizeYoutubeUrl("https://example.com/audio"), /このURLには対応していません/);
  assert.deepEqual(
    parseYoutubeCandidateAudioRequest("/api/reference-voices/youtube/jobs/job_01/audio/c001/cleaned"),
    { jobId: "job_01", candidateId: "c001", variant: "cleaned" }
  );
  assert.equal(parseYoutubeCandidateAudioRequest("/api/reference-voices/youtube/jobs/../audio/c001/original"), null);
});

test("YouTube candidate registration copies the selected WAV and transcript", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-youtube-ref-"));
  try {
    const jobDir = path.join(tempRoot, "runtime", "youtube-reference", "job_01");
    mkdirSync(jobDir, { recursive: true });
    writeFileSync(path.join(jobDir, "c001-original.wav"), makeWavBuffer(4.5));
    writeFileSync(path.join(jobDir, "c001-vocals.wav"), makeWavBuffer(4.5));
    writeFileSync(path.join(jobDir, "result.json"), JSON.stringify({
      ok: true,
      jobId: "job_01",
      candidates: [{
        candidate_id: "c001",
        original_filename: "c001-original.wav",
        cleaned_filename: "c001-vocals.wav"
      }]
    }), "utf-8");

    await assert.rejects(
      registerYoutubeReferenceCandidate(tempRoot, {
        rightsConfirmed: false,
        jobId: "job_01",
        candidateId: "c001",
        voiceId: "unauthorized_voice",
        referenceText: "登録不可",
        useCleaned: true
      }),
      /利用許可/
    );
    const resolved = await resolveYoutubeCandidateAudioPath(tempRoot, { jobId: "job_01", candidateId: "c001", variant: "cleaned" });
    assert.equal(resolved, path.join(jobDir, "c001-vocals.wav"));
    const voice = await registerYoutubeReferenceCandidate(tempRoot, {
      rightsConfirmed: true,
      jobId: "job_01",
      candidateId: "c001",
      voiceId: "youtube_voice",
      referenceText: "許可済み動画から取得した文章です。",
      useCleaned: true
    });
    assert.equal(voice.voiceId, "youtube_voice");
    assert.ok(existsSync(path.join(tempRoot, "reference", "voices", "youtube_voice", "voice.wav")));
    assert.equal(
      readFileSync(path.join(tempRoot, "reference", "voices", "youtube_voice", "voice.txt"), "utf-8"),
      "許可済み動画から取得した文章です。\n"
    );
    await assert.rejects(
      registerYoutubeReferenceCandidate(tempRoot, {
        rightsConfirmed: true,
        jobId: "job_01",
        candidateId: "c001",
        voiceId: "youtube_voice",
        referenceText: "上書き",
        useCleaned: true
      }),
      /同じ参照音声名/
    );
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("normalizeRvcParams requires user-provided model paths and validates ranges", () => {
  assert.throws(() => normalizeRvcParams({ indexRate: "0.5", f0upKey: "2" }), /model path is required/i);
  const params = normalizeRvcParams({
    modelPath: "C:\\models\\sample.pth",
    indexPath: "C:\\models\\sample.index",
    indexRate: "0.5",
    f0upKey: "2"
  });
  assert.equal(params.indexRate, 0.5);
  assert.equal(params.f0method, "rmvpe");
  assert.equal(params.f0upKey, 2);
  assert.equal(params.modelPath, path.resolve("C:\\models\\sample.pth"));
  assert.throws(() => normalizeRvcParams({ modelPath: "C:\\models\\sample.pth", indexPath: "C:\\models\\sample.index", indexRate: 2 }), /index_rate/i);
  assert.throws(() => normalizeRvcParams({ modelPath: "C:\\models\\sample.pth", indexPath: "C:\\models\\sample.index", f0method: "bad method" }), /f0method/i);
});

test("normalizeSpeakChunking validates request chunking overrides", () => {
  const chunking = normalizeSpeakChunking({
    softChunkChars: "240",
    maxChunkChars: "324",
    hardLimitChars: "500",
    pauseBetweenChunksMs: "250"
  });
  assert.deepEqual(chunking, { softChunkChars: 240, maxChunkChars: 324, hardLimitChars: 500, pauseBetweenChunksMs: 250 });
  assert.throws(() => normalizeSpeakChunking({ softChunkChars: 5 }), /softChunkChars/i);
  assert.throws(() => normalizeSpeakChunking({ softChunkChars: 240, maxChunkChars: 120 }), /maxChunkChars/i);
});

test("shared TTS normalization preserves proxy controls and RVC-compatible fields", () => {
  assert.deepEqual(normalizeTtsRequest({
    text: "  共通検証です。 ", model: "sample", voiceId: "voice_1", seed: "42",
    speedScale: "0.85", styleStrength: "5", chunking: { softChunkChars: 240 },
  }), {
    text: "共通検証です。", model: "sample", voiceId: "voice_1", instruction: undefined,
    caption: undefined, styleCaption: undefined, language: undefined, seed: 42,
    chunking: { softChunkChars: 240, maxChunkChars: 320, hardLimitChars: 500, pauseBetweenChunksMs: 250 },
    format: "wav", speedScale: 0.85, styleStrength: 5,
  });
  assert.throws(() => normalizeTtsRequest({ text: "x", model: "sample", seed: "1.5" }), /seed must be an integer/i);
});

test("RVC model catalog discovers ready and incomplete models in the documented placement folder", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-rvc-models-"));
  try {
    const readyDir = path.join(tempRoot, "models", "rvc", "voice_a");
    const incompleteDir = path.join(tempRoot, "models", "rvc", "voice_b");
    mkdirSync(readyDir, { recursive: true });
    mkdirSync(incompleteDir, { recursive: true });
    writeFileSync(path.join(readyDir, "voice_a.pth"), "model");
    writeFileSync(path.join(readyDir, "voice_a.index"), "index");
    writeFileSync(path.join(incompleteDir, "voice_b.pth"), "model");
    const context = createRvcContext({ repoRoot: tempRoot, env: {} });
    const catalog = await listRvcModels(context);
    assert.equal(catalog.modelRoot, path.join(tempRoot, "models", "rvc"));
    assert.equal(catalog.readyCount, 1);
    assert.equal(catalog.models.find((model) => model.label === "voice_a")?.ready, true);
    assert.match(catalog.models.find((model) => model.label === "voice_b")?.errorReason || "", /\.index/);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("selected RVC model is staged into the runtime assets/weights folder without changing the source", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-rvc-stage-"));
  try {
    const rvcCwd = path.join(tempRoot, "runtime", "vendor", "rvc");
    const sourceDir = path.join(tempRoot, "models", "rvc", "voice_a");
    mkdirSync(rvcCwd, { recursive: true });
    mkdirSync(sourceDir, { recursive: true });
    const source = path.join(sourceDir, "voice_a.pth");
    writeFileSync(source, "model-data");
    const context = createRvcContext({ repoRoot: tempRoot, env: { LOCAL_TTS_RVC_CWD: rvcCwd } });
    const staged = await stageRvcModelForRuntime(context, source);
    assert.ok(staged.startsWith(path.join(rvcCwd, "assets", "weights")));
    assert.equal(readFileSync(staged, "utf-8"), "model-data");
    assert.equal(readFileSync(source, "utf-8"), "model-data");

    const nativeModel = path.join(rvcCwd, "assets", "weights", "native.pth");
    mkdirSync(path.dirname(nativeModel), { recursive: true });
    writeFileSync(nativeModel, "native-model-data");
    assert.equal(await stageRvcModelForRuntime(context, nativeModel), nativeModel);
  } finally {
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("RVC configuration can be injected without mutating process environment", () => {
  const context = createRvcContext({
    repoRoot: "C:\\isolated-repo",
    outputDir: "C:\\isolated-output",
    env: { LOCAL_TTS_RVC_ROOT: "C:\\rvc", LOCAL_TTS_RVC_MODEL_PATH: "C:\\models\\voice.pth" },
  });
  assert.equal(context.paths.outputDir, path.resolve("C:\\isolated-output"));
  assert.equal(context.defaults.cwd, path.resolve("C:\\rvc", "vendor", "rvc"));
  assert.equal(context.defaults.modelPath, "C:\\models\\voice.pth");
  assert.equal(normalizeRvcParams({ indexPath: "C:\\models\\voice.index" }, context).modelPath, path.resolve("C:\\models\\voice.pth"));
});

test("RVC artifact and runner boundaries use injected paths and executables", () => {
  const context = createRvcContext({ repoRoot: "C:\\repo", outputDir: "C:\\artifacts", env: {} });
  assert.equal(resolveInjectedRvcAudioPath(context, "converted", "result.wav"), path.resolve("C:\\artifacts", "converted", "result.wav"));
  assert.throws(() => resolveInjectedRvcAudioPath(context, "converted", "../result.wav"), /invalid rvc audio filename/i);
  const command = buildInjectedRvcCommand({ pythonPath: "C:\\python.exe", cwd: "C:\\rvc" }, { modelPath: "C:\\models\\voice.pth", indexPath: "C:\\models\\voice.index", indexRate: 0.5, f0method: "rmvpe", f0upKey: 0, filterRadius: 3, resampleSr: 0, rmsMixRate: 1, protect: 0.33 }, "in.wav", "out.wav");
  assert.equal(command.command, "C:\\python.exe");
  assert.equal(command.cwd, "C:\\rvc");
  assert.equal(command.args[command.args.indexOf("--model_name") + 1], "voice.pth");
});

test("RVC conversion service orchestrates injected TTS, input, and runner boundaries", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-rvc-service-"));
  const context = createRvcContext({ repoRoot: tempRoot, outputDir: path.join(tempRoot, "out"), env: { LOCAL_TTS_RVC_MODEL_PATH: path.join(tempRoot, "voice.pth"), LOCAL_TTS_RVC_INDEX_PATH: path.join(tempRoot, "voice.index") } });
  try {
    const result = await convertWithDependencies(context, { ttsBaseUrl: "http://tts.local" }, { text: "test", model: "sample", inputSource: "tts" }, {
      callTtsJson: async () => ({ ok: true, body: { audioUrl: "/audio.wav" } }),
      copyTtsAudio: async () => ({ source: "test" }),
      runRvcConvert: async () => ({ command: { command: "mock" }, stdout: "ok", stderr: "" }),
    });
    assert.equal(result.input.source, "tts");
    assert.equal(result.tts.request.format, "wav");
    assert.match(result.intermediate.url, /^\/api\/rvc\/audio\/intermediate\//);
    assert.match(result.converted.url, /^\/api\/rvc\/audio\/converted\//);
  } finally { rmSync(tempRoot, { recursive: true, force: true }); }
});

test("RVC conversion reports TTS as the first failed operation before RVC starts", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-rvc-tts-failure-"));
  const context = createRvcContext({ repoRoot: tempRoot, outputDir: path.join(tempRoot, "out"), env: { LOCAL_TTS_RVC_MODEL_PATH: path.join(tempRoot, "voice.pth"), LOCAL_TTS_RVC_INDEX_PATH: path.join(tempRoot, "voice.index") } });
  try {
    await assert.rejects(
      () => convertWithDependencies(context, { ttsBaseUrl: "http://tts.local" }, { text: "test", model: "irodori_v4_small", inputSource: "tts" }, {
        callTtsJson: async () => ({ ok: false, body: { requestId: "req-dead-worker", runtime: "irodori_voicedesign_direct", errorMessage: "Irodori runtimeが停止しました: worker process exited" } }),
      }),
      (error) => {
        assert.equal(error.message, "Irodori runtimeが停止しました: worker process exited");
        assert.equal(error.partialResult.stage, "tts");
        assert.equal(error.partialResult.firstFailedOperation, "POST /v1/speak");
        assert.equal(error.partialResult.rvcStarted, false);
        assert.equal(error.partialResult.tts.result.requestId, "req-dead-worker");
        return true;
      },
    );
  } finally { rmSync(tempRoot, { recursive: true, force: true }); }
});

test("rvcParamStem changes by index_rate for separate output files", () => {
  const base = normalizeRvcParams({
    modelPath: "C:\\models\\sample.pth",
    indexPath: "C:\\models\\sample.index",
    indexRate: 0.35
  });
  assert.notEqual(rvcParamStem(base), rvcParamStem({ ...base, indexRate: 0 }));
  assert.notEqual(rvcParamStem(base), rvcParamStem({ ...base, indexRate: 0.75 }));
});

test("buildRvcCommand passes model filename and absolute index path", () => {
  const params = normalizeRvcParams({
    modelPath: "C:\\models\\sample.pth",
    indexPath: "C:\\models\\sample.index",
    indexRate: 0.75,
    f0upKey: 6,
    protect: 0.45
  });
  const built = buildRvcCommand(params, "C:\\in\\a.wav", "C:\\out\\b.wav");
  assert.equal(built.args[built.args.indexOf("--model_name") + 1], "sample.pth");
  assert.equal(built.args[built.args.indexOf("--index_path") + 1], params.indexPath);
  assert.equal(built.args[built.args.indexOf("--index_rate") + 1], "0.75");
  assert.equal(built.args[built.args.indexOf("--f0up_key") + 1], "6");
  assert.equal(built.args[built.args.indexOf("--protect") + 1], "0.45");
});

test("resolveRvcAudioPath accepts only known output kinds and wav filenames", () => {
  assert.match(resolveRvcAudioPath("inputs", "sample.wav"), /sample\.wav$/);
  assert.match(resolveRvcAudioPath("intermediate", "sample.wav"), /sample\.wav$/);
  assert.match(resolveRvcAudioPath("converted", "sample.wav"), /sample\.wav$/);
  assert.throws(() => resolveRvcAudioPath("converted", "../bad.wav"), /invalid rvc audio filename/i);
  assert.throws(() => resolveRvcAudioPath("bad", "sample.wav"), /invalid rvc audio kind/i);
});

test("RVC audio responses include content length and support byte ranges", async () => {
  const tempRoot = mkdtempSync(path.join(os.tmpdir(), "tts-rvc-range-"));
  const context = createRvcContext({ repoRoot: tempRoot, env: {} });
  mkdirSync(context.paths.convertedDir, { recursive: true });
  const wav = makeWavBuffer(1.25);
  writeFileSync(path.join(context.paths.convertedDir, "range.wav"), wav);
  const server = createServer({ host: "127.0.0.1", port: 0, ttsBaseUrl: "http://127.0.0.1:1", rvcContext: context });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  try {
    const full = await fetch(`http://127.0.0.1:${address.port}/api/rvc/audio/converted/range.wav`);
    assert.equal(full.status, 200);
    assert.equal(Number(full.headers.get("content-length")), wav.length);
    assert.equal(full.headers.get("accept-ranges"), "bytes");
    assert.equal((await full.arrayBuffer()).byteLength, wav.length);

    const partial = await fetch(`http://127.0.0.1:${address.port}/api/rvc/audio/converted/range.wav`, {
      headers: { Range: "bytes=0-43" },
    });
    assert.equal(partial.status, 206);
    assert.equal(partial.headers.get("content-range"), `bytes 0-43/${wav.length}`);
    assert.equal(Number(partial.headers.get("content-length")), 44);
    assert.equal((await partial.arrayBuffer()).byteLength, 44);
  } finally {
    await new Promise((resolve) => server.close(resolve));
    rmSync(tempRoot, { recursive: true, force: true });
  }
});

test("external audio inputs convert non-wav formats before RVC", () => {
  assert.equal(shouldConvertAudioInputToWav("C:\\in\\sample.wav"), false);
  assert.equal(shouldConvertAudioInputToWav("C:\\in\\sample.WAV"), false);
  assert.equal(shouldConvertAudioInputToWav("C:\\in\\sample.m4a"), true);
  assert.equal(shouldConvertAudioInputToWav("C:\\in\\sample.mp3"), true);

  const args = buildFfmpegWavArgs("C:\\in\\sample.m4a", "C:\\out\\sample.wav");
  assert.deepEqual(args, ["-hide_banner", "-loglevel", "error", "-y", "-i", "C:\\in\\sample.m4a", "-ac", "1", "-ar", "40000", "C:\\out\\sample.wav"]);
});

test("post-RVC denoise keeps the original and applies a light voice filter", () => {
  const args = buildFfmpegVoiceDenoiseArgs("C:\\in\\converted.wav", "C:\\out\\converted-denoised.wav");
  assert.deepEqual(args.slice(0, 6), ["-hide_banner", "-loglevel", "error", "-y", "-i", "C:\\in\\converted.wav"]);
  assert.equal(args[args.indexOf("-af") + 1], "highpass=f=70,lowpass=f=16000,afftdn=nr=8:nf=-50:tn=1");
  assert.equal(args.at(-1), "C:\\out\\converted-denoised.wav");
});

test("WSL zero-shot models are included in the model catalog with unavailable reasons", () => {
  const catalogSource = readFileSync(path.join(process.cwd(), "public", "model-catalog.js"), "utf-8");
  const compareSource = readFileSync(path.join(process.cwd(), "public", "compare-page.js"), "utf-8");
  for (const modelId of ["sarashina2_2_tts", "fireredtts2", "t5gemma_tts_2b_2b", "fish_s1_mini"]) {
    assert.match(catalogSource, new RegExp(`DESIRED_MODELS[^;]*${modelId}`, "s"));
  }
  assert.match(compareSource, /model-unavailable-reason/);
  assert.match(compareSource, /model\?\.unavailableReason/);
});

test("frontend initialization has a bounded wait and an explicit failure message", () => {
  const appSource = readFileSync(path.join(process.cwd(), "public", "app.js"), "utf-8");
  assert.match(appSource, /INITIAL_DATA_TIMEOUT_MS/);
  assert.match(appSource, /AbortSignal\.timeout\(INITIAL_DATA_TIMEOUT_MS\)/);
  assert.match(appSource, /初期化に失敗しました/);
});

test("frontend entrypoints delegate subsystem responsibilities", () => {
  const serverSource = readFileSync(path.join(process.cwd(), "server.js"), "utf-8");
  for (const modulePath of ["./server/http-utils.js", "./server/reference-voices.js", "./server/rvc-service.js"]) {
    assert.ok(serverSource.includes(modulePath), `${modulePath} must be imported by server.js`);
  }

  const indexSource = readFileSync(path.join(process.cwd(), "public", "index.html"), "utf-8");
  const appSource = readFileSync(path.join(process.cwd(), "public", "app.js"), "utf-8");
  const scripts = [
    "tts-api-client.js",
    "model-catalog.js",
    "model-capabilities.js",
    "rvc-chunking.js",
    "avatar-sync.js",
    "normal-page.js",
    "compare-page.js",
    "rvc-page.js",
    "app.js",
  ];
  let previousIndex = -1;
  for (const script of scripts) {
    const currentIndex = indexSource.indexOf(script);
    assert.ok(currentIndex > previousIndex, `${script} must be loaded after the previous dependency`);
    previousIndex = currentIndex;
  }
  for (const functionName of ["generateNormal", "generateCompare", "generateRvc"]) {
    assert.doesNotMatch(appSource, new RegExp(`function\\s+${functionName}\\b`));
  }
  assert.ok(appSource.split(/\r?\n/).length < 1000, "app.js must remain an orchestration module under 1000 lines");

  const pythonServerSource = readFileSync(path.join(process.cwd(), "..", "src", "local_tts_service", "server.py"), "utf-8");
  assert.ok(pythonServerSource.split(/\r?\n/).length < 450, "server.py must remain an HTTP composition module under 450 lines");
  assert.match(pythonServerSource, /from \.api\.app import create_app/);
  assert.match(pythonServerSource, /app\s*=\s*create_app\(\)/);
});

test("all generation tabs expose persistent seed and autoplay controls", () => {
  const indexSource = readFileSync(path.join(process.cwd(), "public", "index.html"), "utf-8");
  const uiSource = ["app.js", "normal-page.js", "compare-page.js", "rvc-page.js"]
    .map((filename) => readFileSync(path.join(process.cwd(), "public", filename), "utf-8"))
    .join("\n");

  for (const scope of ["normal", "compare", "rvc"]) {
    assert.match(indexSource, new RegExp(`id="${scope}SeedInput"[^>]*value="1"`));
    assert.match(indexSource, new RegExp(`id="${scope}SeedAutoIncrementInput"[^>]*checked`));
    assert.match(indexSource, new RegExp(`id="${scope}AutoPlayInput"`));
  }
  assert.equal((indexSource.match(/生成後に音声を自動再生/g) || []).length, 3);
  assert.doesNotMatch(indexSource, /id="normalRetryButton"/);
  assert.match(indexSource, /同じ設定・seedで再生成/);
  assert.match(indexSource, /長文は発音や抑揚が不安定/);
  assert.match(indexSource, /短く分けて生成し[^<]*結合/);
  for (const token of [
    "NORMAL_FORM_SETTINGS_KEY",
    "COMPARE_FORM_SETTINGS_KEY",
    "RVC_FORM_SETTINGS_KEY",
    "saveNormalFormSettings",
    "saveCompareFormSettings",
    "saveRvcFormSettings",
    "playNormalResultIfEnabled",
    "playCompareResultIfEnabled",
    "playRvcResultIfEnabled",
    "regenerateLastNormalRequest",
  ]) {
    assert.match(uiSource, new RegExp(token));
  }
});

test("reference audio, concise guidance, diagnostics, and recent history are user-oriented", () => {
  const indexSource = readFileSync(path.join(process.cwd(), "public", "index.html"), "utf-8");
  const styleSource = readFileSync(path.join(process.cwd(), "public", "style.css"), "utf-8");
  const uiSource = ["app.js", "normal-page.js", "compare-page.js", "rvc-page.js"]
    .map((filename) => readFileSync(path.join(process.cwd(), "public", filename), "utf-8"))
    .join("\n");
  const historySource = readFileSync(path.join(process.cwd(), "public", "history.js"), "utf-8");

  assert.match(indexSource, /id="serviceStatus" data-state="checking"/);
  assert.doesNotMatch(indexSource, /<strong><i><\/i>稼働中<\/strong>/);
  assert.match(indexSource, /id="normalReferenceField"/);
  assert.match(indexSource, /id="normalUseReference"/);
  assert.match(indexSource, /id="normalReferenceRequirement"/);
  assert.match(indexSource, /id="normalInstructionRequirement"/);
  assert.match(uiSource, /updateNormalReferenceUi/);
  assert.match(uiSource, /updateNormalRequirementLabels/);
  assert.match(uiSource, /updateIrodoriEmojiPaletteVisibility/);
  assert.match(uiSource, /isIrodoriModel/);
  assert.match(uiSource, /normalUseReference/);
  assert.match(uiSource, /restoreNormalHistoryItem/);
  assert.match(uiSource, /restoreCompareHistoryItem/);

  for (const id of ["normalLogCopyButton", "compareLogCopyButton", "rvcLogCopyButton", "normalLogBox", "compareLogBox", "rvcLogBox"]) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(uiSource, /buildAiDiagnosticLog/);
  assert.match(uiSource, /diagnosticResolutionHints/);
  assert.match(uiSource, /os error 1455/);
  assert.match(uiSource, /setNormalGenerationActive/);
  assert.match(uiSource, /setCompareGenerationActive/);
  assert.match(uiSource, /setRvcGenerationActive/);
  assert.match(uiSource, /normalModel\.disabled = normalGenerationActive/);
  assert.match(uiSource, /rvcModel\.disabled = rvcGenerationActive/);

  assert.match(indexSource, /id="normalAdvancedSettings"/);
  assert.match(indexSource, /id="compareAdvancedSettings"/);
  assert.doesNotMatch(indexSource, /<details[^>]+id="(?:normal|compare)AdvancedSettings"[^>]+open/);
  assert.doesNotMatch(indexSource, /必要なら調整/);
  assert.doesNotMatch(indexSource, /このモデルの特徴/);
  assert.doesNotMatch(indexSource, /モデル選びのヒント/);
  assert.doesNotMatch(indexSource, /id="compareRankingList"/);
  assert.match(styleSource, /grid-template-columns:\s*repeat\(5, minmax\(0, 1fr\)\)/);

  assert.match(indexSource, /RVC-Project\/Retrieval-based-Voice-Conversion-WebUI/);
  assert.match(indexSource, /学習済みRVCモデル/);
  assert.match(indexSource, /使用する動画・音声の権利や利用規約を確認しました/);
  assert.match(indexSource, /動画URLから登録/);
  assert.match(indexSource, /<span>動画URL <b>必須<\/b><\/span>/);
  assert.match(indexSource, /id="youtubeReferenceUrlInput"[^>]+placeholder="https:\/\/\.\.\."/);
  assert.doesNotMatch(indexSource, /YouTube/);
  assert.match(indexSource, /モデルと使用音声の利用条件/);
  assert.doesNotMatch(indexSource, /自分が権利を持つ動画、または音声の利用・加工について明確な許可/);
  assert.equal((indexSource.match(/aria-label="長文分割の説明"/g) || []).length, 3);
  assert.doesNotMatch(indexSource, /<p class="chunk-reason">/);
  assert.doesNotMatch(indexSource, /data-tip="[^"]*ページを再読み込みしても保持/);
  for (const id of ["historyResultSummary", "historyLoadMoreButton", "historyClearAllButton"]) {
    assert.match(indexSource, new RegExp(`id="${id}"`));
  }
  assert.match(historySource, /const HISTORY_PAGE_SIZE = 20/);
  assert.match(historySource, /const MAX_DIAGNOSTIC_TEXT_CHARS = 6000/);
  assert.match(historySource, /if \(historyPageActive\(\)\) renderHistory\(\)/);
  assert.match(historySource, /local-tts:history-clear-all/);
});

test("in-app guide and reference voice registration are ordered by the next user task", () => {
  const indexSource = readFileSync(path.join(process.cwd(), "public", "index.html"), "utf-8");
  const guideHeadings = [
    "1. 最初の音声を作る",
    "2. やりたいことを選ぶ",
    "3. 見本の声に寄せたい場合",
    "4. 困ったとき",
    "5. 注意事項",
  ];
  let previousIndex = -1;
  for (const heading of guideHeadings) {
    const currentIndex = indexSource.indexOf(heading);
    assert.ok(currentIndex > previousIndex, `${heading} must appear after the previous guide section`);
    previousIndex = currentIndex;
  }
  assert.doesNotMatch(indexSource, /class="guide-mode-grid"/);
  assert.doesNotMatch(indexSource, /class="panel guide-combined-panel"/);
  assert.doesNotMatch(indexSource, /id="guideRequirementsTable"/);
  assert.doesNotMatch(indexSource, /長文を分割して生成する理由/);
  for (const tab of ["normal", "compare", "rvc"]) {
    assert.match(indexSource, new RegExp(`data-guide-target="${tab}"`));
  }
  assert.match(indexSource, /data-voice-open="register"/);

  assert.match(indexSource, /data-voice-view="register"[^>]*>新しく登録</);
  assert.match(indexSource, /data-voice-view="manage"[^>]*>登録済み音声</);
  for (const method of ["mic", "file", "youtube"]) {
    assert.match(indexSource, new RegExp(`data-voice-method="${method}"`));
    assert.match(indexSource, new RegExp(`data-voice-method-panel="${method}"`));
  }
  assert.match(indexSource, /accept="\.wav,\.mp3,\.m4a,\.flac,\.ogg,\.aac,audio\/\*"/);
  assert.match(indexSource, /3〜10秒/);
  assert.match(indexSource, /BGMやノイズが少ない/);
  assert.match(indexSource, /id="voiceRegistrationSuccess"/);
});

test("server responds to the static root page", async () => {
  const server = createServer({ host: "127.0.0.1", port: 0, ttsBaseUrl: "http://127.0.0.1:1" });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  try {
    const response = await fetch(`http://127.0.0.1:${address.port}/`, { signal: AbortSignal.timeout(2000) });
    assert.equal(response.status, 200);
    assert.match(await response.text(), /Local TTS|ローカルTTS/i);
    const guideResponse = await fetch(`http://127.0.0.1:${address.port}/rvc-model-guide.html`, { signal: AbortSignal.timeout(2000) });
    assert.equal(guideResponse.status, 200);
    const guideHtml = await guideResponse.text();
    assert.match(guideHtml, /models\\rvc\\my_voice/);
    assert.match(guideHtml, /\.pth/);
    assert.match(guideHtml, /\.index/);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
