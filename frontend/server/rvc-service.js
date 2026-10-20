// Backward-compatible facade. New RVC responsibilities live under server/rvc/.
import { buildFfmpegWavArgs, shouldConvertAudioInputToWav } from "./audio-utils.js";
import { normalizeSpeakChunking } from "./tts-request.js";
import { createRvcContext } from "./rvc/config.js";
import { listRvcModels as listModels } from "./rvc/model-catalog.js";
import { normalizeRvcParams as normalizeParams } from "./rvc/validation.js";
import { buildRvcCommand as createCommand } from "./rvc/rvc-runner.js";
import { denoiseRvcOutput as denoiseOutput, resolveRvcAudioPath as resolveAudioPath, saveRvcRecording as saveRecording } from "./rvc/artifact-store.js";
import { rvcParamStem, synthesizeAndConvertRvc as convertRvc } from "./rvc/conversion-service.js";

const defaultContext = createRvcContext();

export function defaultRvcSettings(context = defaultContext) {
  const { fallbackDemucsPython: _fallback, ...settings } = context.defaults;
  return { ...settings };
}

export function getRvcPaths(context = defaultContext) {
  return { ...context.paths };
}

export function listRvcModels(context = defaultContext) {
  return listModels(context);
}

export function normalizeRvcParams(raw = {}, context = defaultContext) {
  return normalizeParams(raw, context.defaults);
}

export function resolveRvcAudioPath(kind, filename, context = defaultContext) {
  return resolveAudioPath(context, kind, filename);
}

export function buildRvcCommand(params, inputPath, outputPath, context = defaultContext) {
  return createCommand(context.defaults, params, inputPath, outputPath);
}

export function synthesizeAndConvertRvc(config, body) {
  const context = config.rvcContext || defaultContext;
  return convertRvc(context, config, body);
}

export function denoiseRvcOutput(body, context = defaultContext) {
  return denoiseOutput(context, body);
}

export function saveRvcRecording(body, context = defaultContext) {
  return saveRecording(context, body);
}

export { buildFfmpegWavArgs, createRvcContext, normalizeSpeakChunking, rvcParamStem, shouldConvertAudioInputToWav };
