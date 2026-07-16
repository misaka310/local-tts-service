import { existsSync } from "node:fs";
import path from "node:path";
import { createServer } from "../server.js";

function ensure(condition, message) {
  if (!condition) throw new Error(message);
}

function printSkip(reason, details = {}) {
  console.log(JSON.stringify({ ok: true, skipped: true, reason, ...details }, null, 2));
}

function assertLocalPrerequisites() {
  if (process.env.RVC_CONVERT_E2E !== "1") {
    printSkip("RVC convert smoke is local-only. Set RVC_CONVERT_E2E=1 to run it.");
    return false;
  }

  const requiredPaths = [
    process.env.RVC_E2E_INPUT_PATH,
    process.env.RVC_E2E_PYTHON_PATH,
    process.env.RVC_E2E_MODEL_PATH,
    process.env.RVC_E2E_INDEX_PATH
  ].map((item) => String(item || "").trim());
  if (requiredPaths.some((item) => !item)) {
    printSkip("RVC E2E paths are not configured. Set RVC_E2E_INPUT_PATH, RVC_E2E_PYTHON_PATH, RVC_E2E_MODEL_PATH, and RVC_E2E_INDEX_PATH.");
    return false;
  }
  const missing = requiredPaths.filter((item) => !existsSync(item));
  if (missing.length) {
    printSkip("RVC local prerequisites are missing.", { missing });
    return false;
  }
  return true;
}

async function main() {
  if (!assertLocalPrerequisites()) return;

  const server = createServer({
    host: "127.0.0.1",
    port: 0,
    ttsBaseUrl: process.env.TTS_API_BASE_URL || "http://127.0.0.1:8730"
  });
  await new Promise((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  const frontBase = `http://127.0.0.1:${address.port}`;

  try {
    const response = await fetch(`${frontBase}/api/rvc/convert`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        text: "RVC変換の短い動作確認です。",
        model: process.env.RVC_TTS_MODEL || "mock",
        language: "Japanese",
        rvc: {
          inputSource: "file",
          indexRate: Number(process.env.RVC_INDEX_RATE || 0.35),
          f0method: "rmvpe",
          f0upKey: 0,
          filterRadius: 3,
          resampleSr: 0,
          rmsMixRate: 1,
          protect: 0.33,
          externalAudioPath: process.env.RVC_E2E_INPUT_PATH,
          pythonPath: process.env.RVC_E2E_PYTHON_PATH,
          cwd: process.env.RVC_E2E_CWD || path.dirname(process.env.RVC_E2E_PYTHON_PATH),
          modelPath: process.env.RVC_E2E_MODEL_PATH,
          indexPath: process.env.RVC_E2E_INDEX_PATH
        }
      })
    });
    const payload = await response.json();
    if (!response.ok || payload.ok === false) {
      console.error(JSON.stringify({
        ok: false,
        error: payload.errorMessage || payload.error || `HTTP ${response.status}`,
        partialResult: payload.partialResult || null,
        stderr: payload.stderr || ""
      }, null, 2));
      process.exit(1);
    }
    const result = payload.result || {};
    ensure(result.input?.source === "file", "RVC convert smoke must use file input mode");
    ensure(result.intermediate?.url, "intermediate url missing");
    ensure(result.converted?.url, "converted url missing");

    const intermediate = await fetch(`${frontBase}${result.intermediate.url}`);
    const converted = await fetch(`${frontBase}${result.converted.url}`);
    ensure(intermediate.ok, `intermediate fetch failed: HTTP ${intermediate.status}`);
    ensure(converted.ok, `converted fetch failed: HTTP ${converted.status}`);
    const intermediateBytes = (await intermediate.arrayBuffer()).byteLength;
    const convertedBytes = (await converted.arrayBuffer()).byteLength;
    ensure(intermediateBytes > 0, "intermediate wav is empty");
    ensure(convertedBytes > 0, "converted wav is empty");

    console.log(JSON.stringify({
      ok: true,
      skipped: false,
      frontBase,
      intermediate: result.intermediate,
      converted: result.converted,
      intermediateBytes,
      convertedBytes,
      rvcLogPath: result.rvc?.logPath
    }, null, 2));
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
}

main().catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2));
  process.exit(1);
});
