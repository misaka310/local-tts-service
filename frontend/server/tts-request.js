function requestError(message, statusCode = 400) {
  return Object.assign(new Error(message), { statusCode });
}

function optionalNumber(value, label, { integer = false, min = -Infinity, max = Infinity } = {}) {
  if (value === undefined || value === null || String(value).trim() === "") return undefined;
  const normalized = Number(value);
  if (!Number.isFinite(normalized) || (integer && !Number.isInteger(normalized))) {
    throw requestError(`${label} must be ${integer ? "an integer" : "a number"}`);
  }
  if (normalized < min || normalized > max) throw requestError(`${label} must be between ${min} and ${max}`);
  return normalized;
}

export function normalizeSpeakChunking(raw = null) {
  if (raw === undefined || raw === null || raw === "") return undefined;
  if (typeof raw !== "object" || Array.isArray(raw)) throw requestError("chunking must be an object");
  const softChunkChars = optionalNumber(raw.softChunkChars ?? 240, "softChunkChars", { integer: true, min: 20, max: 2000 });
  const maxChunkChars = optionalNumber(raw.maxChunkChars ?? Math.max(softChunkChars, 320), "maxChunkChars", { integer: true, min: softChunkChars, max: 3000 });
  const hardLimitChars = optionalNumber(raw.hardLimitChars ?? Math.max(maxChunkChars, 500), "hardLimitChars", { integer: true, min: maxChunkChars, max: 4000 });
  const pauseBetweenChunksMs = optionalNumber(raw.pauseBetweenChunksMs ?? 250, "pauseBetweenChunksMs", { integer: true, min: 0, max: 5000 });
  return { softChunkChars, maxChunkChars, hardLimitChars, pauseBetweenChunksMs };
}

export function normalizeTtsRequest(body = {}, { format = body.format || "wav", includeControls = true } = {}) {
  const text = String(body.text || "").trim();
  const model = String(body.model || "").trim();
  if (!text) throw requestError("text is required");
  if (!model) throw requestError("model is required");

  const result = {
    text,
    model,
    voiceId: String(body.voiceId || "").trim() || undefined,
    instruction: String(body.instruction || "").trim() || undefined,
    caption: String(body.caption || "").trim() || undefined,
    styleCaption: String(body.styleCaption || "").trim() || undefined,
    language: String(body.language || "").trim() || undefined,
    seed: optionalNumber(body.seed, "seed", { integer: true }),
    chunking: normalizeSpeakChunking(body.chunking),
    format: String(format || "wav").trim() || "wav",
  };
  if (includeControls) {
    result.speedScale = optionalNumber(body.speedScale, "speedScale", { min: 0.5, max: 2 });
    result.styleStrength = optionalNumber(body.styleStrength, "styleStrength", { min: 1, max: 6 });
  }
  return result;
}
