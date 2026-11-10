/**
 * app.js — Main orchestration: session, routing, UI updates, IVR comparison.
 */
(function () {
  "use strict";

  /* ── State ────────────────────────────────────────────────────────── */
  let sessionId = crypto.randomUUID();
  let currentTurn = 1;
  let clarificationContext = null;    // set after a "clarify" decision
  let customerId = "C001";
  let language = "en-IN";
  let vrStartTime = null;             // for VoiceRoute timer
  let ivrStartTime = null;            // for IVR timer
  let asrLatency = 0;

  /* ── DOM refs ─────────────────────────────────────────────────────── */
  const chatArea           = document.getElementById("chat-area");
  const micBtn             = document.getElementById("mic-btn");
  const textInput          = document.getElementById("text-input");
  const sendBtn            = document.getElementById("send-btn");
  const customerSelect     = document.getElementById("customer-select");
  const languageSelect     = document.getElementById("language-select");
  const customerCard       = document.getElementById("customer-card");
  const providerBadge      = document.getElementById("provider-badge");
  const liveTranscript     = document.getElementById("live-transcript");
  const liveTranscriptText = document.getElementById("live-transcript-text");
  const resetSessionBtn    = document.getElementById("reset-session-btn");

  // Brain panel
  const decisionBadge      = document.getElementById("decision-badge");
  const decisionRuleTag    = document.getElementById("decision-rule-tag");
  const queueLabel         = document.getElementById("queue-label");
  const intentBars         = document.getElementById("intent-bars");
  const sentimentBadge     = document.getElementById("sentiment-badge");
  const ticketId           = document.getElementById("ticket-id");
  const nluSource          = document.getElementById("nlu-source");
  const asrProvider        = document.getElementById("asr-provider");
  const handoffSummary     = document.getElementById("handoff-summary");
  const timingASR          = document.getElementById("timing-asr");
  const timingNLU          = document.getElementById("timing-nlu");
  const timingRouter       = document.getElementById("timing-router");
  const timingTTS          = document.getElementById("timing-tts");
  const timingTotal        = document.getElementById("timing-total");
  const vrTimer            = document.getElementById("vr-timer");
  const ivrTimerEl         = document.getElementById("ivr-timer");

  /* ── Welcome HTML Template for Reset ──────────────────────────────── */
  const welcomeHTML = `
    <div class="chat-welcome">
      <div class="welcome-badge">🎙️ Voice-First Demo</div>
      <h3>Welcome to VoiceRoute</h3>
      <p class="welcome-desc">Say anything naturally or click a sample utterance below to test routing in 1 turn:</p>
      <div class="sample-chips">
        <button class="sample-chip" onclick="sendSample('My bill is too high this month')">
          <span class="chip-emoji">💳</span>
          <span class="chip-text">"My bill is too high"</span>
          <span class="chip-tag tag-route">Route</span>
        </button>
        <button class="sample-chip" onclick="sendSample('Mera bill zyada aaya hai')">
          <span class="chip-emoji">🇮🇳</span>
          <span class="chip-text">"Mera bill zyada aaya hai"</span>
          <span class="chip-tag tag-hindi">Hindi</span>
        </button>
        <button class="sample-chip" onclick="sendSample('My calls keep dropping and no signal')">
          <span class="chip-emoji">📶</span>
          <span class="chip-text">"Calls keep dropping"</span>
          <span class="chip-tag tag-route">Tech</span>
        </button>
        <button class="sample-chip" onclick="sendSample('I have a problem with my plan')">
          <span class="chip-emoji">❓</span>
          <span class="chip-text">"Problem with my plan"</span>
          <span class="chip-tag tag-clarify">Clarify</span>
        </button>
        <button class="sample-chip" onclick="sendSample('I want to escalate this to your manager now')">
          <span class="chip-emoji">🚨</span>
          <span class="chip-text">"Escalate to manager"</span>
          <span class="chip-tag tag-escalate">Escalate</span>
        </button>
      </div>
    </div>`;

  /* ── Init ─────────────────────────────────────────────────────────── */
  checkHealth();
  loadCustomer(customerId);

  customerSelect.addEventListener("change", () => {
    customerId = customerSelect.value;
    loadCustomer(customerId);
    resetSession();
  });
  languageSelect.addEventListener("change", () => { language = languageSelect.value; });
  sendBtn.addEventListener("click", handleTextSend);
  textInput.addEventListener("keydown", (e) => { if (e.key === "Enter") handleTextSend(); });
  micBtn.addEventListener("click", toggleMic);
  if (resetSessionBtn) {
    resetSessionBtn.addEventListener("click", resetSession);
  }

  /* ── Health check ─────────────────────────────────────────────────── */
  async function checkHealth() {
    try {
      const resp = await fetch("/health");
      const data = await resp.json();
      const parts = [];
      if (data.llm) parts.push("Gemini ✓");
      else parts.push("NLU (Offline)");
      if (data.gnani_asr) parts.push("Gnani ASR ✓");
      else parts.push("ASR (Browser)");
      if (data.gnani_tts) parts.push("Gnani TTS ✓");
      else parts.push("TTS (Browser)");
      providerBadge.textContent = parts.join(" · ");
    } catch {
      providerBadge.textContent = "Backend offline";
    }
  }

  /* ── Customer card ────────────────────────────────────────────────── */
  async function loadCustomer(id) {
    try {
      const resp = await fetch(`/customer/${id}`);
      const c = await resp.json();
      const initials = c.name ? c.name.split(" ").map(n => n[0]).join("") : id;
      
      let html = `
        <div class="cust-card-inner">
          <div class="cust-avatar">${initials}</div>
          <div class="cust-details">
            <div class="cust-header">
              <span class="cust-name">${c.name}</span>
              <span class="cust-plan-pill">${c.plan}</span>
            </div>
            <div class="cust-sub">${c.phone} · ID: <strong>${c.id}</strong></div>
          </div>
        </div>`;

      if (c.open_tickets && c.open_tickets.length > 0) {
        const t = c.open_tickets[0];
        html += `
          <div class="cust-ticket-badge">
            <span class="ticket-icon">🎫</span>
            <span class="ticket-info"><strong>${t.ticket_id}</strong>: ${t.summary}</span>
            <span class="ticket-queue-pill">${t.queue}</span>
          </div>`;
      }
      customerCard.innerHTML = html;
    } catch {
      customerCard.innerHTML = `<span class="cust-name">${id}</span>`;
    }
  }

  /* ── Session reset ────────────────────────────────────────────────── */
  function resetSession() {
    sessionId = crypto.randomUUID();
    currentTurn = 1;
    clarificationContext = null;
    chatArea.innerHTML = welcomeHTML;
    resetBrainPanel();
    fetch(`/session/reset?session_id=${sessionId}`, { method: "POST" }).catch(() => {});
  }

  /* ── Mic toggle (push-to-talk) ────────────────────────────────────── */
  function toggleMic() {
    if (ASR.isRecording) {
      micBtn.classList.remove("recording");
      micBtn.querySelector(".mic-caption").textContent = "TAP TO SPEAK";
      if (liveTranscript) liveTranscript.classList.add("hidden");
      ASR.stopRecording();
    } else {
      // Barge-in: stop any playing audio immediately
      TTS.stop();
      micBtn.classList.add("recording");
      micBtn.querySelector(".mic-caption").textContent = "LISTENING…";
      if (liveTranscript) {
        liveTranscriptText.textContent = "Listening… speak naturally";
        liveTranscript.classList.remove("hidden");
      }
      vrStartTime = performance.now();
      ASR.startRecording(language, handleASRResult, handleInterimResult);
    }
  }

  function handleInterimResult(text) {
    if (liveTranscriptText && text) {
      liveTranscriptText.textContent = `"${text}"`;
    }
  }

  /* ── ASR result handler ───────────────────────────────────────────── */
  function handleASRResult(result) {
    micBtn.classList.remove("recording");
    micBtn.querySelector(".mic-caption").textContent = "TAP TO SPEAK";
    if (liveTranscript) liveTranscript.classList.add("hidden");
    asrLatency = result.latency_ms || 0;
    asrProvider.textContent = result.provider === "gnani" ? "Gnani Cloud" : "Web Speech";

    if (result.error || !result.transcript) {
      addChatBubble("(Inaudible / Empty audio)", "user");
      sendToRoute("");
    } else {
      addChatBubble(result.transcript, "user");
      sendToRoute(result.transcript);
    }
  }

  /* ── Sample utterance chip send ───────────────────────────────────── */
  window.sendSample = function (text) {
    if (!text) return;
    vrStartTime = performance.now();
    asrLatency = 0;
    asrProvider.textContent = "Preset Audio";
    addChatBubble(text, "user");
    sendToRoute(text);
  };

  /* ── Text send ────────────────────────────────────────────────────── */
  function handleTextSend() {
    const text = textInput.value.trim();
    if (!text) return;
    textInput.value = "";
    vrStartTime = performance.now();
    asrLatency = 0;
    asrProvider.textContent = "Text Input";
    addChatBubble(text, "user");
    sendToRoute(text);
  }

  /* ── Route call ───────────────────────────────────────────────────── */
  async function sendToRoute(transcript) {
    const body = {
      session_id: sessionId,
      transcript: transcript,
      language_hint: language,
      turn: currentTurn,
      clarification_context: clarificationContext,
      customer_id: customerId,
    };

    try {
      const resp = await fetch("/route", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await resp.json();
      handleRouteResponse(data);
    } catch (err) {
      console.error("Route error:", err);
      addChatBubble("Sorry, unable to connect to the router service. Please try again.", "system");
    }
  }

  /* ── Route response handler ───────────────────────────────────────── */
  async function handleRouteResponse(data) {
    updateBrainPanel(data);

    if (data.reply_text) {
      addChatBubble(data.reply_text, "system");
    }

    let ttsLatency = 0;
    if (data.reply_text) {
      ttsLatency = (await TTS.speak(data.reply_text, language)) || 0;
    }

    // Update timings
    timingASR.textContent = asrLatency ? `${asrLatency}ms` : "—";
    timingNLU.textContent = data.timings_ms?.nlu ? `${data.timings_ms.nlu}ms` : "—";
    timingRouter.textContent = data.timings_ms?.router !== undefined ? `${data.timings_ms.router}ms` : "—";
    timingTTS.textContent = ttsLatency ? `${ttsLatency}ms` : "—";

    const totalE2E = vrStartTime ? Math.round(performance.now() - vrStartTime) : (data.timings_ms?.total || 0);
    timingTotal.textContent = `${totalE2E}ms`;
    vrTimer.textContent = `${(totalE2E / 1000).toFixed(2)}s`;

    // Handle clarification turn flow
    if (data.decision === "clarify") {
      clarificationContext = {
        original_transcript: document.querySelector(".chat-role-user:last-of-type .bubble-text")?.textContent || data.reply_text,
        offered_intents: [
          data.intents[0]?.name,
          data.intents[1]?.name || "talk_to_agent",
        ],
      };
      currentTurn = 2;
      // Auto-open mic for the answer after a brief 1.5s pause
      setTimeout(() => {
        if (!ASR.isRecording) toggleMic();
      }, 1500);
    } else {
      currentTurn = 1;
      clarificationContext = null;
    }
  }

  /* ── Brain panel update ───────────────────────────────────────────── */
  function updateBrainPanel(data) {
    const decision = data.decision || "idle";
    const icons = {
      route: "✓ ROUTED",
      resolve: "⚡ SELF-SERVED",
      clarify: "❓ CLARIFY",
      escalate: "🚨 ESCALATED",
      reprompt: "🔄 REPROMPT",
      idle: "IDLE",
    };

    decisionBadge.textContent = icons[decision] || decision.toUpperCase();
    decisionBadge.className = `decision-badge decision-${decision}`;

    queueLabel.textContent = decision === "resolve" ? "None (Call Deflected)" : (data.queue ? `${data.queue} Team` : "None");
    if (decisionRuleTag) {
      if (decision === "resolve") decisionRuleTag.textContent = "Tier-1: CRM Self-Service Deflection";
      else if (decision === "route") decisionRuleTag.textContent = data.ticket_id ? "Rule 7: Ticket Linked" : "Rule 3: High Margin";
      else if (decision === "clarify") decisionRuleTag.textContent = "Rule 4: Ambiguous Intent";
      else if (decision === "escalate") decisionRuleTag.textContent = data.sentiment === "angry" ? "Rule 1: Angry Sentiment" : "Rule 1 / 5: Escalation";
      else if (decision === "reprompt") decisionRuleTag.textContent = "Rule 0: Inaudible Guardrail";
    }

    // Intent bars (top 3)
    const topIntents = (data.intents || []).slice(0, 3);
    intentBars.innerHTML = topIntents.map((intent, i) => {
      const pct = Math.round(intent.confidence * 100);
      const isTop = i === 0;
      const label = intent.name.replace(/_/g, " ");
      return `
        <div class="intent-bar-row">
          <span class="intent-bar-name" title="${intent.name}">${label}</span>
          <div class="intent-bar-track">
            <div class="intent-bar-fill ${isTop ? 'top' : ''}" style="width:${pct}%"></div>
          </div>
          <span class="intent-bar-value">${pct}%</span>
        </div>`;
    }).join("");

    // Sentiment
    const sentiment = data.sentiment || "neutral";
    sentimentBadge.textContent = sentiment;
    sentimentBadge.className = `sentiment-badge sentiment-${sentiment}`;

    // Metadata
    ticketId.textContent = data.ticket_id ? `🎫 ${data.ticket_id}` : "None";
    nluSource.textContent = data.nlu_source === "llm" ? "Gemini 2.5 Flash" : "Keyword Fallback";
    handoffSummary.textContent = data.handoff_summary || "—";
  }

  function resetBrainPanel() {
    decisionBadge.textContent = "IDLE";
    decisionBadge.className = "decision-badge decision-idle";
    queueLabel.textContent = "Awaiting Utterance";
    if (decisionRuleTag) decisionRuleTag.textContent = "Rule Evaluation";
    intentBars.innerHTML = `
      <div class="empty-state">
        <span class="empty-icon">📊</span>
        <p>Confidence scores will appear here after the first turn</p>
      </div>`;
    sentimentBadge.textContent = "—";
    sentimentBadge.className = "sentiment-badge sentiment-neutral";
    ticketId.textContent = "—";
    nluSource.textContent = "—";
    asrProvider.textContent = "—";
    handoffSummary.textContent = "Ready for incoming customer conversation.";
    timingASR.textContent = "—";
    timingNLU.textContent = "—";
    timingRouter.textContent = "—";
    timingTTS.textContent = "—";
    timingTotal.textContent = "—";
  }

  /* ── Chat bubbles ─────────────────────────────────────────────────── */
  function addChatBubble(text, role) {
    const welcome = chatArea.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    const bubbleRow = document.createElement("div");
    bubbleRow.className = `chat-bubble-row chat-role-${role}`;

    const avatar = role === "user"
      ? '<span class="avatar avatar-user">👤</span>'
      : '<span class="avatar avatar-system">⚡</span>';

    const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    bubbleRow.innerHTML = `
      ${avatar}
      <div class="bubble-content">
        <div class="bubble-text">${escapeHtml(text)}</div>
        <div class="bubble-time">${timeStr}</div>
      </div>
    `;

    chatArea.appendChild(bubbleRow);
    chatArea.scrollTop = chatArea.scrollHeight;
  }

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str;
    return div.innerHTML;
  }

  /* ── Traditional IVR Interactive Mock Menu ────────────────────────── */
  const ivrTree = {
    1: {
      title: "Level 2: Billing Menu",
      prompt: '"Press 1 for Bill Enquiry, 2 for Payment, 3 to Dispute a Charge"',
      options: [
        { num: 1, sub: "Enquiry" },
        { num: 2, sub: "Payment" },
        { num: 3, sub: "Dispute" },
      ],
    },
    2: {
      title: "Level 2: Plans & Recharges",
      prompt: '"Press 1 for New Recharge, 2 for Plan Change, 3 for Data Add-on"',
      options: [
        { num: 1, sub: "Recharge" },
        { num: 2, sub: "Change" },
        { num: 3, sub: "Data" },
      ],
    },
    3: {
      title: "Level 2: Technical Support",
      prompt: '"Press 1 for Call Drops, 2 for Slow Internet, 3 for No Signal"',
      options: [
        { num: 1, sub: "Call Drop" },
        { num: 2, sub: "Internet" },
        { num: 3, sub: "No Signal" },
      ],
    },
  };

  window.ivrPress = function (level, choice) {
    if (level === 1) {
      ivrStartTime = performance.now();
      const l2 = document.getElementById("ivr-level-2");
      const tree = ivrTree[choice];
      if (tree) {
        l2.innerHTML = `
          <div class="ivr-breadcrumbs">${tree.title}</div>
          <p class="ivr-prompt">${tree.prompt}</p>
          <div class="ivr-keypad">
            ${tree.options.map(o => `
              <button class="dial-key" onclick="ivrPress(2,${o.num})">
                <span class="key-num">${o.num}</span>
                <span class="key-sub">${o.sub}</span>
              </button>
            `).join("")}
          </div>`;
        l2.classList.remove("hidden");
        document.getElementById("ivr-level-1").classList.add("hidden");
      }
    } else if (level === 2) {
      const l3 = document.getElementById("ivr-level-3");
      l3.innerHTML = `
        <div class="ivr-breadcrumbs">Level 3: Agent Queue Confirmation</div>
        <p class="ivr-prompt">"Please hold while we transfer your call to an agent. Press 1 to confirm transfer, 2 to restart."</p>
        <div class="ivr-keypad">
          <button class="dial-key" onclick="ivrPress(3,1)">
            <span class="key-num">1</span>
            <span class="key-sub">Connect</span>
          </button>
          <button class="dial-key" onclick="ivrPress(3,2)">
            <span class="key-num">2</span>
            <span class="key-sub">Restart</span>
          </button>
        </div>`;
      l3.classList.remove("hidden");
      document.getElementById("ivr-level-2").classList.add("hidden");
    } else if (level === 3) {
      if (choice === 2) {
        // Reset IVR
        document.getElementById("ivr-level-1").classList.remove("hidden");
        document.getElementById("ivr-level-2").classList.add("hidden");
        document.getElementById("ivr-level-3").classList.add("hidden");
        ivrStartTime = null;
        ivrTimerEl.textContent = "—";
        return;
      }
      // Completed DTMF path
      const elapsed = performance.now() - ivrStartTime;
      ivrTimerEl.textContent = `${(elapsed / 1000).toFixed(2)}s`;
      ivrTimerEl.style.color = "#ef4444";

      setTimeout(() => {
        document.getElementById("ivr-level-1").classList.remove("hidden");
        document.getElementById("ivr-level-2").classList.add("hidden");
        document.getElementById("ivr-level-3").classList.add("hidden");
      }, 4000);
    }
  };

})();
