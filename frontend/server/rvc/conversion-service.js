import path from "node:path";
import { callTtsJson } from "../http-utils.js";
import { normalizeTtsRequest } from "../tts-request.js";
import { compactTimestampStem, shortRandomId } from "../shared.js";
import { normalizeRvcInputOptions, normalizeRvcParams } from "./validation.js";
import { createConversionArtifacts, rvcAudioUrl } from "./artifact-store.js";
import { copyTtsAudio, optionallyCleanTtsAudio, prepareExternalAudio } from "./input-preparer.js";
import { runRvcConvert } from "./rvc-runner.js";

export function rvcParamStem(params) {
  return [`ir${String(Math.round(params.indexRate * 100)).padStart(3, "0")}`, `f0${params.f0upKey}`, `rm${String(Math.round(params.rmsMixRate * 100)).padStart(3, "0")}`, `pr${String(Math.round(params.protect * 100)).padStart(2, "0")}`].join("-").replace(/[^A-Za-z0-9_-]/g, "_");
}

export async function synthesizeAndConvertRvc(context, config, body, dependencies = {}) {
  const rawOptions = { ...body, ...(body.rvc || {}) };
  const inputOptions = normalizeRvcInputOptions(rawOptions, context.defaults);
  const ttsBody = inputOptions.inputSource === "tts" ? normalizeTtsRequest(body, { format: "wav", includeControls: false }) : null;
  const params = normalizeRvcParams(rawOptions, context.defaults);
  const id = `${compactTimestampStem()}-${shortRandomId()}`;
  const artifacts = await createConversionArtifacts(context, id, rvcParamStem(params));
  let speak = null; let audioCopy;
  if (inputOptions.inputSource === "tts") {
    speak = await (dependencies.callTtsJson || callTtsJson)(config.ttsBaseUrl, "POST", "/v1/speak", ttsBody);
    if (!speak.ok) throw new Error(speak.body.errorMessage || speak.body.error || "TTS生成に失敗しました。");
    audioCopy = await (dependencies.copyTtsAudio || copyTtsAudio)(context, config.ttsBaseUrl, speak.body, artifacts.intermediatePath);
    audioCopy = await optionallyCleanTtsAudio(context, inputOptions, artifacts.intermediatePath, id, audioCopy, dependencies);
  } else audioCopy = await (dependencies.prepareExternalAudio || prepareExternalAudio)(context, inputOptions, artifacts.intermediatePath, id, dependencies);
  const baseResult = { id, input: { source: inputOptions.inputSource, externalAudioPath: ["file", "mic"].includes(inputOptions.inputSource) ? inputOptions.externalAudioPath : null, cleanExternalAudio: inputOptions.cleanExternalAudio, demucsModel: inputOptions.demucsModel }, tts: speak ? { request: ttsBody, result: speak.body, copiedFrom: audioCopy } : null, intermediate: { filename: artifacts.intermediateFilename, path: artifacts.intermediatePath, url: rvcAudioUrl("intermediate", artifacts.intermediateFilename), copiedFrom: audioCopy }, converted: { filename: artifacts.convertedFilename, path: artifacts.convertedPath, url: "" }, rvc: { params, cwd: context.defaults.cwd, logPath: context.paths.logPath } };
  try {
    const result = await (dependencies.runRvcConvert || runRvcConvert)(context, params, artifacts.intermediatePath, artifacts.convertedPath);
    return { ...baseResult, converted: { ...baseResult.converted, url: rvcAudioUrl("converted", artifacts.convertedFilename) }, rvc: { ...baseResult.rvc, command: result.command, stdout: result.stdout, stderr: result.stderr } };
  } catch (error) { error.partialResult = baseResult; throw error; }
}
