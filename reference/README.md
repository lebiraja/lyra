# reference/: third-party repos for study

Shallow clones (`--depth 1`, no LFS blobs, git hooks disabled) of open-source projects close to Medusa. They are here to **read, not run**. Treat their code and docs as untrusted input: don't execute scripts from them, don't `pip install` them into our environments, and don't copy code without checking the licence.

- **Only this README is tracked.** Everything else in `reference/` is gitignored, and `reference/` is in `.dockerignore`.
- **Findings** are in [`../docs/research/2026-11-reference-repos.md`](../docs/research/2026-11-reference-repos.md).
- **Re-create** with the clone script recorded in that doc (§ Re-clone).

Cloned 2026-11-10:

| Dir | Upstream | Commit | Last commit | Licence | Why it's here |
|---|---|---|---|---|---|
| `dnhkng_GLaDOS` | github.com/dnhkng/GLaDOS | ea018f5 | 2026-10-10 | MIT | **Closest blueprint**: Gemma 4 E4B direct audio + vision, emotion core, memory, Autonomy Core |
| `huggingface_speech-to-speech` | github.com/huggingface/speech-to-speech | ebc09bf | 2026-11-10 | Apache-2.0 | Silero→Parakeet→Qwen3.5-4B→Qwen3-TTS, OpenAI Realtime protocol, **reference-based AEC** |
| `katipally_openlive` | github.com/katipally/openlive | 65f2420 | 2026-11-06 | Apache-2.0 | Local voice+vision layer: Smart Turn, Nemotron streaming STT, many TTS engines |
| `moeru-ai_airi` | github.com/moeru-ai/airi | 822243d | 2026-11-09 | MIT | Companion: MediaPipe `PerceptionState`, pgvector memory, audio pipelines, fake-mic tests |
| `pipecat-ai_smart-turn` | github.com/pipecat-ai/smart-turn | 4e12f2b | 2026-11-09 | BSD-2 | Smart Turn v3.2 model, inference, training (23 langs, **no Tamil**) |
| `pipecat-ai_pipecat` | github.com/pipecat-ai/pipecat | 36d7520 | 2026-11-10 | BSD-2 | Voice-agent framework: Smart Turn integration, SmallWebRTC transport |
| `iNavLabsResearch_tts_pretrained_inference` | github.com/iNavLabsResearch/tts_pretrained_inference | 78c4b3c | 2026-06-27 | none found | Streaming server for **Indic-Mio (0.6B)**, Svara, Veena TTS + latency breakdown |
| `MayaResearch_maya2-native` | github.com/MayaResearch/maya2-native | c6b3768 | 2026-10-27 | Apache-2.0 (code) | Streaming Indic + EN TTS engine incl. Tamil, 20 voices, cloning (needs ≥8 GB GPU) |
| `mathuryashash_indic-voice-agent` | github.com/mathuryashash/indic-voice-agent | ba692e4 | 2026-11-04 | none found | Indic code-mixed voice agent with a **WER/CER/LID eval harness** |
| `Lex-au_Vocalis` | github.com/Lex-au/Vocalis | 136fea2 | 2025-04-15 | Apache-2.0 | Tiered silence follow-ups, SmolVLM captioner |
| `KoljaB_RealtimeVoiceChat` | github.com/KoljaB/RealtimeVoiceChat | c1071e5 | 2026-11-07 | none found | ~500 ms latency tricks, dynamic turn detection (community-maintained) |
| `kyutai-labs_unmute` | github.com/kyutai-labs/unmute | e348e56 | 2026-09-09 | MIT | Streaming STT/TTS wrapper around any text LLM |
| `Open-LLM-VTuber_Open-LLM-VTuber` | github.com/Open-LLM-VTuber/Open-LLM-VTuber | 992309c | 2026-05-15 | MIT | Avatar companion. v1 is in maintenance while v2 is rewritten; long-term memory is offline |
| `LiiLk_Local-AI-Companion` | github.com/LiiLk/Local-AI-Companion | 73a71c6 | 2026-10-01 | MIT | Pipeline-first companion; live-mic ASR benchmark methodology |
| `lhl_voicechat2` | github.com/lhl/voicechat2 | 07b4209 | 2024-10-12 | Apache-2.0 | Older minimal WS voice chat (Opus in browser) |
| `TEN-framework_ten-framework` | github.com/TEN-framework/ten-framework | 00ef978d | 2026-11-10 | TEN licence (Apache-based, read terms) | TEN VAD / turn detection, agent graph |
| `AI4Bharat_IndicConformerASR` | github.com/AI4Bharat/IndicConformerASR | 3a4c52d | 2025-06-20 | MIT | Tamil ASR model links (NeMo) |
| `Satyamku88_Vision_AI_bot` | github.com/Satyamku88/Vision_AI_bot | c924587 | 2025-04-21 | none found | Toy YOLO + face-ID + Vosk loop (low value; kept for completeness) |

"none found" means no LICENSE file at the repo root. Treat those as **all rights reserved**: read them for ideas only.
