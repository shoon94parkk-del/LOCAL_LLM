import re
from typing import Any

from app.db import Database


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db

    @staticmethod
    def _fts_query(text: str) -> str:
        tokens = re.findall(r"[0-9A-Za-z가-힣_]+", text)
        tokens = [t for t in tokens if len(t) > 1][:12]
        return " OR ".join(f'"{t}"' for t in tokens)

    def add_conversation(self, question: str, answer: str) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO conversations(question, answer) VALUES (?, ?)",
                (question, answer),
            )
            conversation_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO memory_fts(source, source_id, title, body) VALUES (?, ?, ?, ?)",
                ("conversation", conversation_id, question, answer),
            )
            return conversation_id

    def add_knowledge(self, rule: str, confidence: float = 0.5, status: str = "candidate") -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO knowledge(rule, confidence, status) VALUES (?, ?, ?)",
                (rule, confidence, status),
            )
            knowledge_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO memory_fts(source, source_id, title, body) VALUES (?, ?, ?, ?)",
                ("knowledge", knowledge_id, "knowledge rule", rule),
            )
            return knowledge_id

    def set_feedback(self, conversation_id: int, status: str, note: str = "") -> None:
        if status not in {"resolved", "failed", "important"}:
            raise ValueError("status must be resolved, failed, or important")

        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT question, answer FROM conversations WHERE id=?",
                (conversation_id,),
            ).fetchone()
            if row is None:
                raise KeyError(conversation_id)

            conn.execute(
                "UPDATE conversations SET feedback=?, feedback_note=?, importance=? WHERE id=?",
                (status, note, 1 if status == "important" else 0, conversation_id),
            )

            if status in {"resolved", "failed"}:
                existing = conn.execute(
                    "SELECT id FROM cases WHERE conversation_id=?",
                    (conversation_id,),
                ).fetchone()
                if existing:
                    case_id = int(existing["id"])
                    conn.execute(
                        "UPDATE cases SET problem=?, solution=?, outcome=?, status=? WHERE id=?",
                        (row["question"], row["answer"], note, status, case_id),
                    )
                    conn.execute(
                        "DELETE FROM memory_fts WHERE source='case' AND source_id=?",
                        (case_id,),
                    )
                else:
                    cur = conn.execute(
                        "INSERT INTO cases(conversation_id, problem, solution, outcome, status) VALUES (?, ?, ?, ?, ?)",
                        (conversation_id, row["question"], row["answer"], note, status),
                    )
                    case_id = int(cur.lastrowid)

                conn.execute(
                    "INSERT INTO memory_fts(source, source_id, title, body) VALUES (?, ?, ?, ?)",
                    ("case", case_id, row["question"], f"{row['answer']}\nOutcome: {note}\nStatus: {status}"),
                )

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        fts_query = self._fts_query(query)
        if not fts_query:
            return []

        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT source, source_id, title, body, bm25(memory_fts) AS rank
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (fts_query, limit),
            ).fetchall()

        return [dict(row) for row in rows]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, question, answer, feedback, feedback_note, importance FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
