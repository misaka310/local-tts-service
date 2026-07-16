import path from "node:path";

function asNumber(value, fallback, label, min, max) {
  const raw = value === undefined || value === null || String(value).trim() === "" ? fallback : Number(value);
  if (!Number.isFinite(raw)) throw new Error(`${label} must be a number`);
  if (raw < min || raw > max) throw new Error(`${label} must be between ${min} and ${max}`);
  return raw;
}

function asInteger(value, fallback, label, min, max) {
  const raw = value === undefined || value === null || String(value).trim() === "" ? fallback : Number(value);
  if (!Number.isInteger(raw)) throw new Error(`${label} must be an integer`);
  if (raw < min || raw > max) throw new Error(`${label} must be between ${min} and ${max}`);
  return raw;
}

export function sanitizeRvcPath(value, fallback, label = "path") {
  const raw = String(value ?? fallback ?? "").trim();
  if (!raw) throw new Error(`${label} is required`);
  return path.resolve(raw);
}

export function sanitizeAudioInputPath(value, fallback) {
  const raw = String(value || fallback || "").trim();
  if (!raw) throw new Error("input audio path is required");
  const resolved = path.resolve(raw);
  const ext = path.extname(resolved).toLowerCase();
  if (![".wav", ".mp3", ".flac", ".m4a", ".ogg", ".aac"].includes(ext)) throw new Error(`unsupported input audio type: ${ext || "no extension"}`);
  return resolved;
}

export function normalizeRvcInputOptions(raw = {}, defaults) {
  const rawSource = String(raw.inputSource || raw.input_source || defaults.inputSource).trim();
  const inputSource = ["tts", "file", "mic"].includes(rawSource) ? rawSource : "tts";
  const demucsModel = String(raw.demucsModel || raw.demucs_model || defaults.demucsModel).trim() || defaults.demucsModel;
  if (!/^[A-Za-z0-9_.-]{1,80}$/.test(demucsModel)) throw new Error("demucsModel contains invalid characters");
  const fallbackAudioPath = inputSource === "mic" ? "" : defaults.externalAudioPath;
  const externalAudioRaw = String(raw.externalAudioPath ?? raw.external_audio_path ?? fallbackAudioPath).trim();
  return {
    inputSource,
    externalAudioPath: externalAudioRaw ? sanitizeAudioInputPath(externalAudioRaw, "") : "",
    cleanExternalAudio: raw.cleanExternalAudio ?? raw.clean_external_audio ?? defaults.cleanExternalAudio,
    demucsPython: sanitizeRvcPath(raw.demucsPython ?? raw.demucs_python, defaults.demucsPython),
    demucsModel,
  };
}

export function normalizeRvcParams(raw = {}, defaults) {
  const f0method = String(raw.f0method || defaults.f0method).trim() || defaults.f0method;
  if (!/^[A-Za-z0-9_-]{1,40}$/.test(f0method)) throw new Error("f0method contains invalid characters");
  return {
    indexRate: asNumber(raw.indexRate ?? raw.index_rate, defaults.indexRate, "index_rate", 0, 1), f0method,
    f0upKey: asInteger(raw.f0upKey ?? raw.f0up_key, defaults.f0upKey, "f0up_key", -24, 24),
    filterRadius: asInteger(raw.filterRadius ?? raw.filter_radius, defaults.filterRadius, "filter_radius", 0, 7),
    resampleSr: asInteger(raw.resampleSr ?? raw.resample_sr, defaults.resampleSr, "resample_sr", 0, 48000),
    rmsMixRate: asNumber(raw.rmsMixRate ?? raw.rms_mix_rate, defaults.rmsMixRate, "rms_mix_rate", 0, 1),
    protect: asNumber(raw.protect, defaults.protect, "protect", 0, 0.5),
    modelPath: sanitizeRvcPath(raw.modelPath ?? raw.model_path, defaults.modelPath, "model path"),
    indexPath: sanitizeRvcPath(raw.indexPath ?? raw.index_path, defaults.indexPath, "index path"),
  };
}
