import path from "node:path";
import { mkdir, readdir } from "node:fs/promises";
import { statIfExists } from "../shared.js";

function safeModelId(value) {
  return String(value || "")
    .trim()
    .replace(/[^A-Za-z0-9_-]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 80) || "rvc-model";
}

async function fileExists(filePath) {
  const fileStat = await statIfExists(filePath);
  return Boolean(fileStat?.isFile());
}

async function modelEntryFromDirectory(directory, name) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = entries.filter((entry) => entry.isFile()).map((entry) => entry.name).sort((a, b) => a.localeCompare(b));
  const modelFiles = files.filter((file) => path.extname(file).toLowerCase() === ".pth");
  const indexFiles = files.filter((file) => path.extname(file).toLowerCase() === ".index");
  const addedIndexes = indexFiles.filter((file) => /^added[_-]/i.test(file));
  const modelFile = modelFiles.length === 1 ? modelFiles[0] : "";
  const indexFile = addedIndexes.length === 1
    ? addedIndexes[0]
    : indexFiles.length === 1
      ? indexFiles[0]
      : "";
  const modelPath = modelFile ? path.join(directory, modelFile) : "";
  const indexPath = indexFile ? path.join(directory, indexFile) : "";
  const missing = [];
  if (!modelFiles.length) missing.push(".pth がありません");
  else if (modelFiles.length > 1) missing.push(".pth が複数あります");
  if (!indexFiles.length) missing.push(".index がありません");
  else if (!indexFile) missing.push("使用する .index を1つに絞れません");
  return {
    id: safeModelId(name),
    label: name,
    modelPath,
    indexPath,
    ready: missing.length === 0,
    errorReason: missing.join("、"),
    source: "model-directory",
  };
}

async function rootLevelModels(modelRoot) {
  const entries = await readdir(modelRoot, { withFileTypes: true });
  const files = entries.filter((entry) => entry.isFile()).map((entry) => entry.name);
  const indexes = new Map(
    files
      .filter((file) => path.extname(file).toLowerCase() === ".index")
      .map((file) => [path.basename(file, path.extname(file)).toLowerCase(), file]),
  );
  return files
    .filter((file) => path.extname(file).toLowerCase() === ".pth")
    .map((file) => {
      const stem = path.basename(file, path.extname(file));
      const indexFile = indexes.get(stem.toLowerCase()) || "";
      return {
        id: safeModelId(stem),
        label: stem,
        modelPath: path.join(modelRoot, file),
        indexPath: indexFile ? path.join(modelRoot, indexFile) : "",
        ready: Boolean(indexFile),
        errorReason: indexFile ? "" : "同名の .index がありません",
        source: "model-root",
      };
    });
}

export async function listRvcModels(context) {
  const modelRoot = path.join(context.repoRoot, "models", "rvc");
  await mkdir(modelRoot, { recursive: true });
  const entries = await readdir(modelRoot, { withFileTypes: true });
  const directoryModels = [];
  for (const entry of entries.sort((a, b) => a.name.localeCompare(b.name))) {
    if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
    directoryModels.push(await modelEntryFromDirectory(path.join(modelRoot, entry.name), entry.name));
  }

  const models = [...directoryModels, ...await rootLevelModels(modelRoot)];
  const configuredModelPath = String(context.defaults.modelPath || "").trim();
  const configuredIndexPath = String(context.defaults.indexPath || "").trim();
  const configuredReady = configuredModelPath && configuredIndexPath
    && await fileExists(configuredModelPath)
    && await fileExists(configuredIndexPath);
  const configuredAlreadyListed = models.some((model) => (
    path.resolve(model.modelPath || "") === path.resolve(configuredModelPath || "")
    && path.resolve(model.indexPath || "") === path.resolve(configuredIndexPath || "")
  ));
  if (configuredReady && !configuredAlreadyListed) {
    const label = path.basename(configuredModelPath, path.extname(configuredModelPath)) || "設定済みモデル";
    models.unshift({
      id: `configured-${safeModelId(label)}`,
      label,
      modelPath: configuredModelPath,
      indexPath: configuredIndexPath,
      ready: true,
      errorReason: "",
      source: "environment",
    });
  }

  const unique = [];
  const ids = new Set();
  for (const model of models) {
    let id = model.id;
    let suffix = 2;
    while (ids.has(id)) id = `${model.id}-${suffix++}`;
    ids.add(id);
    unique.push({ ...model, id });
  }
  return {
    modelRoot,
    models: unique,
    readyCount: unique.filter((model) => model.ready).length,
    guideUrl: "/rvc-model-guide.html",
  };
}
