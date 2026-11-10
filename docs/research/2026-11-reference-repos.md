# Reference Repos: what we learned by reading the code

**Date:** 2026-11-10 · **Repos:** `reference/` (index: [`reference/README.md`](../../reference/README.md)) · **Method:** read READMEs, docs and key source files. Nothing from the clones was executed.

This complements [similar-projects](2026-11-similar-projects.md), which was based on web search alone. Reading the code changed several conclusions. They are marked **⟳** and folded back into the v4 docs.

## 1. GLaDOS is the closest blueprint ⟳

`dnhkng_GLaDOS` is no longer the "console voice assistant" the web summary described. As of Oct 2026 it is a companion with **independent minds** (Emotion, Memory, Vision, Health, Research) that publish to **shared slots**, plus an **Autonomy Core** that decides when something deserves speech. That is our v4 design, built and partly measured.

**What they measured** (`docs/gemma4.md`; RTX 3080 10 GB, llama.cpp `687e7789`, 4k ctx, one slot; their own smoke test, not an accuracy benchmark):
- **Gemma 4 E4B Q4_0 + Q8_0 mmproj: ~4.1 GB GPU allocation.** This is the first real number for our "brain" line in architecture §4, and it is better than our 3.7 GB-plus-overhead estimate for the 4B class on a 6 GB card.
- E4B **direct-audio** transcription 0.23–0.29 s vs Parakeet 0.30 s warm. Image description 0.33 s. Two `[emotion:…]` directions in one reply 0.30 s.
- Transcribe-first then reply: 0.65 s median first sentence, vs 0.98 s when deferred. **Keep the transcript in the path** (history and memory need it).
- Audio limit is 30 s per clip. Longer turns are discarded, never silently truncated.

**Design patterns to borrow:**

| Pattern | Where | Our mapping |
|---|---|---|
| Native audio + optional transcript from the same model | `docs/gemma4.md`, `configs/*` | A **profile that drops Whisper from the GPU**: Gemma 4 E4B hears *and* transcribes. This is a new option for D-1, because it frees ~1.3 GB without moving STT to the CPU. Tamil quality is unknown, so it must pass gate G2. |
| Vision mind with **motion-adaptive cadence (2–5 s)**, timestamped "scene + changes since last image", and a dedicated `expressions` field (gaze, posture first; "unclear" when the face is small or obscured) | `docs/vision.md`, `src/glados/vision/` | Our glance (architecture §3.2) should output `scene`, `changes` and `expressions`, and must say "unclear" rather than guess feelings. Camera updates **never trigger speech by themselves**. |
| Slots with `importance`, `confidence`, `revision`, `attention_key` and an **Autonomy reviewer** returning `{"action":"null"}` / `{"action":"prompt",…}` JSON; deferral during any user activity plus a 2 s pause; cooldown 20 s; silent back-off 40→80→120 s; a delivered-event ledger so the same condition is announced once | `docs/autonomy.md`, `src/glados/autonomy/` | Our **initiative engine** (architecture §5.4) should adopt this exact shape. The uniform-object JSON trick (avoid literal `null` vs object) is a concrete E4B-specific fix. |
| Emotion Core keeping **PAD** (pleasure/arousal/dominance) state for the *assistant* | `src/glados/autonomy/emotion_state.py` | Medusa gets her own mood that drifts with the conversation, which drives TTS style. This is distinct from detecting the *user's* emotion. |
| Inspectable minds and context slots in the web console | `docs/webapp.md` | Our dev HUD (ui-redesign §2.5) plus a "what Medusa is thinking about" panel. |

Licence: MIT, so patterns and code can be reused with attribution.

## 2. Echo cancellation has a working reference implementation ⟳

`huggingface_speech-to-speech/src/speech_to_speech/api/openai_realtime/echo_canceller.py`:
- Uses **`pywebrtc_audio.AudioProcessor(echo_cancellation=True)`** (WebRTC APM) in 10 ms frames.
- Every speaker chunk is queued with the **playback time of its first sample**, and each mic frame is processed with its **capture time on the same clock**. References are released when playback time reaches capture time.
- On a native failure it logs once and falls back to raw mic. Rates must match (8–48 kHz).
- Exposed as `--echo-cancellation` "so the assistant does not hear itself and you can still interrupt on speakers".

**For us** (architecture §3.4): this is the server-side AEC path. Our wrinkle is that the playback clock lives in the browser. The client must stamp each mic chunk and each scheduled TTS chunk with `AudioContext.currentTime`-based times on one clock (both contexts can be derived from `performance.now()`). The server can then align them. If that proves fragile, run the same APM **in the browser** (WASM) where both clocks are local. Licence: Apache-2.0.

Their default stack is also a useful baseline: **Silero → Parakeet TDT → Qwen3.5-4B → Qwen3-TTS**, behind the **OpenAI Realtime** protocol over WS/WebRTC. It runs as the backend for Reachy Mini robots.

## 3. Turn-taking: Smart Turn has no Tamil ⟳

`pipecat-ai_smart-turn/README.md`: v3.2 supports **23 languages including Hindi, Bengali and Marathi, but not Tamil**. It ships an 8 MB int8 CPU / 32 MB fp32 GPU build, BSD-2, with open datasets and training script.
- The base model's prosody cues may transfer partially to Tamil, but **the community `smart-turn-tamil` fine-tune is the real candidate**. Failing that, train with our own Tamil/Tanglish turn data using their open training script.
- Gate G5 must test all three: base, the Tamil fine-tune, and our own fine-tune.
- `openlive` and Pipecat both run it **only during silence after Silero VAD**, which is the same plan as ours.

## 4. Perception contract from airi

`moeru-ai_airi/packages/model-driver-mediapipe`:
- A small, clean contract: `camera frame → @mediapipe/tasks-vision → PerceptionState → overlay`.
- Per-job enable flags and **per-job Hz** (`pose`, `hands`, `face`).
- `quality: { fps, latencyMs, droppedFrames }`, a busy check and a **dropped-frame policy** in `engine.ts`.

Use it as the template for our browser `usePerception` worker. Add our derived features (blendshape affect, attention, slouch) on top, and send `quality` with each percept so the server knows how much to trust it. Licence: MIT.

Also from airi:
- `memory-pgvector` (vector memory; we use sqlite-vec for the same role).
- `pipelines-audio` (one shared mic source fanned out to recorder, STT and detectors).
- **`vitest-plugin-fakemic`**: a fake-microphone runtime for tests, an idea for our frontend e2e (Playwright with a fake media stream).

## 5. TTS: two Indic engines we didn't have ⟳

- **Indic-Mio** (`SPRINGLab/Indic-Mio`, served in `iNavLabsResearch_tts_pretrained_inference`):
  - **Qwen3-0.6B + MioCodec (25 Hz)**, streaming, **23 languages**, with **emotion control** (`happy/sad/angry/…`), `*word*` stress, and zero-shot voice cloning from a reference clip (no named voices).
  - At 0.6B it is a **much better VRAM fit** than the 3B Indic-Speak/Svara (~0.5 GB at Q4 [est]). It could resolve D-1 without shrinking the brain.
  - Add it to gate G3. Their server reports first-chunk latency and RTF per request, which is directly reusable as a measurement method.
  - Licence: model card to check, and the server repo has no licence file.
- **Maya3 / maya2-native** (MayaResearch): streaming Indic + English TTS **including Tamil**, 20 voices, 3–10 s cloning, a bundled **Indic text normaliser** (numbers, dates, currency, ALL-CAPS). It needs **≥ 8 GB GPU** and torch 2.8/cu128, so it does **not fit** our 6 GB budget. The **text normaliser** is worth studying for our TTS front-end (Apache-2.0 code).

The same iNavLabs server also hosts **Veena** (maya-research, Llama-3B + SNAC) and **Human-1** (JoshTalks, a Moshi-based Hindi full-duplex model). Human-1 is the first open Indic full-duplex speech model we've seen. It is Hindi-only and too big for us, but worth watching.

## 6. STT options seen in the wild
- **openlive** offers Whisper on **WebGPU in the browser**, or native **Nemotron (streaming, transcribes while you talk)**, Parakeet, Moonshine and Canary. Running streaming STT in the browser on WebGPU is a further VRAM-saving idea (the browser shares the same GPU, so it isn't free).
- **indic-voice-agent** (Hindi/Kannada/English, code-mixed):
  - restricts Whisper LID to `hi/kn/en` and adds a **Unicode script check**
  - normalises (NFC, strips ZWNJ/ZWJ, Indic danda punctuation) before WER/CER
  - starts TTS on the **first sentence or clause**

  Copy its `eval/stt_bench.py` approach (jiwer plus normalisation plus LID accuracy) for gate G2, with Tamil's U+0B80–U+0BFF block in place of Kannada.
- **Local-AI-Companion** `docs/lil-35-voice-benchmark.md`: benchmark ASR **through the real mic path** (VAD segmentation, natural pauses, cut-offs), not only clean clips. Report `VAD end → transcript ready`. Add this as a live variant of G2/G5.

## 7. Friend behaviours
- **Vocalis** `backend/routes/websocket.py`: **tiered silence follow-ups** (tier 0–2, "casual follow-up" first, escalating) when the user goes quiet after a turn. This maps to our initiative engine's "silence after a sad turn" trigger, with GLaDOS-style cooldowns.
- **Open-LLM-VTuber** v1 is in maintenance while v2 is a full rewrite, and its **long-term memory is offline** ("temporarily removed, coming back"). Don't build on it. Its avatar and desktop-pet UX is the takeaway.

## 8. What changes in our plan
1. **D-1 gains two options** (architecture §4):
   - **Gemma 4 E4B native audio**, which removes Whisper from the GPU (~4.1 GB measured by GLaDOS on a different card).
   - **Indic-Mio 0.6B** TTS in place of a 3B LLM-TTS.

   Together they could make "seeing brain + native Tamil voice" fit in 6 GB.
2. **G2** adds E4B native-audio transcription (Tamil and Tanglish). **G3** adds Indic-Mio. **G5** adds the Tamil Smart Turn fine-tune as the primary candidate.
3. **The initiative engine** follows GLaDOS's Autonomy design: slots, a JSON reviewer, deferral, cooldown, back-off, ledger.
4. **AEC** follows the HF `EchoCanceller` design (WebRTC APM plus timestamped reference).
5. **The perception worker** follows airi's `PerceptionState` contract.

## Re-clone
```bash
# from repo root; shallow, no LFS, hooks disabled
export GIT_LFS_SKIP_SMUDGE=1 GIT_TERMINAL_PROMPT=0
for r in dnhkng/GLaDOS huggingface/speech-to-speech katipally/openlive moeru-ai/airi \
         pipecat-ai/smart-turn pipecat-ai/pipecat iNavLabsResearch/tts_pretrained_inference \
         MayaResearch/maya2-native mathuryashash/indic-voice-agent Lex-au/Vocalis \
         KoljaB/RealtimeVoiceChat kyutai-labs/unmute Open-LLM-VTuber/Open-LLM-VTuber \
         LiiLk/Local-AI-Companion lhl/voicechat2 TEN-framework/ten-framework \
         AI4Bharat/IndicConformerASR Satyamku88/Vision_AI_bot; do
  git clone --depth 1 --single-branch -c core.hooksPath=/dev/null \
    "https://github.com/$r.git" "reference/${r//\//_}"
done
```
