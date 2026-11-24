# Research: what makes a voice companion feel human (Nov 2026)

**Question:** What makes Lyra feel like a friend rather than an assistant, given one GPU, a half-duplex mic and three languages (EN, TA, Tanglish)?
**Feeds:** [v4/persona.md](../v4/persona.md) (behaviour spec) and [v4/plan.md](../v4/plan.md) D-44…D-47.
**Method:** a web search for papers and practitioner write-ups (2023–2026), the 18 reference repos (`reference/`), and the v3 code audit. Figures marked [abs] were taken from abstracts or search excerpts and **not checked against the full paper**. Treat them as direction, not fact.

---

## 1. Findings

### 1.1 Timing beats wording
- Human turn gaps cluster around ~200 ms. Anything past ~1 s reads as "machine thinking". The plan already targets a reflex median ≤ 1.0 s (S1). The finding here is that the **first sound** matters more than the first word. A short acknowledgement ("hmm", "aama", "wait") at 0.8 s holds the floor naturally (D-21, `ack_think`).
- **Backchannels** ("mm-hm", "seri", "aama") while the user is talking are the strongest human cue. They are also the hardest to get right: timing, a form that fits the meaning, and how often all matter. Current spoken LMs struggle to produce them frequently and appropriately [abs: ACL 2026 backchannel paper; Full-Duplex-Bench, arXiv 2503.04721; RESPOND, arXiv 2603.21682].
  - **Constraint for us:** a spoken backchannel means playing audio while the mic is open. Under the half-duplex echo guard (D-35), that audio would leak into the mic or be dropped. **Spoken backchannels are therefore gated on G8 (AEC).** Until then Lyra backchannels **visually**: the voice line "nods" (ui-redesign.md) when Smart Turn reports a pause but not an end of turn.
- **Floor-claiming should be adjustable.** RESPOND exposes two knobs, how often to acknowledge and how assertively to claim the turn. F-Actor (arXiv 2601.11329) makes backchannel and interruption tendency promptable, and its authors note these tendencies "strongly influence" how human a system feels [abs]. **Adopt:** `INITIATIVE_LEVEL` already covers unprompted speech; add `BACKCHANNEL_LEVEL` (off/low/normal) for the AEC era.

### 1.2 Voice presence, and its limits
- Sesame's CSM write-up ("Crossing the uncanny valley of conversational voice", Feb 2025) defines **voice presence** as emotional intelligence, conversational dynamics (timing, pauses, interruptions), contextual awareness and a consistent personality. It conditions TTS on the **conversation history**, so prosody follows context.
  - Its co-founder still called it "firmly in the valley": too eager, and sometimes the wrong tone, prosody or pacing.
  - In blind tests listeners couldn't tell short phrases apart from a human, but they still preferred human voices over long conversations [press coverage].
- **What we can do on a 6 GB laptop:**
  - **One consistent voice** (D-11, reinforced by D-47). Identity breaks the moment the voice changes, which is why the Kokoro/Piper "backup voice" is now off by default (D-47).
  - Emotion per reply from the `[mood]` tag plus the PAD state (D-27).
  - **Energy matching:** short, quick replies to short, quick turns, and slower ones to slow, low-energy turns. This is cheap to do: the reply length cap and TTS emotion follow the user's speech rate and emotion2vec arousal.
  - Pass the **previous reply's emotion** into TTS, so prosody doesn't swing randomly between sentences.

### 1.3 Memory you can feel
- People judge "knows me" from **callbacks**: unprompted, correct references to earlier shared moments ("how did the Friday exam go?"), not from fact recall on request.
- The Generative Agents architecture (Park et al., 2023, arXiv 2304.03442) is the reference design:
  - a **memory stream** of natural-language observations
  - retrieval scored by **recency × importance × relevance**, with importance LLM-rated 1–10
  - **reflection**, which periodically turns memories into higher-level inferences and writes them back to the stream
- Structured companion memory improves emotional-intelligence scores over raw history: ZifaMem reports +11.4% pooled across four backbones (arXiv 2607.17564) [abs].
- **Persona consistency over time is a memory problem, not only a weights problem** (ARPM, arXiv 2605.14802; PERMA benchmark, arXiv 2603.23231) [abs].
- **Adopt** (details in [user-model.md](../v4/user-model.md)):
  - importance scores on archive turns
  - a nightly **reflection** job that writes `insights`
  - an `open_loops` table that drives follow-ups (the initiative "Follow-up" mind)
  - a **Lyra self-memory** that keeps what *she* has said about herself consistent

### 1.4 Relationships deepen gradually
- **Social penetration theory**, applied to human–chatbot relationships:
  - Closeness grows as self-disclosure widens and deepens, driven by perceived rewards and costs (12-week study, n = 28, Oslo/SINTEF; Replika interview studies; Skjuve doctoral thesis 2023).
  - Chatbots need an adapted version of the theory, because disclosure isn't truly mutual.
- **Gradual** disclosure by the chatbot significantly increased perceived intimacy, whether or not its persona matched the user's (arXiv 2505.24658, two studies, n = 29 and n = 53) [abs].
- **Adopt a relationship level** (`familiarity` 0–4, see persona.md §4). It is computed from days known, sessions and the user's disclosure depth. It gates:
  - nicknames and teasing
  - how personal Lyra's questions get
  - how much of her own "self" she shares

  Lyra never jumps to intimacy on day one.

### 1.5 Healthy, not sticky
- The OpenAI × MIT Media Lab studies (March 2025):
  - an RCT with ~1,000 participants over 4 weeks
  - an analysis of ~40 M ChatGPT conversations
  - not peer reviewed

  They found that **higher daily use correlated with more loneliness, more dependence and less socialising**. Power users were the most likely to call the bot a friend. Voice helped at first, but **that advantage faded at high usage**, especially with a neutral voice. The authors caution that cause and effect is unclear.
- **This is a design constraint, not a footnote**, because Lyra is explicitly built to be a friend. **Adopt** (persona.md §6):
  - She is glad when he talks about other people and plans with them, and asks about them.
  - No guilt trips and no "I missed you so much"-style hooks. Absence gets an honest "you're back!", never pressure.
  - She never discourages him from logging off or going out, and sometimes encourages it.
  - The weekly insight (user-model.md §5) includes a social-time signal: are friends and family mentioned, and how many hours a night are spent with Lyra.
  - The v3 crisis override stays, and is strengthened by fused distress signals (plan §18).

### 1.6 Small human imperfections
These are practitioner consensus and observations from the reference repos (GLaDOS, airi, Vocalis), not formal studies:
- **Disfluency, sparingly:** an occasional "hmm", "wait" or Tamil filler ("aiyo", "seri", "paavam"). Never more than one per reply, and never in serious moments.
- **Clarifying instead of guessing:** "wait, Friday or Saturday?" This beats confident errors and matches the plan's honesty rule.
- **Not always answering in full:** a friend sometimes replies with a question, a reaction ("no way") or one word.
- **Anti-repetition:** LLM companions repeat openers ("Oh nice!", "That's awesome"). Keep a ring buffer of Lyra's last 30 reply openers and penalise repeats (persona.md §5).
- **Opinions of her own**, held consistently: no sycophancy, and disagreeing kindly is allowed. Sycophancy is the most common "this is a bot" tell.

### 1.7 Perception used like a friend would
Narrating what the camera sees ("I can see you are yawning") is creepy. **Weaving** it in ("you sound wiped, long day?") is friendly. The plan already says Lyra never narrates (§7.2). Two additions here:
- Use perception mostly to **choose tone and length**, not as content.
- Mention a visual cue **at most once per session** unless he brings it up.

---

## 2. What changes in the plan (summary)
| Finding | Change | Where |
|---|---|---|
| Identity = one voice | Backup voice off by default; outage lines are pre-rendered in Lyra's voice | D-47, plan §9.4, §16.3 |
| Callbacks feel personal | `open_loops` + Follow-up mind; importance + reflection → `insights` | D-43, user-model.md |
| Consistent self | Persona bible + `lyra_self` memory | D-45, persona.md §2 |
| Gradual intimacy | `familiarity` level gating style | D-46, persona.md §4 |
| Healthy companion | Wellbeing rules, social-time insight | D-46, persona.md §6 |
| Backchannels | Visual now; spoken only after G8 | D-44, persona.md §5.3 |
| Anti-repetition, energy matching | Opener ring buffer, length and emotion follow the user | D-44, persona.md §5 |
| Human-likeness has to be measured | Gate **G10** ("feels like a friend" rubric + Lebi's weekly 1–5) | plan §20.2 |

---

## Sources
- [Sesame: Crossing the uncanny valley of conversational voice](https://sesame.com/research) · [Beebom hands-on](https://beebom.com/sesame-ai-voice-companion-maya-experience-like-talking-to-real-person) · [R&D World](https://www.rdworldonline.com/the-rd-story-behind-sesame-ai-the-startup-that-just-open-sourced-its-groundbreaking-voice-generation-model/)
- [Full-Duplex-Bench (arXiv 2503.04721)](https://arxiv.org/html/2503.04721v1) · [RESPOND (arXiv 2603.21682)](https://arxiv.org/html/2603.21682v2) · [F-Actor (arXiv 2601.11329)](https://arxiv.org/html/2601.11329v2) · [Duplex cue adaptation (arXiv 2609.13117)](https://huggingface.co/papers/2609.13117.md) · [ACL 2026 backchannel work](https://aclanthology.org/2026.acl-long.629.pdf)
- [Generative Agents (arXiv 2304.03442)](https://arxiv.org/pdf/2304.03442v2)
- [ZifaMem (arXiv 2607.17564)](https://arxiv.org/abs/2607.17564) · [ARPM (arXiv 2605.14802)](https://arxiv.org/pdf/2605.14802) · [PERMA (arXiv 2603.23231)](https://arxiv.org/html/2603.23231v1) · [Persona design taxonomy (arXiv 2511.02979)](https://arxiv.org/pdf/2511.02979v2)
- [Gradual self-disclosure / "Can LLMs and humans be friends?" (arXiv 2505.24658)](https://arxiv.org/html/2505.24658v1) · [Skjuve thesis abstract](https://www.sv.uio.no/psi/forskning/aktuelt/arrangementer/disputaser/2025/Skjuve/abstract.html) · [Longitudinal SPT study](https://duo.uio.no/handle/10852/105545) · [How AI companionship develops (arXiv 2510.10079)](https://arxiv.org/pdf/2510.10079) · [Disclosure trajectories (arXiv 2610.29413)](https://arxiv.org/pdf/2610.29413)
- [MIT Technology Review on the OpenAI/MIT study](https://www.technologyreview.com/2025/03/21/1113635/) · [MIT Media Lab project page](https://www.media.mit.edu/projects/mit-openai-study/updates/) · [Fortune](https://fortune.com/2025/03/24/chatgpt-making-frequent-users-more-lonely-study-openai-mit-media-lab/)
