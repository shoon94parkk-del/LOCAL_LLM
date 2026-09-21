from __future__ import annotations

import uuid
from typing import Any

from app.db import Database


class SessionStore:
    def __init__(self, db: Database):
        self.db = db

    def create(self, title: str = "새 작업") -> dict[str, Any]:
        title = (title or "새 작업").strip()[:200] or "새 작업"
        session_id = uuid.uuid4().hex
        with self.db.connect() as conn:
            conn.execute(
                "INSERT INTO sessions(id, title) VALUES (?, ?)",
                (session_id, title),
            )
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
        return dict(row)

    def _require(self, session_id: str):
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, title, created_at, updated_at FROM sessions WHERE id=?",
                (session_id,),
            ).fetchone()
        if row is None:
            raise KeyError(session_id)
        return row

    def add_message(self, session_id: str, role: str, content: str) -> int:
        if role not in {"user", "assistant", "system"}:
            raise ValueError("invalid session message role")
        content = str(content).strip()
        if not content:
            raise ValueError("session message content is required")
        self._require(session_id)
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO session_messages(session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content),
            )
            conn.execute(
                "UPDATE sessions SET updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (session_id,),
            )
            return int(cur.lastrowid)

    def messages(self, session_id: str, limit: int = 30) -> list[dict[str, Any]]:
        self._require(session_id)
        limit = max(1, min(int(limit), 200))
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, role, content, created_at FROM ("
                "SELECT id, role, content, created_at FROM session_messages "
                "WHERE session_id=? ORDER BY id DESC LIMIT ?"
                ") ORDER BY id ASC",
                (session_id, limit),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, session_id: str, message_limit: int = 100) -> dict[str, Any]:
        row = self._require(session_id)
        result = dict(row)
        result["messages"] = self.messages(session_id, message_limit)
        return result

    def list(self, limit: int = 30) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 100))
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT s.id, s.title, s.created_at, s.updated_at, "
                "COUNT(m.id) AS message_count "
                "FROM sessions s LEFT JOIN session_messages m ON m.session_id=s.id "
                "GROUP BY s.id ORDER BY s.updated_at DESC, s.rowid DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def context(self, session_id: str, limit: int = 12, max_chars: int = 60_000) -> list[dict[str, str]]:
        messages = self.messages(session_id, limit)
        selected: list[dict[str, str]] = []
        used = 0
        for item in reversed(messages):
            content = str(item["content"])
            if used + len(content) > max_chars and selected:
                break
            if len(content) > max_chars:
                content = content[-max_chars:]
            selected.append({"role": str(item["role"]), "content": content})
            used += len(content)
        selected.reverse()
        return selected
