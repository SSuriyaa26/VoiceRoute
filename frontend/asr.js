/**
 * asr.js — ASR module with Gnani (primary) and Web Speech API (fallback).
 *
 * Exports: window.ASR = { startRecording, stopRecording, isRecording }
 */
(function () {
  "use strict";

  let mediaRecorder = null;
  let audioChunks = [];
  let isRecording = false;
  let webSpeechRecognition = null;
  let onResultCallback = null;
  let useWebSpeech = false;   // set true when /asr fails

  /* ── Gnani ASR via MediaRecorder → POST /asr ──────────────────────── */

  async function startGnaniRecording(language, onResult) {
    onResultCallback = onResult;
    audioChunks = [];

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm;codecs=opus" });

      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) audioChunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        // Release mic
        stream.getTracks().forEach((t) => t.stop());

        const blob = new Blob(audioChunks, { type: "audio/webm" });
        const formData = new FormData();
        formData.append("file", blob, "recording.webm");
        formData.append("language", language);

        const start = performance.now();
        try {
          const resp = await fetch("/asr", { method: "POST", body: formData });
          const data = await resp.json();
          const latency = Math.round(performance.now() - start);

          if (data.error) {
            // Gnani failed — fall back to Web Speech for this session
            console.warn("Gnani ASR error, switching to Web Speech fallback");
            useWebSpeech = true;
            showFallbackBadge(true);
            onResultCallback({ transcript: "", provider: "gnani", latency_ms: latency, error: data.error });
          } else {
            onResultCallback({ ...data, latency_ms: data.latency_ms || latency });
          }
        } catch (err) {
          console.error("ASR fetch error:", err);
          useWebSpeech = true;
          showFallbackBadge(true);
          onResultCallback({ transcript: "", provider: "gnani", latency_ms: 0, error: "asr_failed" });
        }
      };

      mediaRecorder.start();
      isRecording = true;
    } catch (err) {
      console.error("Microphone access denied:", err);
      onResultCallback({ transcript: "", provider: "none", latency_ms: 0, error: "mic_denied" });
    }
  }

  function stopGnaniRecording() {
    if (mediaRecorder && mediaRecorder.state === "recording") {
      mediaRecorder.stop();
    }
    isRecording = false;
  }

  /* ── Web Speech API fallback ──────────────────────────────────────── */

  function startWebSpeechRecording(language, onResult, onInterim) {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      onResult({ transcript: "", provider: "webspeech", latency_ms: 0, error: "not_supported" });
      return;
    }

    webSpeechRecognition = new SpeechRecognition();
    webSpeechRecognition.lang = language;
    webSpeechRecognition.interimResults = true;
    webSpeechRecognition.maxAlternatives = 1;

    const start = performance.now();
    let finalTranscript = "";

    webSpeechRecognition.onresult = (event) => {
      let interimTranscript = "";
      for (let i = event.resultIndex; i < event.results.length; ++i) {
        if (event.results[i].isFinal) {
          finalTranscript += event.results[i][0].transcript;
        } else {
          interimTranscript += event.results[i][0].transcript;
        }
      }
      if (onInterim && interimTranscript) {
        onInterim(interimTranscript);
      }
      if (finalTranscript) {
        const latency = Math.round(performance.now() - start);
        onResult({ transcript: finalTranscript, provider: "webspeech", latency_ms: latency });
      }
    };

    webSpeechRecognition.onerror = (event) => {
      const latency = Math.round(performance.now() - start);
      onResult({ transcript: "", provider: "webspeech", latency_ms: latency, error: event.error });
    };

    webSpeechRecognition.onend = () => { isRecording = false; };

    webSpeechRecognition.start();
    isRecording = true;
  }

  function stopWebSpeechRecording() {
    if (webSpeechRecognition) {
      webSpeechRecognition.stop();
      webSpeechRecognition = null;
    }
    isRecording = false;
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

  window.ASR = {
    startRecording(language, onResult, onInterim) {
      if (useWebSpeech) {
        startWebSpeechRecording(language, onResult, onInterim);
      } else {
        startGnaniRecording(language, onResult);
      }
    },

    stopRecording() {
      if (useWebSpeech) {
        stopWebSpeechRecording();
      } else {
        stopGnaniRecording();
      }
    },

    get isRecording() {
      return isRecording;
    },

    get provider() {
      return useWebSpeech ? "webspeech" : "gnani";
    },
  };
})();

