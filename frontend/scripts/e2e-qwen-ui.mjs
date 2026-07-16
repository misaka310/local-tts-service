import { createServer } from "../server.js";

const CHROME_PATH = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

function makeWavDataUrl(durationSec = 0.25, sampleRate = 16000) {
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
  for (let i = 0; i < samples; i += 1) {
    const value = Math.round(Math.sin((i / sampleRate) * Math.PI * 2 * 440) * 4000);
    buffer.writeInt16LE(value, 44 + i * 2);
  }
  return `data:audio/wav;base64,${buffer.toString("base64")}`;
}

async function audioState(locator) {
  return locator.evaluate(async (audio) => {
    audio.load();
    await audio.play();
    await new Promise((resolve) => setTimeout(resolve, 450));
    const src = audio.currentSrc || audio.src || "";
    return {
      hasSrc: Boolean(src),
      srcPrefix: src.slice(0, 24),
      paused: audio.paused,
      readyState: audio.readyState,
      duration: audio.duration
    };
  });
}

async function main() {
  const server = createServer({
    host: "127.0.0.1",
    port: 0,
    ttsBaseUrl: "http://127.0.0.1:1"
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const frontBase = `http://127.0.0.1:${address.port}`;

  const { chromium } = await import("playwright-core");
  const browser = await chromium.launch({
    headless: true,
    executablePath: CHROME_PATH,
    args: ["--autoplay-policy=no-user-gesture-required"]
  });

  const page = await browser.newPage({ viewport: { width: 1752, height: 831 } });
  await page.addInitScript(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: { writeText: async (value) => { window.__lastClipboardText = String(value || ""); } }
    });
  });
  await page.addInitScript(() => {
    const fakeDevices = [{ kind: "audioinput", deviceId: "voice-mic", label: "Fake Voice Microphone" }];
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        enumerateDevices: async () => fakeDevices,
        getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }),
        addEventListener: () => {},
        removeEventListener: () => {}
      }
    });
    class FakeMediaRecorder {
      static isTypeSupported() { return true; }
      constructor(stream, options = {}) {
        this.stream = stream;
        this.mimeType = options.mimeType || "audio/webm";
        this.state = "inactive";
        this.ondataavailable = null;
        this.onstop = null;
      }
      start() { this.state = "recording"; }
      stop() {
        if (this.state !== "recording") return;
        this.state = "inactive";
        this.ondataavailable?.({ data: new Blob(["fake-reference-audio"], { type: this.mimeType }) });
        queueMicrotask(() => this.onstop?.());
      }
    }
    window.MediaRecorder = FakeMediaRecorder;
  });
  const pendingRequests = new Map();
  const browserErrors = [];
  page.on("request", (request) => pendingRequests.set(request, request.url()));
  page.on("requestfinished", (request) => pendingRequests.delete(request));
  page.on("requestfailed", (request) => pendingRequests.delete(request));
  page.on("pageerror", (error) => browserErrors.push(error.message || String(error)));
  page.on("console", (message) => {
    if (message.type() === "error") browserErrors.push(message.text());
  });
  const audioUrls = [makeWavDataUrl(1.5), makeWavDataUrl(1.7)];
  const referenceAudioUrl = makeWavDataUrl(3);
  let speakCount = 0;
  let failNextSpeak = false;
  let failSpeakModel = "";
  let slowCompareGeneration = false;
  let compareRequestOrdinal = 0;
  const speakBodies = [];
  let referenceVoiceSaveCount = 0;
  let referenceTextSaveCount = 0;
  let referenceArchiveChangeCount = 0;
  let youtubeCandidateRequestCount = 0;
  let youtubeRegisterCount = 0;
  const referenceVoices = [
    {
      voiceId: "sample_neutral",
      displayName: "sample_neutral",
      enabled: true,
      archived: false,
      hasReferenceAudio: true,
      hasReferenceText: true,
      audioDurationSec: 5,
      minReferenceDurationSec: 3,
      maxReferenceDurationSec: 10,
      referenceText: "これは既存の参照音声テキストです。",
      audioUrl: "/api/reference-voices/sample_neutral/audio"
    }
  ];

  await page.route("**/api/models", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        models: [
          {
            id: "qwen3_tts_clone_1_7b",
            model: "qwen3_tts_clone_1_7b",
            label: "Qwen3-TTS Voice Clone 1.7B",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: true,
            requiresReferenceText: true,
            supportsInstruction: true
          },
          {
            id: "sarashina2_2_tts",
            model: "sarashina2_2_tts",
            label: "Sarashina2.2-TTS",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: true,
            requiresReferenceText: true,
            supportsInstruction: false
          },
          {
            id: "fireredtts2",
            model: "fireredtts2",
            label: "FireRedTTS-2",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: true,
            requiresReferenceText: true,
            supportsInstruction: false
          },
          {
            id: "t5gemma_tts_2b_2b",
            model: "t5gemma_tts_2b_2b",
            label: "T5Gemma-TTS 2B-2B",
            available: false,
            enabled: false,
            unavailableReason: "モデル重みが未導入です。Hugging Faceの利用条件への同意が必要です。",
            supportsReferenceVoice: true,
            requiresReferenceAudio: true,
            requiresReferenceText: true,
            supportsInstruction: false
          },
          {
            id: "fish_s1_mini",
            model: "fish_s1_mini",
            label: "FishAudio S1-mini",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: true,
            requiresReferenceText: true,
            supportsInstruction: false
          },
          {
            id: "irodori_v3",
            model: "irodori_v3",
            label: "Irodori v3",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: false,
            supportsInstruction: false,
            supportsSpeedControl: true,
            executionDevice: "cpu",
            cpuFallback: true,
            performanceWarning: "IrodoriはCPUで動作しています。GPU動作より大幅に遅く、音声生成に数分かかる場合があります。"
          },
          {
            id: "irodori_v2",
            model: "irodori_v2",
            label: "Irodori v2",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: false,
            supportsInstruction: false,
            supportsSpeedControl: false,
            executionDevice: "cpu",
            cpuFallback: true,
            performanceWarning: "IrodoriはCPUで動作しています。GPU動作より大幅に遅く、音声生成に数分かかる場合があります。"
          },
          {
            id: "irodori_v3_voicedesign",
            model: "irodori_v3_voicedesign",
            label: "Irodori v3 VoiceDesign",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: false,
            supportsInstruction: true,
            supportsSpeedControl: true,
            supportsStyleStrength: true
          }
        ]
      })
    });
  });
  await page.route("**/api/reference-voices", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        defaultReferenceVoice: "sample_neutral",
        voices: [
          {
            voiceId: "sample_neutral",
            displayName: "sample_neutral",
            enabled: true,
            hasReferenceText: true,
            audioDurationSec: 5,
            minReferenceDurationSec: 3,
            maxReferenceDurationSec: 10
          }
        ]
      })
    });
  });
  await page.route("**/api/reference-voices", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      const body = request.postDataJSON();
      referenceVoiceSaveCount += 1;
      const voice = {
        voiceId: body.voiceId,
        displayName: body.voiceId,
        enabled: true,
        archived: false,
        hasReferenceAudio: true,
        hasReferenceText: true,
        audioDurationSec: 4.2,
        minReferenceDurationSec: 3,
        maxReferenceDurationSec: 10,
        referenceText: body.referenceText,
        audioUrl: `/api/reference-voices/${encodeURIComponent(body.voiceId)}/audio`
      };
      const existingIndex = referenceVoices.findIndex((item) => item.voiceId === voice.voiceId);
      if (existingIndex >= 0) referenceVoices[existingIndex] = voice;
      else referenceVoices.push(voice);
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, voice }) });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ok: true, backendAvailable: true, defaultReferenceVoice: "sample_neutral", voices: referenceVoices })
    });
  });
  await page.route("**/api/reference-voices/*/text", async (route) => {
    const voiceId = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-2));
    const body = route.request().postDataJSON();
    const voice = referenceVoices.find((item) => item.voiceId === voiceId);
    if (voice) {
      voice.referenceText = body.referenceText;
      voice.hasReferenceText = Boolean(body.referenceText);
      referenceTextSaveCount += 1;
    }
    await route.fulfill({ status: voice ? 200 : 404, contentType: "application/json", body: JSON.stringify(voice ? { ok: true, voiceId, referenceText: body.referenceText } : { ok: false, error: "not found" }) });
  });
  await page.route("**/api/reference-voices/*/archive", async (route) => {
    const voiceId = decodeURIComponent(new URL(route.request().url()).pathname.split("/").at(-2));
    const body = route.request().postDataJSON();
    const voice = referenceVoices.find((item) => item.voiceId === voiceId);
    if (voice) {
      voice.archived = Boolean(body.archived);
      voice.enabled = !voice.archived;
      voice.errorReason = voice.archived ? "archived" : null;
      referenceArchiveChangeCount += 1;
    }
    await route.fulfill({ status: voice ? 200 : 404, contentType: "application/json", body: JSON.stringify(voice ? { ok: true, voiceId, archived: voice.archived } : { ok: false, error: "not found" }) });
  });
  await page.route("**/api/reference-voices/youtube/candidates", async (route) => {
    const body = route.request().postDataJSON();
    youtubeCandidateRequestCount += 1;
    ensure(body.rightsConfirmed === true, "YouTube candidate request must confirm usage rights");
    ensure(body.useDemucs === true, "YouTube candidate request should enable Demucs in this test");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        jobId: "job_e2e",
        title: "許可済みテスト動画",
        transcriptSource: "subtitle:source.ja.vtt",
        candidates: [
          {
            candidate_id: "c001",
            start_sec: 12.3,
            end_sec: 18.1,
            duration_sec: 5.8,
            score: 97,
            text: "字幕から取得した最初の候補です。",
            originalAudioUrl: "/api/reference-voices/youtube/jobs/job_e2e/audio/c001/original",
            cleanedAudioUrl: "/api/reference-voices/youtube/jobs/job_e2e/audio/c001/cleaned",
            audioUrl: "/api/reference-voices/youtube/jobs/job_e2e/audio/c001/cleaned",
            demucsApplied: true
          },
          {
            candidate_id: "c002",
            start_sec: 31.0,
            end_sec: 36.2,
            duration_sec: 5.2,
            score: 91,
            text: "字幕から取得した二つ目の候補です。",
            originalAudioUrl: "/api/reference-voices/youtube/jobs/job_e2e/audio/c002/original",
            audioUrl: "/api/reference-voices/youtube/jobs/job_e2e/audio/c002/original",
            demucsApplied: false,
            demucsError: "テスト用Demucs失敗"
          }
        ]
      })
    });
  });
  await page.route("**/api/reference-voices/youtube/register", async (route) => {
    const body = route.request().postDataJSON();
    youtubeRegisterCount += 1;
    const voice = {
      voiceId: body.voiceId,
      displayName: body.voiceId,
      enabled: true,
      archived: false,
      hasReferenceAudio: true,
      hasReferenceText: true,
      audioDurationSec: 5.8,
      referenceText: body.referenceText,
      audioUrl: `/api/reference-voices/${encodeURIComponent(body.voiceId)}/audio`
    };
    referenceVoices.push(voice);
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, voice }) });
  });
  await page.route("**/api/reference-voices/youtube/jobs/*/audio/*/*", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "audio/wav",
      body: Buffer.from(referenceAudioUrl.split(",")[1], "base64")
    });
  });
  await page.route("**/api/reference-voices/*/audio", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "audio/wav",
      body: Buffer.from(referenceAudioUrl.split(",")[1], "base64")
    });
  });
  await page.route("**/api/rvc/defaults", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        defaults: {
          indexRate: 0.35,
          f0method: "rmvpe",
          f0upKey: 0,
          filterRadius: 3,
          resampleSr: 0,
          rmsMixRate: 1,
          protect: 0.33,
          modelPath: "C:\\models\\sample-rvc-model.pth",
          indexPath: "C:\\models\\added.index",
          inputSource: "mic",
          externalAudioPath: "",
          cleanExternalAudio: false,
          demucsModel: "htdemucs_ft"
        },
        modelRoot: "C:\\models\\rvc",
        readyCount: 1,
        guideUrl: "/rvc-model-guide.html",
        models: [{
          id: "sample-rvc",
          label: "sample-rvc",
          modelPath: "C:\\models\\sample-rvc-model.pth",
          indexPath: "C:\\models\\added.index",
          ready: true,
          errorReason: ""
        }]
      })
    });
  });
  await page.route("**/api/speak", async (route) => {
    const request = route.request();
    const body = request.postDataJSON();
    speakBodies.push(body);
    const shouldFailNext = failNextSpeak;
    const shouldFailModel = Boolean(failSpeakModel && body.model === failSpeakModel);
    if (shouldFailNext) failNextSpeak = false;
    if (shouldFailModel) failSpeakModel = "";
    if (slowCompareGeneration) {
      const ordinal = compareRequestOrdinal;
      compareRequestOrdinal += 1;
      if (ordinal > 0) await new Promise((resolve) => setTimeout(resolve, 900));
    }
    const index = speakCount;
    speakCount += 1;
    if (shouldFailNext || shouldFailModel) {
      if (shouldFailNext) await new Promise((resolve) => setTimeout(resolve, 650));
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          errorMessage: `NameError while generating ${body.model}: diagnostic_probe is not defined`,
          stderr: `Traceback: diagnostic_probe is not defined for ${body.model}`,
          runtime: "mock-runtime",
        }),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        result: {
          model: body.model,
          runtime: "mock",
          audioUrl: audioUrls[index % audioUrls.length],
          filename: `qwen-ui-${index + 1}.wav`,
          durationSec: index === 0 ? 0.35 : 0.45
        }
      })
    });
  });

  try {
    try {
      await page.goto(`${frontBase}/`, { waitUntil: "networkidle", timeout: 120000 });
    } catch (error) {
      console.error(JSON.stringify({ phase: "initial-navigation", pendingRequests: [...pendingRequests.values()] }, null, 2));
      throw error;
    }
    await page.evaluate(() => {
      window.localStorage.clear();
      window.localTtsHistory?.clear?.();
    });
    await page.reload({ waitUntil: "networkidle", timeout: 120000 });

    await page.waitForSelector("#normalModelSelect");
    await page.waitForSelector("#normalReferenceVoiceSelect");
    await page.waitForSelector("#normalTextInput");
    await page.waitForSelector("#normalAudioPlayer", { state: "attached" });
    await page.waitForSelector("#normalHistoryList");
    await page.waitForFunction(() => document.querySelector("#serviceStatus")?.dataset.state === "running", { timeout: 10000 });
    ensure((await page.locator("#serviceStatus").textContent())?.includes("稼働中"), "service card must reflect verified backend state");
    try {
      await page.waitForSelector("#irodoriEmojiPalette-normal .irodori-emoji-chip", { state: "attached" });
    } catch (error) {
      const state = await page.evaluate(() => ({
        model: document.querySelector("#normalModelSelect")?.value || "",
        status: document.querySelector("#normalStatusText")?.textContent || "",
        paletteHidden: document.querySelector("#irodoriEmojiPalette-normal")?.hidden,
      }));
      console.error(JSON.stringify({ phase: "initial-ui", browserErrors, state }, null, 2));
      throw error;
    }

    const faviconHref = await page.locator('link[rel="icon"]').getAttribute("href");
    ensure(faviconHref === "./favicon.svg", `favicon link mismatch: ${faviconHref}`);
    ensure(await page.evaluate(async () => (await fetch("./favicon.svg")).ok), "favicon.svg is not served");

    for (const scope of ["normal", "compare", "rvc"]) {
      ensure(await page.locator(`#${scope}InstructionRequirement`).count() === 1, `${scope} instruction requirement badge is missing`);
      const labelText = await page.locator(`#${scope}InstructionInput`).locator("xpath=ancestor::label[1]").textContent();
      ensure(!labelText?.includes("対応モデルのみ"), `${scope} instruction label should use the same requirement badge pattern`);
    }

    const emojiPaletteNotes = await page.locator(".irodori-emoji-head").evaluateAll((nodes) => nodes.map((node) => node.textContent || ""));
    ensure(emojiPaletteNotes.length === 3, `expected three Irodori emoji notes, got ${emojiPaletteNotes.length}`);
    ensure(emojiPaletteNotes.every((text) => text.includes("Irodori専用") && text.includes("カーソル位置へ挿入")), "Irodori-only emoji note is missing");

    const normalFormHierarchy = await page.evaluate(() => {
      const text = document.querySelector("#normalTextInput");
      const instruction = document.querySelector("#normalInstructionInput");
      const guidance = document.querySelector("#normalAdvancedGuidance");
      const emojiSlot = document.querySelector("#irodoriEmojiSlot-normal");
      const advanced = document.querySelector("#normalAdvancedSettings");
      return {
        instructionInsideAdvanced: Boolean(guidance?.contains(instruction)),
        emojiInsideAdvanced: Boolean(guidance?.contains(emojiSlot)),
        advancedClosed: Boolean(advanced && !advanced.open),
        textVisible: Boolean(text && text.getBoundingClientRect().width > 0),
      };
    });
    ensure(normalFormHierarchy.instructionInsideAdvanced, "normal instruction should be inside advanced settings");
    ensure(normalFormHierarchy.emojiInsideAdvanced, "normal Irodori emoji palette should be inside advanced settings");
    ensure(normalFormHierarchy.advancedClosed && normalFormHierarchy.textVisible, "normal advanced settings should start closed without hiding the main text field");

    const removedButtonLabels = ["ホーム", "お気に入り", "設定", "ヘルプ", "この設定を保存", "詳細を見る", "すべての評価をクリア"];
    for (const label of removedButtonLabels) {
      ensure(await page.getByRole("button", { name: label, exact: true }).count() === 0, `dead button should not exist: ${label}`);
    }
    ensure(await page.locator(".sidebar .nav-item[data-tab]").count() === 6, "sidebar should contain six real pages");
    ensure(await page.locator(".top-tab[data-tab]").count() === 6, "top bar should contain six real pages");
    for (const tab of ["compare", "rvc", "history", "voices", "guide", "normal"]) {
      await page.locator(`.sidebar .nav-item[data-tab="${tab}"]`).click();
      await page.waitForSelector(`#${tab === "normal" ? "normal" : tab}Page.active`);
    }

    await page.locator('.top-tab[data-tab="guide"]').click();
    await page.waitForSelector("#guidePage.active");
    const guideHeadings = await page.locator("#guidePage h2").allTextContents();
    ensure(guideHeadings.slice(0, 5).join("|") === [
      "1. 最初の音声を作る",
      "2. やりたいことを選ぶ",
      "3. 見本の声に寄せたい場合",
      "4. 困ったとき",
      "5. 注意事項",
    ].join("|"), `guide section order is wrong: ${guideHeadings.join(" | ")}`);
    const guideText = await page.locator("#guidePage").textContent();
    ensure(guideText?.includes("この画面が開いていれば起動は完了しています") && guideText.includes("local-tts.bat"), "guide should start from the already-open app and keep the unified launcher note");
    ensure(!guideText?.includes("setup-and-start-local-tts.bat") && !guideText.includes("start-local-tts.bat"), "removed entrypoints must not return to the in-app guide");
    ensure(guideText?.includes("読ませる文章") && guideText.includes("利用可能なTTSモデル"), "guide should explain normal generation inputs");
    ensure(guideText?.includes("学習済みRVCモデル") && guideText.includes("index"), "guide should explain RVC inputs");
    ensure(guideText?.includes("音声ファイルを登録する") && guideText.includes("動画URLから候補"), "guide should explain the three reference registration routes");
    ensure(guideText?.includes("3〜10秒") && guideText.includes("BGMやノイズが少ない"), "guide should explain reference voice quality");
    ensure(!guideText?.includes("長文を分割して生成する理由"), "guide should not contain the removed long-text explanation");
    for (const target of ["normal", "compare", "rvc"]) {
      ensure(await page.locator(`#guidePage [data-guide-target="${target}"]`).count() === 1, `guide task action missing: ${target}`);
    }
    ensure(await page.locator('#guidePage [data-voice-open="register"]').count() === 1, "guide reference registration action is missing");
    const guideLayout = await page.evaluate(() => {
      const pageElement = document.querySelector("#guidePage");
      const cards = Array.from(document.querySelectorAll("#guidePage .guide-task-card"));
      if (!pageElement || cards.length !== 3) return null;
      const pageRect = pageElement.getBoundingClientRect();
      return {
        pageFits: document.documentElement.scrollWidth <= window.innerWidth + 2,
        cardWidths: cards.map((card) => card.getBoundingClientRect().width),
        cardsInside: cards.every((card) => {
          const rect = card.getBoundingClientRect();
          return rect.left >= pageRect.left - 2 && rect.right <= pageRect.right + 2;
        })
      };
    });
    ensure(guideLayout, "guide layout metrics unavailable");
    ensure(guideLayout.pageFits && guideLayout.cardsInside, `guide layout overflow: ${JSON.stringify(guideLayout)}`);
    ensure(guideLayout.cardWidths.every((width) => width >= 260), `guide task card too narrow: ${JSON.stringify(guideLayout)}`);
    ensure(new URL(page.url()).hash === "#guide", "guide tab should update the URL hash");
    if (process.env.GUIDE_SCREENSHOT) {
      await page.screenshot({ path: process.env.GUIDE_SCREENSHOT, fullPage: true });
    }
    await page.reload({ waitUntil: "networkidle", timeout: 120000 });
    await page.waitForSelector("#guidePage.active");
    await page.setViewportSize({ width: 980, height: 900 });
    const narrowGuideLayout = await page.evaluate(() => {
      const grid = document.querySelector("#guidePage .guide-task-grid");
      return {
        columns: grid ? getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length : 0,
        pageFits: document.documentElement.scrollWidth <= window.innerWidth + 2
      };
    });
    ensure(narrowGuideLayout.columns === 1 && narrowGuideLayout.pageFits, `guide narrow layout failed: ${JSON.stringify(narrowGuideLayout)}`);
    await page.setViewportSize({ width: 1752, height: 831 });
    await page.locator('#guidePage [data-guide-target="normal"]').click();
    await page.waitForSelector("#normalPage.active");
    ensure(!(await page.locator("#normalAdvancedSettings").evaluate((element) => element.open)), "normal advanced settings should start closed");
    await page.locator("#normalAdvancedSettings > summary").click();

    const emojiLayouts = await page.locator("#irodoriEmojiPalette-normal .irodori-emoji-chip").evaluateAll((chips) => chips.map((chip) => {
      const emoji = chip.querySelector("span");
      const label = chip.querySelector("small");
      if (!emoji || !label) return null;
      const chipRect = chip.getBoundingClientRect();
      const emojiRect = emoji.getBoundingClientRect();
      const labelRect = label.getBoundingClientRect();
      return {
        chipTop: Math.round(chipRect.top),
        chipLeft: Math.round(chipRect.left),
        emojiCenterY: emojiRect.top + emojiRect.height / 2,
        labelCenterY: labelRect.top + labelRect.height / 2,
        emojiRight: emojiRect.right,
        labelLeft: labelRect.left
      };
    }));
    ensure(emojiLayouts.length === 10, `expected 10 Irodori emoji chips, got ${emojiLayouts.length}`);
    for (const emojiLayout of emojiLayouts) {
      ensure(emojiLayout, "Irodori emoji layout metrics unavailable");
      ensure(Math.abs(emojiLayout.emojiCenterY - emojiLayout.labelCenterY) <= 3, "Irodori emoji and label are vertically misaligned");
      ensure(emojiLayout.labelLeft >= emojiLayout.emojiRight - 2, "Irodori emoji label overlaps the emoji");
    }
    const emojiRows = new Set(emojiLayouts.map((item) => item?.chipTop));
    const emojiColumns = new Set(emojiLayouts.slice(0, 5).map((item) => item?.chipLeft));
    ensure(emojiRows.size === 2 && emojiColumns.size === 5, `Irodori emoji palette should stay in two compact rows: rows=${emojiRows.size}, columns=${emojiColumns.size}`);

    const normalTextBeforeEmojiClicks = await page.locator("#normalTextInput").inputValue();
    const normalEmojiButtons = page.locator("#irodoriEmojiPalette-normal .irodori-emoji-chip");
    for (let index = 0; index < await normalEmojiButtons.count(); index += 1) {
      await normalEmojiButtons.nth(index).click();
    }
    ensure((await page.locator("#normalTextInput").inputValue()).length > normalTextBeforeEmojiClicks.length, "emoji buttons did not insert text");
    await page.fill("#normalTextInput", normalTextBeforeEmojiClicks);

    const infoDots = page.locator(".info-dot");
    ensure(await infoDots.count() >= 3, `expected explanatory tooltips, got ${await infoDots.count()}`);
    const tooltipTexts = await infoDots.evaluateAll((nodes) => nodes.map((node) => node.getAttribute("data-tip") || ""));
    ensure(tooltipTexts.every(Boolean), "one or more info tooltip texts are missing");
    ensure(!tooltipTexts.some((text) => text.includes("ページを再読み込みしても保持")), "tooltips should explain parameters instead of persistence behavior");
    ensure(tooltipTexts.filter((text) => text.includes("seed") && text.includes("1増やします")).length === 3, "seed auto-update explanations should exist for normal, compare, and RVC");
    ensure(tooltipTexts.filter((text) => text.includes("再生します")).length >= 3, "autoplay explanations should describe what gets played");

    const verifyVisibleTooltips = async (locator, label) => {
      const count = await locator.count();
      for (let index = 0; index < count; index += 1) {
        const infoDot = locator.nth(index);
        await infoDot.hover();
        await page.waitForTimeout(120);
        const tooltipState = await infoDot.evaluate((element) => {
          const style = getComputedStyle(element, "::after");
          const clippingAncestor = Array.from(function* ancestors() {
            let current = element.parentElement;
            while (current) { yield current; current = current.parentElement; }
          }()).find((ancestor) => {
            const ancestorStyle = getComputedStyle(ancestor);
            return [ancestorStyle.overflow, ancestorStyle.overflowX, ancestorStyle.overflowY]
              .some((value) => value === "hidden" || value === "clip");
          });
          return {
            content: style.content,
            opacity: Number(style.opacity),
            clippingAncestor: clippingAncestor?.id || clippingAncestor?.className || "",
          };
        });
        ensure(tooltipState.content && tooltipState.content !== "none" && tooltipState.content !== '""', `${label} tooltip ${index + 1} content missing`);
        ensure(tooltipState.opacity >= 0.9, `${label} tooltip ${index + 1} is not visible: opacity=${tooltipState.opacity}`);
        ensure(!tooltipState.clippingAncestor, `${label} tooltip ${index + 1} is clipped by ${tooltipState.clippingAncestor}`);
      }
    };

    ensure(await page.locator("#normalAdvancedSettings").evaluate((element) => element.open), "normal advanced settings should remain open for detailed-control checks");
    await verifyVisibleTooltips(page.locator("#normalPage .info-dot"), "normal");
    await page.selectOption("#normalModelSelect", "qwen3_tts_clone_1_7b");
    ensure(await page.locator("#irodoriEmojiPalette-normal").isHidden(), "Irodori emoji palette should hide for non-Irodori models");
    await page.selectOption("#normalModelSelect", "irodori_v2");
    ensure(await page.locator("#irodoriEmojiPalette-normal").isVisible(), "Irodori emoji palette should show for Irodori v2");
    ensure((await page.locator("#normalStatusText").textContent()).includes("IrodoriはCPUで動作しています。GPU動作より大幅に遅く、音声生成に数分かかる場合があります。"), "CPU Irodori warning should be visible");
    ensure(await page.locator("#normalStatusText").evaluate((element) => element.classList.contains("warning")), "CPU Irodori warning should use warning styling");
    ensure(await page.locator("#normalReferenceRequirement").textContent() === "任意", "Irodori v2 reference badge should say optional");
    ensure(!(await page.locator("#normalUseReference").isDisabled()), "Irodori v2 reference toggle should be available");
    ensure(await page.locator("#normalUseReference").isChecked(), "Irodori v2 reference should be enabled by default");
    ensure(await page.locator("#normalInstructionField").isHidden(), "unsupported instruction should not be displayed");
    ensure(await page.locator("#normalInstructionInput").isDisabled(), "hidden unsupported instruction should not accept input");
    ensure(await page.locator("#normalSpeedControl").isHidden(), "Irodori v2 speed control should be hidden because the official v2 checkpoint has no duration predictor");
    await page.uncheck("#normalUseReference");
    ensure(await page.locator("#normalReferenceVoiceSelect").isDisabled(), "Irodori v2 reference choices should disable when reference is off");
    await page.check("#normalUseReference");
    const emojiLayout = await page.evaluate(() => {
      const guidance = document.querySelector("#normalAdvancedGuidance")?.getBoundingClientRect();
      const palette = document.querySelector("#irodoriEmojiPalette-normal")?.getBoundingClientRect();
      if (!guidance || !palette) return null;
      return {
        widthDifference: Math.abs(guidance.width - palette.width - 28),
        insideGuidance: palette.left >= guidance.left && palette.right <= guidance.right,
      };
    });
    ensure(emojiLayout, "Irodori emoji layout metrics unavailable");
    ensure(emojiLayout.insideGuidance && emojiLayout.widthDifference <= 4, `Irodori emoji frame should fill the advanced area when instruction is unsupported: ${JSON.stringify(emojiLayout)}`);

    await page.locator('.top-tab[data-tab="compare"]').click();
    await page.waitForSelector("#comparePage.active");
    const compareModelCards = await page.locator("#compareModelCards [data-model-card]").evaluateAll((cards) => cards.map((card) => ({
      id: card.dataset.modelCard || "",
      unavailable: Boolean(card.querySelector('input[type="checkbox"]')?.disabled),
    })));
    const firstUnavailableCompareIndex = compareModelCards.findIndex((item) => item.unavailable);
    ensure(firstUnavailableCompareIndex < 0 || compareModelCards.slice(firstUnavailableCompareIndex).every((item) => item.unavailable), `available comparison model appears below an unavailable model: ${JSON.stringify(compareModelCards)}`);
    ensure(!(await page.locator("#compareAdvancedSettings").evaluate((element) => element.open)), "compare advanced settings should start closed");
    await page.locator("#compareAdvancedSettings > summary").click();
    await verifyVisibleTooltips(page.locator("#comparePage .info-dot"), "compare");
    ensure(await page.locator("#irodoriEmojiPalette-compare").isVisible(), "compare emoji palette should show while an Irodori model is selected");
    await page.locator('[data-model-card="irodori_v3_voicedesign"] input').uncheck();
    ensure((await page.locator("#compareStatusText").textContent()).includes("IrodoriはCPUで動作しています。GPU動作より大幅に遅く、音声生成に数分かかる場合があります。"), "compare should show the CPU Irodori warning");
    ensure(await page.locator("#compareStatusText").evaluate((element) => element.classList.contains("warning")), "compare CPU Irodori warning should use warning styling");
    await page.locator('[data-model-card="irodori_v3"] input').uncheck();
    ensure(await page.locator("#irodoriEmojiPalette-compare").isHidden(), "compare emoji palette should hide when no Irodori model is selected");
    await page.locator('[data-model-card="irodori_v3"] input').check();
    ensure(await page.locator("#irodoriEmojiPalette-compare").isVisible(), "compare emoji palette should return when an Irodori model is selected");
    await page.locator('.top-tab[data-tab="normal"]').click();
    await page.waitForSelector("#normalPage.active");
    await page.selectOption("#normalModelSelect", "irodori_v3");
    ensure(await page.locator("#normalReferenceRequirement").textContent() === "任意", "Irodori v3 reference badge should say optional");
    ensure(await page.locator("#normalInstructionField").isHidden(), "unsupported Irodori v3 instruction should not be displayed");
    ensure(await page.locator("#normalInstructionInput").isDisabled(), "hidden Irodori v3 instruction should not accept input");
    ensure(await page.locator("#normalSpeedControl").isVisible(), "Irodori v3 speed control should be visible");
    ensure(await page.locator("#normalUseReference").isChecked(), "reference audio should be enabled by default");
    await page.uncheck("#normalUseReference");
    ensure(await page.locator("#normalReferenceVoiceSelect").isDisabled(), "reference voice choices should disable when reference audio is off");
    ensure(await page.locator("#normalReferencePreviewButton").isDisabled(), "reference preview should disable when reference audio is off");
    ensure(await page.locator("#normalReferenceField").evaluate((element) => element.classList.contains("is-disabled")), "reference field should be visibly muted when disabled");
    await page.check("#normalUseReference");
    ensure(!(await page.locator("#normalReferenceVoiceSelect").isDisabled()), "reference voice choices should re-enable");
    await page.uncheck("#normalUseReference");
    const speakCountBeforeNoReference = speakBodies.length;
    await page.click("#normalGenerateButton");
    await page.waitForFunction(() => document.querySelector("#normalStatusText")?.textContent === "生成が完了しました。", null, { timeout: 15000 });
    ensure(speakBodies.length === speakCountBeforeNoReference + 1, "generation with reference disabled did not issue a request");
    ensure(!("voiceId" in speakBodies.at(-1)), "reference-disabled generation should not send voiceId");
    await page.selectOption("#normalModelSelect", "irodori_v3_voicedesign");
    if (!(await page.locator("#normalUseReference").isChecked())) await page.check("#normalUseReference");
    ensure(!(await page.locator("#normalReferenceVoiceSelect").isDisabled()), "optional VoiceDesign reference choices should be enabled while reference is on");
    const speedControl = page.locator("#normalSpeedControl");
    const styleControl = page.locator("#normalStyleStrengthControl");
    ensure(await speedControl.isVisible(), "speed slider should be visible for Irodori VoiceDesign");
    ensure(await styleControl.isVisible(), "style slider should be visible for Irodori VoiceDesign");
    await page.fill("#normalInstructionInput", "");
    ensure(await page.locator("#normalStyleStrength").isDisabled(), "style strength should be disabled until a VoiceDesign instruction is entered");
    await page.fill("#normalInstructionInput", "明るく自然なトーン");
    ensure(!(await page.locator("#normalStyleStrength").isDisabled()), "style strength should enable when a VoiceDesign instruction is entered");
    await page.locator("#normalSpeedScale").evaluate((input) => { input.value = "1.20"; input.dispatchEvent(new Event("input", { bubbles: true })); });
    await page.locator("#normalStyleStrength").evaluate((input) => { input.value = "4.5"; input.dispatchEvent(new Event("input", { bubbles: true })); });
    ensure(await page.locator("#normalSpeedValue").textContent() === "1.20x", "speed slider value label did not update");
    ensure(await page.locator("#normalStyleStrengthValue").textContent() === "4.5", "style slider value label did not update");
    const normalTopLayout = await page.evaluate(() => {
      const model = document.querySelector("#normalModelSelect")?.getBoundingClientRect();
      const reference = document.querySelector("#normalReferenceVoiceSelect")?.getBoundingClientRect();
      const seed = document.querySelector("#normalSeedInput")?.getBoundingClientRect();
      const referenceLabel = document.querySelector("#normalReferenceField .field-title-row > span")?.getBoundingClientRect();
      const referenceToggle = document.querySelector("#normalUseReference")?.getBoundingClientRect();
      if (!model || !reference || !seed || !referenceLabel || !referenceToggle) return null;
      return {
        inputTopSpread: Math.max(model.top, reference.top, seed.top) - Math.min(model.top, reference.top, seed.top),
        labelToToggleGap: referenceToggle.left - referenceLabel.right,
      };
    });
    ensure(normalTopLayout, "normal top control layout metrics unavailable");
    ensure(normalTopLayout.inputTopSpread <= 6, `model, reference, and seed inputs are misaligned: ${normalTopLayout.inputTopSpread}px`);
    ensure(normalTopLayout.labelToToggleGap >= 6 && normalTopLayout.labelToToggleGap <= 20, `reference toggle is detached from its label: ${normalTopLayout.labelToToggleGap}px`);
    ensure(await page.locator("#normalReferenceRequirement").textContent() === "任意", "VoiceDesign reference badge should say optional");
    ensure(await page.locator("#normalInstructionRequirement").textContent() === "任意", "optional instruction should show an optional badge");
    ensure(await page.locator(".chunk-reason").count() === 0, "long-form chunk explanation should not remain visible in the form");
    ensure((await page.locator('[aria-label="長文分割の説明"]').first().getAttribute("data-tip"))?.includes("最後に1つの音声へ結合"), "chunking reason should be available as a tooltip");
    const normalSpacing = await page.evaluate(() => {
      const chunk = document.querySelector('[data-chunk-scope="normal"]')?.getBoundingClientRect();
      const speed = document.querySelector("#normalSynthesisControls")?.getBoundingClientRect();
      const options = document.querySelector(".normal-output-options")?.getBoundingClientRect();
      const action = document.querySelector("#normalGenerateButton")?.closest(".action-row")?.getBoundingClientRect();
      if (!chunk || !speed || !options || !action) return null;
      return {
        chunkToSpeed: speed.top - chunk.bottom,
        speedToOptions: options.top - speed.bottom,
        optionsToAction: action.top - options.bottom,
      };
    });
    ensure(normalSpacing, "normal generation spacing metrics unavailable");
    ensure(normalSpacing.chunkToSpeed >= 24, `chunk and speed controls are too close: ${normalSpacing.chunkToSpeed}`);
    ensure(normalSpacing.speedToOptions >= 24, `speed and output options are too close: ${normalSpacing.speedToOptions}`);
    ensure(normalSpacing.optionsToAction >= 20, `output options and generate action are too close: ${normalSpacing.optionsToAction}`);

    if (process.env.NORMAL_UI_SCREENSHOT) {
      await page.screenshot({ path: process.env.NORMAL_UI_SCREENSHOT, fullPage: true });
    }

    const modelOptions = await page.locator("#normalModelSelect option").evaluateAll((nodes) =>
      nodes.map((node) => ({ value: node.value, text: node.textContent || "", disabled: node.disabled }))
    );
    const firstUnavailableOptionIndex = modelOptions.findIndex((item) => item.disabled);
    ensure(firstUnavailableOptionIndex < 0 || modelOptions.slice(firstUnavailableOptionIndex).every((item) => item.disabled), `available normal model appears below an unavailable model: ${JSON.stringify(modelOptions)}`);
    ensure(modelOptions.some((item) => item.value === "qwen3_tts_clone_1_7b"), "qwen3_tts_clone_1_7b missing");
    for (const modelId of ["sarashina2_2_tts", "fireredtts2", "fish_s1_mini"]) {
      const option = modelOptions.find((item) => item.value === modelId);
      ensure(option && !option.disabled, `${modelId} should be selectable in normal generation`);
    }
    const t5Option = modelOptions.find((item) => item.value === "t5gemma_tts_2b_2b");
    ensure(t5Option?.disabled, "t5gemma_tts_2b_2b should be disabled while weights are unavailable");
    ensure(t5Option?.text.includes("利用不可"), "T5Gemma unavailable state is not visible in normal generation");

    await page.selectOption("#normalModelSelect", "irodori_v3_voicedesign");
    await page.selectOption("#normalReferenceVoiceSelect", "sample_neutral");
    await page.fill("#normalTextInput", "これは音声合成の動作確認です。");
    await page.fill("#normalSeedInput", "1001");
    ensure(await page.locator("#normalSeedAutoIncrementInput").isChecked(), "normal seed auto-update should be on by default");
    await page.check("#normalAutoPlayInput");
    const normalChunkPanel = page.locator('[data-chunk-scope="normal"]');
    await normalChunkPanel.locator('[data-chunk-preset="160"]').click();
    ensure(await normalChunkPanel.locator('[data-chunk-target]').inputValue() === "160", "normal chunk preset did not apply");
    ensure(await normalChunkPanel.locator('[data-chunk-hard-max]').getAttribute("type") === "hidden", "normal chunk hard max should be internal only");
    await normalChunkPanel.locator('[data-chunk-preview-toggle]').click();
    await page.waitForFunction(() => !document.querySelector('[data-chunk-scope="normal"] + [data-chunk-preview]')?.hidden);
    await normalChunkPanel.locator('[data-chunk-preview-toggle]').click();
    await page.click("#normalReferencePreviewButton");
    await page.waitForFunction(() => document.querySelector("#normalReferencePreviewButton")?.textContent === "■");
    await page.click("#normalReferencePreviewButton");
    await page.waitForFunction(() => document.querySelector("#normalReferencePreviewButton")?.textContent === "▶");

    const joyInstruction = "嬉しそうに、明るく自然な笑顔を感じる声。配信の挨拶のように軽く弾むトーンで、聞き取りやすく話す。大げさに叫ばない。";
    const angerInstruction = "少し怒っているが、ネタとして聞ける範囲。低めで強めのトーン。圧を出しつつ、怖くなりすぎず、短く言い切る。";

    await page.fill("#normalInstructionInput", joyInstruction);
    ensure(!(await page.locator("#normalGenerateButton").isDisabled()), "generate button should be enabled");

    await page.click("#normalGenerateButton");
    await page.waitForSelector("#normalResultCard:not([hidden])", { timeout: 180000 });
    await page.waitForFunction(() => {
      const el = document.querySelector("#normalAudioPlayer");
      return Boolean(el && el.getAttribute("src"));
    }, { timeout: 180000 });

    const firstAudio = await audioState(page.locator("#normalAudioPlayer"));
    ensure(firstAudio.hasSrc, "first audio src is empty");
    ensure(firstAudio.readyState >= 2, `first audio not ready enough: ${firstAudio.readyState}`);
    ensure(firstAudio.duration > 0, `first audio duration should be > 0, got ${firstAudio.duration}`);
    ensure(await page.locator("#normalSeedAutoIncrementInput").isChecked(), "normal seed auto-update should stay enabled after opting in");
    ensure(await page.locator("#normalSeedInput").inputValue() === "1002", "normal seed did not increment after successful generation");
    const firstNormalSpeakBody = speakBodies.at(-1);
    ensure(firstNormalSpeakBody?.chunking?.softChunkChars === 160, "normal generation did not send the selected chunk target");
    ensure(firstNormalSpeakBody?.chunking?.hardLimitChars === 500, "normal generation did not keep the internal hard chunk limit");
    ensure(firstNormalSpeakBody?.speedScale === 1.2, "normal generation did not send the speed slider value");
    ensure(firstNormalSpeakBody?.styleStrength === 4.5, "normal generation did not send the style slider value");
    ensure(firstNormalSpeakBody?.instruction === joyInstruction, "VoiceDesign instruction was not sent to /api/speak");

    await page.waitForFunction(() => document.querySelectorAll("#normalHistoryList .mini-history-item").length >= 1, { timeout: 15000 });
    const latestNormalHistory = page.locator("#normalHistoryList .mini-history-item").first();
    ensure((await latestNormalHistory.locator(".mini-history-text").textContent())?.includes("これは音声合成の動作確認です"), "recent generation should show the saved text");
    ensure(await latestNormalHistory.locator("[data-restore-normal-history]").count() === 1, "recent generation should restore text and settings");
    ensure((await latestNormalHistory.locator(".mini-history-chips").textContent())?.includes("seed 1001"), "recent generation should show seed information");

    const normalAudioPausedBeforeButton = await page.locator("#normalAudioPlayer").evaluate((audio) => audio.paused);
    await page.locator('[data-audio-target="normalAudioPlayer"]').click();
    await page.waitForFunction((before) => document.querySelector("#normalAudioPlayer")?.paused !== before, normalAudioPausedBeforeButton);

    const miniHistoryPlay = page.locator("#normalHistoryList [data-history-audio]").first();
    await miniHistoryPlay.click();
    await page.waitForFunction(() => document.querySelector("#normalHistoryList [data-history-audio]")?.textContent === "❚❚");
    await miniHistoryPlay.click();
    await page.waitForFunction(() => document.querySelector("#normalHistoryList [data-history-audio]")?.textContent === "▶");

    ensure(await page.locator("#normalRetryButton").count() === 0, "duplicate normal retry button should be removed");
    const historyCountBeforeRegenerate = await page.locator("#normalHistoryList .mini-history-item").count();
    const speakCountBeforeRegenerate = speakBodies.length;
    await page.click("#normalRegenerateButton");
    await page.waitForFunction((count) => document.querySelectorAll("#normalHistoryList .mini-history-item").length > count, historyCountBeforeRegenerate);
    ensure(speakBodies.length === speakCountBeforeRegenerate + 1, "exact regenerate did not issue one request");
    ensure(speakBodies.at(-1)?.seed === firstNormalSpeakBody?.seed, "exact regenerate did not preserve the previous seed");
    ensure(await page.locator("#normalSeedInput").inputValue() === "1002", "exact regenerate should not consume the next form seed");
    ensure(await page.locator("#normalRegenerateButton").textContent().then((text) => text.includes("同じ設定・seed")), "exact regenerate role is not visible");

    const normalAudioSrcBeforeFailure = await page.locator("#normalAudioPlayer").getAttribute("src");
    failNextSpeak = true;
    await page.click("#normalGenerateButton");
    await page.waitForFunction(() => document.querySelector("#normalModelSelect")?.disabled);
    ensure(await page.locator("#normalModelSelect").isDisabled(), "normal model choice should lock while generation is active");
    ensure(await page.locator("#normalResultCard").isVisible(), "normal result player should remain visible while another generation is active");
    ensure(await page.locator("#normalAudioPlayer").getAttribute("src") === normalAudioSrcBeforeFailure, "normal generation should keep the previous player until replacement is ready");
    await page.waitForFunction(() => document.querySelector("#normalLogBox")?.textContent?.includes("Local TTS diagnostic log"));
    const normalFailureLog = await page.locator("#normalLogBox").textContent();
    ensure(normalFailureLog?.includes("screen: normal") && normalFailureLog.includes("diagnostic_probe is not defined"), "normal diagnostic should keep actionable backend details");
    ensure(normalFailureLog?.includes("Request:") && normalFailureLog.includes("Error response:"), "normal diagnostic should include request and error response");
    await page.waitForFunction(() => !document.querySelector("#normalModelSelect")?.disabled);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForFunction(() => document.querySelector("#normalModelSelect")?.value === "irodori_v3_voicedesign");
    ensure(await page.locator("#normalReferenceVoiceSelect").inputValue() === "sample_neutral", "reference voice was not restored after reload");
    ensure(await page.locator("#normalSeedInput").inputValue() === "1002", "next seed was not restored after reload");
    ensure(await page.locator("#normalSeedAutoIncrementInput").isChecked(), "seed auto-update was not restored after reload");
    ensure(await page.locator("#normalAutoPlayInput").isChecked(), "autoplay setting was not restored after reload");
    await page.locator("#normalAdvancedSettings > summary").click();

    await page.fill("#normalInstructionInput", angerInstruction);
    const historyCountBeforeSecondGenerate = await page.locator("#normalHistoryList .mini-history-item").count();
    await page.click("#normalGenerateButton");
    await page.waitForFunction((count) => document.querySelectorAll("#normalHistoryList .mini-history-item").length > count, historyCountBeforeSecondGenerate, { timeout: 180000 });

    await page.locator('.top-tab[data-tab="compare"]').click();
    await page.waitForSelector("#comparePage.active");
    await page.locator("#compareAdvancedSettings > summary").click();
    await page.selectOption("#compareReferenceVoiceSelect", "sample_neutral");
    await page.click("#compareReferencePreviewButton");
    await page.waitForFunction(() => document.querySelector("#compareReferencePreviewButton")?.textContent === "■");
    await page.click("#compareReferencePreviewButton");
    await page.waitForFunction(() => document.querySelector("#compareReferencePreviewButton")?.textContent === "▶");
    ensure(await page.locator("#compareSeedInput").inputValue() === "1", "compare seed should start at 1");
    ensure(await page.locator("#compareSeedAutoIncrementInput").isChecked(), "compare seed auto-update should be on by default");
    await page.fill("#compareSeedInput", "2001");
    await page.check("#compareAutoPlayInput");
    ensure(await page.locator("#compareSameConditions").count() === 0, "redundant same-conditions checkbox should be removed");
    ensure(await page.locator("#compareLockSeed").count() === 0, "redundant seed-lock checkbox should be removed");
    const compareConditionNote = await page.locator(".compare-condition-note").textContent();
    ensure(compareConditionNote?.includes("同じテキスト・参照音声・seed・長文分割設定"), "automatic comparison conditions are not explained");
    const compareControlLayout = await page.evaluate(() => {
      const primary = document.querySelector("#compareReferencePrimary");
      const voice = document.querySelector("#compareReferenceVoiceSelect")?.closest("label");
      const seed = document.querySelector("#compareSeedInput")?.closest(".seed-field");
      const options = document.querySelector("#comparePage .compare-generation-options");
      const advanced = document.querySelector("#compareAdvancedSettings");
      const guidance = document.querySelector("#compareAdvancedGuidance");
      const instruction = document.querySelector("#compareInstructionInput");
      const emojiSlot = document.querySelector("#irodoriEmojiSlot-compare");
      if (!primary || !voice || !seed || !options || !advanced || !guidance || !instruction || !emojiSlot) return null;
      return {
        voicePrimary: primary.contains(voice),
        seedPrimary: primary.contains(seed),
        optionsAdvanced: advanced.contains(options),
        instructionAdvanced: guidance.contains(instruction),
        emojiAdvanced: guidance.contains(emojiSlot),
        voiceWidth: voice.getBoundingClientRect().width,
        primaryTop: primary.getBoundingClientRect().top,
        advancedTop: advanced.getBoundingClientRect().top,
      };
    });
    ensure(compareControlLayout, "compare control layout metrics unavailable");
    ensure(compareControlLayout.voicePrimary, "compare reference voice should be a primary visible control");
    ensure(compareControlLayout.seedPrimary && compareControlLayout.optionsAdvanced, "compare seed should match the primary normal-generation hierarchy while autoplay remains advanced");
    ensure(compareControlLayout.instructionAdvanced && compareControlLayout.emojiAdvanced, "compare instruction and emotion controls should be inside advanced settings");
    ensure(compareControlLayout.voiceWidth >= 280, `compare reference voice field is too narrow: ${compareControlLayout.voiceWidth}`);
    ensure(compareControlLayout.primaryTop < compareControlLayout.advancedTop, "compare reference voice should appear above advanced settings");
    const compareChunkPanel = page.locator('[data-chunk-scope="compare"]');
    await compareChunkPanel.locator('[data-chunk-preset="360"]').click();
    ensure(await compareChunkPanel.locator('[data-chunk-target]').inputValue() === "360", "compare chunk preset did not apply");
    ensure(await compareChunkPanel.locator('[data-chunk-hard-max]').getAttribute("type") === "hidden", "compare chunk hard max should be internal only");
    await compareChunkPanel.locator('[data-chunk-preview-toggle]').click();
    await page.waitForFunction(() => !document.querySelector('[data-chunk-scope="compare"] + [data-chunk-preview]')?.hidden);
    await compareChunkPanel.locator('[data-chunk-preview-toggle]').click();
    for (const modelId of ["sarashina2_2_tts", "fireredtts2", "fish_s1_mini"]) {
      const card = page.locator(`[data-model-card="${modelId}"]`);
      ensure(await card.count() === 1, `${modelId} comparison card is missing`);
      ensure(!(await card.locator("input").isDisabled()), `${modelId} comparison checkbox should be enabled`);
    }
    const t5Card = page.locator('[data-model-card="t5gemma_tts_2b_2b"]');
    ensure(await t5Card.count() === 1, "T5Gemma comparison card is missing");
    ensure(await t5Card.locator("input").isDisabled(), "T5Gemma comparison checkbox should be disabled");
    const t5UnavailableText = await t5Card.locator(".model-unavailable-reason").textContent();
    ensure(t5UnavailableText?.includes("Hugging Faceの利用条件への同意が必要"), "T5Gemma unavailable reason is not shown in comparison UI");

    await page.click("#compareClearButton");
    ensure(await page.locator('[data-model-card] input:checked').count() === 0, "compare clear button did not clear model selection");
    await page.click("#compareSelectAllButton");
    const selectedCompareCount = await page.locator('[data-model-card] input:checked').count();
    ensure(selectedCompareCount >= 2, `compare select-all selected only ${selectedCompareCount} models`);

    await page.reload({ waitUntil: "domcontentloaded" });
    await page.waitForSelector("#comparePage.active");
    await page.waitForFunction(() => document.querySelector("#compareSeedInput")?.value === "2001");
    ensure(await page.locator("#compareReferenceVoiceSelect").inputValue() === "sample_neutral", "compare reference voice was not restored after reload");
    ensure(await page.locator("#compareSeedAutoIncrementInput").isChecked(), "compare seed auto-update was not restored after reload");
    ensure(await page.locator("#compareAutoPlayInput").isChecked(), "compare autoplay was not restored after reload");
    ensure(await page.locator('[data-model-card] input:checked').count() === selectedCompareCount, "compare model selection was not restored after reload");
    ensure(await page.locator('[data-chunk-scope="compare"] [data-chunk-target]').inputValue() === "360", "compare chunk setting was not restored after reload");
    await page.locator("#compareAdvancedSettings > summary").click();

    if (process.env.COMPARE_LAYOUT_SCREENSHOT) {
      await page.screenshot({ path: process.env.COMPARE_LAYOUT_SCREENSHOT, fullPage: true });
    }

    await page.fill("#compareInstructionInput", "比較用の落ち着いた話し方");
    const compareTextBeforeEmojiClicks = await page.locator("#compareTextInput").inputValue();
    const compareEmojiButtons = page.locator("#irodoriEmojiPalette-compare .irodori-emoji-chip");
    for (let index = 0; index < await compareEmojiButtons.count(); index += 1) await compareEmojiButtons.nth(index).click();
    ensure((await page.locator("#compareTextInput").inputValue()).length > compareTextBeforeEmojiClicks.length, "compare emoji buttons did not insert text");
    await page.fill("#compareTextInput", compareTextBeforeEmojiClicks);

    const speakCountBeforeCompare = speakCount;
    const compareBodyStart = speakBodies.length;
    const failedCompareModel = await page.locator('[data-model-card] input:checked').last().inputValue();
    failSpeakModel = failedCompareModel;
    ensure(Boolean(failedCompareModel), "comparison diagnostic probe model is missing");
    slowCompareGeneration = true;
    compareRequestOrdinal = 0;
    await page.click("#compareGenerateButton");
    await page.waitForFunction(() => document.querySelectorAll("#compareResultsGrid .status-badge.success").length >= 1, null, { timeout: 180000 });
    ensure(await page.locator('[data-model-card] input:not(:disabled)').count() === 0, "comparison model choices should be locked while generation is active");
    ensure(await page.locator("#compareSelectAllButton").isDisabled(), "compare select-all should be disabled while generation is active");
    ensure(await page.locator("#compareClearButton").isDisabled(), "compare clear should be disabled while generation is active");
    ensure(await page.locator("#compareResultsGrid .compare-audio-pending").count() >= 1, "unfinished comparison cards should show a non-interactive pending state");
    ensure(await page.locator("#compareResultsGrid .compare-audio-pending audio").count() === 0, "unfinished comparison cards should not expose an empty audio player");
    const firstCompletedModel = await page.evaluate(() => {
      const card = Array.from(document.querySelectorAll("#compareResultsGrid [data-result-model]"))
        .find((item) => item.querySelector(".status-badge.success"));
      return card?.dataset.resultModel || "";
    });
    ensure(Boolean(firstCompletedModel), "first completed comparison model is missing");
    const firstCompletedCard = page.locator(`#compareResultsGrid [data-result-model="${firstCompletedModel}"]`);
    await firstCompletedCard.locator("audio").evaluate((audio) => {
      audio.loop = true;
      audio.dataset.persistProbe = "active";
    });
    await firstCompletedCard.locator("[data-dynamic-audio]").click();
    await page.waitForFunction((id) => !document.querySelector(`#compareAudio-${id}`)?.paused, firstCompletedModel);
    await page.waitForFunction((id) => {
      const audio = document.querySelector(`#compareAudio-${id}`);
      return document.querySelectorAll("#compareResultsGrid .status-badge.success").length >= 2
        && audio?.dataset.persistProbe === "active"
        && !audio.paused;
    }, firstCompletedModel, { timeout: 180000 });
    await firstCompletedCard.locator("audio").evaluate((audio) => {
      audio.pause();
      audio.loop = false;
    });
    await page.waitForFunction(() => document.querySelector("#compareStatusText")?.textContent === "比較生成が完了しました。", null, { timeout: 180000 });
    slowCompareGeneration = false;
    ensure(await page.locator('[data-model-card] input:not(:disabled)').count() >= 1, "available comparison model choices should unlock after generation");
    ensure(!(await page.locator("#compareSelectAllButton").isDisabled()), "compare select-all should unlock after generation");
    ensure(!(await page.locator("#compareClearButton").isDisabled()), "compare clear should unlock after generation");
    const compareFailureLog = await page.locator("#compareLogBox").textContent();
    ensure(compareFailureLog?.includes("screen: compare") && compareFailureLog.includes("diagnostic_probe is not defined"), "compare diagnostic should keep model-specific backend details");
    ensure(compareFailureLog?.includes(`model: ${failedCompareModel}`), "compare diagnostic should identify the failed model");
    await page.waitForFunction(() => Array.from(document.querySelectorAll("#compareResultsGrid audio")).some((audio) => !audio.paused));
    ensure(await page.locator("#compareResultsGrid audio").evaluateAll((audios) => audios.filter((audio) => !audio.paused).length === 1), "compare autoplay should play exactly one completed result");
    await page.locator("#compareResultsGrid audio").evaluateAll((audios) => audios.forEach((audio) => audio.pause()));
    ensure(await page.locator("#compareResultsGrid [data-result-model]").count() === selectedCompareCount, "compare result card count mismatch");
    ensure(speakCount === speakCountBeforeCompare + selectedCompareCount, "compare generate did not call every selected model");
    ensure(await page.locator("#compareSeedInput").inputValue() === "2002", "compare batch generation did not increment seed once");
    const compareSpeakBodies = speakBodies.slice(compareBodyStart);
    ensure(compareSpeakBodies.length === selectedCompareCount, "compare request body count mismatch");
    ensure(compareSpeakBodies.every((body) => body.chunking?.softChunkChars === 360), "compare generation did not send the selected chunk target to every model");
    ensure(compareSpeakBodies.every((body) => body.chunking?.hardLimitChars === 500), "compare generation did not keep the internal hard chunk limit");
    const instructionModels = new Set(["qwen3_tts_clone_1_7b", "irodori_v3_voicedesign"]);
    ensure(compareSpeakBodies.filter((body) => instructionModels.has(body.model)).every((body) => body.instruction === "比較用の落ち着いた話し方"), "comparison instruction was not sent to supported models");
    ensure(compareSpeakBodies.filter((body) => !instructionModels.has(body.model)).every((body) => !("instruction" in body)), "comparison instruction should not be sent to unsupported models");

    const firstCompareResult = page.locator("#compareResultsGrid [data-result-model]").first();
    const adoptedModel = await firstCompareResult.getAttribute("data-result-model");
    ensure(Boolean(adoptedModel), "compare result model id missing");
    const compareAudio = firstCompareResult.locator("audio");
    ensure(await compareAudio.evaluate((audio) => audio.paused), "compare audio should start paused");
    await firstCompareResult.locator("[data-dynamic-audio]").click();
    await page.waitForFunction((id) => !document.querySelector(`#compareAudio-${id}`)?.paused, adoptedModel);
    await compareAudio.evaluate((audio) => audio.pause());

    const speakCountBeforeSingleRegenerate = speakCount;
    await firstCompareResult.locator("[data-regenerate-model]").click();
    await page.waitForFunction(() => document.querySelector("#compareStatusText")?.textContent?.includes("再生成が完了しました。"), { timeout: 180000 });
    ensure(speakCount === speakCountBeforeSingleRegenerate + 1, "single-model regenerate button did not call TTS");
    ensure(await page.locator("#compareSeedInput").inputValue() === "2003", "single-model regenerate did not increment compare seed");
    await page.waitForFunction((id) => !document.querySelector(`#compareAudio-${id}`)?.paused, adoptedModel);
    await page.locator(`#compareAudio-${adoptedModel}`).evaluate((audio) => audio.pause());

    await page.locator(`#compareResultsGrid [data-result-model="${adoptedModel}"] [data-adopt-model]`).click();
    await page.waitForSelector("#normalPage.active");
    ensure(await page.locator("#normalModelSelect").inputValue() === adoptedModel, "adopt button did not copy the model to normal generation");
    ensure(await page.locator('[data-chunk-scope="normal"] [data-chunk-target]').inputValue() === "360", "adopt button did not copy compare chunk settings to normal generation");

    await page.click("#normalClearHistoryButton");
    await page.waitForFunction(() => document.querySelectorAll("#normalHistoryList .mini-history-item").length === 0);
    await page.locator('.top-tab[data-tab="compare"]').click();
    await page.waitForSelector("#comparePage.active");
    await page.waitForFunction(() => document.querySelectorAll("#compareHistoryList .mini-history-item").length >= 1);
    const latestCompareHistory = page.locator("#compareHistoryList .mini-history-item").first();
    ensure((await latestCompareHistory.locator(".mini-history-text").textContent())?.includes(compareTextBeforeEmojiClicks.trim().slice(0, 8)), "recent comparison should show the compared text");
    ensure((await latestCompareHistory.locator(".mini-history-chips").textContent())?.includes("成功"), "recent comparison should show the success count");
    ensure((await latestCompareHistory.locator(".mini-history-chips").textContent())?.includes("推奨"), "recent comparison should show the recommended model");
    ensure(await latestCompareHistory.locator("[data-restore-compare-history]").count() === 1, "recent comparison should restore comparison conditions");
    await page.click("#compareClearHistoryButton");
    await page.waitForFunction(() => document.querySelectorAll("#compareHistoryList .mini-history-item").length === 0);

    await page.locator('.top-tab[data-tab="voices"]').click();
    await page.waitForSelector("#voicesPage.active");
    ensure(await page.locator('[data-voice-view-panel="register"]').isVisible(), "reference voice page should open on new registration");
    ensure(!(await page.locator('[data-voice-view-panel="manage"]').isVisible()), "management should not be visible with registration forms");
    await page.locator('[data-voice-view="manage"]').click();
    await page.waitForSelector('[data-voice-manage-id="sample_neutral"]');
    ensure(await page.locator("#voiceExistingTextInput").inputValue() === "これは既存の参照音声テキストです。", "existing reference text was not displayed");
    await page.fill("#voiceExistingTextInput", "修正後の既存参照音声テキストです。");
    await page.click("#voiceExistingTextSaveButton");
    await page.waitForFunction(() => document.querySelector("#voiceExistingTextInput")?.value === "修正後の既存参照音声テキストです。");
    ensure(referenceTextSaveCount === 1, "existing reference text save endpoint was not called");

    await page.locator('[data-voice-view="register"]').click();
    await page.locator('[data-voice-method="mic"]').click();
    ensure(await page.locator('[data-voice-method-panel="mic"]').isVisible(), "microphone registration form did not open");
    await page.fill("#voiceIdInput", "new_voice_e2e");
    await page.fill("#voiceReferenceTextInput", "新しい参照音声として実際に読んだ文章です。");
    await page.selectOption("#voiceMicDeviceSelect", "voice-mic");
    await page.click("#voiceRecordStartButton");
    await page.waitForFunction(() => document.querySelector("#voiceRecordStartButton")?.disabled && !document.querySelector("#voiceRecordStopButton")?.disabled);
    await page.click("#voiceRecordStopButton");
    await page.waitForFunction(() => document.querySelector("#voiceRecordingBadge")?.textContent === "録音済み");
    ensure(!(await page.locator("#voiceSaveButton").isDisabled()), "reference voice save button should be enabled after recording");
    await page.click("#voiceSaveButton");
    await page.waitForSelector("#voiceRegistrationSuccess:not([hidden])");
    ensure((await page.locator("#voiceRegistrationSuccess").textContent())?.includes("new_voice_e2e"), "registration success panel should identify the new voice");
    await page.locator('[data-success="manage"]').click();
    await page.waitForSelector('[data-voice-manage-id="new_voice_e2e"]');
    ensure(referenceVoiceSaveCount === 1, "new reference voice save endpoint was not called");
    await page.waitForFunction(() => Boolean(document.querySelector('#normalReferenceVoiceSelect option[value="new_voice_e2e"]')));
    ensure(await page.locator("#voiceUseExistingIdButton").count() === 0, "unrequested recording replacement button should not exist");

    await page.click('[data-voice-manage-id="new_voice_e2e"]');
    await page.click("#voiceArchiveButton");
    await page.waitForFunction(() => document.querySelector('[data-voice-manage-id="new_voice_e2e"]')?.classList.contains("archived"));
    ensure(referenceArchiveChangeCount === 1, "archive endpoint was not called");
    ensure(await page.locator('[data-voice-manage-id="new_voice_e2e"]').count() === 1, "archived voice should remain in the management list");
    for (const selectId of ["normalReferenceVoiceSelect", "compareReferenceVoiceSelect", "rvcReferenceVoiceSelect"]) {
      const archivedOption = page.locator(`#${selectId} option[value="new_voice_e2e"]`);
      await archivedOption.waitFor({ state: "detached" });
      ensure(await archivedOption.count() === 0, `archived voice should be hidden from ${selectId}`);
    }

    await page.reload({ waitUntil: "networkidle", timeout: 120000 });
    await page.waitForSelector("#voicesPage.active");
    await page.locator('[data-voice-view="manage"]').click();
    await page.waitForSelector('[data-voice-manage-id="new_voice_e2e"].archived');
    await page.click('[data-voice-manage-id="new_voice_e2e"]');
    ensure(await page.locator("#voiceExistingTextInput").inputValue() === "新しい参照音声として実際に読んだ文章です。", "archived reference text did not persist after reload");
    ensure(await page.locator("#voiceArchiveButton").textContent() === "アーカイブから戻す", "archived voice should offer restore");
    await page.click("#voiceArchiveButton");
    await page.waitForFunction(() => !document.querySelector('[data-voice-manage-id="new_voice_e2e"]')?.classList.contains("archived"));
    ensure(referenceArchiveChangeCount === 2, "restore endpoint was not called");
    await page.waitForFunction(() => Boolean(document.querySelector('#normalReferenceVoiceSelect option[value="new_voice_e2e"]')));

    await page.locator('[data-voice-view="register"]').click();
    await page.locator('[data-voice-method="youtube"]').click();
    ensure(await page.locator('[data-voice-method-panel="youtube"]').isVisible(), "YouTube registration form did not open");
    ensure((await page.locator(".rights-confirmation").textContent()).includes("権利や利用規約を確認"), "YouTube rights confirmation is missing");
    await page.fill("#youtubeReferenceUrlInput", "https://youtu.be/dQw4w9WgXcQ");
    ensure(await page.locator("#youtubeReferenceAnalyzeButton").isDisabled(), "YouTube analyze must remain disabled before rights confirmation");
    await page.check("#youtubeReferenceRightsInput");
    ensure(!(await page.locator("#youtubeReferenceAnalyzeButton").isDisabled()), "YouTube analyze should not require a voice name before candidate review");
    ensure(await page.locator("#youtubeReferenceDemucsInput").isChecked(), "BGM removal should be enabled by default");
    await page.click("#youtubeReferenceAnalyzeButton");
    await page.waitForFunction(() => document.querySelectorAll(".youtube-candidate-card").length === 2);
    ensure(youtubeCandidateRequestCount === 1, "YouTube candidate endpoint was not called");
    ensure(await page.locator('.youtube-candidate-card[data-youtube-candidate-id$=":c001"] audio').count() === 2, "BGM-removed candidate should show cleaned and original audio");
    const separationWarning = await page.locator('.youtube-candidate-card[data-youtube-candidate-id$=":c002"] .youtube-candidate-warning').textContent();
    ensure(separationWarning?.includes("BGM・伴奏除去") && !separationWarning.includes("Demucs"), "user-facing separation fallback warning was not normalized");
    const youtubeLayout = await page.evaluate(() => {
      const panel = document.querySelector('[data-voice-method-panel="youtube"]')?.getBoundingClientRect();
      const grid = document.querySelector("#youtubeReferenceCandidates");
      const cards = Array.from(document.querySelectorAll(".youtube-candidate-card")).map((element) => element.getBoundingClientRect());
      const textareas = Array.from(document.querySelectorAll("[data-youtube-candidate-text]"));
      const rights = document.querySelector(".rights-confirmation");
      return {
        panelLeft: panel?.left || 0,
        panelRight: panel?.right || 0,
        columns: grid ? getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length : 0,
        cardWidths: cards.map((card) => card.width),
        cardInsidePanel: cards.every((card) => card.left >= (panel?.left || 0) - 2 && card.right <= (panel?.right || 0) + 2),
        transcriptFits: textareas.every((textarea) => textarea.scrollHeight <= textarea.clientHeight + 3 && getComputedStyle(textarea).overflowY === "hidden"),
        rightsFits: !rights || rights.scrollWidth <= rights.clientWidth + 2,
        pageFits: document.documentElement.scrollWidth <= window.innerWidth + 2
      };
    });
    ensure(youtubeLayout.columns === 3, `YouTube candidate grid should use three desktop columns: ${JSON.stringify(youtubeLayout)}`);
    ensure(youtubeLayout.cardWidths.every((width) => width >= 300), `YouTube candidate card is too narrow: ${JSON.stringify(youtubeLayout)}`);
    ensure(youtubeLayout.cardInsidePanel && youtubeLayout.transcriptFits && youtubeLayout.rightsFits && youtubeLayout.pageFits, `YouTube layout overflow: ${JSON.stringify(youtubeLayout)}`);
    await page.fill("#youtubeReferenceNameInput", "youtube_voice_e2e");
    await page.fill('.youtube-candidate-card[data-youtube-candidate-id$=":c001"] [data-youtube-candidate-text]', "修正したYouTube候補の文字起こしです。");
    await page.click('.youtube-candidate-card[data-youtube-candidate-id$=":c001"] [data-youtube-register]');
    await page.waitForSelector("#voiceRegistrationSuccess:not([hidden])");
    await page.locator('[data-success="manage"]').click();
    await page.waitForSelector('[data-voice-manage-id="youtube_voice_e2e"]');
    ensure(youtubeRegisterCount === 1, "YouTube candidate registration endpoint was not called");
    for (const selectId of ["normalReferenceVoiceSelect", "compareReferenceVoiceSelect", "rvcReferenceVoiceSelect"]) {
      await page.waitForSelector(`#${selectId} option[value="youtube_voice_e2e"]`, { state: "attached" });
    }
    await page.click('[data-voice-manage-id="youtube_voice_e2e"]');
    ensure(await page.locator("#voiceExistingTextInput").inputValue() === "修正したYouTube候補の文字起こしです。", "YouTube transcript edit was not saved");

    if (process.env.VOICE_MANAGER_SCREENSHOT) {
      await page.screenshot({ path: process.env.VOICE_MANAGER_SCREENSHOT, fullPage: true });
    }

    await page.locator('.top-tab[data-tab="history"]').click();
    await page.waitForSelector("#historyPage.active");
    await page.waitForFunction(() => document.querySelectorAll("#historyList .history-card").length >= 2, { timeout: 15000 });
    const historyCountBeforeReload = await page.locator("#historyList .history-card").count();
    ensure(historyCountBeforeReload >= 2, `expected 2 history entries, got ${historyCountBeforeReload}`);

    for (const value of ["normal", "compare", "rvc", "all"]) {
      const filter = page.locator(`[data-history-filter="type"][data-value="${value}"]`);
      await filter.click();
      ensure(await filter.evaluate((button) => button.classList.contains("active")), `history type filter did not activate: ${value}`);
    }
    for (const value of ["success", "failed", "all"]) {
      const filter = page.locator(`[data-history-filter="status"][data-value="${value}"]`);
      await filter.click();
      ensure(await filter.evaluate((button) => button.classList.contains("active")), `history status filter did not activate: ${value}`);
    }

    let firstHistoryCard = page.locator("#historyList .history-card").first();
    await firstHistoryCard.locator('[data-history-action="play"]').click();
    await page.waitForFunction(() => !document.querySelector("#historyList .history-card audio")?.paused);
    await firstHistoryCard.locator('[data-history-action="copy"]').click();
    ensure(Boolean(await page.evaluate(() => window.__lastClipboardText)), "history copy button did not copy text");
    await firstHistoryCard.locator('[data-history-action="folder"]').click();
    ensure(Boolean(await page.evaluate(() => window.__lastClipboardText)), "history file-info button did not copy a value");
    await firstHistoryCard.locator('[data-history-action="favorite"]').click();
    await page.waitForFunction(() => document.querySelector("#historyList .history-card [data-history-action='favorite']")?.textContent?.includes("お気に入り済み"));

    await page.check("#historyFavoriteOnly");
    ensure(await page.locator("#historyList .history-card").count() >= 1, "favorite-only filter hid the favorited item");
    await page.uncheck("#historyFavoriteOnly");
    firstHistoryCard = page.locator("#historyList .history-card").first();
    await page.locator("#historyDetailBody [data-history-action='favorite']").click();
    await page.click("#historyDetailClose");
    ensure((await page.locator("#historyDetailBody").textContent()).includes("左の履歴を選択"), "history detail close button did not close the detail");

    firstHistoryCard = page.locator("#historyList .history-card:has(.history-type-badge.normal)").first();
    await firstHistoryCard.locator('[data-history-action="restore"]').click();
    await page.waitForSelector("#normalPage.active");
    await page.locator('.top-tab[data-tab="history"]').click();
    await page.waitForSelector("#historyPage.active");

    const historyAudioOne = await audioState(page.locator("#historyList audio").nth(0));
    const historyAudioTwo = await audioState(page.locator("#historyList audio").nth(1));
    ensure(historyAudioOne.duration > 0, "latest history audio should be playable");
    ensure(historyAudioTwo.duration > 0, "previous history audio should be playable");

    await page.reload({ waitUntil: "networkidle", timeout: 120000 });
    await page.waitForSelector("#historyPage.active");
    await page.waitForFunction(() => document.querySelectorAll("#historyList .history-card").length >= 2, { timeout: 15000 });
    const historyCountAfterReload = await page.locator("#historyList .history-card").count();
    ensure(historyCountAfterReload >= 2, `history should persist after reload, got ${historyCountAfterReload}`);

    await page.evaluate(() => window.localTtsHistory.clear());
    await page.waitForFunction(() => document.querySelectorAll("#historyList .history-card").length === 0, { timeout: 10000 });

    const historyPerformanceFixture = await page.evaluate(() => {
      const items = Array.from({ length: 120 }, (_, index) => ({
        id: `history-performance-${index}`,
        createdAt: new Date(Date.now() - index * 1000).toISOString(),
        type: index % 3 === 0 ? "rvc" : index % 3 === 1 ? "compare" : "normal",
        status: "success",
        text: `履歴パフォーマンス確認 ${index}`,
        model: "irodori_v3",
        models: ["irodori_v3", "mock"],
        raw: { stderr: "x".repeat(20000), request: { seed: index } },
      }));
      localStorage.setItem("local-tts-generation-history-v1", JSON.stringify(items));
      for (const key of ["local-tts-normal-history-v3", "local-tts-compare-history-v1", "local-tts-rvc-history-v1"]) {
        localStorage.setItem(key, JSON.stringify(items.slice(0, 8)));
      }
      location.hash = "#normal";
      return { originalBytes: new Blob([JSON.stringify(items)]).size };
    });
    await page.reload({ waitUntil: "networkidle", timeout: 120000 });
    await page.waitForSelector("#normalPage.active");
    ensure(await page.locator("#historyList .history-card").count() === 0, "hidden history page must not eagerly render cards");
    ensure(await page.locator("#historyList audio").count() === 0, "hidden history page must not create audio elements");

    await page.locator('.top-tab[data-tab="history"]').click();
    await page.waitForSelector("#historyPage.active");
    await page.waitForFunction(() => document.querySelectorAll("#historyList .history-card").length === 20, { timeout: 10000 });
    ensure((await page.locator("#historyResultSummary").textContent())?.includes("20 / 120件"), "history summary must show displayed and saved counts");
    ensure(await page.locator("#historyList audio").count() === 20, "history must create audio elements only for the visible page");
    await page.click("#historyLoadMoreButton");
    await page.waitForFunction(() => document.querySelectorAll("#historyList .history-card").length === 40, { timeout: 10000 });
    const historyDesktopLayout = await page.evaluate(() => ({
      pageFits: document.documentElement.scrollWidth <= window.innerWidth + 2,
      clearButtonVisible: Boolean(document.querySelector("#historyClearAllButton")?.getBoundingClientRect().width),
      loadMoreVisible: !document.querySelector("#historyLoadMoreButton")?.hidden,
    }));
    ensure(historyDesktopLayout.pageFits && historyDesktopLayout.clearButtonVisible && historyDesktopLayout.loadMoreVisible, `desktop history layout is not usable: ${JSON.stringify(historyDesktopLayout)}`);
    await page.setViewportSize({ width: 760, height: 900 });
    await page.waitForTimeout(100);
    const historyMobileLayout = await page.evaluate(() => ({
      pageFits: document.documentElement.scrollWidth <= window.innerWidth + 2,
      clearButtonFits: document.querySelector("#historyClearAllButton")?.scrollWidth <= document.querySelector("#historyClearAllButton")?.clientWidth + 2,
      loadMoreFits: document.querySelector("#historyLoadMoreButton")?.scrollWidth <= document.querySelector("#historyLoadMoreButton")?.clientWidth + 2,
    }));
    ensure(historyMobileLayout.pageFits && historyMobileLayout.clearButtonFits && historyMobileLayout.loadMoreFits, `mobile history layout overflows: ${JSON.stringify(historyMobileLayout)}`);

    const compactedHistory = await page.evaluate(() => {
      const raw = localStorage.getItem("local-tts-generation-history-v1") || "[]";
      const items = JSON.parse(raw);
      return {
        bytes: new Blob([raw]).size,
        count: items.length,
        firstRawTextLength: String(items[0]?.rawText || "").length,
        hasLegacyRaw: Object.prototype.hasOwnProperty.call(items[0] || {}, "raw"),
      };
    });
    ensure(compactedHistory.count === 120, `history save limit changed unexpectedly: ${compactedHistory.count}`);
    ensure(!compactedHistory.hasLegacyRaw, "legacy nested raw payload must be compacted out of browser history");
    ensure(compactedHistory.firstRawTextLength <= 6100, `history diagnostic payload was not bounded: ${compactedHistory.firstRawTextLength}`);
    ensure(compactedHistory.bytes < historyPerformanceFixture.originalBytes, "history migration did not reduce stored payload size");

    page.once("dialog", (dialog) => dialog.accept());
    await page.click("#historyClearAllButton");
    await page.waitForFunction(() => document.querySelectorAll("#historyList .history-card").length === 0, { timeout: 10000 });
    const clearedHistoryKeys = await page.evaluate(() => ({
      full: JSON.parse(localStorage.getItem("local-tts-generation-history-v1") || "[]").length,
      normal: JSON.parse(localStorage.getItem("local-tts-normal-history-v3") || "[]").length,
      compare: JSON.parse(localStorage.getItem("local-tts-compare-history-v1") || "[]").length,
      rvc: JSON.parse(localStorage.getItem("local-tts-rvc-history-v1") || "[]").length,
    }));
    ensure(Object.values(clearedHistoryKeys).every((count) => count === 0), `clear-all did not clear peer histories: ${JSON.stringify(clearedHistoryKeys)}`);

    console.log(JSON.stringify({
      ok: true,
      frontBase,
      historyCountBeforeReload,
      historyCountAfterReload,
      historyPerformanceFixture,
      compactedHistory,
      clearedHistoryKeys,
      firstAudio,
      historyAudioOne,
      historyAudioTwo,
      speakCount
    }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message, stack: error.stack }, null, 2));
  process.exit(1);
});
