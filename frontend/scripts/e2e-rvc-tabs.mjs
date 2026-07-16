import { createServer } from "../server.js";

const CHROME_PATH = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SAMPLE_TEXT = "これは音声変換の動作確認です。自然な発音と聞き取りやすさを確認します。";

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

function makeWavBuffer(durationSec = 1, sampleRate = 16000) {
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

async function ensureVisible(locator, message) {
  ensure(await locator.isVisible(), message);
}

async function ensureHidden(locator, message) {
  ensure(!(await locator.isVisible()), message);
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
    const fakeDevices = [
      { kind: "audioinput", deviceId: "default", label: "既定 - Fake Microphone" },
      { kind: "audioinput", deviceId: "mic-1", label: "Fake Microphone 1" },
      { kind: "audioinput", deviceId: "mic-2", label: "Fake Microphone 2" }
    ];
    const mediaDevices = navigator.mediaDevices || {};
    Object.defineProperty(navigator, "mediaDevices", {
      configurable: true,
      value: {
        ...mediaDevices,
        enumerateDevices: async () => fakeDevices,
        getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }),
        addEventListener: () => {},
        removeEventListener: () => {}
      }
    });
  });
  await page.addInitScript(() => {
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
        this.ondataavailable?.({ data: new Blob(["fake-audio"], { type: this.mimeType }) });
        queueMicrotask(() => this.onstop?.());
      }
    }
    window.MediaRecorder = FakeMediaRecorder;
  });
  const referenceAudioBuffer = makeWavBuffer(3);
  await page.route("**/api/models", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        models: [
          {
            id: "irodori_v3",
            model: "irodori_v3",
            label: "Irodori v3",
            available: true,
            enabled: true,
            supportsReferenceVoice: true,
            requiresReferenceAudio: false,
            supportsInstruction: true,
            executionDevice: "cpu",
            cpuFallback: true,
            performanceWarning: "IrodoriはCPUで動作しています。GPU動作より大幅に遅く、音声生成に数分かかる場合があります。"
          },
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
          }
        ]
      })
    });
  });
  let exposeRvcModels = true;
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
          modelPath: "C:\\models\\rvc\\voice-a\\voice-a.pth",
          indexPath: "C:\\models\\rvc\\voice-a\\voice-a.index",
          inputSource: "tts",
          externalAudioPath: "",
          cleanExternalAudio: false,
          demucsModel: "htdemucs_ft"
        },
        modelRoot: "C:\\models\\rvc",
        readyCount: exposeRvcModels ? 2 : 0,
        guideUrl: "/rvc-model-guide.html",
        models: exposeRvcModels ? [
          { id: "voice-a", label: "Voice A", modelPath: "C:\\models\\rvc\\voice-a\\voice-a.pth", indexPath: "C:\\models\\rvc\\voice-a\\voice-a.index", ready: true, errorReason: "" },
          { id: "voice-b", label: "Voice B", modelPath: "C:\\models\\rvc\\voice-b\\voice-b.pth", indexPath: "C:\\models\\rvc\\voice-b\\voice-b.index", ready: true, errorReason: "" }
        ] : [
          { id: "incomplete", label: "Incomplete Voice", modelPath: "C:\\models\\rvc\\incomplete\\voice.pth", indexPath: "", ready: false, errorReason: ".index がありません" }
        ]
      })
    });
  });
  let recordingUploadCount = 0;
  const convertBodies = [];
  let convertCount = 0;
  let convertFailureCount = 0;
  let failNextConvert = false;
  let denoiseCount = 0;
  await page.route("**/api/reference-voices/*/audio", async (route) => {
    await route.fulfill({ status: 200, contentType: "audio/wav", body: referenceAudioBuffer });
  });
  await page.route("**/api/rvc/audio/**", async (route) => {
    await route.fulfill({ status: 200, contentType: "audio/wav", body: makeWavBuffer(1.4) });
  });
  await page.route("**/api/reference-voices", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        defaultReferenceVoice: "sample_voice",
        voices: [
          {
            voiceId: "sample_voice",
            displayName: "sample_voice",
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

  await page.route("**/api/rvc/recording", async (route) => {
    recordingUploadCount += 1;
    const requestBody = JSON.parse(route.request().postData() || "{}");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        recording: {
          filename: `mic-e2e-${recordingUploadCount}.wav`,
          path: `C:\\rvc\\mic-e2e-${recordingUploadCount}.wav`,
          url: `/api/rvc/audio/intermediate/mic-e2e-${recordingUploadCount}.wav`,
          durationSec: 1.2,
          scriptText: requestBody.scriptText || "",
          createdAt: new Date().toISOString()
        }
      })
    });
  });

  await page.route("**/api/rvc/convert", async (route) => {
    const requestBody = JSON.parse(route.request().postData() || "{}");
    convertBodies.push(requestBody);
    if (failNextConvert) {
      failNextConvert = false;
      convertFailureCount += 1;
      await route.fulfill({
        status: 500,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          errorMessage: "CUDA out of memory while running RVC inference",
          stderr: "Traceback: CUDA out of memory while running RVC inference",
          command: ["python", "infer-web.py", "--model", requestBody.rvc?.modelPath || "missing.pth"]
        })
      });
      return;
    }
    convertCount += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        result: {
          id: `converted-e2e-${convertCount}`,
          input: { source: requestBody.rvc?.inputSource || "file" },
          tts: {},
          intermediate: {
            filename: "prepared-e2e.wav",
            path: "C:\\rvc\\prepared-e2e.wav",
            url: "/api/rvc/audio/intermediate/prepared-e2e.wav"
          },
          converted: {
            filename: `converted-e2e-${convertCount}.wav`,
            path: `C:\\rvc\\converted-e2e-${convertCount}.wav`,
            url: `/api/rvc/audio/converted/converted-e2e-${convertCount}.wav`
          },
          rvc: requestBody.rvc || {}
        }
      })
    });
  });

  await page.route("**/api/rvc/denoise", async (route) => {
    denoiseCount += 1;
    const requestBody = JSON.parse(route.request().postData() || "{}");
    const denoisedFilename = String(requestBody.filename || "converted-e2e-1.wav").replace(/\.wav$/i, "-denoised.wav");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ok: true,
        result: {
          original: { filename: requestBody.filename },
          denoised: {
            filename: denoisedFilename,
            path: `C:\\rvc\\${denoisedFilename}`,
            url: `/api/rvc/audio/converted/${denoisedFilename}`
          }
        }
      })
    });
  });

  try {
    await page.goto(`${frontBase}/`, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForSelector('#normalPage.active');
    await ensureVisible(page.locator('[data-tab="normal"]').first(), "normal tab missing");
    await ensureVisible(page.locator('[data-tab="compare"]').first(), "compare tab missing");
    await ensureVisible(page.locator('[data-tab="rvc"]').first(), "rvc tab missing");
    await ensureVisible(page.locator('[data-tab="history"]').first(), "history tab missing");
    await ensureVisible(page.locator('[data-tab="guide"]').first(), "guide tab missing");
    ensure(await page.locator('#normalTextInput').inputValue() === SAMPLE_TEXT, "normal default text mismatch");
    await ensureHidden(page.locator('#normalLanguageInput'), "normal language field should be hidden");

    await page.locator('.top-tab[data-tab="guide"]').click();
    await page.waitForSelector('#guidePage.active');
    ensure((await page.locator('#guideRvcActionCard h3').textContent()) === "既存音声の声質を変える", "guide should explain the RVC task first");
    ensure((await page.locator('#guideRvcActionCard a').getAttribute('href'))?.includes('RVC-Project/Retrieval-based-Voice-Conversion-WebUI'), "official RVC training link is missing");

    await page.locator('.top-tab[data-tab="history"]').click();
    await page.waitForSelector('#historyPage.active');
    await ensureVisible(page.locator('#historyList'), "history list missing");
    await ensureVisible(page.locator('#historySearchInput'), "history search missing");

    await page.locator('.top-tab[data-tab="compare"]').click();
    await page.waitForSelector('#comparePage.active');
    await ensureVisible(page.locator('#compareModelCards'), "compare page did not open");
    ensure(await page.locator('#compareTextInput').inputValue() === SAMPLE_TEXT, "compare default text mismatch");
    await ensureHidden(page.locator('#compareLanguageInput'), "compare language field should be hidden");

    const preSwitchScrollY = await page.evaluate(() => { window.scrollTo(0, document.documentElement.scrollHeight); return window.scrollY; });
    ensure(preSwitchScrollY > 0, "RVC tab switch scroll test requires a scrollable page");
    await page.locator('.top-tab[data-tab="rvc"]').click();
    await page.waitForSelector('#rvcPage.active');
    await page.waitForTimeout(50);
    var rvcLayout = await page.evaluate(() => {
      const form = document.querySelector('#rvcPage .form-panel');
      const logPanel = document.querySelector('#rvcLogBox')?.closest('.panel');
      const params = document.querySelector('#rvcPage .rvc-params-panel');
      const convert = document.querySelector('#rvcConvertButton');
      if (!form || !logPanel || !params || !convert) return null;
      const formRect = form.getBoundingClientRect();
      const logRect = logPanel.getBoundingClientRect();
      const paramsRect = params.getBoundingClientRect();
      const convertRect = convert.getBoundingClientRect();
      return {
        scrollY: window.scrollY,
        logPosition: getComputedStyle(logPanel.parentElement).position,
        formTop: formRect.top,
        logTop: logRect.top,
        paramsWidth: paramsRect.width,
        convertWidth: convertRect.width
      };
    });
    ensure(rvcLayout, "RVC layout metrics unavailable");
    ensure(rvcLayout.scrollY <= 64, `RVC tab should open within the fixed header range: scrollY=${rvcLayout.scrollY}`);
    ensure(rvcLayout.logPosition === "static", "RVC execution log should not detach from the form while scrolling");
    ensure(Math.abs(rvcLayout.formTop - rvcLayout.logTop) <= 2, "RVC form and execution log should align at the top");
    ensure(rvcLayout.convertWidth >= rvcLayout.paramsWidth - 40, "RVC convert button should fill the parameter panel");
    await ensureHidden(page.locator('#rvcLanguageInput'), "rvc language field should be hidden");
    ensure(await page.locator('#rvcTextInput').inputValue() === SAMPLE_TEXT, "rvc default text mismatch");
    ensure(await page.locator('#rvcIndexRatePresetSelect').inputValue() === "0.35", "RVC index_rate preset default mismatch");
    ensure(await page.locator('#rvcF0UpKeyPresetSelect').inputValue() === "0", "RVC f0up_key preset default mismatch");
    ensure(await page.locator('#rvcProtectPresetSelect').inputValue() === "0.33", "RVC protect preset default mismatch");
    ensure((await page.locator('#rvcLogBox').textContent()) === "エラーはありません。", "RVC log should start with a short no-error message");
    await ensureVisible(page.locator('#rvcLogCopyButton'), "AI-ready log copy button is missing");
    await ensureVisible(page.locator('#rvcIndexRatePresetSelect'), "RVC voice similarity control missing");
    await ensureVisible(page.locator('#rvcF0UpKeyPresetSelect'), "RVC pitch control missing");
    await ensureVisible(page.locator('#rvcProtectPresetSelect'), "RVC stability control missing");
    ensure(await page.locator('#rvcVoiceModelSelect option').count() === 2, "two RVC models should be selectable");
    ensure(await page.locator('#rvcVoiceModelSelect').inputValue() === "voice-a", "configured RVC model should be selected by default");
    ensure((await page.locator('#rvcModelPathInput').inputValue()).endsWith('voice-a.pth'), "selected RVC model path was not resolved");
    await ensureHidden(page.locator('#rvcDemucsModelInput'), "internal background-removal model input should be hidden");
    await ensureHidden(page.locator('#rvcMissingModelPanel'), "model setup panel should hide when usable models exist");

    await ensureHidden(page.locator('#rvcMicControls'), "RVC mic controls should be hidden when no previous source exists");
    await ensureHidden(page.locator('#rvcFileSourceControls'), "RVC file source controls should be hidden in TTS mode");
    await ensureVisible(page.locator('#rvcTtsControls'), "RVC TTS controls should be visible by default");
    await ensureVisible(page.locator('#rvcTextInput'), "RVC text should be visible by default");
    ensure(await page.locator('#rvcIntermediateTitle').textContent() === "TTS入力音声", "TTS should be the initial source when no previous source exists");
    ensure(await page.locator('input[name="rvcInputSource"][value="tts"]').isChecked(), "TTS input source should be checked by default");
    ensure((await page.locator('#rvcStatusText').textContent()).includes("IrodoriはCPUで動作しています。GPU動作より大幅に遅く、音声生成に数分かかる場合があります。"), "RVC TTS source should show the CPU Irodori warning");
    ensure(await page.locator('#rvcStatusText').evaluate((element) => element.classList.contains('warning')), "RVC CPU Irodori warning should use warning styling");

    await page.locator('input[name="rvcInputSource"][value="mic"]').click();
    await ensureVisible(page.locator('#rvcMicControls'), "RVC mic controls should show after selecting mic");
    await page.waitForFunction(() => Boolean(document.querySelector('#rvcMicDeviceSelect option[value="mic-2"]')));
    await page.locator('#rvcMicDeviceSelect').selectOption('mic-2');
    ensure(await page.locator('#rvcMicDeviceSelect').inputValue() === "mic-2", "RVC mic device selection did not apply");
    await page.evaluate(async () => { await window.loadRvcMicDevices(); });
    ensure(await page.locator('#rvcMicDeviceSelect').inputValue() === "mic-2", "RVC mic device reset to default after reload");

    await page.click('#rvcMicStartButton');
    await page.waitForFunction(() => document.querySelector('#rvcMicStartButton')?.disabled && !document.querySelector('#rvcMicStopButton')?.disabled);
    ensure(await page.locator('#rvcMicBadge').textContent() === "録音中", "RVC mic start button did not start recording");
    await page.click('#rvcMicStopButton');
    await page.waitForFunction(() => document.querySelector('#rvcMicPath')?.textContent?.includes('mic-e2e-1.wav'));
    ensure(recordingUploadCount === 1, "RVC mic stop did not upload the recording");
    ensure(!(await page.locator('#rvcMicUseButton').isDisabled()), "RVC use-recording button should be enabled after recording");
    await page.click('#rvcMicUseButton');
    ensure((await page.locator('#rvcMicBadge').textContent()) === "入力に設定済み", "RVC use-recording button did not select the recording");

    await page.click('#rvcMicRerecordButton');
    await page.waitForFunction(() => document.querySelector('#rvcMicBadge')?.textContent === "録音中");
    await page.click('#rvcMicStopButton');
    await page.waitForFunction(() => document.querySelector('#rvcMicPath')?.textContent?.includes('mic-e2e-2.wav'));
    ensure(recordingUploadCount === 2, "RVC rerecord button did not create a new recording");

    await page.locator('input[name="rvcInputSource"][value="tts"]').click();
    await ensureVisible(page.locator('#rvcTtsControls'), "RVC TTS controls should be visible in TTS mode");
    await ensureVisible(page.locator('#rvcTextInput'), "RVC text should be visible in TTS mode");
    ensure(await page.locator('#rvcSeedInput').inputValue() === "1", "RVC seed should start at 1");
    ensure(await page.locator('#rvcSeedAutoIncrementInput').isChecked(), "RVC seed auto-update should be on by default");
    await page.fill('#rvcSeedInput', '3001');
    await page.check('#rvcAutoPlayInput');
    await ensureHidden(page.locator('#rvcFileSourceControls'), "RVC file source controls should be hidden in TTS mode");
    await ensureHidden(page.locator('#rvcMicControls'), "RVC mic controls should be hidden in TTS mode");
    ensure(await page.locator('#rvcIntermediateTitle').textContent() === "TTS入力音声", "TTS mode title mismatch");
    ensure(await page.locator('#rvcPrepareTtsButton').count() === 0, "obsolete RVC prepare button should be removed");
    ensure(await page.locator('#rvcCleanExternalAudioInput').count() === 0, "obsolete pre-RVC cleanup toggle should be removed");
    ensure(await page.locator('#rvcChunkHardMaxInput').getAttribute('type') === "hidden", "RVC hard max should remain internal only");
    await page.click('#rvcReferencePreviewButton');
    await page.waitForFunction(() => document.querySelector('#rvcReferencePreviewButton')?.textContent === "■");
    await page.click('#rvcReferencePreviewButton');
    await page.waitForFunction(() => document.querySelector('#rvcReferencePreviewButton')?.textContent === "▶");

    await ensureVisible(page.locator('#rvcAdvancedSettings'), "RVC advanced settings should be visible in TTS mode");
    await page.locator('#rvcAdvancedSettings > summary').click();
    ensure(await page.locator('#rvcAdvancedSettings').evaluate((element) => element.open), "RVC advanced settings did not open");
    await page.fill('#rvcInstructionInput', '明るく自然な話し方で読み上げる');

    const rvcTextBeforeEmojiClicks = await page.locator('#rvcTextInput').inputValue();
    const rvcEmojiButtons = page.locator('#irodoriEmojiPalette-rvc .irodori-emoji-chip');
    ensure(await rvcEmojiButtons.count() === 10, "RVC emoji palette should have 10 buttons");
    for (let index = 0; index < await rvcEmojiButtons.count(); index += 1) await rvcEmojiButtons.nth(index).click();
    ensure((await page.locator('#rvcTextInput').inputValue()).length > rvcTextBeforeEmojiClicks.length, "RVC emoji buttons did not insert text");
    await page.fill('#rvcTextInput', rvcTextBeforeEmojiClicks);

    for (const preset of ["160", "240", "360"]) {
      const button = page.locator(`[data-chunk-scope="rvc"] [data-chunk-preset="${preset}"]`);
      await button.click();
      ensure(await page.locator('#rvcChunkTargetInput').inputValue() === preset, `RVC chunk preset did not apply: ${preset}`);
      ensure(await button.evaluate((element) => element.classList.contains('active')), `RVC chunk preset did not become active: ${preset}`);
    }
    await page.click('#rvcChunkPreviewToggle');
    await ensureVisible(page.locator('#rvcChunkPreview'), "RVC chunk preview did not open");
    await page.click('#rvcChunkPreviewToggle');
    await ensureHidden(page.locator('#rvcChunkPreview'), "RVC chunk preview did not close");

    const rvcHelpButtons = page.locator('.rvc-help');
    ensure(await rvcHelpButtons.count() === 3, "RVC should have three help buttons");
    for (let index = 0; index < await rvcHelpButtons.count(); index += 1) {
      const button = rvcHelpButtons.nth(index);
      await button.click();
      ensure(await button.evaluate((element) => element.classList.contains('open')), `RVC help button ${index + 1} did not open`);
      await button.click();
      ensure(!(await button.evaluate((element) => element.classList.contains('open'))), `RVC help button ${index + 1} did not close`);
    }

    await page.selectOption('#rvcVoiceModelSelect', 'voice-b');
    ensure((await page.locator('#rvcModelPathInput').inputValue()).endsWith('voice-b.pth'), "RVC model switch did not update the model path");
    ensure((await page.locator('#rvcIndexPathInput').inputValue()).endsWith('voice-b.index'), "RVC model switch did not update the index path");
    await page.click('#rvcConvertButton');
    await page.waitForFunction(() => document.querySelector('#rvcConvertedAudio')?.getAttribute('src')?.includes('converted-e2e-1.wav'));
    ensure(convertCount === 1, "RVC convert button did not call the convert endpoint");
    ensure(convertBodies[0]?.instruction === '明るく自然な話し方で読み上げる', "RVC TTS instruction was not sent to the conversion request");
    ensure(convertBodies[0]?.rvc?.modelId === 'voice-b', "selected RVC model ID was not sent to the conversion request");
    ensure(convertBodies[0]?.rvc?.modelPath?.endsWith('voice-b.pth'), "selected RVC model path was not sent to the conversion request");
    ensure(convertBodies[0]?.rvc?.indexPath?.endsWith('voice-b.index'), "selected RVC index path was not sent to the conversion request");
    ensure((await page.locator('#rvcConvertedBadge').textContent()) === "変換済み", "RVC convert button did not mark the result as converted");
    ensure((await page.locator('#rvcLogBox').textContent()) === "処理が完了しました。", "successful RVC log should stay short");
    ensure(!(await page.locator('#rvcLogBox').textContent())?.includes('{'), "RVC log should not expose raw JSON");
    ensure(await page.locator('#rvcSeedInput').inputValue() === "3002", "RVC seed did not increment after successful TTS conversion");
    await page.waitForFunction(() => document.querySelectorAll('#rvcHistoryList .mini-history-item').length === 1);
    ensure(await page.locator('#rvcHistoryList [data-history-audio]').count() === 1, "successful RVC history should keep the converted audio");
    ensure(await page.locator('#rvcHistoryList [data-restore-rvc-history]').count() === 1, "RVC history should expose settings restore");
    await page.waitForFunction(() => !document.querySelector('#rvcConvertedAudio')?.paused);
    await page.locator('#rvcConvertedAudio').evaluate((audio) => audio.pause());
    await ensureVisible(page.locator('#rvcDenoiseButton'), "post-RVC denoise button should appear after conversion");
    await page.click('#rvcDenoiseButton');
    await page.waitForFunction(() => document.querySelector('#rvcDenoisedAudio')?.getAttribute('src')?.includes('converted-e2e-1-denoised.wav'));
    ensure(denoiseCount === 1, "post-RVC denoise endpoint was not called");
    await ensureVisible(page.locator('#rvcDenoisedCard'), "post-RVC denoised result should be shown");

    failNextConvert = true;
    await page.click('#rvcConvertButton');
    await page.waitForFunction(() => document.querySelector('#rvcLogBox')?.textContent?.includes('Local TTS diagnostic log'));
    ensure(convertFailureCount === 1, "RVC failure route was not exercised");
    const failureLog = await page.locator('#rvcLogBox').textContent();
    ensure(failureLog?.includes('GPUメモリ不足'), "RVC failure log should translate the symptom for the user");
    ensure(failureLog?.includes('screen: rvc'), "RVC diagnostic should identify its screen");
    ensure(failureLog?.includes('Request:') && failureLog.includes('Error response:'), "RVC diagnostic should include request and error response");
    ensure(failureLog?.includes('Traceback: CUDA out of memory'), "RVC diagnostic should preserve the complete backend error");
    ensure((failureLog?.length || 0) > 600, "RVC failure log should keep enough detail for AI troubleshooting");
    ensure((await page.locator('#rvcConvertedAudio').getAttribute('src'))?.includes('converted-e2e-1.wav'), "failed regeneration should keep the previous converted player");
    ensure((await page.locator('#rvcConvertedBadge').textContent()) === "変換済み", "failed regeneration should not replace the previous converted result state");
    await page.waitForFunction(() => document.querySelectorAll('#rvcHistoryList .mini-history-item').length === 2);
    await page.locator('#rvcHistoryList [data-restore-rvc-history="1"]').click();
    ensure(await page.locator('#rvcSeedInput').inputValue() === "3001", "RVC history restore should restore the original generation seed");
    await page.click('#rvcLogCopyButton');
    await page.waitForFunction(() => document.querySelector('#rvcStatusText')?.textContent?.includes('診断ログをコピーしました'));

    await page.locator('input[name="rvcInputSource"][value="file"]').click();
    await ensureVisible(page.locator('#rvcFileSourceControls'), "RVC file source controls should show in wav mode");
    await ensureHidden(page.locator('#rvcTtsControls'), "RVC TTS controls should hide in wav mode");
    await ensureHidden(page.locator('#rvcMicControls'), "RVC mic controls should hide in wav mode");
    await ensureHidden(page.locator('#rvcTextInput'), "RVC text should hide in wav mode");
    ensure(await page.locator('#rvcIntermediateTitle').textContent() === "ファイル入力音声", "file mode title mismatch");
    await page.locator('#rvcExternalAudioPathInput').fill('C:\\audio\\sample.m4a');
    await page.locator('#rvcExternalAudioPathInput').dispatchEvent('change');
    ensure(await page.locator('#rvcExternalAudioPathHistory option[value="C:\\\\audio\\\\sample.m4a"]').count() === 1, "RVC file path history option missing");

    await page.locator('input[name="rvcInputSource"][value="mic"]').click();
    await ensureVisible(page.locator('#rvcMicControls'), "RVC mic controls should return in mic mode");
    await ensureHidden(page.locator('#rvcFileSourceControls'), "RVC file source controls should hide after returning to mic mode");

    await page.goto(`${frontBase}/#rvc`, { waitUntil: "networkidle", timeout: 60000 });
    await page.waitForSelector('#rvcPage.active');
    await page.waitForFunction(() => document.querySelector('#rvcSeedInput')?.value === '3001');
    ensure(await page.locator('#rvcSeedAutoIncrementInput').isChecked(), "RVC seed auto-update was not restored after reload");
    ensure(await page.locator('#rvcAutoPlayInput').isChecked(), "RVC autoplay was not restored after reload");
    ensure(await page.locator('#rvcModelSelect').inputValue() === 'irodori_v3', "RVC TTS model was not restored after reload");
    ensure(await page.locator('#rvcVoiceModelSelect').inputValue() === 'voice-b', "selected RVC voice model was not restored after reload");
    ensure(await page.locator('#rvcReferenceVoiceSelect').inputValue() === 'sample_voice', "RVC reference voice was not restored after reload");
    ensure(await page.locator('input[name="rvcInputSource"][value="mic"]').isChecked(), "RVC should restore the previously selected input source");
    ensure(await page.locator('#rvcHistoryList .mini-history-item').count() === 2, "RVC recent history should persist after reload");
    await ensureVisible(page.locator('#rvcMicControls'), "restored mic input source should show mic controls");
    await page.waitForSelector('#rvcPage.active');
    await page.waitForTimeout(50);
    var rvcLayout = await page.evaluate(() => {
      const form = document.querySelector('#rvcPage .form-panel');
      const logPanel = document.querySelector('#rvcLogBox')?.closest('.panel');
      const params = document.querySelector('#rvcPage .rvc-params-panel');
      const convert = document.querySelector('#rvcConvertButton');
      if (!form || !logPanel || !params || !convert) return null;
      const formRect = form.getBoundingClientRect();
      const logRect = logPanel.getBoundingClientRect();
      const paramsRect = params.getBoundingClientRect();
      const convertRect = convert.getBoundingClientRect();
      return {
        scrollY: window.scrollY,
        logPosition: getComputedStyle(logPanel.parentElement).position,
        formTop: formRect.top,
        logTop: logRect.top,
        paramsWidth: paramsRect.width,
        convertWidth: convertRect.width
      };
    });
    ensure(rvcLayout, "RVC layout metrics unavailable");
    ensure(rvcLayout.scrollY <= 64, `RVC tab should open within the fixed header range: scrollY=${rvcLayout.scrollY}`);
    ensure(rvcLayout.logPosition === "static", "RVC execution log should not detach from the form while scrolling");
    ensure(Math.abs(rvcLayout.formTop - rvcLayout.logTop) <= 2, "RVC form and execution log should align at the top");
    ensure(rvcLayout.convertWidth >= rvcLayout.paramsWidth - 40, "RVC convert button should fill the parameter panel");

    ensure(await page.locator('#rvcExternalAudioPathHistory option[value="C:\\\\audio\\\\sample.m4a"]').count() === 1, "RVC file path history should persist after reload");

    if (process.env.RVC_LAYOUT_SCREENSHOT) {
      await page.locator('input[name="rvcInputSource"][value="tts"]').click();
      await page.screenshot({ path: process.env.RVC_LAYOUT_SCREENSHOT, fullPage: true });
    }

    exposeRvcModels = false;
    await page.reload({ waitUntil: "networkidle", timeout: 60000 });
    await page.locator('.top-tab[data-tab="rvc"]').click();
    await page.waitForSelector('#rvcPage.active');
    await ensureVisible(page.locator('#rvcMissingModelPanel'), "RVC model setup panel should replace the unusable workspace when no model is ready");
    await ensureHidden(page.locator('#rvcWorkspace'), "RVC conversion controls should hide when no model is ready");
    ensure((await page.locator('#rvcModelDirectoryPath').textContent()) === 'C:\\models\\rvc', "RVC model placement path should be shown exactly");
    ensure((await page.locator('#rvcModelGuideLink').getAttribute('href')) === '/rvc-model-guide.html', "RVC model guide link is missing");
    ensure((await page.locator('#rvcModelScanNote').textContent())?.includes('.index がありません'), "incomplete RVC model reason should be shown");

    console.log(JSON.stringify({
      ok: true,
      frontBase,
      recordingUploadCount,
      convertCount,
      denoiseCount,
      checked: [
        "normal tab",
        "compare tab",
        "rvc tab",
        "history tab",
        "history page",
        "default text",
        "language fields hidden",
        "rvc mic recording source",
        "rvc mic device selection retention",
        "rvc mic start stop rerecord use",
        "rvc reference preview",
        "rvc emoji buttons",
        "rvc chunk presets and preview",
        "rvc help click toggles",
        "rvc simplified input controls",
        "rvc convert and post-denoise",
        "rvc player persistence during failed regeneration",
        "rvc recent history restore and reload persistence",
        "rvc mode switching",
        "rvc file path history",
        "rvc defaults",
        "rvc trained-model guide and official link",
        "compact AI-ready failure log",
        "hash route"
      ]
    }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
