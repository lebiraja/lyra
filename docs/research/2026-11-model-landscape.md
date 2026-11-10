# Model Landscape for an Edge Companion (Nov 2026)

**Date:** 2026-11-10 · **Target box:** RTX 4050 Laptop 6 GB, i7-13650HX, 15 GB RAM · **Languages:** English, Tamil, Tanglish

This is a shortlist per pipeline stage, not a leaderboard. Most numbers come from model cards, vendor posts or community cards, and **almost none were measured on our hardware or on Tamil conversational speech**. Every pick below is therefore a *candidate*, and it is promoted only after the benchmark gates in [`../v4/roadmap.md`](../v4/roadmap.md) pass. Claim quality is tagged:

- **[card]** official model card or paper
- **[3p]** third-party or community card
- **[vendor]** marketing
- **[est]** our own estimate

VRAM figures marked [est] use ~0.6 byte/param for Q4_K_M GGUF, plus the projector, plus the KV cache. They must be measured.

---

## 1. Brain: multimodal LLM (text + image/video in)

The current brain (Qwen3-4B-Instruct-2507) is text-only. A **single multimodal model** that serves as both the eyes and the brain avoids a second resident model on a 6 GB card. That is the main reason to switch.

| Model | Size | Modalities in | Why it's interesting | Concerns |
|---|---|---|---|---|
| **Qwen3.5-4B** | 4B dense | text, image, video | Released 2026-03-02, Apache-2.0, natively multimodal, 262K ctx [3p]. MMLU-Pro ~79 vs Gemma 4 E4B ~69 [3p]. IndicParam found the Qwen family the strongest small models on low-resource Indic languages (pre-3.5 data) [card]. Has a thinking toggle. | Uses ~512 tokens per image vs Gemma's 256, and one CPU test found image prefill ~9× slower than Gemma E4B [3p]. llama.cpp vision support for the small sizes is less documented than for 35B-A3B [3p]. |
| **Gemma 4 E4B** | ~4.5B effective; **~4.1 GB GPU measured** (Q4_0 + Q8_0 mmproj, 4k ctx, RTX 3080) by GLaDOS [3p] | text, image, **audio** (ASR, ≤30 s clips) | Released 2026-04-02, Apache-2.0 [3p]. Official ggml-org GGUFs plus Google QAT Q4_0 GGUFs [card]. Fast image prefill (256 tokens/image) [3p]. 140+ languages claimed [card]. | Weaker on general benchmarks than Qwen3.5-4B [3p]. No published Tamil numbers for text or audio. Needs the correct chat template or the output is garbled [3p]. |
| **Gemma 4 E2B** | ~2.3B effective | text, image, audio | Same family at half the footprint. This is the *fallback brain* if the voice stack needs the VRAM. | Reasoning and Tamil fluency probably too weak for a "friend". Test it. |
| **Qwen3.5-2B** | 2B | text, image, video | Small fallback with the same template and tooling as the 4B. | Same concern as E2B. |
| Qwen3-VL-4B | 4B | text, image, video | Strong video understanding [3p]. | Superseded by Qwen3.5-4B for our purposes. |
| LFM3-VL-2B (Liquid) | 1.9B | text, image, video @2 fps | Edge-oriented [3p]. | New, thinly tested. Licence to check. |
| SmolVLM2 (256M–2.2B) | tiny | image, video | <1 GB VRAM at 256M [3p]. Used by Vocalis as a *captioner* for a text-only LLM. | Too weak as the brain, but viable as a CPU captioner. |
| Qwen2.5-Omni-3B / Qwen3-Omni-30B-A3B | — | audio+video in, speech out | True end-to-end speech-to-speech. | Omni-3B is under a **non-commercial** research licence. Qwen3-Omni is far too large. No reproducible local S2S setups were reported as of the HN thread [3p]. **Rejected for now.** |

**Recommendation (to verify):** build on **Qwen3.5-4B** as the primary candidate and **Gemma 4 E4B** as the challenger. Run the same Tanglish and vision eval on both (roadmap gate G1). If the voice stack needs GPU memory, step down to **Gemma 4 E2B / Qwen3.5-2B** and measure how much "friend quality" is lost.

**"If it needs to think, it can think":** both families support a reasoning mode. The design keeps thinking **off by default** for latency and turns it on per turn through a router (see architecture §5.3).

## 2. Ears: STT / ASR

Tanglish is the hard case: Tamil grammar with English nouns and verbs, sometimes switching mid-word ("meeting-ku late aayiduchu").

| Model | Size / runtime | Tamil evidence | Notes |
|---|---|---|---|
| **faster-whisper large-v3-turbo** (current) | 809M, CTranslate2 int8 GPU (~1.3 GB) | No turbo-specific Tamil WER found. large-v3 on FLEURS-Tamil is reported at **26–49% WER** depending on normalisation [3p] | Good English. Multilingual LID. Tends to *translate* or switch script on code-mixed input. Keep it as the English and fallback engine. |
| **Indic-Transcribe Core / Flex** (Bodhan AI + AI4Bharat, Sept 2026) | 1.2B, based on NVIDIA Canary-1B-v2, NeMo | Tamil WER ~19.8 (Core) / 20.9 (Flex), as reported **by a competing model's card** [3p] | 25+ Indian languages plus English. Gated, under the **Indic Open Model License v1.0** (fine for personal use; third-party hosted API needs approval) [3p]. Streaming is unsupported in Core, and the cards conflict on Flex [3p]. |
| **IndicConformer 600M multilingual** (AI4Bharat) | 600M, ONNX, **CPU-capable** via sherpa-onnx int8 | 18.1% [3p, test set unnamed] to 25.5% WER on FLEURS-Tamil [3p] | MIT per the repo, although community copies say CC-BY-4.0, so check [3p]. Offline CTC works in sherpa-onnx. The streaming RNNT export is unresolved [3p]. **Running on the CPU frees ~1.3 GB of VRAM.** AI4Bharat now recommends Indic-Transcribe over it [card]. |
| Whisper LoRA fine-tunes for Tamil-English code-switch | — | 2026 papers (Springer; DravidianLangTech) [card] | A research path: LoRA on our own Tanglish recordings. |
| Gemma 4 E4B audio-in | shares the brain | No Tamil ASR benchmark, English-only eval published [3p] | Interesting because it removes the STT stage and lets the brain *hear* tone, but it is limited to ≤30 s clips and needs a parallel ASR for the transcript. Experiment only. |
| NVIDIA Parakeet TDT | ~0.6B | English-focused | Used by HF `speech-to-speech`. Fast English option. |

**Recommendation (to verify):** a benchmark-driven pick on **Lebi's own voice** (roadmap gate G2): 30 min of EN, TA and Tanglish clips, scored on WER/CER plus code-mix fidelity (keeps English words in Latin script, doesn't translate). Front-runners:
- **Indic-Transcribe Core** for TA and Tanglish.
- **Whisper turbo** for pure EN.
- **IndicConformer on CPU** as the VRAM-saving variant.

## 3. Voice: TTS

What matters for a friend:
1. Natural, warm prosody.
2. **One consistent voice across EN and TA**, so the timbre doesn't switch mid-conversation.
3. Tanglish read as one continuous utterance.
4. Time-to-first-audio under ~250 ms.
5. Fits the remaining VRAM, or runs on the CPU.

| Model | Size / runtime | Languages | Notes |
|---|---|---|---|
| **Kokoro-82M** (current EN) | 82M ONNX, CPU | EN (+ a few others, no Tamil) | Very cheap, good quality. One on-device benchmark measured ~3.7 s first audio in its setup [3p], but our per-sentence use already works. Keep it for English-only replies. |
| **Piper ta_IN-Valluvar** (current TA) | ONNX CPU | TA | Intelligible but flat. Replace it. |
| **Indic-Speak** (Bodhan AI + AI4Bharat, Sept 2026) | 3.36–3.78B Llama-3.2-3B backbone → SNAC 24 kHz tokens → Vocos [card] | **22 Indian languages + English**, 45 voices [vendor] | The card says English words inside an Indic sentence are read in the same voice and accent [card], which suits Tanglish. Claims ~200 ms TTFA [vendor]. AI4Bharat recommends it over Indic Parler-TTS [card]. Indic Open Model License. English is read with an Indian accent, which is arguably *right* for a Tamil friend. **Top candidate for the single-voice goal.** |
| **Svara TTS v1** (kenpath) | 3.3B Llama (Orpheus lineage), SNAC 24 kHz | 19 Indic + Indian English [card], Tamil coverage unconfirmed [3p] | GGUF, OpenVINO INT4, MLX and FP8 builds exist, plus a streaming WS server [3p]. Challenger to Indic-Speak. |
| **Indic-Mio** (SPRINGLab) | **Qwen3-0.6B + MioCodec 25 Hz** | 23 languages incl. Indic [3p: iNavLabs server README] | Streaming, emotion tags, `*word*` stress, zero-shot cloning (no named voices). **~0.5 GB at Q4 [est]**, so it may solve the VRAM squeeze. Licence to check. Found by reading `reference/`, see [reference-repos](2026-11-reference-repos.md) §5. |
| Maya3 / maya2-native | streaming engine | 11 Indic incl. TA + EN, 20 voices, cloning | Needs ≥ 8 GB GPU, so it **does not fit**. Its bundled Indic text normaliser is worth studying. |
| IndicF5 (AI4Bharat) | F5-TTS DiT | 11 Indic incl. TA, voice cloning | Non-streaming, not real-time on CPU [3p]. Ranked **last of seven** in a large Indian-language preference study [card]. **Rejected for realtime.** |
| Indic Parler-TTS | ~0.9B | 22 Indic | Superseded by Indic-Speak (AI4Bharat's own note) [card]. |
| Qwen3-TTS 0.6B / 1.7B | 0.6B ~4–6 GB [3p] | 10 languages (no evidence Tamil is one) | 97 ms first packet on vLLM with CUDA graphs [card]. English-only option if Kokoro feels flat. |
| Chatterbox (Resemble, MIT) | ~0.5B | EN (+ multilingual variant) | Emotion "exaggeration" dial, 5 s cloning [3p]. Slower than Kokoro [3p]. |
| Orpheus 3B | 3B | EN | Expressive tags (laughs, sighs), ~8 GB [3p]. Too big next to the brain. |
| CosyVoice 2/3 | ~0.5B | zh/en/… | ~150 ms streaming [vendor]. No Tamil. |

**LLM-TTS VRAM reality [est]:** a 3B SNAC-token TTS needs ~83+ tokens/s for real-time audio (Orpheus-class), which means **GPU**. At Q4_K_M that is ~2.0–2.4 GB plus a small KV cache. It cannot coexist with a 4B multimodal brain *and* GPU Whisper in 6 GB (see architecture §4 for the VRAM profiles).

**Recommendation (to verify):** gate G3 runs **Indic-Speak vs Svara**: Q4 GGUF on GPU, measure TTFA, RTF and VRAM, and do an A/B listening test on 20 Tanglish sentences. Kokoro stays as the CPU fallback and for pure-English replies if the single voice loses.

## 4. Turn-taking and VAD

| Model | Runtime | Notes |
|---|---|---|
| **Silero VAD v5** (current) | ONNX CPU, ~1 ms/frame | Keep it as the frame gate. |
| **Smart Turn v3.2** (Pipecat/Daily) | ~8 MB int8 ONNX, CPU | Semantic end-of-turn from audio. **Official 23 languages include Hindi/Bengali/Marathi but not Tamil** (repo README, read 2026-11-10), so the Tamil fine-tune is the primary candidate. 12 ms [vendor] to ~95 ms on a t3.medium [card], and ~20 ms with 4 threads [3p]. **A community Tamil fine-tune exists** (`santhosh-005/smart-turn-tamil`) [3p], and so does a Hinglish one. **Strong pick.** |
| LiveKit turn detector (multilingual) | Qwen2.5-0.5B, CPU <500 MB RAM | ~50–160 ms per turn [card]. *Text*-based, so it needs a transcript first. Second choice. |
| TEN VAD / TEN Turn Detection | — | Alternative from the TEN framework. Benchmark only if Smart Turn fails. |

## 5. Perception: face, body, scene

Split it into a **fast lane** (every frame, cheap, in the browser) and a **slow lane** (VLM keyframe, on demand).

| Need | Pick | Where | Notes |
|---|---|---|---|
| Face presence, 52 ARKit blendshapes, head pose (4×4) | **MediaPipe Face Landmarker** (`@mediapipe/tasks-vision`) | Browser, GPU delegate (WebGL) | 478 landmarks. Gaze, blink and yawn are *derived* from blendshapes and landmarks; there is no built-in gaze API [3p]. **Zero server cost.** |
| Posture, slouch, leaning in, away from desk | **MediaPipe Pose Landmarker (lite)** | Browser | Activity cues like "stood up" or "hunched for 2 h". |
| Hands (wave, thumbs-up, holding a phone) | MediaPipe Gesture Recognizer / Hand Landmarker | Browser | Optional, phase 3. |
| Facial emotion | Derive from blendshapes, **or** keep EmotiEffNet-B0 ONNX on face crops | Browser (blendshape rules / small MLP) or server CPU | Blendshapes avoid shipping JPEGs at all. |
| Scene and activity ("coding, phone in hand, coffee, dark room") | **The brain VLM** (Qwen3.5-4B / Gemma 4) on a keyframe | Server GPU | Triggered: on scene change, every ~30–60 s while idle, or when the user refers to something visual. |
| Identity ("is this Lebi?") | Face embedding (e.g. InsightFace-class, *check licence*) or speaker embedding (ECAPA/WeSpeaker) | CPU | Optional. Only useful once there are multiple users. Privacy note in the architecture doc. |

## 6. Memory: embeddings and graph

| Component | Candidates | Notes |
|---|---|---|
| Multilingual embeddings | **EmbeddingGemma-300M**, **Qwen3-Embedding-0.6B**, bge-m3, multilingual-e5-small (+ Indic LoRA) | Tamil-trimmed vocab variants exist for EmbeddingGemma (57% smaller) and Qwen3-Embedding (20% smaller), but have no benchmarks [3p]. The large Indic-tuned `qwen-indic-v1` is 8B, too big. Pick by a small Tamil/Tanglish retrieval test (gate G4). CPU is fine. |
| Vector index | **sqlite-vec** (in the existing SQLite) | No new service. Fits RAM. |
| Graph | Keep `SemanticGraphStore` behind its interface. Start with **SQLite tables** (entities/edges with `valid_from/valid_to`), keep **Neo4j** optional | Neo4j's JVM costs 1–2 GB RAM on a 15 GB box. Graphiti (bi-temporal KG on Neo4j) is the reference design [3p], but its per-episode LLM extraction calls are expensive on a 4B local model. Borrow its *schema ideas* (bi-temporal edges, episodes), not necessarily the library. Mem0 is simpler, but its graph layer status is disputed [3p]. |
| Extraction | The brain LLM, **asynchronously during idle** ("sleep consolidation"), with a JSON schema | Replaces the English regexes. Handles TA and Tanglish natively. |

## 7. Speech emotion recognition

| Model | Notes |
|---|---|
| superb/wav2vec2-base-superb-er (current) | IEMOCAP, 4-class, English-acted. Weak fit. |
| **emotion2vec+ base / large** | Foundation SER fine-tuned on ~42.5k h of pseudo-labelled data (large ~300M). The authors claim it beats popular HF SER models [card]. No multilingual head-to-head found. Top candidate. Export to ONNX for CPU. |

## 8. Runtime and serving

- **llama.cpp server** stays the brain runtime: CUDA build, `--mmproj` for vision, `cache_prompt`, KV cache quantisation (`-ctk q8_0 -ctv q8_0`) to save VRAM. The LLM-TTS (Indic-Speak/Svara) can run as a **second llama.cpp instance** that emits SNAC tokens, the same way Orpheus GGUF servers do.
- **ONNX Runtime CPU** for VAD, Smart Turn, SER, IndicConformer and the embedder. Pin the thread count per model so they don't fight over the 14 cores.
- **Not chosen:** vLLM (VRAM-hungry with paged KV on 6 GB, multi-GPU oriented), TensorRT-LLM (build complexity; revisit for the final 20% of latency).

---

## Sources

VLMs and brains
- [Gemma 4 model card (Google)](https://ai.google.dev/gemma/docs/core/model_card_4) · [HF blog: Welcome Gemma 4](https://huggingface.co/blog/gemma4) · [google/gemma-4-E2B](https://huggingface.co/google/gemma-4-E2B) · [Run Gemma with llama.cpp](https://ai.google.dev/gemma/docs/integrations/llamacpp) · [NVIDIA: Gemma 4 on edge](https://developer.nvidia.com/blog/bringing-ai-closer-to-the-edge-and-on-device-with-gemma-4/) · [Unsloth Gemma 4 docs](https://unsloth.ai/docs/models/gemma-4) · [Gemma (Wikipedia)](https://en.wikipedia.org/wiki/Gemma_(language_model))
- [Unsloth: Qwen3.5 small models](https://x.com/UnslothAI/status/2028463220063871426?lang=en) · [Ollama qwen3.5](https://ollama.com/library/qwen3.5) · [Qwen 3.5 small models deep dive](https://trilogyai.substack.com/p/deep-dive-qwen-35-brings-native-multimodality) · [InsiderLLM Qwen3.5 small](https://insiderllm.com/guides/qwen-3-5-small-models-9b-beats-30b/)
- [Reddit snapshot: Qwen3.5-4B vs Gemma E4B doc/vision test](https://reddit.sentinel-team.org/posts/1sfr6qo/snapshots/2026-04-09T16%3A11%3A00.655487Z) · [Gemma 4 vs Qwen 3.5 comparison](https://gemma4all.com/blog/gemma-4-vs-qwen-3-5-benchmarks)
- [tinyweights: best local VLMs 2026](https://tinyweights.dev/posts/best-local-vision-language-models-2026/) · [InsiderLLM: vision models by GPU tier](https://insiderllm.com/guides/vision-models-locally/) · [SmolVLM paper](https://arxiv.org/pdf/2504.05299)
- [Qwen2.5-Omni-3B (VentureBeat)](https://venturebeat.com/ai/qwen-swings-for-a-double-with-2-5-omni-3b-model-that-runs-on-consumer-pcs-laptops) · [Qwen3-Omni paper](https://arxiv.org/html/2509.17765v1) · [HN: local speech-to-speech setups](https://hn.nuxt.dev/item/46731068)
- [IndicParam benchmark](https://arxiv.org/html/2512.00333v2) · [VakyArth Indic pragmatics](https://arxiv.org/pdf/2609.01788) · [Sarvam-1](https://www.sarvam.ai/blogs/sarvam-1)

STT
- [bodhan-ai/indic-transcribe-core](https://huggingface.co/bodhan-ai/indic-transcribe-core) · [bodhan-ai/indic-transcribe-flex](https://huggingface.co/bodhan-ai/indic-transcribe-flex) · [Hima-ASR card (Tamil WER comparison)](https://huggingface.co/Prahaladha/hima-asr) · [Analytics Vidhya: Bodhan AI four models](https://www.analyticsvidhya.com/blog/2026/09/bodhan-ai-indic-models/) · [Business Today: Indic-Transcribe](https://www.businesstoday.in/technology/artificial-intelligence/story/from-hindi-to-regional-accents-this-new-ai-model-is-built-to-understand-26-indian-languages-549708-2026-08-18)
- [ai4bharat/indic-conformer-600m-multilingual](https://huggingface.co/ai4bharat/indic-conformer-600m-multilingual) · [IndicConformer sherpa-onnx int8](https://huggingface.co/Docglasses-AI/indic-conformer-600m-sherpa-onnx-int8) · [sherpa-onnx discussion #3199](https://github.com/k2-fsa/sherpa-onnx/discussions/3199) · [AI4Bharat/IndicConformerASR](https://github.com/AI4Bharat/IndicConformerASR)
- [tamil-asr-qwen3 (FLEURS-Tamil numbers)](https://huggingface.co/osmapi/tamil-asr-qwen3) · [BuzzASR Tamil](https://huggingface.co/BuzzASR/tamil) · [IndicWhisper / Vistaar paper](https://www.isca-archive.org/interspeech_2023/bhogale23_interspeech.pdf) · [Vividh-ASR](https://huggingface.co/blog/adalat-ai/vividh-benchmark)
- [Tamil-English code-mixed ASR with LoRA/QLoRA](https://link.springer.com/article/10.1186/s13636-026-00477-y) · [WhisTam @ DravidianLangTech 2026](https://aclanthology.org/2026.dravidianlangtech-1.70/) · [Gemma 4 public ASR eval](https://huggingface.co/datasets/huckiyang/gemma-4-public-bench-eval)

TTS
- [bodhan-ai/indic-speak](https://huggingface.co/bodhan-ai/indic-speak) · [Bodhan console](https://console.bodhan.ai/) · [kenpath/svara-tts-v1](https://huggingface.co/kenpath/svara-tts-v1) · [svara-tts GGUF](https://huggingface.co/mradermacher/svara-tts-v1-GGUF) · [Svara streaming server](https://github.com/iNavLabsResearch/tts_pretrained_inference)
- [AI4Bharat/IndicF5](https://github.com/AI4Bharat/IndicF5) · [IndicF5 ONNX (not realtime on CPU)](https://huggingface.co/developerabu/IndicF5-ONNX) · [Indian-language TTS preference study](https://arxiv.org/pdf/2604.21481) · [ai4bharat/indic-parler-tts](https://huggingface.co/ai4bharat/indic-parler-tts) · [Maya TTS native engine](https://github.com/MayaResearch/maya2-native)
- [Qwen3-TTS paper](https://arxiv.org/html/2601.15621) · [Picovoice on-device TTS benchmark](https://picovoice.ai/blog/on-device-tts/) · [Kokoro vs XTTS vs Chatterbox](https://localaimaster.com/blog/kokoro-vs-xtts-vs-chatterbox) · [BentoML open TTS 2026](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)

Turn-taking, emotion, perception, memory
- [Smart Turn v3 announcement](https://www.daily.co/blog/announcing-smart-turn-v3-with-cpu-inference-in-just-12ms/) · [Smart Turn v3.2 ONNX](https://huggingface.co/soniqo/Smart-Turn-v3.2-ONNX) · [smart-turn-tamil](https://huggingface.co/santhosh-005/smart-turn-tamil) · [LiveKit turn detector](https://docs.livekit.io/agents/logic/turns/turn-detector) · [TEN framework](https://github.com/TEN-framework)
- [emotion2vec+ (HF)](https://huggingface.co/emotion2vec/emotion2vec_plus_seed) · [EmoBox benchmark](https://www.arxiv.org/pdf/2406.07162)
- [MediaPipe Face Landmarker web guide](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker/web_js) · [Face Landmarker overview](https://ai.google.dev/mediapipe/solutions/vision/face_landmarker)
- [Mem0 vs Zep/Graphiti](https://vectorize.io/articles/mem0-vs-zep) · [Agent memory systems: Letta, Mem0, Graphiti, Cognee](https://codepointer.substack.com/p/agent-memory-systems-and-knowledge) · [EmbeddingGemma Tamil trim](https://huggingface.co/alphaedge-ai/embeddinggemma-tam-32768) · [Qwen3-Embedding Tamil trim](https://huggingface.co/alphaedge-ai/Qwen3-Embedding-tam-32768) · [qwen-indic-v1](https://huggingface.co/LingoIITGN/qwen-indic-v1)
