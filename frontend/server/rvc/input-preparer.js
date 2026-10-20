import path from "node:path";
import { existsSync } from "node:fs";
import { copyFile, mkdir, writeFile } from "node:fs/promises";
import { assertExistingFile } from "../shared.js";
import { convertAudioFileToWav, shouldConvertAudioInputToWav } from "../audio-utils.js";
import { runDemucsVocals } from "./demucs-runner.js";

export async function copyTtsAudio(context, ttsBaseUrl, speakBody, intermediatePath, { fetchImpl = fetch } = {}) {
  const audioPath = String(speakBody.audioPath || "").trim();
  if (audioPath && existsSync(audioPath)) { await copyFile(audioPath, intermediatePath); return { source: "audioPath", sourcePath: audioPath }; }
  const audioUrl = String(speakBody.audioUrl || "").trim();
  if (!audioUrl) throw new Error("TTS result has no audioPath/audioUrl");
  const resolvedUrl = new URL(audioUrl, `${ttsBaseUrl}/`).toString();
  const response = await fetchImpl(resolvedUrl);
  if (!response.ok) throw new Error(`TTS audio download failed: HTTP ${response.status} ${resolvedUrl}`);
  await writeFile(intermediatePath, Buffer.from(await response.arrayBuffer()));
  return { source: "audioUrl", sourceUrl: resolvedUrl };
}

export async function prepareExternalAudio(context, options, intermediatePath, id, dependencies = {}) {
  const sourcePath = options.externalAudioPath;
  await assertExistingFile("external input audio", sourcePath);
  await mkdir(path.dirname(intermediatePath), { recursive: true });
  if (String(options.cleanExternalAudio) === "true" || options.cleanExternalAudio === true) {
    const cleanedPath = path.join(context.paths.inputCleanDir, `rvc-cleaned-${id}.wav`);
    const cleanup = await (dependencies.runDemucsVocals || runDemucsVocals)(context, sourcePath, cleanedPath, options, id);
    await copyFile(cleanedPath, intermediatePath);
    return { source: "externalAudio", sourcePath, cleaned: true, cleanedPath, cleanup };
  }
  if (shouldConvertAudioInputToWav(sourcePath)) {
    const conversion = await convertAudioFileToWav(context.repoRoot, sourcePath, intermediatePath, "入力音声");
    return { source: "externalAudio", sourcePath, cleaned: false, convertedToWav: true, conversion };
  }
  await copyFile(sourcePath, intermediatePath);
  return { source: "externalAudio", sourcePath, cleaned: false, convertedToWav: false };
}

export async function optionallyCleanTtsAudio(context, options, intermediatePath, id, copiedFrom, dependencies = {}) {
  if (!(String(options.cleanExternalAudio) === "true" || options.cleanExternalAudio === true)) return { ...copiedFrom, cleaned: false };
  const cleanedPath = path.join(context.paths.inputCleanDir, `rvc-cleaned-${id}.wav`);
  const cleanup = await (dependencies.runDemucsVocals || runDemucsVocals)(context, intermediatePath, cleanedPath, options, id);
  await copyFile(cleanedPath, intermediatePath);
  return { ...copiedFrom, cleaned: true, cleanedPath, cleanup };
}
