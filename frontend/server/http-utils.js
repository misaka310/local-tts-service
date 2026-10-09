import path from "node:path";
import http from "node:http";
import https from "node:https";
import { createReadStream, existsSync, statSync } from "node:fs";
import { Readable } from "node:stream";

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

export const LONG_TTS_REQUEST_TIMEOUT_MS = 35 * 60 * 1000;

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

const WORKER_API_EXACT_PATHS = new Set(["/api/health", "/api/models", "/api/speak"]);
const WORKER_API_PREFIXES = ["/api/reference-voices", "/api/rvc/", "/audio/"];

export function isWorkerOwnedPath(pathname) {
  const normalized = String(pathname || "");
  return WORKER_API_EXACT_PATHS.has(normalized) || WORKER_API_PREFIXES.some((prefix) => normalized.startsWith(prefix));
}

async function readRawRequestBody(req, maxBytes = 60 * 1024 * 1024) {
  if (req.method === "GET" || req.method === "HEAD") return null;
  const chunks = [];
  let size = 0;
  for await (const chunk of req) {
    const buffer = Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk);
    size += buffer.length;
    if (size > maxBytes) throw Object.assign(new Error("request body too large"), { statusCode: 413 });
    chunks.push(buffer);
  }
  return chunks.length ? Buffer.concat(chunks) : null;
}

export async function proxyWorkerRequest(req, res, workerBaseUrl, url) {
  const base = String(workerBaseUrl || "").replace(/\/$/, "");
  if (!base) throw Object.assign(new Error("旧PC worker の接続先が設定されていません。"), { statusCode: 502 });
  if (!isWorkerOwnedPath(url.pathname)) {
    throw Object.assign(new Error("worker proxy path is not allowed"), { statusCode: 403 });
  }

  const headers = {};
  for (const name of ["content-type", "accept", "range"]) {
    const value = req.headers[name];
    if (value) headers[name] = value;
  }
  const body = await readRawRequestBody(req);

  let upstream;
  try {
    const requestUrl = base + url.pathname + url.search;
    upstream = req.method === "POST" && url.pathname === "/api/speak"
      ? await requestBufferWithTimeout(requestUrl, { method: req.method, headers, body })
      : await fetch(requestUrl, { method: req.method, headers, body });
  } catch {
    sendJson(res, 502, { ok: false, error: "旧PC worker に接続できません。旧PCの起動状態とネットワーク接続を確認してください。" });
    return;
  }

  const responseHeaders = {};
  for (const name of ["content-type", "content-length", "content-range", "accept-ranges", "cache-control", "content-disposition"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders[name] = value;
  }

  const contentType = String(upstream.headers.get("content-type") || "").toLowerCase();
  if (url.pathname === "/api/speak" && contentType.includes("application/json")) {
    const raw = await upstream.text();
    let payload = null;
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch {
      payload = null;
    }
    if (payload && payload.result && typeof payload.result.audioUrl === "string") {
      try {
        const audioUrl = new URL(payload.result.audioUrl, base);
        if (audioUrl.pathname.startsWith("/audio/")) payload.result.audioUrl = `${audioUrl.pathname}${audioUrl.search}`;
      } catch {
        // Preserve an upstream value that is not a valid URL.
      }
    }
    const bodyBuffer = Buffer.from(payload ? JSON.stringify(payload) : raw, "utf-8");
    responseHeaders["content-length"] = String(bodyBuffer.length);
    res.writeHead(upstream.status, responseHeaders);
    res.end(bodyBuffer);
    return;
  }

  res.writeHead(upstream.status, responseHeaders);
  if (!upstream.body) {
    res.end();
    return;
  }
  await new Promise((resolve, reject) => {
    const stream = Readable.fromWeb(upstream.body);
    stream.on("error", reject);
    res.on("finish", resolve);
    res.on("error", reject);
    stream.pipe(res);
  });
}

export async function callTtsJson(ttsBaseUrl, method, endpoint, payload) {
  const requestUrl = String(ttsBaseUrl) + endpoint;
  const requestOptions = {
    method,
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined
  };
  const response = method === "POST" && endpoint === "/v1/speak"
    ? await requestBufferWithTimeout(requestUrl, requestOptions)
    : await fetch(requestUrl, requestOptions);
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

function requestBufferWithTimeout(url, options) {
  const requestUrl = new URL(url);
  let transport = null;
  if (requestUrl.protocol === "https:") {
    transport = https;
  } else if (requestUrl.protocol === "http:") {
    transport = http;
  }
  if (!transport) return Promise.reject(new TypeError("TTS request URL must use HTTP or HTTPS"));

  return new Promise((resolve, reject) => {
    let request = null;
    let settled = false;
    let timeoutId = null;
    const fail = (error) => {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutId);
      if (request && !request.destroyed) request.destroy();
      reject(error);
    };
    const requestHeaders = { ...(options.headers || {}) };
    let requestBody = null;
    if (options.body != null) {
      requestBody = Buffer.isBuffer(options.body) ? options.body : Buffer.from(options.body);
    }
    if (requestBody && !Object.keys(requestHeaders).some((name) => name.toLowerCase() === "content-length")) {
      requestHeaders["Content-Length"] = String(requestBody.length);
    }

    request = transport.request(requestUrl, {
      method: options.method || "GET",
      headers: requestHeaders,
    }, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(Buffer.from(chunk)));
      response.once("error", fail);
      response.once("close", () => {
        if (!response.complete) fail(new Error("TTS response closed before completion"));
      });
      response.once("end", () => {
        if (settled) return;
        settled = true;
        clearTimeout(timeoutId);
        const responseBody = Buffer.concat(chunks);
        const status = Number(response.statusCode) || 502;
        resolve({
          ok: status >= 200 && status < 300,
          status,
          headers: {
            get(name) {
              const value = response.headers[String(name).toLowerCase()];
              return Array.isArray(value) ? value.join(", ") : value ?? null;
            },
          },
          body: Readable.toWeb(Readable.from(responseBody.length ? [responseBody] : [])),
          text: async () => responseBody.toString("utf-8"),
        });
      });
    });
    timeoutId = setTimeout(() => {
      fail(Object.assign(new Error("TTS generation request timed out after " + LONG_TTS_REQUEST_TIMEOUT_MS + "ms"), { code: "ETIMEDOUT" }));
    }, LONG_TTS_REQUEST_TIMEOUT_MS);
    request.once("error", fail);
    request.end(requestBody || undefined);
  });
}
