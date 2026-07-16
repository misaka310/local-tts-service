import { spawn, spawnSync } from "node:child_process";
import { promises as fs } from "node:fs";
import net from "node:net";
import path from "node:path";
import { createServer } from "../server.js";

const CHROME_PATH = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const TARGET_TEXT = "こんにちは。音声生成の確認です。日本語を自然に読み上げられるか確認しています。";
const FRONTEND_DIR = process.cwd();
const REPO_ROOT = path.resolve(FRONTEND_DIR, "..");
const RESULT_PATH = path.join(REPO_ROOT, "runtime", "logs", "e2e-wsl-models-live-result.json");

const delay = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

async function getFreePort() {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  const address = server.address();
  const port = typeof address === "object" && address ? address.port : 0;
  await new Promise((resolve) => server.close(resolve));
  ensure(port > 0, "failed to reserve a backend port");
  return port;
}

function terminateProcessTree(processId) {
  if (!processId) return;
  if (process.platform === "win32") {
    spawnSync("taskkill.exe", ["/PID", String(processId), "/T", "/F"], {
      windowsHide: true,
      stdio: "ignore",
      timeout: 10000,
    });
    return;
  }
  try {
    process.kill(-processId, "SIGTERM");
  } catch {
    try { process.kill(processId, "SIGTERM"); } catch { /* already stopped */ }
  }
}

async function waitForBackend(baseUrl, child, logs) {
  const deadline = Date.now() + 120000;
  let lastError = "not started";
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      throw new Error(`backend exited before startup: code=${child.exitCode}\n${logs.stderr.slice(-4000)}`);
    }
    try {
      const response = await fetch(`${baseUrl}/v1/models`, { signal: AbortSignal.timeout(30000) });
      if (response.ok) return await response.json();
      lastError = `HTTP ${response.status}`;
    } catch (error) {
      lastError = error.message || String(error);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`backend startup timed out: ${lastError}\n${logs.stderr.slice(-4000)}`);
}

async function startIsolatedBackend() {
  const port = await getFreePort();
  const baseUrl = `http://127.0.0.1:${port}`;
  const configPath = path.join(REPO_ROOT, "config", "config.local.json");
  const config = JSON.parse(await fs.readFile(configPath, "utf8"));
  config.host = "127.0.0.1";
  config.port = port;

  const tempDir = path.join(REPO_ROOT, "runtime", "requests");
  await fs.mkdir(tempDir, { recursive: true });
  const tempConfigPath = path.join(tempDir, `e2e-live-config-${process.pid}-${Date.now()}.json`);
  await fs.writeFile(tempConfigPath, `${JSON.stringify(config, null, 2)}\n`, "utf8");

  const pythonPath = path.join(REPO_ROOT, ".venv", "Scripts", "python.exe");
  const logs = { stdout: "", stderr: "" };
  const child = spawn(pythonPath, ["-m", "local_tts_service.server"], {
    cwd: REPO_ROOT,
    windowsHide: true,
    detached: process.platform !== "win32",
    env: {
      ...process.env,
      PYTHONPATH: path.join(REPO_ROOT, "src"),
      PYTHONIOENCODING: "utf-8",
      PYTHONUTF8: "1",
      LOCAL_TTS_CONFIG_PATH: tempConfigPath
    },
    stdio: ["ignore", "pipe", "pipe"]
  });
  child.stdout.on("data", (chunk) => { logs.stdout = (logs.stdout + chunk.toString("utf8")).slice(-20000); });
  child.stderr.on("data", (chunk) => { logs.stderr = (logs.stderr + chunk.toString("utf8")).slice(-20000); });

  try {
    const modelsPayload = await waitForBackend(baseUrl, child, logs);
    return { baseUrl, child, logs, tempConfigPath, modelsPayload };
  } catch (error) {
    terminateProcessTree(child.pid);
    await fs.rm(tempConfigPath, { force: true });
    throw error;
  }
}

async function main() {
  let backend = null;
  let frontendServer = null;
  let browser = null;
  await fs.mkdir(path.dirname(RESULT_PATH), { recursive: true });
  await fs.rm(RESULT_PATH, { force: true });
  try {
    console.log("[LIVE E2E] starting isolated backend");
    backend = await startIsolatedBackend();
    console.log(`[LIVE E2E] backend ready: ${backend.baseUrl}`);
    const modelMap = new Map((backend.modelsPayload.models || []).map((item) => [item.id || item.model, item]));
    const wslModelIds = ["sarashina2_2_tts", "fireredtts2", "t5gemma_tts_2b_2b", "fish_s1_mini"];
    for (const modelId of wslModelIds) {
      ensure(modelMap.get(modelId)?.available === true, `${modelId} is unavailable in the isolated backend`);
    }

    frontendServer = createServer({ host: "127.0.0.1", port: 0, ttsBaseUrl: backend.baseUrl });
    await new Promise((resolve) => frontendServer.listen(0, "127.0.0.1", resolve));
    const address = frontendServer.address();
    const frontBase = `http://127.0.0.1:${address.port}`;

    const { chromium } = await import("playwright-core");
    browser = await chromium.launch({
      headless: true,
      executablePath: CHROME_PATH,
      args: ["--autoplay-policy=no-user-gesture-required"]
    });
    const page = await browser.newPage({ viewport: { width: 1752, height: 900 } });
    await page.addInitScript(() => window.localStorage.clear());
    await page.goto(frontBase, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForSelector("#normalModelSelect option", { state: "attached", timeout: 60000 });

    const options = await page.locator("#normalModelSelect option").evaluateAll((nodes) =>
      nodes.map((node) => ({ value: node.value, text: node.textContent || "", disabled: node.disabled }))
    );
    for (const modelId of wslModelIds) {
      const option = options.find((item) => item.value === modelId);
      ensure(option && !option.disabled, `${modelId} is not selectable in live normal generation`);
    }

    await page.locator('.top-tab[data-tab="compare"]').click();
    await page.waitForSelector("#comparePage.active");
    for (const modelId of wslModelIds) {
      const card = page.locator(`[data-model-card="${modelId}"]`);
      ensure(await card.count() === 1, `${modelId} live comparison card is missing`);
      ensure(!(await card.locator("input").isDisabled()), `${modelId} live comparison card is disabled`);
    }

    await page.locator('.top-tab[data-tab="normal"]').click();
    await page.waitForSelector("#normalPage.active");
    await page.selectOption("#normalModelSelect", "t5gemma_tts_2b_2b");
    const requestedReferenceVoice = process.env.LOCAL_TTS_E2E_REFERENCE_VOICE || "";
    const referenceOptions = await page.locator("#normalReferenceVoiceSelect option").evaluateAll((nodes) =>
      nodes.map((node) => ({ value: node.value, disabled: node.disabled }))
    );
    const referenceOption = requestedReferenceVoice
      ? referenceOptions.find((item) => item.value === requestedReferenceVoice && !item.disabled)
      : referenceOptions.find((item) => item.value && !item.disabled);
    ensure(referenceOption, requestedReferenceVoice
      ? `requested reference voice is unavailable: ${requestedReferenceVoice}`
      : "no usable reference voice is available for live generation");
    await page.selectOption("#normalReferenceVoiceSelect", referenceOption.value);
    await page.fill("#normalTextInput", TARGET_TEXT);
    await page.fill("#normalSeedInput", "260711");
    ensure(!(await page.locator("#normalGenerateButton").isDisabled()), "live generate button is disabled");

    console.log("[LIVE E2E] clicking T5Gemma generate button");
    const generationStartedMs = Date.now();
    const speakResponsePromise = page.waitForResponse(
      (response) => response.url().endsWith("/api/speak") && response.request().method() === "POST",
      { timeout: 300000 }
    );
    await page.click("#normalGenerateButton");
    const speakResponse = await speakResponsePromise;
    const responseText = await speakResponse.text();
    let speakPayload = {};
    try {
      speakPayload = responseText ? JSON.parse(responseText) : {};
    } catch {
      throw new Error(`live /api/speak returned invalid JSON: ${responseText.slice(0, 500)}`);
    }
    ensure(speakResponse.ok(), `live /api/speak failed: HTTP ${speakResponse.status()} ${responseText.slice(0, 1000)}`);
    ensure(speakPayload.ok === true, `live /api/speak returned ok=false: ${responseText.slice(0, 1000)}`);
    ensure(speakPayload.result?.model === "t5gemma_tts_2b_2b", `unexpected live model: ${speakPayload.result?.model}`);

    await page.waitForFunction(
      () => document.querySelector("#normalStatusText")?.textContent === "生成が完了しました。",
      null,
      { timeout: 300000 }
    );
    await page.waitForSelector("#normalResultCard:not([hidden])", { timeout: 300000 });
    await page.waitForFunction(
      () => {
        const audio = document.querySelector("#normalAudioPlayer");
        return Boolean(audio && audio.getAttribute("src") && Number.isFinite(audio.duration) && audio.duration > 0 && audio.readyState >= 1);
      },
      null,
      { timeout: 60000 }
    );

    const audioResult = await page.locator("#normalAudioPlayer").evaluate((audio) => ({
      src: audio.currentSrc || audio.src || "",
      duration: audio.duration,
      readyState: audio.readyState
    }));
    const generatedAudioPath = String(speakPayload.result.audioPath || "");
    ensure(generatedAudioPath, "live response did not include audioPath");
    const generatedAudioStat = await fs.stat(generatedAudioPath);
    audioResult.bytes = generatedAudioStat.size;
    audioResult.fileMtimeMs = generatedAudioStat.mtimeMs;
    ensure(audioResult.bytes > 44, `generated WAV is too small: ${audioResult.bytes}`);
    ensure(audioResult.duration > 0, `generated WAV duration is invalid: ${audioResult.duration}`);
    ensure(generatedAudioStat.mtimeMs >= generationStartedMs - 2000, "frontend returned an old WAV instead of a newly generated file");

    const result = {
      ok: true,
      frontBase,
      ttsBaseUrl: backend.baseUrl,
      model: speakPayload.result.model,
      voiceId: speakPayload.result.voiceId,
      audioPath: generatedAudioPath,
      audioUrl: speakPayload.result.audioUrl,
      frontendAudio: audioResult,
      availableModels: wslModelIds
    };
    await fs.writeFile(RESULT_PATH, `${JSON.stringify(result, null, 2)}\n`, "utf8");
    console.log("[LIVE E2E] result written");
    console.log(JSON.stringify(result, null, 2));
  } finally {
    if (browser) await Promise.race([browser.close().catch(() => {}), delay(5000)]);
    if (frontendServer) {
      frontendServer.closeIdleConnections?.();
      frontendServer.closeAllConnections?.();
      frontendServer.close(() => {});
    }
    if (backend) {
      terminateProcessTree(backend.child.pid);
      backend.child.stdout?.destroy();
      backend.child.stderr?.destroy();
      await fs.rm(backend.tempConfigPath, { force: true });
    }
  }
}

main().then(() => {
  // This is a standalone E2E runner. Exit after bounded cleanup so stale
  // browser/backend handles cannot keep CI or Codex verification alive.
  process.exit(0);
}).catch(async (error) => {
  const result = { ok: false, error: error.message, stack: error.stack };
  await fs.mkdir(path.dirname(RESULT_PATH), { recursive: true }).catch(() => {});
  await fs.writeFile(RESULT_PATH, `${JSON.stringify(result, null, 2)}\n`, "utf8").catch(() => {});
  console.error(JSON.stringify(result, null, 2));
  process.exit(1);
});
