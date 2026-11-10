# DECISIONS

Append-only. Records decisions, deviations and mistakes. Never rewrite an entry. Supersede it with a new one.

Format: `ID · date · status (proposed / accepted / superseded) · decision · why · alternatives`.

---

### D-0 · 2026-11-10 · accepted · v4 work starts with research and docs, no code
- **Why:** Lebi asked for a full research pass before building. The model landscape moved a lot in 2026 (Gemma 4, Qwen3.5, Indic-Transcribe, Indic-Speak, Smart Turn v3).
- **Alternatives:** prototype first (rejected: VRAM constraints make blind prototyping wasteful).

### D-1 · 2026-11-10 · proposed (open, see BLOCKERS) · VRAM profile for native Tamil voice
- **Options** (architecture §4):
  - **P2:** STT on the CPU, brain 4B and LLM-TTS on the GPU.
  - **P2-alt:** 2B brain, GPU STT, LLM-TTS.
  - **Aggressive quantisation.**
- **Why open:** depends on the measured G0–G3 numbers.
- **Current lean:** P2 if a CPU ASR passes G2 at ≤400 ms.

### D-2 · 2026-11-10 · proposed · single TTS voice for EN + TA
- **Lean:** Indic-Speak (or Svara) for everything, so the friend has one voice.
- **Risk:** Indian-accented English.
- **Decided by:** G3 blind A/B.
- **Fallback:** Kokoro for pure-EN chunks.

### D-3 · 2026-11-10 · proposed · licence posture for Indic Open Model License weights
- **Lean:** personal and local use only. Weights are downloaded by `make models`, never baked into public images.

### D-4 · 2026-11-10 · proposed · transport
- **Lean:** keep WebSocket, add typed binary frames and server-side AEC with a known reference.
- **Revisit:** WebRTC (Pipecat SmallWebRTC/aiortc) if AEC quality is poor.

### D-5 · 2026-11-10 · proposed · framework
- **Lean:** keep our pipeline (tested, small, echo guard proven) and borrow components (Smart Turn, transport ideas, eval patterns).
- **Alternative:** port to Pipecat (rejected for now because it would discard the tested pipeline and tests).

### D-6 · 2026-11-10 · proposed · perception split
- **Lean:**
  - Per-frame perception (MediaPipe face and pose) runs **in the browser**, sending feature JSON at ~4 Hz.
  - Scene understanding uses the **brain VLM on keyframes**, on triggers only.
  - Replaces the v3 5 Hz base64 JPEG stream.
- **Why:** zero server GPU cost per frame, privacy (no pixels leave by default), and one resident model.

### D-7 · 2026-11-10 · proposed · Neo4j off by default; SQLite + sqlite-vec for v4 memory
- **Why:** 15 GB RAM. JVM cost 1–2 GB. Single-user scale.
- **Neo4j stays** behind `SemanticGraphStore` and `--profile memory`.

### D-8 · 2026-11-10 · proposed · new D-1 options found by reading `reference/` (amends D-1, does not replace it)
- **P3:** Gemma 4 E4B as the brain that both **hears** (native audio and transcript) and **sees**. GLaDOS measured ~4.1 GB with vision. This removes Whisper from the GPU.
- **Indic-Mio 0.6B** as the Tamil/Tanglish/EN voice (~0.5 GB est.) instead of a 3B LLM-TTS.
- **Why:** together they may fit "sees + native Tamil voice" in ~5.2 GB without shrinking the brain.
- **Decided by:** G2 (E4B Tamil ASR) and G3 (Indic-Mio quality).
- **Evidence:** `docs/research/2026-11-reference-repos.md` §1, §5, §8.

### D-9 · 2026-11-10 · accepted · third-party repos live in a gitignored `reference/`
- **What:** read-only shallow clones for study. Only `reference/README.md` is tracked, and the folder is excluded from Docker build context.
- **Why:** Lebi asked to study prior art in-repo. Third-party code must not enter our history or images, and several repos have no licence file.

### D-10 · 2026-11-10 · accepted · old plan docs move to `docs/archive/`, not deleted
- **What:** `tamil_support_plan.md`, `emotion-aware-conversation.md`, `implementation_plan.md` and `human-like-memory-architecture-plan.md` are implemented or superseded. They were moved with `git mv` so history follows them.
- **Why:** keeps `docs/` focused on the running system and v4 without losing the reasoning.

---
## Master plan decisions (2026-11-11). Detail in `docs/v4/plan.md`

**From Lebi (asked 2026-11-10), all accepted:**
- **D-11 Voice:** one Indian female voice for EN, TA and Tanglish (a cloned timbre, so she has one identity).
- **D-12 Initiative:** balanced. She greets, follows up on remembered things and speaks up on strong cues, at most 1 unprompted line per 15 min, never while he talks. "Be quiet" mutes her.
- **D-13 Eyes:** camera only in v4.0. Screen awareness moves to v4.1.
- **D-14 UI:** the abstract "Marginalia" voice line, no avatar.
- **D-15 Distribution:** personal use only. Gated or Indic-licence weights are OK, but are never baked into public images.
- **D-16 Scope:** pure companion, no tools in v4.0.
- **D-17 Session:** open the app, press begin, then hands-free while the tab is open.
- **D-18 GPU:** Medusa owns the GPU. Budget ≤ 5.6 GB, hard cap 5.9 GB, and `make preflight` checks for foreign GPU processes.
- **D-19 Language:** mirror the user (EN/TA/mix), with a UI pin.
- **D-20 Memory:** keep everything, indefinitely, and make it editable: facts, episodes, routines, mood notes. Never pixels or audio. Unconfirmed facts decay out of retrieval.
- **D-21 Thinking:** spoken ack ≤ 0.8 s, answer ≤ 5 s, with a reasoning budget.
- **D-22 Eval data:** voice from `~/Projects/voice-auth` (41 clips, ~56 min, labelled en/ta/mixed, no transcripts). Images from open datasets (COCO, FER-2013, HMDB51).

**Technical, all accepted:**
- **D-23** Gemma 4 E4B (`ggml-org/gemma-4-E4B-it-GGUF` Q4_0 + mmproj Q8_0) is the single brain that hears (`input_audio`) and sees. Clips are capped at 28 s, and the turn is force-ended at the cap.
- **D-24** llama.cpp runs `--parallel 2`. Slot 0 is conversation only and slot 1 is utility. The `InferenceScheduler` uses priority classes and preemption.
- **D-25** Parallel hear: the slot-0 reply comes from audio while slot 1 transcribes. The transcript replaces the audio in history. `transcript_first` is the fallback mode, and G7 picks the default.
- **D-26** Self-routing: the brain's first tag `[think]` or `[look]` triggers at most one re-issue on the cached prefix. There is no separate classifier.
- **D-27** `[mood:x]` tags map to Indic-Mio emotions. Medusa keeps her own PAD mood state.
- **D-28** Cache-stable prompt: persona → profile (frozen per session) → history → `<now>` → user turn.
- **D-29** Perception has two lanes: MediaPipe in a browser worker sends 4 Hz percepts, and E4B glances run on keyframes with a motion-adaptive cadence. Camera alone never triggers speech.
- **D-30** The initiative engine follows the GLaDOS Autonomy design: slots, a uniform-JSON reviewer, deferral, a 15-min cooldown, back-off and a ledger.
- **D-31** Memory: SQLite is the source of truth, with sqlite-vec (EmbeddingGemma-300M) and FTS5 trigram, plus Neo4j as a rebuildable projection via an outbox. Retrieval uses RRF fusion and decay.
- **D-32** A numbered, forward-only SQL migration runner with a backup. The migration PR needs Lebi's approval.
- **D-33** Protocol v4: Pydantic is the source of truth, with generated Zod and a contract test. Binary frames are tagged (0x01/0x02/0x03). Version mismatch closes with 4400.
- **D-34** Single user: a new tab takes over (close 4409).
- **D-35** Half-duplex echo guard in v4.0. AEC (WebRTC APM, browser-stamped clocks) comes in P9, and barge-in is enabled only if G8 passes.
- **D-36** Per-session `TaskGroup`, plus a global scheduler, EventWriter and MemoryWorker. Blocking work runs in executors.
- **D-37** Observability: per-turn traces, per-component health, Prometheus metrics, and the dev HUD.
- **D-38** Only `llm` and `tts` use the GPU. `backend` becomes CPU-only `python:3.12-slim`. Start order is llm → tts (VRAM-aware bf16/int8/unavailable) → backend. Neo4j runs by default with a 1G heap.
- **D-39** Noto Serif Tamil and Noto Sans Tamil, shadcn/ui restyled, and MediaPipe in a Web Worker.
- **D-40** Deferred to v4.1: screen, tools/MCP, speaker verification (voice-auth ECAPA), wake word, desktop wrapper.

**Pre-decided fallbacks:**
- G1/G2 fail → Profile B (Qwen3.5-4B + Whisper turbo + IndicConformer CPU).
- G3 fail → Svara → Indic-Speak → Kokoro + Piper.
- G4 fail → Qwen3-Embedding-0.6B.
- G5 fail → own Smart Turn fine-tune.
- G6 fail → keep wav2vec2.
- G8 fail → half-duplex.

**Resolves:**
- D-1 → Profile A, pending G0 confirmation.
- D-2 → D-11.
- D-3 → D-15.
- D-4: WebSocket is kept, and AEC comes in P9.
- D-5: keep our pipeline.
