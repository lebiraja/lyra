# Medusa v4: UI Redesign (proposal)

**Status:** PROPOSAL, no code changed · **Date:** 2026-11-10 · Context: [UI audit](../research/2026-11-current-state-audit.md#4-ui-audit-frontendsrc) · [architecture](architecture.md)

## 1. Direction: "Marginalia"

v3's *Quiet Room* (warm charcoal, amber ember, serif voice) is the right temperature, so it stays. What changes is the **composition**. v3 is a chat log. v4 is a lamp-lit page where the companion's **presence** sits at the centre and what it **sees** and **remembers** shows up as notes in the margins, the way a friend's thoughts sit around a conversation.

- **Centre: the voice line.** One horizontal hand-drawn line in ember, used as a shared signal. It traces *your* mic while you speak and *Medusa's* TTS envelope while she speaks. When she thinks, it goes still and a slow dot travels along it. This replaces both the waveform footer and the status dot.
- **Above the line: the spoken phrase.** The sentence Medusa is saying right now, set large in serif and lit word by word in sync with playback (chunk timing is known server-side). Earlier lines drift up and fade. The full transcript is one tap away, not the default.
- **Left margin: "what I see".** Small italic notes taken from perception, e.g. *at desk · dim light · mug* or *you look tired*. Each fades after ~20 s. Tapping one shows "why I think this" (the cues), and a wrong note can be dismissed ("not tired"), which feeds a correction back into the session.
- **Right margin: "what I remembered".** When a memory is used in a reply, it appears as a note: *remembered: exam on Friday*. Tapping it opens it in the Notebook. This makes memory use visible and builds trust.
- **Bottom status rail** (one line, small caps avoided, lowercase like v3):
  - camera state, with a hard toggle and an always-visible dot when on
  - language chip `auto · en · ta`, showing what was detected
  - quiet mode
  - the conversations drawer

**Explicitly avoided:** card grids, gradients and glows, chat bubbles, avatars with faces, emoji, "New ✨" badges, uppercase tracked labels and pulsing everything. v3's `animate-pulse` on the title and the emotion line goes away.

```
┌──────────────────────────────────────────────────────────────────────┐
│ conversations                    Medusa                     notebook │
│                                                                      │
│  at desk                                                             │
│  dim light            "dei, you've been at this                      │
│  mug in hand           since ten thirty. break?"        remembered:  │
│                                                         exam friday  │
│  looks tired                                                         │
│                                                                      │
│  ───────────────────────╮╭──╮╭─────────────────────────────────────  │
│                         ╰╯  ╰╯   (voice line)                        │
│                                                                      │
│  ● camera on   [self-view ▢]    auto: tanglish    quiet    ⌨ type    │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. Screens

### 2.1 Arrival
- Replaces v3's single "begin" button. The voice line is already drawn and still. Medusa's name sits in serif with no pulse.
- Two clear choices: **"talk"** (mic) and **"talk + let me see you"** (mic + camera). The camera choice explains in one line what happens to frames: "processed here, never saved".
- If memory exists, a first line appears before any audio plays, e.g. *"back again. how did the exam go?"*, and is then spoken (the proactive greeting).

### 2.2 Conversation (above)
- **Self-view:** an optional small toggle in the rail, monochrome and warm-tinted to match the room. A developer toggle overlays the face mesh and pose skeleton, which is useful for debugging perception.
- **Typing:** `⌨` expands an input into the rail. Typed turns render the same way.
- **Thinking route:** when the router picks *think*, the spoken ack ("hmm, let me think") appears and the dot travels the line. If the model exposes reasoning, a collapsible "her thinking" note can show it, off by default.
- **Look route:** a brief shutter tick on the self-view tells the user a keyframe was taken. Honesty matters here.

### 2.3 Notebook (memory drawer, right side)
- Sections: **About you** (profile and facts), **Recently** (episodes by day), **Patterns** (routines) and **Forgotten** (an undo window).
- Every item shows its source ("you said, Sun 23:41") and can be edited or deleted. "Forget everything" sits at the bottom behind a confirmation.
- Shows text in the language it was said (Tamil script renders properly, see §4).

### 2.4 Conversations drawer (left)
The existing `SessionDrawer`, restyled. A session title comes from the first line, or an LLM title later.

### 2.5 Dev HUD (hidden, `?` key)
A per-turn latency trace (end-of-turn, STT, prefill, first token, first audio), the router mode, VRAM from `/api/health`, and the percept rate. This is how gates G0–G5 are run against the real UI.

## 3. Motion and sound
- The voice line is the only constantly moving element. It is drawn on `<canvas>` at 60 fps from the mic `AnalyserNode` and the playback envelope.
- Margin notes fade in over 400 ms and out over 1.2 s, with no slide or bounce.
- `prefers-reduced-motion`: the line becomes a static state glyph and notes appear without fades.
- No UI sounds except the optional shutter tick on keyframes.

## 4. Type and colour
- Keep the v3 tokens (`--color-room`, `--color-ink*`, `--color-ember*`).
- **Fix:** Newsreader and Inter have **no Tamil glyphs**, so Tamil text currently falls back to whatever system font exists. Pair them with **Noto Serif Tamil** (for the spoken phrase) and **Noto Sans Tamil** or **Mukta Malar** (for UI text), self-hosted through `@fontsource`, as v3 already does for Inter and Newsreader.
- Tamil script needs ~10–15% more line height than Latin at the same size. Set `lang="ta"` on spans so the font stack and line-height apply per run, which matters for Tanglish lines that mix both scripts.
- Colour encodes state only: ember = Medusa's voice, ink-dim = yours, ember-soft = thinking. Affect is **never** shown as a colour on the user, which would feel judgmental.

## 5. Tech plan
- **Stack:** React 19 + Vite + Tailwind 4 (existing), with **shadcn/ui** as the customised base for the drawers, dialog, toggle and tooltip, restyled to the room tokens. Magic UI is used only if a specific motion needs it; the voice line is custom canvas.
- **Perception in a Web Worker:** `@mediapipe/tasks-vision` Face Landmarker and Pose Landmarker, with the GPU delegate (WebGL) and `OffscreenCanvas`, run inside a dedicated worker so landmark inference never janks the UI thread. Model files (`.task`) and WASM are served by our nginx, not a CDN, to keep it offline.
- **Feature extraction:** blendshapes to features in the worker. A ~4 Hz `percept` message goes to `useConversation`.
- **New hooks:**
  - `usePerception` (camera, worker and percepts)
  - `useKeyframe` (grab a JPEG on `request_keyframe`)
  - `useMemory` (Notebook REST)
  - `useTrace` (dev HUD)
- **Protocol** types are updated in `src/types/protocol.ts` (Zod) in lockstep with `docs/API.md`, per architecture §9.
- **Tests:** vitest + testing-library for the hooks' state machines, and Playwright for arrival → talk → camera toggle → notebook edit, with a fake media stream.

## 6. Mobile / second device
- The layout collapses to one column. Margin notes stack under the spoken phrase, and the Notebook becomes a bottom sheet.
- **Phone as camera (stretch):** open the app on the phone with `?role=eyes` to send percepts and keyframes only, while audio stays on the laptop. Useful when the laptop camera has a bad angle.

## 7. Open UI questions
1. Should Medusa have *any* visual body (Live2D/VRM like Open-LLM-VTuber or Utsuwa), or stay abstract? Recommendation: **abstract** (the line), because a face invites uncanny comparisons and costs GPU/CPU next to MediaPipe.
2. Should the "what I see" notes be on by default? Recommendation: on, but only notes above a confidence threshold and at most 3 visible.
3. Should the transcript be default-visible for accessibility? Recommendation: a user setting, remembered per device.
