(() => {
  const ASSET_ROOT = "./motion-pngtuber/runway_char";
  const MOUTH_PATHS = {
    closed: `${ASSET_ROOT}/mouth/closed.png`,
    half: `${ASSET_ROOT}/mouth/half.png`,
    open: `${ASSET_ROOT}/mouth/open.png`,
    e: `${ASSET_ROOT}/mouth/e.png`,
    u: `${ASSET_ROOT}/mouth/u.png`,
  };

  function init(options = {}) {
    const audio = document.querySelector(options.audioSelector || "#normalAudioPlayer");
    const textInput = document.querySelector(options.textSelector || "#normalTextInput");
    const card = document.querySelector(options.cardSelector || "#avatarSyncCardRight");
    const oldCard = document.querySelector("#avatarSyncCard");
    if (oldCard) oldCard.style.display = "none";
    if (!audio || !card || card.dataset.avatarSyncReady === "true") return null;

    const stage = card.querySelector(".avatar-stage");
    const video = card.querySelector("#avatarLoopVideo");
    const status = card.querySelector("#avatarSyncStatus");
    const toggle = card.querySelector("#avatarToggleButton");
    const oldMouth = card.querySelector("#avatarMouthImage");
    if (!stage || !video) return null;
    card.dataset.avatarSyncReady = "true";
    if (oldMouth) oldMouth.style.display = "none";

    stage.querySelectorAll("canvas").forEach((node) => node.remove());
    const canvas = document.createElement("canvas");
    canvas.id = "avatarLipCanvas";
    canvas.width = 832;
    canvas.height = 1104;
    canvas.style.position = "absolute";
    canvas.style.inset = "0";
    canvas.style.width = "100%";
    canvas.style.height = "100%";
    canvas.style.display = "block";
    stage.appendChild(canvas);
    const ctx = canvas.getContext("2d");

    let debug = card.querySelector("#avatarAudioDebug");
    if (!debug) {
      debug = document.createElement("small");
      debug.id = "avatarAudioDebug";
      debug.style.display = "block";
      debug.style.color = "#607089";
      debug.style.lineHeight = "1.45";
      card.appendChild(debug);
    }

    const mouthImages = {};
    Object.entries(MOUTH_PATHS).forEach(([key, src]) => {
      const image = new Image();
      image.src = src;
      mouthImages[key] = image;
    });

    let track = null;
    let decoded = null;
    let decodedUrl = "";
    let audioContext = null;
    let rafId = 0;
    let active = true;
    let env = 0;
    let shape = "closed";
    let lastSwitch = 0;
    let rmsPeak = 0.001;
    let lastRms = 0;

    function setDebug(text) {
      debug.textContent = text;
    }

    function setStatus(text, state = "pending") {
      if (!status) return;
      status.textContent = text;
      status.className = `status-badge ${state}`;
    }

    async function loadTrack() {
      if (track) return track;
      const response = await fetch(`${ASSET_ROOT}/mouth_track.json`, { cache: "no-store" });
      if (!response.ok) throw new Error(`mouth_track.json HTTP ${response.status}`);
      track = await response.json();
      return track;
    }

    async function loadDecodedAudio() {
      const src = audio.currentSrc || audio.src;
      if (!src) return null;
      if (decoded && decodedUrl === src) return decoded;
      const response = await fetch(src, { cache: "no-store" });
      if (!response.ok) throw new Error(`audio HTTP ${response.status}`);
      const buffer = await response.arrayBuffer();
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      if (!AudioContextClass) return null;
      audioContext = audioContext || new AudioContextClass();
      decoded = await audioContext.decodeAudioData(buffer.slice(0));
      decodedUrl = src;
      setDebug(`audio: decoded ${decoded.duration.toFixed(2)}s`);
      return decoded;
    }

    function rmsAt(time) {
      if (!decoded) return audio.paused ? 0 : 0.04;
      const channel = decoded.getChannelData(0);
      const center = Math.max(0, Math.min(channel.length - 1, Math.floor(time * decoded.sampleRate)));
      const radius = Math.floor(decoded.sampleRate * 0.035);
      const start = Math.max(0, center - radius);
      const end = Math.min(channel.length, center + radius);
      if (end <= start) return 0;
      let sum = 0;
      for (let index = start; index < end; index += 1) sum += channel[index] * channel[index];
      return Math.sqrt(sum / (end - start));
    }

    function lipFromKana(char) {
      if (!char || /[、。,.!?！？…]/.test(char)) return "closed";
      if (/[んンっッー]/.test(char)) return "closed";
      if (/[いきしちにひみりぎじぢびぴイキシチニヒミリギジヂビピえけせてねへめれげぜでべぺエケセテネヘメレゲゼデベペ]/.test(char)) return "e";
      if (/[うくすつぬふむゆるぐずづぶぷウクスツヌフムユルグズヅブプおこそとのほもよろをごぞどぼぽオコソトノホモヨロヲゴゾドボポ]/.test(char)) return "u";
      return "open";
    }

    function lipFromTextTime(time) {
      const chars = Array.from(String(textInput?.value || "").replace(/\s+/g, ""));
      if (!chars.length) return "half";
      const duration = audio.duration || decoded?.duration || 1;
      const index = Math.max(0, Math.min(chars.length - 1, Math.floor((time / Math.max(duration, 0.1)) * chars.length)));
      return lipFromKana(chars[index]);
    }

    function chooseMouth(rms, now) {
      lastRms = rms;
      rmsPeak = Math.max(rmsPeak * 0.996, rms, 0.001);
      const scriptLip = lipFromTextTime(audio.currentTime || 0);
      const silenceGate = Math.max(0.0045, rmsPeak * 0.16);
      if (decoded && rms < silenceGate) {
        env *= 0.42;
        if (now - lastSwitch >= 70 && shape !== "closed") {
          shape = "closed";
          lastSwitch = now;
        }
        return shape;
      }

      const normalized = Math.min(1, rms / Math.max(rmsPeak * 1.05, 0.014));
      env = env * 0.82 + normalized * 0.18;
      if (now - lastSwitch < 115) return shape;
      let next = scriptLip;
      if (scriptLip === "open" && env < 0.88) next = "half";
      if (env < 0.22 && decoded) next = "closed";
      if (next !== shape) {
        shape = next;
        lastSwitch = now;
      }
      return shape;
    }

    function frameInfo() {
      const frames = track && Array.isArray(track.frames) ? track.frames : null;
      if (!frames?.length) return { cx: 430, cy: 574, w: 90, h: 50, angle: 0 };
      const fps = track.fps || 24;
      const avatarTime = audio.paused ? (video.currentTime || 0) : (audio.currentTime || 0);
      return frames[Math.floor(avatarTime * fps) % frames.length] || frames[0];
    }

    function draw() {
      if (!ctx) return;
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      if (video.readyState >= 2) {
        try {
          const targetTime = (audio.currentTime || 0) % Math.max(video.duration || 5, 0.1);
          if (!audio.paused && Math.abs((video.currentTime || 0) - targetTime) > 0.25) video.currentTime = targetTime;
        } catch {
          // Seeking can fail briefly while metadata is loading.
        }
        ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      } else {
        ctx.fillStyle = "#eef2f7";
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.fillStyle = "#607089";
        ctx.font = "28px sans-serif";
        ctx.fillText("loading avatar...", 280, 552);
      }

      const box = canvas.getBoundingClientRect();
      if (!audio.paused) setDebug(`audio: playing / lip: ${shape} / rms: ${lastRms.toFixed(4)} / video: ${video.readyState} / canvas: ${Math.round(box.width)}x${Math.round(box.height)}`);
      else setDebug(`${audio.currentSrc || audio.src ? "audio: ready" : "audio: no src"} / video: ${video.readyState} / canvas: ${Math.round(box.width)}x${Math.round(box.height)}`);

      const selected = active && !audio.paused && !audio.ended
        ? chooseMouth(rmsAt(audio.currentTime || 0), performance.now())
        : "closed";
      const mouth = mouthImages[selected] || mouthImages.closed;
      if (mouth?.complete) {
        const frame = frameInfo();
        const width = Math.max((frame.w || 90) * 0.58, 34);
        const height = Math.max((frame.h || 46) * 0.58, 20);
        ctx.save();
        ctx.translate(frame.cx || 430, frame.cy || 574);
        ctx.rotate(((frame.angle || 0) * Math.PI) / 180);
        ctx.drawImage(mouth, -width / 2, -height / 2, width, height);
        ctx.restore();
      }
      rafId = requestAnimationFrame(draw);
    }

    function ensureVideo() {
      if (!video.src || !video.src.includes("loop_mouthless.mp4")) video.src = `${ASSET_ROOT}/loop_mouthless.mp4`;
      video.muted = true;
      video.loop = true;
      if (video.readyState < 2) video.load();
      video.play().catch(() => {});
      if (!rafId) draw();
    }

    async function start() {
      if (!active) return;
      setStatus("同期中", "success");
      setDebug(`audio: playing ${audio.currentSrc || audio.src || "no-src"}`);
      await loadTrack().catch((error) => setDebug(`track error: ${error.message}`));
      await loadDecodedAudio().catch((error) => setDebug(`audio decode skipped: ${error.message}`));
      ensureVideo();
    }

    function stop() {
      env = 0;
      shape = "closed";
      lastRms = 0;
      setStatus(active ? "待機中" : "OFF", active ? "pending" : "failed");
      ensureVideo();
    }

    audio.addEventListener("play", start);
    audio.addEventListener("pause", stop);
    audio.addEventListener("ended", stop);
    audio.addEventListener("error", () => setDebug(`audio error: ${audio.error ? audio.error.code : "unknown"}`));
    if (toggle) {
      toggle.textContent = "キャラ同期 ON";
      toggle.onclick = () => {
        active = !active;
        toggle.textContent = active ? "キャラ同期 ON" : "キャラ同期 OFF";
        if (!active) stop();
        else if (!audio.paused) start();
        else setStatus("待機中", "pending");
      };
    }

    setStatus("待機中", "pending");
    setDebug("audio: waiting");
    loadTrack().catch((error) => setDebug(`track error: ${error.message}`)).finally(ensureVideo);
    return { audio, video, canvas };
  }

  window.LocalTtsAvatar = Object.freeze({ init });
})();
