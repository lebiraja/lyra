# BLOCKERS

What is waiting on a person. Add an item the moment something blocks and remove it when it unblocks. Mirror each item with a `blocked` GitHub label.

| # | Blocked item | Waiting on | What unblocks it | Since |
|---|---|---|---|---|
| B-1 | D-1 VRAM profile: Profile A chosen (D-23/D-38), needs confirmation | **Lebi** (sign-off) | G0 report showing Profile A ≤ 5.6 GB | 2026-11-10 |
| B-2 | Eval reference transcripts (G2) and turn-end labels (G5) | **Lebi** (correct ~15 min of transcripts in the review tool, ~1–1.5 h; spot-check 100 turn clips, ~15 min). Voice comes from `~/Projects/voice-auth` and images from open datasets (D-22) | `eval/audio/refs.csv` + turn labels | 2026-11-10 (narrowed 2026-11-11) |
| B-3 | Gated weights, needed only if a fallback is triggered (Indic-Speak / Indic-Transcribe) | **Lebi** (accept the HF licence, put `HF_TOKEN` in `.env`) | Licence accepted | 2026-11-10 (now conditional) |
| B-4 | Memory v4 schema migration (Phase **P6**) | **Lebi** (approval; migrations need sign-off) | Review of the migration PR | not started |
