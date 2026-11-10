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
