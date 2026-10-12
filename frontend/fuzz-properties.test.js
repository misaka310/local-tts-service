import assert from "node:assert/strict";
import test from "node:test";
import fc from "fast-check";
import { normalizeYoutubeUrl, parseYoutubeCandidateAudioRequest } from "./youtube-reference.js";

const allowedHosts = new Set(["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"]);

test("property: YouTube URL normalization only accepts supported HTTP(S) video URLs", () => {
  fc.assert(
    fc.property(fc.string(), (raw) => {
      try {
        const normalized = normalizeYoutubeUrl(raw);
        const parsed = new URL(normalized);
        assert.ok(allowedHosts.has(parsed.hostname));
        assert.ok(parsed.protocol === "http:" || parsed.protocol === "https:");
      } catch (error) {
        assert.ok(error instanceof Error);
      }
    }),
    { numRuns: 1000 },
  );
});

test("property: candidate audio route parser never throws on arbitrary paths", () => {
  fc.assert(
    fc.property(fc.string(), (pathname) => {
      const parsed = parseYoutubeCandidateAudioRequest(pathname);
      if (parsed !== null) {
        assert.match(parsed.jobId, /^[A-Za-z0-9_-]{1,80}$/);
        assert.match(parsed.candidateId, /^[A-Za-z0-9_-]{1,80}$/);
        assert.ok(parsed.variant === "original" || parsed.variant === "cleaned");
      }
    }),
    { numRuns: 1000 },
  );
});
