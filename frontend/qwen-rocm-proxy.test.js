import assert from "node:assert/strict";
import http from "node:http";
import test from "node:test";
import { createServer } from "./server.js";

function listen(server) {
  return new Promise((resolve) => server.listen(0, "127.0.0.1", () => resolve("http://127.0.0.1:" + server.address().port)));
}
function close(server) {
  return new Promise((resolve) => server.close(resolve));
}
test("R9700 Qwen routes separately while other models and voices stay on the legacy worker", async () => {
  const legacyCalls = [];
  const qwenCalls = [];
  const legacy = http.createServer(async (req, res) => {
    legacyCalls.push(req.url);
    if (req.method === "POST") {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const data = JSON.parse(Buffer.concat(chunks).toString());
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ ok: true, result: { model: data.model, audioUrl: "/audio/legacy.wav" } }));
      return;
    }
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ ok: true, source: "legacy" }));
  });
  const qwen = http.createServer(async (req, res) => {
    qwenCalls.push(req.url);
    if (req.method === "POST") {
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const data = JSON.parse(Buffer.concat(chunks).toString());
      assert.equal(data.model, "qwen3_tts_clone_1_7b");
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify({ ok: true, result: { model: data.model, audioUrl: "/audio/qwen-r9700/mock.wav" } }));
      return;
    }
    res.setHeader("Content-Type", "audio/wav");
    res.end(Buffer.from("RIFF_FAKE_WAV"));
  });
  const oldBase = await listen(legacy);
  const qwenBase = await listen(qwen);
  const front = createServer({ deploymentRole: "frontend", workerBaseUrl: oldBase, qwenWorkerBaseUrl: qwenBase });
  const frontBase = await listen(front);
  const post = (model) => fetch(frontBase + "/api/speak", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify({ model, voiceId:"probe", text:"Hello" }) });
  try {
    const selected = await post("qwen3_tts_clone_1_7b");
    assert.equal(selected.status, 200);
    assert.equal((await selected.json()).result.audioUrl, "/audio/qwen-r9700/mock.wav");
    assert.equal((await fetch(frontBase + "/audio/qwen-r9700/mock.wav")).status, 200);
    const normal = await post("irodori_v3");
    assert.equal(normal.status, 200);
    assert.equal((await normal.json()).result.model, "irodori_v3");
    await fetch(frontBase + "/api/reference-voices");
    assert.deepEqual(qwenCalls, ["/api/speak", "/audio/qwen-r9700/mock.wav"]);
    assert.deepEqual(legacyCalls, ["/api/speak", "/api/reference-voices"]);
  } finally {
    await close(front);
    await close(legacy);
    await close(qwen);
  }
});
test("Qwen routing remains off when not explicitly configured", async () => {
  const legacy = http.createServer((req, res) => {
    res.setHeader("Content-Type", "application/json");
    res.end(JSON.stringify({ ok:true, model:"legacy" }));
  });
  const base = await listen(legacy);
  const front = createServer({ deploymentRole:"frontend", workerBaseUrl:base });
  const frontBase = await listen(front);
  try {
    const result = await fetch(frontBase + "/api/speak", {method:"POST", headers:{"Content-Type":"application/json"},body:JSON.stringify({model:"qwen3_tts_clone_1_7b",voiceId:"probe",text:"Hello"})});
    assert.equal(result.status,200);
    assert.equal((await result.json()).model,"legacy");
  } finally {
    await close(front);
    await close(legacy);
  }
});
