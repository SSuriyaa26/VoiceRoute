# VoiceRoute ⚡

> **A voice-first, AI-powered telecom customer support router that eliminates "Press 1 for X" IVR menus entirely.**  
> Built for the **Gnani.ai Building Challenge**.  
> 📄 **Solution Pitch Document (1 Page)**: [`PITCH.md`](PITCH.md)

A caller speaks naturally in their preferred language (**English, Hindi, Tamil, or code-mixed Hinglish/Tanglish**). In a single turn, VoiceRoute identifies their intent, extracts key entities, measures sentiment, matches existing CRM tickets, and makes an explainable, deterministic routing decision — speaking back a fluent native reply.

---

## 📸 Overview & Architecture

```
 Browser Mic ──(audio)──► POST /asr ──► Gnani STT REST (fallback: Browser Web Speech API)
                                            │ transcript
                                            ▼
                                POST /route ─► Gemini 3.5 Flash NLU (JSON intent & sentiment)
                                            │
                                            ▼
                                      router.py (Deterministic Python Rules 0–7)
                                            │ decision + target queue + ticket_id + reply_text
                                            ▼
 Browser Speaker ◄─(audio)── POST /tts ◄── Gnani Timbre TTS (fallback: speechSynthesis)
```

1. **Voice Input (ASR)**: Audio captured via browser microphone is automatically converted to 16 kHz mono WAV via `ffmpeg` and transcribed using **Gnani STT REST** (`/stt/v3`). If offline or without keys, it seamlessly falls back to the native **Web Speech API** with live interim streaming.
2. **Natural Language Understanding (NLU)**: **Google Gemini 3.5 Flash** parses caller intent, calibrated confidence scores ($0.0 - 1.0$), entities, language mix, and sentiment. An offline keyword classifier serves as fallback.
3. **Deterministic Business Rules Engine**: Pure Python ([`backend/router.py`](backend/router.py)) evaluates routing logic without network I/O or LLM hallucination:
   - **`route`**: Confident match ($\text{confidence} \ge 0.80$ and $\text{margin} \ge 0.15$) directed to target queue (Billing, Sales, Tech Support, Retention).
   - **`clarify`**: Ambiguous intent prompts a single targeted question offering the top two intents, then auto-reopens the mic for Turn 2.
   - **`escalate`**: Angry callers, supervisor demands combined with frustration, or unresolvable inquiries route to Senior Escalation or General Agent.
   - **`reprompt`**: Inaudible/silent speech asks the caller to repeat (capped at 1 per session).
4. **CRM & Open Ticket Linking**: Matches caller profile against open tickets (e.g. C001 Priya Sharma $\rightarrow$ Billing dispute `T-1042`), attaching the ticket and routing directly to that ticket's assigned department.
5. **Spoken Output (TTS)**: **Gnani Timbre TTS** (`timbre-v2.5` with Nalini/Bhavna/Ambuja voices) synthesizes the reply. Pronunciation pre-processing formats ticket IDs (`T-1042` $\rightarrow$ *"T dash 1 0 4 2"*) and amounts (`₹249` $\rightarrow$ *"249 rupees"*).
6. **Live Side-by-Side IVR Benchmark**: An interactive 3-tier DTMF keypad stopwatch demonstrates the dramatic speed difference (~18s on traditional IVR vs. ~1.8s on VoiceRoute).

---

## 📄 Solution Pitch (1 Page)

👉 **See [`PITCH.md`](PITCH.md)** for our official 1-page solution pitch covering problem statement, business value, architecture, and measurable impact.

---

## 🛠️ Tech Stack

| Layer | Primary Provider | Graceful Fallback |
|---|---|---|
| **ASR (Speech-to-Text)** | Gnani STT REST (`/stt/v3`) | Browser Web Speech API |
| **NLU (Language Understanding)** | Google Gemini (`gemini-3.5-flash-lite`) | Multilingual Keyword Classifier |
| **Routing Logic** | Deterministic Python Rules Engine | General Agent Queue |
| **TTS (Text-to-Speech)** | Gnani Timbre TTS SSE (`/api/v1/tts/sse`) | Browser `speechSynthesis` |
| **Backend** | Python 3.11+, FastAPI, Uvicorn, Pydantic v2 | — |
| **Frontend** | Vanilla HTML5 / CSS3 / JavaScript (Zero build step) | — |

---

## ⚡ Quickstart

### 1. Clone & Install Dependencies
```bash
git clone https://github.com/your-username/voiceroute.git
cd voiceroute
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy the example environment file:
```bash
cp .env.example .env
```
Edit `.env` with your API keys:
```env
GEMINI_API_KEY=your_gemini_api_key_here
GNANI_API_KEY=your_gnani_api_key_here
LLM_MODEL=gemini-3.5-flash-lite
```
*(Note: If API keys are omitted, VoiceRoute operates fully offline using the keyword fallback and browser speech APIs!)*

### 3. Launch the Server
```bash
uvicorn backend.main:app --reload --port 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in Google Chrome.

---

## 🧪 Testing & Evaluation

### Run Unit Tests
Verifies all 8 routing rules, boundary cases, reprompt guards, and fallbacks:
```bash
pytest tests/ -v
```
*(34/34 passing tests)*

### Run Evaluation Benchmark
Evaluates the 36-utterance multilingual benchmark dataset:
```bash
# Run quick sanity check (6 diverse cases across all routing paths)
python tests/eval.py --quick

# Run all 36 utterances with rate-limit pacing
python tests/eval.py

# Run first 10 utterances with custom delay
python tests/eval.py --limit 10 --delay 1.5
```

#### Benchmark Results (Measured Live on Gemini 3.5 Flash):
- **Intent Accuracy**: **96.7%** (29/30 scoreable utterances)
- **Decision Accuracy**: **83.3%** (30/36 utterances)
- **Mean NLU Latency**: **1,249 ms** (~1.2s)
- **P95 Latency**: **1,935 ms** (< 2.0s)

---

## 📁 Project Structure

```
voiceroute/
  ├── PITCH.md                 # 1-page official solution pitch
  ├── .gitignore               # Secrets and build artifact exclusion
  ├── .env.example             # Template for API credentials
  ├── requirements.txt         # Python package dependencies
  ├── README.md                # Project documentation
  │
  ├── backend/
  │   ├── main.py              # FastAPI endpoints (/route, /asr, /tts, /health)
  │   ├── config.py            # Central constants, queues, thresholds & dynamic reload
  │   ├── models.py            # Pydantic v2 validation models
  │   ├── nlu.py               # Gemini 3.5 Flash NLU + multilingual keyword fallback
  │   ├── router.py            # Pure deterministic business rules engine
  │   ├── session.py           # In-memory session tracking (max 1 clarify/reprompt)
  │   ├── gnani_asr.py         # Gnani STT client + ffmpeg 16 kHz WAV conversion
  │   ├── gnani_tts.py         # Gnani Timbre SSE client + WAV audio assembler
  │   └── mock_customers.json  # 3 telecom CRM customer records with tickets
  │
  ├── frontend/
  │   ├── index.html           # Split dashboard: Call Center + Brain Panel + IVR strip
  │   ├── styles.css           # Modern dark-mode UI with soundwave animations
  │   ├── app.js               # UI controller, session state, Brain panel & IVR timer
  │   ├── asr.js               # Dual ASR (Gnani MediaRecorder + Web Speech API)
  │   └── tts.js               # Dual TTS (Gnani audio stream + SpeechSynthesis)
  │
  └── tests/
      ├── test_router.py       # 22 tests verifying Rules 0 through 7
      ├── test_nlu_fallback.py # 12 tests verifying keyword classification
      ├── utterances.json      # 36 benchmark utterances (EN, HI, TA, code-mix)
      └── eval.py              # Automated evaluation benchmark runner
```

---

## 📞 Production Telephony Path

While this hackathon project demonstrates browser-based audio, the production deployment path connects directly to carrier networks (Airtel, Jio, Vi) via:
- **`pipecat-gnani`**: Real-time WebRTC/SIP pipeline plugin by Gnani.
- **SIP Trunking**: Directly interfaces FreeSWITCH / Asterisk telephony switches.
- **Server-Side VAD**: Hands-free barge-in detection on live cellular audio streams.

---

## 🛡️ License

Built for the **Gnani.ai Building Challenge**. Distributed under the MIT License.
