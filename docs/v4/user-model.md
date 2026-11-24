# Lyra v4: Total-recall archive and user model

**Status:** APPROVED DESIGN (2026-11-24). Extends [plan.md](plan.md) §11 (memory v4). Where they differ, this file wins for the archive and user-model parts.
**Decisions:** D-42 (store everything, local), D-43 (layered user model + reflection), D-48 (audio archive opt-in). **Evidence:** [user-modelling research](../research/2026-11-user-modelling-memory.md), [human-likeness research](../research/2026-11-human-likeness.md).
**Phase:** P6 (schema `003` ships with or right after `002`; the migration needs Lebi's approval). The reflection and insights work is P7.

---

## 1. Goal

Lyra keeps **everything Lebi shares with her, forever, on his machine**:
- every word he said, in his own script (Tamil in Tamil, English in Latin)
- every word she said, including what was cut off
- how he sounded and looked at each moment, as numbers and short text, never pixels
- what she learnt from all of that

She uses it to know him the way a close friend does: his people, routines, moods, plans, the way he talks, the jokes they share, what he hasn't finished telling her. He can **see, search, correct, export and erase** all of it.

**Non-negotiables:**
- **Fully local.** No network after model download. Nothing leaves the laptop.
- **No pixels, ever.** Camera frames are discarded after inference (S8).
- **Raw audio only if Lebi turns it on** (§2.3).
- **Lossless:** the archive is the source of truth. Everything derived can be rebuilt from it.

---

## 2. What is stored: five layers

| Layer | Contents | Table(s) | Written | Retention | Rebuildable from |
|---|---|---|---|---|---|
| **L0 Archive** | every turn verbatim: user transcript, Lyra's full reply **and** what was actually spoken before an interrupt, timestamps, language, route, input mode | `messages` (extended), `sessions` | every turn (EventWriter) | forever | — (source of truth) |
| **L1 Signals** | per turn: voice emotion (emotion2vec+ scores), arousal, speech rate, face affect histogram, attention, presence, the SceneNote **text** at that moment; per minute: `perception_minutes` | `turn_signals`, `observations`, `perception_minutes` | every turn / minute | forever (numbers + text only) | — (source of truth) |
| **L2 Knowledge** | facts (bi-temporal), entities (people, places, things), episodes (session summaries), Lyra's self-statements | `facts`, `entities`, `edges`, `episodes`, `lyra_self` | idle extraction (D-31) | forever; superseded rows kept with `valid_to` | L0 + L1 |
| **L3 Understanding** | insights, routines, communication style, mood timeline, open loops, topics, relationship state | `insights`, `routines`, `style_profile`, `mood_daily`, `open_loops`, `topics`, `relationship_state` | reflection job (nightly / importance trigger), roll-ups at session end | forever, versioned | L0–L2 |
| **L4 Profile** | ≤ 300-token text Lyra reads at session start (frozen for the prefix cache) | `person_profile` (versioned) | session end | last 50 versions | L2 + L3 |

Indexes (all derived and rebuildable): `vec_memory` + `fts_memory` (plan §11.1) are extended to cover **archive turns**, so "what did I say about my sister last month" works. Neo4j projects L2 and L3 entities, topics and open loops.

### 2.1 What "everything" includes, concretely
| Category | Example | Layer |
|---|---|---|
| Identity | name, age, home town, languages, job/studies | L2 facts |
| People | sister Priya, friend Arun (+ how he feels about them, last mentioned) | L2 entities + edges, L3 relationship notes |
| Places & things | college, the café he likes, his bike | L2 |
| Events & plans | exam Fri 15 Nov, trip to Ooty next month | L2 facts with `valid_from`, L3 open loops |
| Preferences | filter coffee, Anirudh songs, hates mornings (and when that changed) | L2 bi-temporal facts |
| Routines | sleeps ~01:00, codes 21:00–00:30, skips lunch on Tuesdays | L3 routines (from turns + perception minutes) |
| Moods | daily valence/arousal, stress weeks, good days | L1 → L3 mood timeline |
| Communication style | Tanglish ratio, slang, humour, reply length he likes, topics he deflects | L3 style profile |
| Goals & worries | finish the Lyra project, worried about placements | L2 facts + L3 insights |
| Shared history | inside jokes, things Lyra promised, stories told | L2 episodes, `lyra_self`, L3 open loops |
| Boundaries | "don't bring up X", "don't comment on my sleep" | L2 facts `predicate=boundary`, **hard-filtered** into the persona prefix |

### 2.2 What is never stored
- camera frames, keyframes and video
- raw audio, unless §2.3 is on
- anything typed into the camera or other apps (Lyra has no screen access in v4.0, D-13)

### 2.3 Audio archive (opt-in, D-48)
- **Setting:** `ARCHIVE_AUDIO=false` (default), with a toggle in Notebook → Settings.
- **When on:** each user utterance is saved as **Opus 24 kbps mono** in `data/audio/YYYY/MM/<turn_id>.opus` (~1 MB/min). Path, duration and hash are recorded in `audio_clips`. Lyra's own audio is never stored; it can be regenerated.
- **Why someone would turn it on:**
  - re-transcribe old turns with a better hear model later
  - personal Tanglish LoRA training data (v4.1)
  - replaying his own voice notes in the Notebook
- **Retention:** `ARCHIVE_AUDIO_DAYS` (default 365; 0 = forever). A nightly job deletes older clips; transcripts are kept.
- **S8 changes accordingly:** with the toggle off, no audio bytes anywhere. With it on, audio only under `data/audio/` and nowhere else (logs, Neo4j, other volumes).

---

## 3. Schema: migration `003_archive_user_model.sql`

Forward-only, transactional, backup first (plan §11.2). **Needs Lebi's approval.**

```sql
-- L0: extend the v3 messages table (already verbatim per turn)
ALTER TABLE messages ADD COLUMN turn_id TEXT;            -- ULID, joins traces/signals
ALTER TABLE messages ADD COLUMN lang TEXT;               -- en|ta|mix
ALTER TABLE messages ADD COLUMN lang_ratio REAL;         -- Tamil-script ratio (plan §8)
ALTER TABLE messages ADD COLUMN input_mode TEXT;         -- voice|text|initiative|greeting
ALTER TABLE messages ADD COLUMN started_at TEXT;         -- speech start (user) / first audio (assistant)
ALTER TABLE messages ADD COLUMN ended_at TEXT;
ALTER TABLE messages ADD COLUMN spoken_text TEXT;        -- assistant: what was actually voiced before an interrupt
ALTER TABLE messages ADD COLUMN interrupted INTEGER DEFAULT 0;
ALTER TABLE messages ADD COLUMN route TEXT;              -- reflex|think|look
ALTER TABLE messages ADD COLUMN importance INTEGER;      -- 1..10, set by extraction (Generative Agents)
ALTER TABLE messages ADD COLUMN edited_at TEXT;          -- user corrected the transcript in the Notebook
ALTER TABLE messages ADD COLUMN deleted_at TEXT;         -- soft delete; hard purge job (§7)
CREATE UNIQUE INDEX idx_messages_turn ON messages(turn_id, role);

-- L1
turn_signals(turn_id TEXT PRIMARY KEY, voice_emotion_json TEXT, valence REAL, arousal REAL,
             speech_rate_wpm REAL, pause_ratio REAL, face_affect_json TEXT, attention REAL,
             present REAL, scene_note_id INTEGER, created_at TEXT)
observations(id INTEGER PK, session_id TEXT, at TEXT, kind TEXT CHECK(kind IN('scene','event')),
             text TEXT, json TEXT)                         -- SceneNote text / perception events, no pixels
audio_clips(turn_id TEXT PK, path TEXT, duration_s REAL, sha256 TEXT, created_at TEXT)  -- only if ARCHIVE_AUDIO

-- L2 addition
lyra_self(id INTEGER PK, statement TEXT, topic TEXT, said_at TEXT, turn_id TEXT,
          status TEXT CHECK(status IN('active','retracted')))   -- "my favourite song is…", promises

-- L3
insights(id INTEGER PK, kind TEXT CHECK(kind IN('pattern','change','strength','worry','social','weekly')),
         text TEXT, evidence_json TEXT, confidence REAL, period_from TEXT, period_to TEXT,
         version INTEGER, status TEXT CHECK(status IN('active','dismissed','superseded')), created_at TEXT)
routines(id INTEGER PK, name TEXT, schedule_json TEXT, evidence_json TEXT, confidence REAL,
         valid_from TEXT, valid_to TEXT, updated_at TEXT)                 -- {"days":[1-5],"from":"21:00","to":"00:30"}
style_profile(version INTEGER PK, json TEXT, created_at TEXT)            -- §4.3
mood_daily(day TEXT PK, valence REAL, arousal REAL, label TEXT, n_turns INT, talk_minutes REAL,
           present_minutes REAL, notes TEXT)
open_loops(id INTEGER PK, text TEXT, kind TEXT CHECK(kind IN('event','plan','worry','question','promise')),
           due_at TEXT, entity_ids_json TEXT, source_turn_id TEXT,
           status TEXT CHECK(status IN('open','followed_up','closed','dropped')),
           followups INT DEFAULT 0, last_followup_at TEXT, created_at TEXT)
topics(id INTEGER PK, label TEXT, entity_ids_json TEXT, first_seen TEXT, last_seen TEXT, turn_count INT)
relationship_state(id INTEGER PK CHECK(id=1), familiarity INT, days_known INT, sessions INT,
                   disclosure_depth REAL, nickname TEXT, updated_at TEXT)

-- indexes over the archive (derived; rebuildable)
-- memory_items.kind gains 'turn' and 'insight'; vec_memory and fts_memory cover them.
CREATE INDEX idx_messages_session_time ON messages(session_id, created_at);
CREATE INDEX idx_open_loops_status_due ON open_loops(status, due_at);
CREATE INDEX idx_insights_status ON insights(status, kind);
```

**Backfill:** v3 `messages` rows get `turn_id = 'legacy-<id>'`, `lang` from the script ratio, `input_mode = 'voice'|'text'` from `conversation_events` where known, else `NULL`. Archive embeddings are computed lazily by the MemoryWorker.

---

## 4. Derivation jobs

### 4.1 Per turn (hot path: writes only, no LLM)
`EventWriter` batch: the `messages` row (user + assistant, with `spoken_text`/`interrupted`), `turn_signals` (emotion2vec+ scores, speech rate = words ÷ speech seconds, the face affect histogram over the turn window, attention/presence from `PerceptState`, the current `scene_note_id`), and `audio_clips` if on. Budget: **< 2 ms** on the event loop; the actual I/O runs in the writer task.

### 4.2 Idle extraction (existing D-31 job, extended)
Runs on slot 1 when idle ≥ 20 s or at session end. The extraction schema (plan §7.6) gains:
```json
{"importance":[{"turn_id":"…","score":1}],
 "open_loops":[{"text":"exam on Friday","kind":"event","due_at":"ISO|null","entities":["…"]}],
 "closed_loops":[{"open_loop_id":0,"resolution":"said it went well"}],
 "lyra_self":[{"statement":"I said my favourite Anirudh song is 'Why This Kolaveri Di'","topic":"music"}],
 "boundaries":[{"text":"don't talk about my weight","scope":"topic"}],
 "disclosure_depth":0}
```
`disclosure_depth` uses 0 = small talk, 1 = preferences/opinions, 2 = personal events/feelings, 3 = vulnerabilities (the social-penetration levels, persona.md §4).

### 4.3 Reflection (nightly, or when Σ importance of unreflected turns ≥ 50)
Slot 1, thinking budget 512, schema-constrained, one run ≤ 60 s, preemptible by any user turn (InferenceScheduler priority "extraction"). Input: the turns since the last reflection (importance ≥ 4 in full, the rest as one line each), the last 14 `mood_daily` rows, `perception_minutes` aggregates, active facts, routines and open loops. Output:
```json
{"insights":[{"kind":"pattern|change|strength|worry|social","text":"…","evidence_turn_ids":["…"],"confidence":0.0}],
 "routines":[{"name":"late-night coding","schedule":{"days":[1,2,3,4,5],"from":"21:00","to":"00:30"},"confidence":0.0}],
 "style":{"tanglish_ratio":0.0,"avg_words_per_turn":0,"humour":"dry|playful|…","slang":["machan","semma"],
          "prefers_reply_length":"short|medium","deflects_topics":["…"],"pet_phrases":["…"]},
 "topics":[{"label":"placements","entities":["…"]}],
 "profile_hints":["…"]}
```
Rules:
- An insight needs ≥ 2 evidence turns from ≥ 2 different days.
- Inferences about health, sexuality, religion or politics are **never** written as insights unless Lebi said them himself (then they are facts with his words as the source).
- A **weekly** insight (Sunday) summarises mood, energy, sleep timing (from perception and talk times), social mentions and wins. It is shown in the Notebook. Lyra mentions it only if he asks, or once, lightly, as a Sunday-evening initiative slot (importance "regular").

### 4.4 Roll-ups (pure SQL, session end + nightly)
- `mood_daily`: talk-weighted mean valence/arousal from `turn_signals`, plus face affect from `perception_minutes`, `talk_minutes` and `present_minutes`.
- `relationship_state`:
  - `days_known` and `sessions`
  - `disclosure_depth` = EMA (α = 0.1) of the per-turn values
  - `familiarity` = f(days_known, sessions, disclosure_depth) per persona.md §4

### 4.5 Profile (session end, plan §11.5, extended)
The ≤ 300-token profile is composed from fixed sections, so it is stable and easy to diff:
1. who he is
2. people that matter
3. what's going on now (top open loops)
4. routines
5. how he talks (style)
6. boundaries (**always included, never truncated**)
7. what Lyra has said about herself (top 5 `lyra_self`)

---

## 5. How Lyra uses it (read side)
| Moment | Uses | How |
|---|---|---|
| Session start | L4 profile + `relationship_state` | frozen into the prefix (D-28) |
| Every turn | hybrid retrieval (plan §11.4) now over facts, episodes, insights **and archive turns** | ≤ 180 tokens in `<now>`; archive turns quoted with their date ("on 3 Nov you said …") |
| Every turn | style profile | `<now>` gets `style_hint` (reply length, Tanglish ratio) so she mirrors him |
| Arrival / idle | open loops due today/tomorrow or ≥ 2 days overdue | Follow-up mind (plan §12) → "how did the exam go?" Max 1 follow-up per loop per day; 2 unanswered follow-ups → `dropped` |
| "Remember when…" / "what did I say about…" | archive FTS + vec | answers with the quote and date; says so honestly when nothing matches |
| Weekly | weekly insight | Notebook card; optional Sunday initiative slot |

**Honesty rule (persona):** Lyra only claims a memory if it is in the profile, `<now>` or a retrieved quote. When she is unsure: "I think you said Friday? or was it Saturday?"

---

## 6. Notebook ("what Lyra knows about you", UI P8)
Tabs:
- **About you:** profile sections, editable inline. Each item shows "learnt from…" and links to the turn.
- **People:** entities with relationship notes and last mentioned.
- **Timeline:** mood strip per day, sessions and episodes, insights pinned on dates.
- **Conversations:** full archive, searchable (FTS + semantic), filter by date/language/mood. Transcripts can be **corrected** (sets `edited_at`; re-extraction is queued) or **deleted** (propagates, §7). If the audio archive is on, a play button.
- **Patterns:** routines, insights (dismiss = `status='dismissed'`, never shown again), style.
- **Open threads:** open loops (close or drop manually).
- **Lyra:** what she has said about herself.
- **Settings:** audio archive toggle + retention, export, forget.

---

## 7. Edit, forget, export, rebuild
| Action | Effect |
|---|---|
| Correct a transcript | update the `messages` text, set `edited_at`; derived facts with that `source_turn_id` are re-extracted |
| Delete a turn | soft delete now (`deleted_at`). Within 60 s a purge job removes the row, its signals and audio, its `memory_items`/vec/fts rows, and every derived item whose **only** source is that turn. Multi-source items lose that evidence id. Outbox deletes go to Neo4j |
| "Forget that" (voice) | deletes the last user turn **and** what was extracted from it (plan §11.7) |
| Forget a person | deletes the entity, its edges and facts, its open loops, and redacts the name in insights (rewritten by the next reflection) |
| Forget everything | double confirmation. Truncates L0–L4 plus the indexes, Neo4j and `data/audio/`. Keeps only `schema_version` |
| Export | `GET /api/memory/export?include=archive,signals,knowledge,understanding,audio` → a zip with JSONL per table + `audio/` (if on) + a README |
| Rebuild | `make memory-rebuild` re-derives L2–L4 and all indexes from L0+L1 (long; runs niced; resumable via `memory_jobs`) |
| Backup | `make backup` → `data/backups/lyra-full-<ts>.tar.zst` (DB + audio), last 5 kept. The pre-migration backup (plan §11.2) is separate |

Disk encryption is outside the app. The recommendation is to keep `data/` on a LUKS-encrypted disk (the CachyOS default installer offers it). SQLCipher was considered and rejected: sqlite-vec and FTS5 builds would need custom compiling, and a key stored next to the DB adds nothing.

---

## 8. REST additions (plan §14)
| Method | Path | Purpose |
|---|---|---|
| GET | `/api/archive/search?q=&from=&to=&lang=&mode=fts\|semantic\|hybrid` | archive search (quotes with turn ids) |
| GET | `/api/archive/turns/{turn_id}` | a turn with its signals, observations and derived items |
| PATCH | `/api/archive/turns/{turn_id}` | correct a transcript |
| DELETE | `/api/archive/turns/{turn_id}` | delete with propagation |
| GET | `/api/archive/audio/{turn_id}` | Opus stream (404 if archiving is off) |
| GET | `/api/model/insights?kind=&status=` · PATCH `/api/model/insights/{id}` | list / dismiss |
| GET | `/api/model/routines` · `/api/model/style` · `/api/model/mood?from&to` · `/api/model/relationship` | Notebook views |
| GET/PATCH | `/api/model/open-loops[/{id}]` | list / close / drop |
| GET | `/api/model/lyra-self` | her self-statements |
| GET/PATCH | `/api/settings/archive` | `{archive_audio, archive_audio_days}` |

---

## 9. Config (plan §15 additions)
| Var | Default | Meaning |
|---|---|---|
| `ARCHIVE_AUDIO` | `false` | D-48 |
| `ARCHIVE_AUDIO_DAYS` | `365` | 0 = forever |
| `REFLECTION_HOUR` | `4` | local hour for the nightly reflection |
| `REFLECTION_IMPORTANCE_TRIGGER` | `50` | Σ importance since the last reflection |
| `OPEN_LOOP_MAX_FOLLOWUPS` | `2` | then `dropped` |
| `ARCHIVE_RETRIEVAL` | `true` | include archive turns in per-turn retrieval |

---

## 10. Failure handling (plan §16.2 additions)
| # | Failure | Response |
|---|---|---|
| E29 | Archive write fails (disk full, I/O) | EventWriter retries 3×, then holds up to 5,000 rows in RAM and flags health `memory: degraded`. The UI shows a "not saving" rail warning. **The conversation never blocks on the archive** |
| E30 | Reflection invalid JSON or timeout | 1 repair retry → dead-letter; previous insights stay active; retry next night |
| E31 | Audio archive write fails | skip that clip (transcript is still saved), log a warning, health `archive_audio: degraded` |
| E32 | Purge job fails mid-delete | per-turn transaction; the soft-deleted row stays hidden and is retried every 60 s; never re-surfaces in retrieval (queries filter `deleted_at IS NULL`) |

---

## 11. Tests and gates
- **Unit:** schema of each JSON job; consolidation; the importance trigger; open-loop lifecycle (open → followed_up → closed/dropped, max follow-ups); boundary facts always in the profile; profile section order; style hint derivation.
- **Migration:** `003` on a v3 fixture plus a `002` fixture; backfill; idempotent.
- **Data mutation (full coverage, CLAUDE.md):** delete propagation (single- vs multi-source items), forget person, forget everything (no rows, no audio files, no Neo4j nodes), export round-trip.
- **Privacy (S8 extended):** with `ARCHIVE_AUDIO=false`, no Opus/RIFF/PCM/JPEG signatures anywhere. With it on, audio only under `data/audio/`.
- **G4 (extended):** add 20 archive-search probes ("what did I say about X on/around date") in EN/TA/mix: hit@5 ≥ 0.85. Add 10 preference/style probes (the Mem-PAL idea): ≥ 7/10.
- **G10 (new, persona.md §8):** follow-up precision (a follow-up refers to a real open loop, on time) ≥ 90%. Zero boundary violations in the dialog set.
