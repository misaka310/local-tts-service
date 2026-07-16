import path from "node:path";
import { createReadStream, existsSync, statSync } from "node:fs";

const MIME_TYPES = {
  ".html": "text/html; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".svg": "image/svg+xml",
  ".png": "image/png",
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".webp": "image/webp",
  ".mp4": "video/mp4",
  ".wav": "audio/wav"
};

const LOCAL_BROWSER_HOSTS = new Set(["127.0.0.1", "localhost", "[::1]", "::1"]);

export function sendJson(res, statusCode, payload) {
  const body = Buffer.from(JSON.stringify(payload, null, 2), "utf-8");
  res.writeHead(statusCode, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": body.length,
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type"
  });
  res.end(body);
}

export function readRequestBody(req, maxBytes = 60 * 1024 * 1024) {
  return new Promise((resolve, reject) => {
    let body = "";
    req.setEncoding("utf-8");
    req.on("data", (chunk) => {
      body += chunk;
      if (body.length > maxBytes) {
        req.destroy();
        reject(new Error("request body too large"));
      }
    });
    req.on("end", () => {
      if (!body.trim()) return resolve({});
      try {
        resolve(JSON.parse(body));
      } catch (error) {
        reject(new Error(`invalid JSON: ${error.message}`));
      }
    });
    req.on("error", reject);
  });
}

export async function callTtsJson(ttsBaseUrl, method, endpoint, payload) {
  const response = await fetch(`${ttsBaseUrl}${endpoint}`, {
    method,
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined
  });
  const rawText = await response.text();
  let parsed;
  try {
    parsed = rawText ? JSON.parse(rawText) : {};
  } catch {
    parsed = { ok: false, raw: rawText };
  }
  return {
    ok: response.ok && parsed.ok !== false,
    status: response.status,
    body: parsed,
    rawText
  };
}

export function serveFile(res, filePath, contentType = null, rangeHeader = "") {
  if (!existsSync(filePath)) {
    sendJson(res, 404, { ok: false, error: "not found" });
    return;
  }
  const ext = path.extname(filePath).toLowerCase();
  const fileSize = statSync(filePath).size;
  const resolvedContentType = contentType || MIME_TYPES[ext] || "application/octet-stream";
  const rangeMatch = /^bytes=(\d*)-(\d*)$/i.exec(String(rangeHeader || "").trim());
  if (rangeMatch && fileSize > 0) {
    const requestedStart = rangeMatch[1] === "" ? null : Number(rangeMatch[1]);
    const requestedEnd = rangeMatch[2] === "" ? null : Number(rangeMatch[2]);
    const start = requestedStart == null
      ? Math.max(0, fileSize - Math.max(0, requestedEnd || 0))
      : requestedStart;
    const end = requestedStart == null
      ? fileSize - 1
      : Math.min(fileSize - 1, requestedEnd == null ? fileSize - 1 : requestedEnd);
    if (!Number.isInteger(start) || !Number.isInteger(end) || start < 0 || start > end || start >= fileSize) {
      res.writeHead(416, {
        "Content-Range": `bytes */${fileSize}`,
        "Accept-Ranges": "bytes",
        "Cache-Control": "no-store",
      });
      res.end();
      return;
    }
    res.writeHead(206, {
      "Content-Type": resolvedContentType,
      "Content-Length": end - start + 1,
      "Content-Range": `bytes ${start}-${end}/${fileSize}`,
      "Accept-Ranges": "bytes",
      "Cache-Control": "no-store",
    });
    createReadStream(filePath, { start, end }).pipe(res);
    return;
  }
  res.writeHead(200, {
    "Content-Type": resolvedContentType,
    "Content-Length": fileSize,
    "Accept-Ranges": "bytes",
    "Cache-Control": "no-store"
  });
  createReadStream(filePath).pipe(res);
}

export function serveDirectoryFile(res, rootDir, requestedPath) {
  const normalizedRequest = requestedPath === "/" ? "/index.html" : requestedPath;
  const decoded = decodeURIComponent(normalizedRequest);
  const filePath = path.normalize(path.join(rootDir, decoded));
  if (!filePath.startsWith(rootDir)) {
    sendJson(res, 403, { ok: false, error: "forbidden" });
    return;
  }
  serveFile(res, filePath);
}

export function isAllowedLocalBrowserOrigin(origin) {
  if (!origin) return true;
  try {
    const parsed = new URL(String(origin));
    return (parsed.protocol === "http:" || parsed.protocol === "https:") && LOCAL_BROWSER_HOSTS.has(parsed.hostname);
  } catch {
    return false;
  }
}
