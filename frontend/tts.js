/**
 * tts.js — TTS module with Gnani (primary) and browser speechSynthesis (fallback).
 *
 * Exports: window.TTS = { speak, stop, isSpeaking }
 */
(function () {
  "use strict";

  let currentAudio = null;
  let isSpeaking = false;
  let useWebTTS = false;  // set true when /tts fails

  /* ── Gnani TTS via POST /tts ──────────────────────────────────────── */

  async function speakGnani(text, language) {
    const start = performance.now();
    try {
      const resp = await fetch("/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, language }),
      });

      if (!resp.ok || resp.headers.get("content-type")?.includes("json")) {
        // Server returned error JSON
        const data = await resp.json().catch(() => ({}));
        if (data.error) {
          console.warn("Gnani TTS error, switching to browser fallback");
          useWebTTS = true;
          showFallbackBadge(true);
          speakBrowser(text, language);
          return Math.round(performance.now() - start);
        }
      }

      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const latency = Math.round(performance.now() - start);

      return new Promise((resolve) => {
        currentAudio = new Audio(url);
        isSpeaking = true;

        currentAudio.onended = () => {
          isSpeaking = false;
          URL.revokeObjectURL(url);
          resolve(latency);
        };
        currentAudio.onerror = () => {
          isSpeaking = false;
          URL.revokeObjectURL(url);
          // Fall back to browser TTS
          useWebTTS = true;
          showFallbackBadge(true);
          speakBrowser(text, language);
          resolve(latency);
        };

        currentAudio.play().catch(() => {
          isSpeaking = false;
          speakBrowser(text, language);
          resolve(latency);
        });
      });
    } catch (err) {
      console.error("TTS fetch error:", err);
      useWebTTS = true;
      showFallbackBadge(true);
      speakBrowser(text, language);
      return Math.round(performance.now() - start);
    }
  }

  /* ── Browser speechSynthesis fallback ─────────────────────────────── */

  function speakBrowser(text, language) {
    if (!window.speechSynthesis) return;

    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = language;
    utterance.rate = 1.0;

    isSpeaking = true;
    utterance.onend = () => { isSpeaking = false; };
    utterance.onerror = () => { isSpeaking = false; };

    window.speechSynthesis.speak(utterance);
  }

  /* ── Stop any playback (barge-in) ─────────────────────────────────── */

  function stop() {
    if (currentAudio) {
      currentAudio.pause();
      currentAudio.currentTime = 0;
      currentAudio = null;
    }
    if (window.speechSynthesis) {
      window.speechSynthesis.cancel();
    }
    isSpeaking = false;
  }

  /* ── Helper ───────────────────────────────────────────────────────── */

  function showFallbackBadge(show) {
    const badge = document.getElementById("fallback-badge");
    if (badge) {
      badge.classList.toggle("badge-hidden", !show);
      badge.classList.toggle("badge-warn", show);
    }
  }

  /* ── Public API ───────────────────────────────────────────────────── */

  window.TTS = {
    async speak(text, language) {
      if (useWebTTS) {
        speakBrowser(text, language);
        return 0;
      }
      return speakGnani(text, language);
    },

    stop,

    get isSpeaking() { return isSpeaking; },

    get provider() { return useWebTTS ? "webspeech" : "gnani"; },
  };
})();

