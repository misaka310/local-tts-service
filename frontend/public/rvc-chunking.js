(() => {
  function clampInteger(value, fallback, min, max) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed)) return fallback;
    return Math.min(max, Math.max(min, Math.round(parsed)));
  }

  function splitTextForChunkPreview(text, targetChars, hardMaxChars) {
    const normalized = String(text || "").trim();
    if (!normalized) return [];
    const soft = clampInteger(targetChars, 240, 40, 2000);
    const hard = clampInteger(hardMaxChars, 500, soft, 3000);
    const max = Math.min(hard, Math.max(soft, Math.round(soft * 1.35)));
    if (normalized.length <= max) return [normalized];

    const tokens = [];
    let start = 0;
    Array.from(normalized).forEach((char, index) => {
      if ("\n。！？!?".includes(char)) {
        tokens.push(normalized.slice(start, index + 1));
        start = index + 1;
      }
    });
    if (start < normalized.length) tokens.push(normalized.slice(start));

    const chunks = [];
    let current = "";
    for (const token of tokens) {
      const piece = token.trim();
      if (!piece) continue;
      if (piece.length > hard) {
        if (current) chunks.push(current);
        current = "";
        for (let offset = 0; offset < piece.length; offset += max) chunks.push(piece.slice(offset, offset + max));
        continue;
      }
      if (!current) {
        current = piece;
        continue;
      }
      const candidate = `${current}\n${piece}`;
      if (candidate.length <= soft || (piece.length <= max && candidate.length <= max)) current = candidate;
      else {
        chunks.push(current);
        current = piece;
      }
    }
    if (current) chunks.push(current);
    return chunks.length ? chunks : [normalized];
  }

  window.LocalTtsChunking = Object.freeze({ clampInteger, splitTextForChunkPreview });
})();
