"""SQLite persistence for sessions, events, and transitional memory artifacts."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT 'New conversation',
    persona TEXT NOT NULL DEFAULT 'medusa',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, id);

CREATE TABLE IF NOT EXISTS conversation_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    role TEXT CHECK (role IN ('user', 'assistant')),
    content TEXT,
    message_type TEXT,
    language TEXT,
    emotion_label TEXT,
    emotion_confidence REAL,
    metadata_json TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_conversation_events_session
    ON conversation_events(session_id, id);

CREATE TABLE IF NOT EXISTS memory_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT REFERENCES sessions(id) ON DELETE CASCADE,
    artifact_type TEXT NOT NULL,
    content TEXT NOT NULL,
    canonical_key TEXT,
    confidence REAL NOT NULL DEFAULT 0.5,
    provenance_event_id INTEGER REFERENCES conversation_events(id) ON DELETE SET NULL,
    metadata_json TEXT,
    valid_from TEXT NOT NULL,
    valid_to TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memory_artifacts_session
    ON memory_artifacts(session_id, id);
CREATE INDEX IF NOT EXISTS idx_memory_artifacts_key
    ON memory_artifacts(canonical_key, id);
CREATE INDEX IF NOT EXISTS idx_memory_artifacts_status
    ON memory_artifacts(status, valid_to);

-- Rolling per-conversation summaries for personas with cross-session memory (Friend).
CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    persona TEXT NOT NULL,
    session_id TEXT,
    summary TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_memories_persona ON memories(persona, id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, path: Path):
        self.path = path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(self.path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA foreign_keys = ON")
        await self._db.executescript(_SCHEMA)
        await self._migrate()
        await self._db.commit()

    async def _migrate(self) -> None:
        """Add columns introduced after the first release to pre-existing DBs."""
        cur = await self._db.execute("PRAGMA table_info(sessions)")
        columns = {row["name"] for row in await cur.fetchall()}
        if "persona" not in columns:
            await self._db.execute(
                "ALTER TABLE sessions ADD COLUMN persona TEXT NOT NULL DEFAULT 'medusa'"
            )

        cur = await self._db.execute("PRAGMA table_info(conversation_events)")
        event_columns = {row["name"] for row in await cur.fetchall()}
        event_additions = {
            "message_type": "TEXT",
            "language": "TEXT",
            "emotion_label": "TEXT",
            "emotion_confidence": "REAL",
            "metadata_json": "TEXT",
        }
        for name, sql_type in event_additions.items():
            if name not in event_columns:
                await self._db.execute(
                    f"ALTER TABLE conversation_events ADD COLUMN {name} {sql_type}"
                )

    async def record_event(
        self,
        session_id: str,
        event_type: str,
        *,
        role: str | None = None,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        payload = metadata or {}
        created_at = payload.get("created_at", _now())
        cur = await self.db.execute(
            """INSERT INTO conversation_events
               (
                   session_id,
                   event_type,
                   role,
                   content,
                   message_type,
                   language,
                   emotion_label,
                   emotion_confidence,
                   metadata_json,
                   created_at
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                event_type,
                role,
                content,
                payload.get("message_type"),
                payload.get("language"),
                payload.get("emotion_label"),
                payload.get("emotion_confidence"),
                json.dumps(payload, ensure_ascii=True) if payload else None,
                created_at,
            ),
        )
        await self.db.commit()
        return int(cur.lastrowid)

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Database not connected"
        return self._db

    async def create_session(self, persona: str = "medusa") -> str:
        session_id = str(uuid.uuid4())
        await self.db.execute(
            "INSERT INTO sessions (id, persona, created_at) VALUES (?, ?, ?)",
            (session_id, persona, _now()),
        )
        await self.db.commit()
        return session_id

    async def session_exists(self, session_id: str) -> bool:
        cur = await self.db.execute("SELECT 1 FROM sessions WHERE id = ?", (session_id,))
        return await cur.fetchone() is not None

    async def get_session_persona(self, session_id: str) -> str | None:
        cur = await self.db.execute(
            "SELECT persona FROM sessions WHERE id = ?", (session_id,)
        )
        row = await cur.fetchone()
        return row["persona"] if row else None

    async def list_sessions(self) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """SELECT s.id, s.title, s.persona, s.created_at, COUNT(m.id) AS message_count
               FROM sessions s LEFT JOIN messages m ON m.session_id = s.id
               GROUP BY s.id ORDER BY s.created_at DESC"""
        )
        return [dict(r) for r in await cur.fetchall()]

    async def delete_session(self, session_id: str) -> bool:
        cur = await self.db.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        payload = metadata or {}
        created_at = payload.get("created_at", _now())
        await self.db.execute(
            "INSERT INTO messages (session_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (session_id, role, content, created_at),
        )
        await self.record_event(
            session_id,
            "message",
            role=role,
            content=content,
            metadata={
                **payload,
                "message_type": payload.get("message_type", "final"),
                "created_at": created_at,
            },
        )
        # First user message becomes the session title
        if role == "user":
            await self.db.execute(
                """UPDATE sessions SET title = ?
                   WHERE id = ? AND title = 'New conversation'""",
                (content[:60], session_id),
            )
        await self.db.commit()

    async def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY id",
            (session_id,),
        )
        return [dict(r) for r in await cur.fetchall()]

    async def get_events(self, session_id: str) -> list[dict[str, Any]]:
        cur = await self.db.execute(
            """SELECT
                   id,
                   event_type,
                   role,
                   content,
                   message_type,
                   language,
                   emotion_label,
                   emotion_confidence,
                   metadata_json,
                   created_at
               FROM conversation_events
               WHERE session_id = ?
               ORDER BY id""",
            (session_id,),
        )
        events = []
        for row in await cur.fetchall():
            event = dict(row)
            raw_metadata = event.pop("metadata_json", None)
            event["metadata"] = json.loads(raw_metadata) if raw_metadata else {}
            events.append(event)
        return events

    async def save_memory_artifact(
        self,
        *,
        session_id: str,
        artifact_type: str,
        content: str,
        canonical_key: str | None = None,
        confidence: float = 0.5,
        provenance_event_id: int | None = None,
        metadata: dict[str, Any] | None = None,
        valid_from: str | None = None,
        valid_to: str | None = None,
        status: str = "active",
    ) -> int:
        now = _now()
        cur = await self.db.execute(
            """INSERT INTO memory_artifacts
               (
                   session_id,
                   artifact_type,
                   content,
                   canonical_key,
                   confidence,
                   provenance_event_id,
                   metadata_json,
                   valid_from,
                   valid_to,
                   status,
                   created_at,
                   updated_at
               )
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                session_id,
                artifact_type,
                content,
                canonical_key,
                confidence,
                provenance_event_id,
                json.dumps(metadata or {}, ensure_ascii=True),
                valid_from or now,
                valid_to,
                status,
                now,
                now,
            ),
        )
        artifact_id = int(cur.lastrowid)
        await self.db.commit()
        return artifact_id

    async def list_memory_artifacts(
        self,
        *,
        session_id: str | None = None,
        artifact_type: str | None = None,
        only_active: bool = False,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        clauses: list[str] = []
        params: list[Any] = []
        if session_id is not None:
            clauses.append("session_id = ?")
            params.append(session_id)
        if artifact_type is not None:
            clauses.append("artifact_type = ?")
            params.append(artifact_type)
        if only_active:
            clauses.append("status = 'active' AND valid_to IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = await self.db.execute(
            f"""SELECT *
                FROM memory_artifacts
                {where}
                ORDER BY id DESC
                LIMIT ?""",
            (*params, limit),
        )
        artifacts = []
        for row in await cur.fetchall():
            artifact = dict(row)
            raw_metadata = artifact.pop("metadata_json", None)
            artifact["metadata"] = json.loads(raw_metadata) if raw_metadata else {}
            artifacts.append(artifact)
        return artifacts

    async def invalidate_memory_artifacts(
        self,
        *,
        canonical_key: str,
        replacement_artifact_id: int | None = None,
        invalidated_at: str | None = None,
        exclude_artifact_id: int | None = None,
    ) -> None:
        now = invalidated_at or _now()
        metadata = {}
        if replacement_artifact_id is not None:
            metadata["replacement_artifact_id"] = replacement_artifact_id
        exclude_clause = ""
        params: list[Any] = [
            now,
            now,
            json.dumps(metadata, ensure_ascii=True) if metadata else "{}",
            replacement_artifact_id,
            canonical_key,
        ]
        if exclude_artifact_id is not None:
            exclude_clause = " AND id != ?"
            params.append(exclude_artifact_id)
        await self.db.execute(
            """UPDATE memory_artifacts
               SET valid_to = ?,
                   status = 'superseded',
                   updated_at = ?,
                   metadata_json = CASE
                       WHEN metadata_json IS NULL OR metadata_json = ''
                           THEN ?
                       ELSE json_set(metadata_json, '$.replacement_artifact_id', ?)
                   END
               WHERE canonical_key = ?
                 AND status = 'active'
                 AND valid_to IS NULL"""
            + exclude_clause,
            params,
        )
        await self.db.commit()

    # ---- cross-session memory (Friend persona) ----

    async def save_memory(self, persona: str, session_id: str | None, summary: str) -> None:
        await self.db.execute(
            "INSERT INTO memories (persona, session_id, summary, created_at) VALUES (?, ?, ?, ?)",
            (persona, session_id, summary, _now()),
        )
        await self.db.commit()

    async def get_memories(self, persona: str, limit: int = 12) -> list[str]:
        """Most recent memory summaries for a persona, oldest-first for prompt order."""
        cur = await self.db.execute(
            "SELECT summary FROM memories WHERE persona = ? ORDER BY id DESC LIMIT ?",
            (persona, limit),
        )
        rows = await cur.fetchall()
        return [r["summary"] for r in reversed(rows)]

    async def has_memory_for_session(self, session_id: str) -> bool:
        cur = await self.db.execute(
            "SELECT 1 FROM memories WHERE session_id = ?", (session_id,)
        )
        return await cur.fetchone() is not None
