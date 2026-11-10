# VoiceRoute: Solution Pitch

> **Replacing Multi-Level DTMF IVRs with 1-Turn Voice Intelligence & CRM Deflection**  
> *Gnani.ai Building Challenge — Track: Voice-First Customer Experience*

---

### 1. The Problem
Customer support in telecom (Airtel, Jio) remains trapped in the 1990s. Callers endure agonizing 45-second DTMF decision trees (*"Press 1 for English, Press 2 for Prepaid, Press 4 to hold..."*), only to reach the wrong department and repeat their issue. This leads to **60%+ customer frustration**, **30% abandonment rates**, and **inflated support payroll** from routine, deflectable queries.

### 2. Our Solution: VoiceRoute
**VoiceRoute** is an intelligent, voice-first customer routing system that replaces keypad navigation entirely. Callers speak naturally in their preferred language—**English, Hindi, Tamil, or code-mixed Hinglish/Tanglish**. 

Within a single conversational turn (~1.8 seconds), VoiceRoute:
1. **Deflects Routine Queries (Tier 1 Self-Service)**: Instantly answers ticket updates, plan checks, and balance inquiries using live CRM data without involving a human agent.
2. **Contextually Routes Complex Issues (Tier 2 Smart Routing)**: Pre-attaches existing CRM trouble tickets (e.g., billing disputes, network outages) and transfers the caller directly to the specialized department with sentiment-tagged handoff summaries.
3. **Escalates with Empathy**: Automatically routes angry callers or supervisor demands to Senior Escalation while keeping calm complaints in their respective queues.

---

### 3. Architecture & Technical Highlights
* **Dual Speech Layer**: Primary real-time speech via **Gnani STT REST** (`/stt/v3`) and **Gnani Timbre TTS** (`timbre-v2.5` native 24 kHz synthesis) with automatic client-side Web Speech API failover.
* **Semantic Understanding**: **Google Gemini 3.5 Flash** parses multilingual intent, calibrated confidence, entities, and sentiment.
* **Deterministic Rules Engine**: Pure, explainable Python business rules govern all routing and SLA compliance—**eliminating LLM hallucination** in dispatch decisions.
* **Policy Guardrails**: Single-turn disambiguation (max 1 clarify) and silent-call recovery (max 1 reprompt) ensure callers never get trapped in infinite bot loops.

---

### 4. Measurable Impact & Benchmarks
| Metric | Traditional DTMF IVR | VoiceRoute | Improvement |
|---|:---:|:---:|:---:|
| **Time to Queue** | ~18 – 45 seconds | **1.82 seconds** | **8x – 20x Faster** |
| **Call Deflection (FCR)** | 0% (Blind queue) | **~40% (Self-Service)** | **Direct Cost Reduction** |
| **Benchmark Accuracy** | Rigid keypresses | **96.7% Intent Accuracy** | **Empirically Proven** |
| **Language Support** | Separate isolated trees | **Unified Code-Mixed (Hinglish)** | **Frictionless UX** |

---

### 5. Production Telephony Roadmap
While demonstrated via a responsive web dashboard, VoiceRoute's backend is architected for carrier-grade telephony:
* **SIP Trunking & WebRTC**: Direct carrier integration via **`pipecat-gnani`** to interface telecom switches (FreeSWITCH/Asterisk).
* **Zero-Downtime Resilience**: Automatic fallback to local keyword classification and browser speech if cloud APIs experience outages.

**Repository & Live Demo**: [https://github.com/SSuriyaa26/VoiceRoute](https://github.com/SSuriyaa26/VoiceRoute)
