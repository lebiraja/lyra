# Similar Open-Source Projects (prior art)

**Date:** 2026-11-10 · **Question:** what already exists on GitHub that does some of "local companion that hears, sees, remembers and talks fast", and what can we borrow?

None of these covers all of voice + camera perception + long-term personal memory + Tamil + fully offline. Each covers a slice, and several have solved a sub-problem we still have open. Star counts and activity come from third-party reviews; check the repos before depending on them.

## Closest matches

| Project | What it does | Local? | Vision | Memory | What to borrow |
|---|---|---|---|---|---|
| [**Open-LLM-VTuber**](https://github.com/Open-LLM-VTuber/Open-LLM-VTuber) (MIT) | Hands-free voice chat with any LLM, voice interruption, Live2D avatar, swappable ASR/LLM/TTS | Yes, offline mode | Camera, screen recording, screenshots | Not prominent | The **avatar-as-presence** UI pattern. Swappable engine registry. It also tackles speaker echo without headphones ([review](https://www.promptquorum.com/power-local-llm/open-llm-vtuber-review)). |
| [**moeru-ai/airi**](https://github.com/moeru-ai/airi) | Self-hosted "soul container" companion: realtime voice, plays Minecraft/Factorio, web/macOS/Windows | Self-hosted | Game/screen context | Yes | Always-listening "voice call mode" ([releases](https://github.com/moeru-ai/airi/releases)), agentic "doing things together" ideas, character framing. |
| [**katipally/openlive**](https://github.com/katipally/openlive) | On-device voice + vision layer for any model/agent: VAD, STT, TTS, barge-in locally; pitched as an open Gemini Live / OpenAI Realtime | Yes | Yes | No (bring your own) | Architecture for a **voice+vision I/O layer separated from the brain**, which matches our pipeline/brain split. |
| [**Lex-au/Vocalis**](https://github.com/Lex-au/Vocalis) | Real-time local speech-to-speech: custom VAD, faster-whisper, LLM, TTS. **Vision via SmolVLM-256M captions** fed to a text-only LLM ([thread](https://nyc1.lr.ggtyler.dev/r/LocalLLaMA/comments/1jy1x1b/vocalis_local_conversational_ai_assistant_speech)) | Yes | Captioner pattern | Session | The **"tiny captioner → text LLM"** fallback if a multimodal brain doesn't fit. Also its AI-initiated follow-ups when the user goes quiet. |
| [**KoljaB/RealtimeVoiceChat**](https://github.com/KoljaB/RealtimeVoiceChat) (MIT) | ~500 ms voice chat: RealtimeSTT + RealtimeTTS, WS audio chunks, smart turn detection ([Show HN](https://news.ycombinator.com/item?id=43899028)) | Yes | No | No | The latency engineering: partial transcripts, early LLM start on probable end-of-turn, streaming TTS. Its turn model is English-only. |
| [**huggingface/speech-to-speech**](https://pypi.org/project/speech-to-speech/) | Modular VAD → STT (Parakeet TDT) → LLM → TTS (Qwen3-TTS) behind an **OpenAI-Realtime-compatible WS API** | Yes | Optional mlx-vlm on macOS | No | A Realtime-compatible protocol would let our backend be driven by any Realtime client. Also see the [Reachy Mini fully-local write-up](https://huggingface.co/blog/local-reachy-mini-conversation). |
| [**dnhkng/GLaDOS**](https://github.com/dnhkng/GLaDOS) (MIT) | **Corrected after reading the code (2026-11-10):** a full companion on Gemma 4 E4B (direct audio + vision) with Emotion/Memory/Vision minds and an Autonomy Core | Yes | **Yes**: motion-adaptive scene + changes + expressions | **Yes** | **Closest blueprint** for v4; see [reference-repos](2026-11-reference-repos.md) §1. |
| [**Kyutai Unmute**](https://kyutai.org/) | Gives any text LLM a real-time voice using Kyutai's streaming STT/TTS | Self-host | No | No | True streaming STT (text while you speak). English/French only, and integration is all-or-nothing ([discussion](https://github.com/KoljaB/RealtimeVoiceChat/issues/28)). |
| [**TEN framework**](https://github.com/TEN-framework) (Apache-2.0) | Real-time voice/vision/avatar agent framework plus TEN VAD and TEN Turn Detection | Partly (demos use cloud APIs) | Yes (demos use Gemini Live) | — | TEN VAD and turn detector as benchmark alternatives. Graph-based extension design. |
| [**Pipecat**](https://github.com/pipecat-ai/pipecat) | Python voice-agent framework: frame pipeline, transports (WebSocket/**SmallWebRTC**), `LocalSmartTurnAnalyzerV3` | Yes, with local services | Video frames supported | Via services | **Smart Turn integration** and a **WebRTC transport, which gives real browser AEC** and Opus. We could adopt its transport alone, or the whole framework (see the decision in `DECISIONS.md`). |
| [LiiLk/Local-AI-Companion](https://github.com/LiiLk/Local-AI-Companion) | Offline companion, faster-whisper + Kokoro, vision "later" | Yes | Planned | — | Confirms the same starting stack as ours. |
| [Utsuwa](https://www.utsuwa.ai/) | Open companion, 3D VRM avatar, voice, persistent memory, offline-capable | Yes | No | **Yes** | Memory UX for companions. VRM avatar as an alternative to Live2D. |
| [Satyamku88/Vision_AI_bot](https://github.com/Satyamku88/Vision_AI_bot) | Offline: YOLOv8 objects, face recognition, Vosk voice, DeepSeek via Ollama | Yes | Object + face ID | — | A simple object-detection plus face-ID loop. Windows-only, not a model to copy. |

Curated lists: [awesome-ai-companion](https://github.com/DasterProkio/awesome-ai-companion) · GitHub topics [ai-companion](https://github.com/topics/ai-companion?l=python&o=desc&s=updated) and [voice-assistant-ai](https://github.com/topics/voice-assistant-ai).

Indic-specific references:
- [indicspeechLiveTranslate](https://github.com/Ribin-Baby/indicspeechLiveTranslate): IndicConformer on Riva plus Indic TTS, real-time.
- [indic-voice-agent](https://github.com/mathuryashash/indic-voice-agent): Hindi/Kannada voice agent with WER, latency and tool-accuracy evals. Its eval harness is a good template.
- Community Gemma-4-E4B Tamil fine-tunes paired with Orpheus-style Tamil TTS: [gemma4-tamil-e4b-it](https://huggingface.co/prasadvittaldev/gemma4-tamil-e4b-it).

## What this tells us

1. **The voice loop is a solved pattern**: VAD → STT → LLM → TTS with barge-in. Our v3 already sits at the GLaDOS/Vocalis level. The leaders differentiate on **turn-taking** (smart turn, early start) and **transport** (WebRTC for AEC).
2. **Vision is done in two ways:**
   - A multimodal brain on a frame (Open-LLM-VTuber, openlive).
   - A tiny captioner feeding a text brain (Vocalis).

   Nobody we found does **continuous cheap perception** (landmarks, posture, attention) **plus occasional VLM understanding**. That two-lane design is our differentiator and suits a 6 GB card.
3. **Memory is the weakest area across the board.** Most projects keep chat history only. Personal, temporal, *editable* memory ("you were stressed about the exam last week, how did it go?") is where we can be meaningfully better.
4. **Tamil/Tanglish native voice-to-voice doesn't exist** as an open companion. The pieces (Indic-Transcribe, Indic-Speak, Svara, smart-turn-tamil) only appeared in 2026.
5. **Build or adopt:** adopting Pipecat wholesale would replace our tested pipeline and echo guard. Borrowing **Smart Turn, the WebRTC transport idea and the eval-harness patterns** keeps our code and tests. This is recorded as an open decision in `DECISIONS.md`.
