# Medusa v4: Checklist

Executable companion to [plan.md](plan.md). Section numbers (§) refer to plan.md.

Each phase follows the same workflow:
- Every task becomes an issue, then a branch, then a small PR that is independently green, merged with `gh pr merge --merge`.
- Tick a box only when its PR is merged **and** verified.
- **Gate** boxes need a report in `docs/benchmarks/`.
- 👤 = needs Lebi.

## Decisions sign-off
- [x] D-11…D-22 answered by Lebi (2026-11-10)
- [x] D-23…D-40 technical decisions recorded in `DECISIONS.md`
- [ ] 👤 D-1 final VRAM profile: confirmed by G0 (expected Profile A)
- [ ] 👤 Medusa voice reference clip chosen (Indic-Mio sample or own clip) at G3

## 👤 Lebi tasks
- [ ] Correct the ~15-min stratified transcript subset in the review tool (~1–1.5 h) (P1, blocker B-2)
- [ ] Spot-check 100 turn-end samples (~15 min) (P1)
- [ ] Self-label 50 clips for emotion (~15 min) (P7, G6)
- [ ] Blind A/B listening sheet, 40 sentences (~20 min) (P3, G3)
- [ ] Accept gated licences on Hugging Face if a fallback model needs it (Indic-Speak, Indic-Transcribe)
- [ ] Approve the memory migration PR (P6, CLAUDE.md rule)
- [ ] Final "feels like a friend" sign-off (P9)

---

## P0: Hygiene fixes (no new models)
- [ ] Unicode-aware tokeniser in `retriever.py`, `extractor.py`, `neo4j_store.py`, with a **failing-first** test using a Tamil memory (audit §3.1)
- [ ] Remove the duplicate summary injection (`retriever.py:97` vs `_load_prompt`) + test (audit §3.3)
- [ ] Prompt order: emotion/memory fragments after history (audit §3.2). TTFT before/after recorded in the PR
- [ ] `EventWriter`: batched writes off the token loop (audit §3.4) + test that the deltas are still recorded
- [ ] Producer/consumer TTS (`SentenceQueue`), so LLM and TTS overlap (audit §3.5) + test
- [ ] TTS routing by the reply text's script; greeting language from the session (audit §3.6) + tests
- [ ] DoD: `make test` green, `make lint` green, STATUS/FIXES entries

## P1: Eval kit + G0 baseline (§20.1)
- [ ] `eval/` gitignored (done) and the `scripts/bench/` scaffold
- [ ] Import the 41 voice WAVs from `~/Projects/voice-auth` using the **duration-match label rule** → `eval/audio/manifest.csv`
- [ ] Silero segmentation → `utts.csv` (3–15 s)
- [ ] Draft transcripts: Whisper large-v3, IndicConformer-600M, E4B (throwaway bench container)
- [ ] `scripts/bench/review_ui.py` (local review page: play, edit, ok/skip)
- [ ] 👤 Corrected references → `refs.csv` (or the silver fallback, flagged)
- [ ] Turn-end set (100, balanced EN/TA) + 👤 spot-check
- [ ] Vision set: COCO val2017 (40), FER-2013 test (40), HMDB51 frames (30) → `eval/vision/labels.csv`
- [ ] Dialog set: 40 scripts + 10 recall probes (`eval/dialog/*.yaml`) + rubric + judge runner
- [ ] Bench harness: jiwer + NFC + ZWJ/ZWNJ/danda strip + Tamil script check + LID accuracy
- [ ] `make preflight` (foreign GPU processes, free VRAM ≥ 5.7 GB, `FORCE=1`)
- [ ] **Gate G0 (baseline):** v3 stack + each candidate alone (E4B, Indic-Mio bf16/int8, Qwen3.5-4B) → report

## P2: Brain (§5.1, §6.3–6.5, §7, §13)
- [ ] Pin a llama.cpp `server-cuda` build verified with Gemma 4 audio + mmproj
- [ ] `make models`: E4B Q4_0 + mmproj Q8_0 (host-side, no host Python)
- [ ] `llm` command flags exactly as §5.1; measure VRAM (G0 update)
- [ ] `BrainClient`: `id_slot` pinning, streaming, `Deadline`, `CircuitBreaker`, `input_audio` WAV parts
- [ ] `InferenceScheduler`: slot 0 single-flight; slot 1 priority queue; preemption by user turn + tests
- [ ] `HearStage` interface: `NativeAudioHear` (E4B) and `WhisperIndicHear` (Profile B) + contract tests
- [ ] Hear modes `parallel` / `transcript_first` (config) + transcript-replaces-audio history rule + tests
- [ ] Control-tag parser (`[think]`, `[look]`, `[mood:x]`, first-8-tokens rule, single re-issue) + tests
- [ ] Persona v2 (`medusa.yaml`): language, control and perception-honesty rules
- [ ] `<now>` block builder (≤ 350 tokens) + cache-stable layout (§7.1) + TTFT-flat-over-turns test
- [ ] Protocol v4 skeleton: Pydantic `protocol.py`, `hello` + version check (4400), tagged binary frames, error codes, takeover (4409), `make protocol` codegen + contract test
- [ ] v3 UI compatibility shim (until P8)
- [ ] Canned lines registry (text) + `lag`/`down` paths (E10/E11)
- [ ] Failure tests E8–E13, E28 against a fake llama.cpp
- [ ] **Gate G1** (brain: dialog rubric vs Qwen3.5-4B, vision, glance timing)
- [ ] **Gate G2** (E4B transcription EN/TA/mix)
- [ ] Decision: Profile A confirmed, **or** Profile B adopted (DECISIONS entry)

## P3: Voice (§9)
- [ ] `tts_service/` FastAPI app: Indic-Mio + MioCodec, streaming `/synthesize`, `/health`, `/voices`
- [ ] VRAM-aware load (bf16 → int8 → unavailable) at start + test with mocked `mem_get_info`
- [ ] 👤 Medusa voice reference → `config/voice/medusa.pt` (global embedding)
- [ ] Mood → emotion mapping (Indic/English tag sets)
- [ ] Clause segmenter (first chunk ≤ 9 words) + per-chunk language by script + Tamil/English number/date normaliser
- [ ] PCM validator (NaN, RMS, duration bounds, first-chunk timeout) + tests
- [ ] Breaker + CPU fallback (Kokoro/Piper `TTSRouter`) + `voice_degraded` event
- [ ] Canned lines pre-synthesised at boot (and regenerated when TTS recovers)
- [ ] Compose: `tts` service, GPU reservation, depends on `llm` healthy; `backend` becomes CPU-only `python:3.12-slim`
- [ ] Failure tests E15–E16; kill-tts mid-session test (S7)
- [ ] **Gate G3** (TTFA, RTF, 👤 blind A/B, Tanglish continuity)
- [ ] **Gate G0** update with Profile A total VRAM ≤ 5.6 GB

## P4: Turn-taking (§6.3)
- [ ] `turn_detect.py`: Silero + Smart Turn v3.2 (EN) + smart-turn-tamil (TA/mix), routed by the last user language
- [ ] Caps: 1.5 s silence, 28 s utterance (forced end, E7)
- [ ] Fallback `TURN_DETECTOR=silence` on load failure (E6) + test
- [ ] Echo guard behaviour unchanged (`tests/test_echo_guard.py` green)
- [ ] **Gate G5** (≤ 5% premature, median ≤ 300 ms); thresholds written to `.env.example`

## P5: Eyes (§10, §6.6)
- [ ] `@mediapipe/tasks-vision` pinned; `.task` models served by nginx (offline)
- [ ] Perception Web Worker (OffscreenCanvas): face 15 fps, pose 5 fps, dropped-frame policy, crash restart (E24)
- [ ] `percept` message (§10.1) at 4 Hz; camera on/off (`camera{on}`), stops the track when off
- [ ] `PerceptState`: windows, derived signals (§10.2), debounced events, `perception_minutes`
- [ ] Glance policy + SceneNote (JSON schema) + `scene` event; keyframe `0x03` on `request_keyframe`
- [ ] `[look]` route end-to-end (E14)
- [ ] Privacy test: no JPEG/RIFF bytes in DB, logs or volumes after a session (S8)
- [ ] **Gate G9** (worker fps, main thread budget); vision part of G1 re-run end-to-end

## P6: Memory v4 (§11)
- [ ] Migration runner + backup + `001_baseline.sql` + `002_memory_v4.sql` + tests (v3 fixture → v4, idempotent)
- [ ] 👤 Migration PR approved by Lebi
- [ ] `MemoryWorker` (idle ≥ 20 s / session end), `memory_jobs` queue + dead-letter (E19)
- [ ] LLM extractor (JSON schema §7.6) + supersede/confirm/negate rules + tests (full coverage)
- [ ] EmbeddingGemma-300M embedder + sqlite-vec + FTS5 trigram (triggers) + tests with Tamil text
- [ ] Hybrid retrieval: vec + FTS5 + Neo4j 1-hop → RRF → decay → 180-token budget (deadline 150 ms) + tests
- [ ] Neo4j projection via `graph_outbox` (idempotent MERGE) + `make graph-rebuild` + down-path test (E21)
- [ ] Profile job (≤ 300 tokens, versioned) + frozen-per-session prefix
- [ ] Notebook REST (§14): facts CRUD, episodes, patterns, profile, forget (last_turn/all), export + tests
- [ ] Backfill job: `memory_artifacts` → facts, `memories` → episodes
- [ ] **Gate G4** (cross-lingual recall@5 ≥ 0.85); S4 recall probes ≥ 8/10

## P7: Friend behaviours (§12, §6.4)
- [ ] Initiative slots (arrival, follow-up, wellbeing, silence tiers) + reviewer (JSON §7.7) + ledger + cooldown 15 min + back-off + quiet mode
- [ ] Tests: never fires during speech or within 2 s; ≤ 1 unprompted line / 15 min; same `attention_key` is never repeated; arrival exempt once
- [ ] `[think]` route: ack ≤ 0.8 s, thinking budget 384, deadline 4.5 s → short answer (E12) + tests
- [ ] PAD mood state + default TTS emotion mapping + tests
- [ ] emotion2vec+ base (CPU) replacing wav2vec2 SER (behind a flag until G6)
- [ ] **Gate G6** (👤 50 self-labelled clips)

## P8: UI v4 "Marginalia" (ui-redesign.md + §13)
- [ ] Generated Zod protocol client (`protocol.gen.ts`) + `useConversation` v4 (hello, tagged frames, stale-audio drop by `turn_id`)
- [ ] Playback stamps (`playback` message) for the echo-guard tail
- [ ] Arrival screen (talk / talk + see me, one-line privacy note)
- [ ] Voice line canvas (mic + TTS envelope; still dot travelling while thinking)
- [ ] Synced spoken phrase (word lighting from chunk timing); transcript drawer
- [ ] Margin notes: "what I see" (with "why" + dismiss) and "what I remembered" (opens the Notebook)
- [ ] Status rail: camera dot + hard toggle, language chip (auto/en/ta), quiet, type input
- [ ] Notebook drawer (about you, recently, patterns, forgotten/undo, forget everything)
- [ ] Dev HUD (`?`): per-turn trace, route, VRAM, percept rate, breaker states
- [ ] Noto Serif Tamil / Noto Sans Tamil, `lang="ta"` spans, line-height
- [ ] shadcn/ui base restyled to the room tokens; `prefers-reduced-motion`; mobile layout
- [ ] vitest for hooks; Playwright e2e with fake media (Chrome flags + eval WAV)

## P9: Polish + release
- [ ] AEC behind `AEC_ENABLED`: browser clock stamps on `0x01`/`playback`, WebRTC APM (`pywebrtc_audio`) per the HF `EchoCanceller` design
- [ ] **Gate G8** → `ALLOW_BARGE_IN=true` only if passed (else documented as half-duplex)
- [ ] Latency tuning (segmentation, `-c`, quant ladder, hear mode)
- [ ] Soak script (30 min) with VRAM/RAM sampling
- [ ] **Gate G7** (S1–S8)
- [ ] Docs synced: architecture.md (v4 replaces v3), API.md, docker.md, README, HANDOVER
- [ ] VERSIONS: backend 4.0.0, frontend 4.0.0, protocol 4; STATUS entry; tag `v4.0.0`
- [ ] 👤 Final sign-off
