# Medusa v4: Roadmap and Benchmark Gates

> **Superseded by [plan.md](plan.md) §20–21 and [checklist.md](checklist.md) (2026-11-11).** The phases are renumbered P0–P9, and the gate thresholds were finalised there.

**Status:** PROPOSAL · **Date:** 2026-11-10 · Architecture: [architecture.md](architecture.md) · Models: [landscape](../research/2026-11-model-landscape.md)

The rule: **no model enters the main pipeline until it passes its gate on this laptop with Lebi's data.** Each gate yields a short report in `docs/benchmarks/` (numbers plus a decision) and an entry in `DECISIONS.md`. Heavy runs go one at a time, under `nice` (per CLAUDE.md ops habits).

## 0. Eval kit (build first, used by every gate)

| Asset | Contents | Notes |
|---|---|---|
| `eval/audio/` | ~30 min of Lebi's recordings: 10 min EN, 10 min TA, 10 min Tanglish. Read sentences plus free talk, quiet room plus fan/street noise, laptop mic | Hand-corrected reference transcripts. Tanglish references use Tamil script for Tamil words and Latin for English words. |
| `eval/turns/` | 100 turn-end cases: complete vs "um… and then" mid-thought pauses, EN/TA | For Smart Turn. |
| `eval/vision/` | 60 webcam stills of Lebi: desk, coding, phone, eating, tired, laughing, away | Labels for activity and objects. Local only, **gitignored**. |
| `eval/dialog/` | 40 short multi-turn scripts (EN/TA/Tanglish) with expected "friend-like" qualities, plus 10 memory-recall probes | Scored with a rubric: naturalness, language match, brevity, no hallucinated history. |
| `eval/tts/` | 40 reply sentences (EN, TA, Tanglish, numbers, names) | Blind A/B listening sheet. |
| `scripts/bench_*.py` | Runners that print a markdown table plus JSON | Restore generated reports instead of committing noise. |

All of `eval/` with personal data stays **out of git** (add it to `.gitignore`).

## 1. Gates

| Gate | Question | Candidates | Pass criteria |
|---|---|---|---|
| **G0 VRAM/latency baseline** | What do today's stack and each candidate actually cost? | v3 stack; each candidate alone | Measured VRAM (`nvidia-smi` peak), load time, steady-state latency. Replaces the [est] numbers in architecture §4. |
| **G1 Brain** | Which multimodal brain is the friend? | Qwen3.5-4B, Gemma 4 E4B (Q4_K_M / QAT Q4_0); fallbacks Gemma 4 E2B, Qwen3.5-2B | TTFT ≤ 250 ms with a warm prefix; ≥ 25 tok/s; dialog rubric ≥ v3 Qwen3-4B on EN and better on TA/Tanglish; vision: ≥ 80% correct activity/object on `eval/vision`; glance latency ≤ 1.2 s per keyframe. |
| **G2 Ears** | Which STT engine(s)? | Whisper turbo (GPU), Indic-Transcribe Core/Flex (GPU and CPU), IndicConformer 600M int8 (CPU), **Gemma 4 E4B native audio** (no separate STT) | WER EN ≤ 8%; CER TA ≤ 12%; Tanglish code-mix fidelity ≥ 90% (English words kept in Latin, no translation); latency ≤ 300 ms on a 5 s utterance. CPU variant ≤ 400 ms to qualify for profile P2. |
| **G3 Voice** | Which TTS, and can it be one voice? | Indic-Speak, Svara v1 (Q4 GGUF on GPU), **Indic-Mio 0.6B**; Kokoro (EN baseline) | TTFA ≤ 250 ms; RTF ≤ 0.5; blind A/B: preferred over Piper on TA ≥ 80% and not worse than Kokoro on EN (or else D-2 = keep Kokoro for EN); Tanglish read without voice switch or mispronounced English. |
| **G4 Memory retrieval** | Which embedder? | EmbeddingGemma-300M, Qwen3-Embedding-0.6B, bge-m3, ME5-small | Recall@5 ≥ 0.85 on 50 cross-lingual probes (EN query → TA memory and back); CPU embed ≤ 30 ms per sentence. |
| **G5 Turn-taking** | Does Smart Turn beat the 900 ms timeout? | **smart-turn-tamil** (primary: base v3.2 has no Tamil), Smart Turn v3.2, own fine-tune via their open training script, LiveKit multilingual | ≤ 5% premature cut-offs on `eval/turns`; median end-of-turn decision ≤ 300 ms. |
| **G6 Emotion** | Is emotion2vec+ better than v3 SER? | emotion2vec+ base/large vs superb wav2vec2 | Agreement with Lebi's self-labels on 50 clips beats v3 by ≥ 10 pts; CPU ≤ 150 ms. |
| **G7 End-to-end** | Does it feel like a friend, fast? | the integrated v4 profile | Median end-of-speech → first audio ≤ 1.0 s (reflex), p90 ≤ 1.5 s; 30-min session with no OOM, no echo loop, no crash; Lebi's subjective "feels like a friend" score goes up week over week. |

## 2. Phases

Each phase is a set of GitHub issues and PRs (per the issue → PR workflow), small and independently green.

### Phase 0: Hygiene and quick wins (no new models)
These fix audit findings and are worth doing even if v4 never happens.
1. Unicode-aware tokenisation in retriever/extractor/neo4j_store, with a regression test using a Tamil memory (audit §3.1, bug).
2. Remove the duplicate summary injection (audit §3.3, bug).
3. Cache-friendly prompt order: move emotion and memory to the end (audit §3.2). Measure TTFT before and after.
4. Batch event writes off the token loop (audit §3.4).
5. Producer/consumer TTS (audit §3.5).
6. Per-chunk TTS routing by reply script, and greeting language from session history (audit §3.6).
7. `print` → `logger` (audit §3.10).
8. Docs drift: README, docker.md, API.md and conftest still mention five personas.

### Phase 1: Eval kit and gates G0, G5, G2
- Record and label the eval set. Write the bench scripts.
- Integrate Smart Turn behind a flag (`TURN_DETECTOR=smart|silence`).
- Decide on STT (D-1 inputs).

### Phase 2: Eyes (profile P1)
- G1 brain bake-off, then swap `llm` to the multimodal 4B with `--mmproj`.
- Browser perception worker (MediaPipe face and pose) plus the `percept` protocol, replacing the JPEG stream.
- `PerceptState`, events, the `<now>` block, the glance (keyframe on trigger) and router v1 (reflex/look).
- Camera-off-by-default UX and an indicator, shipped with this phase rather than after it.

### Phase 3: Native voice (profile P2 / P2-alt, after D-1)
- G3 TTS bake-off. Add a `tts-llm` service plus a SNAC/Vocos decoder.
- Single-voice routing, Tamil-script normalisation and transliteration before TTS.
- emotion2vec+ (G6) and drop `torch` from the backend if possible.

### Phase 4: Knows me (memory v4)
- G4 embedder. Add sqlite-vec and the facts/episodes/patterns tables (migration: **needs Lebi's approval**).
- LLM extractor (JSON schema) in idle time, the profile generator and the Notebook REST API.
- Perception-derived episodes ("was up till 2am coding").

### Phase 5: Friend behaviours and UI v4
- Initiative engine with rate limits, quiet mode, and the think route with a spoken ack.
- The full "Marginalia" UI: voice line, synced phrase, margin notes, Notebook, dev HUD.
- Stretch: server-side AEC with a reference signal (or a WebRTC transport, per D-4), enabling barge-in on speakers.

### Phase 6: Polish and latency
- Speculative STT on probable turn end, first-clause segmentation tuning, KV/quant tuning.
- G7 end-to-end. Release `v4.0.0`.

## 3. Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Brain + LLM-TTS don't fit 6 GB together | **High** | Profiles P2/P2-alt; CPU STT; Kokoro fallback; D-1 decided on measured numbers |
| Tanglish STT mangles code-mix (translation or script flips) | High | G2 code-mix metric; LoRA fine-tune on own data (2026 papers show it works) as a Phase 6 option |
| Indic-Speak/Svara have no stable llama.cpp/SNAC streaming path | Medium | Svara already has GGUF builds and a WS streaming server; Orpheus-style servers are a known pattern |
| MediaPipe plus the UI thread jank on an iGPU/dGPU browser | Medium | Web Worker plus OffscreenCanvas; percept at 4 Hz; lite models |
| RAM pressure (15 GB) | Medium | Neo4j off; one CPU model per thread pool; measure at G0 |
| Licence (Indic Open Model License) limits sharing images | Low (personal use) | D-3; don't push weights to Docker Hub images |
| Perception feels creepy | Medium | Camera off by default, visible notes with "why", dismiss/correct, never store pixels |
