import path from "node:path";
import { readFile, stat } from "node:fs/promises";

export function removeBom(text) {
  return String(text || "").replace(/^\uFEFF/, "");
}

export async function readJsonIfExists(filePath) {
  try {
    const raw = await readFile(filePath, "utf-8");
    return JSON.parse(removeBom(raw));
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") return null;
    throw error;
  }
}

export async function statIfExists(filePath) {
  try {
    return await stat(filePath);
  } catch (error) {
    if (error && typeof error === "object" && error.code === "ENOENT") return null;
    throw error;
  }
}

export function normalizeBaseUrl(url, fallback) {
  const trimmed = String(url || "").trim();
  return (trimmed || fallback).replace(/\/+$/, "");
}

export function compactTimestampStem(date = new Date()) {
  return date.toISOString().replace(/[-:.]/g, "").replace("T", "-").replace("Z", "");
}

export function shortRandomId() {
  return Math.random().toString(16).slice(2, 10).padEnd(8, "0");
}

export function truncateLog(value, limit = 6000) {
  const text = String(value || "");
  return text.length > limit ? `${text.slice(0, limit)}\n...[truncated ${text.length - limit} chars]` : text;
}

export function safeStemFromPath(filePath) {
  return path.basename(filePath, path.extname(filePath)).replace(/[^A-Za-z0-9_-]/g, "_").slice(0, 80) || "audio";
}

export async function assertExistingFile(label, filePath) {
  const fileStat = await statIfExists(filePath);
  if (!fileStat || !fileStat.isFile()) throw new Error(`${label} not found: ${filePath}`);
}

export async function assertExistingDirectory(label, dirPath) {
  const dirStat = await statIfExists(dirPath);
  if (!dirStat || !dirStat.isDirectory()) throw new Error(`${label} not found: ${dirPath}`);
}
