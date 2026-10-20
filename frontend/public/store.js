(function bootstrapStore(global) {
  "use strict";

  function createStore(initial = {}) {
    let state = { ...initial };
    const listeners = new Set();
    return Object.freeze({
      getState: () => state,
      setState(patch) {
        const next = typeof patch === "function" ? patch(state) : patch;
        state = { ...state, ...(next || {}) };
        listeners.forEach((listener) => listener(state));
        return state;
      },
      subscribe(listener) {
        listeners.add(listener);
        return () => listeners.delete(listener);
      },
    });
  }

  function createStorage(storage) {
    return Object.freeze({
      loadObject(key, fallback = {}) {
        try {
          const value = JSON.parse(storage.getItem(key) || "null");
          return value && typeof value === "object" && !Array.isArray(value) ? value : fallback;
        } catch { return fallback; }
      },
      loadList(key, limit = Infinity) {
        try {
          const value = JSON.parse(storage.getItem(key) || "[]");
          return Array.isArray(value) ? value.slice(0, limit) : [];
        } catch { return []; }
      },
      save(key, value) { storage.setItem(key, JSON.stringify(value)); },
    });
  }

  global.LocalTts = global.LocalTts || {};
  global.LocalTts.store = Object.freeze({ createStore, createStorage });
})(globalThis);
