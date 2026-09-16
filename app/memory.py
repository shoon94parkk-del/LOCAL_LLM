import re
from difflib import SequenceMatcher
from typing import Any

from app.db import Database


SEARCHABLE_KNOWLEDGE_STATUSES = {"candidate", "validated"}
KNOWLEDGE_STATUSES = SEARCHABLE_KNOWLEDGE_STATUSES | {"conflicted", "rejected"}
AUTO_VALIDATE_CONFIDENCE = 0.72
AUTO_VALIDATE_EVIDENCE = 2
OPPOSITE_PAIRS = (
    ("증가", "감소"),
    ("상승", "하락"),
    ("높", "낮"),
    ("성공", "실패"),
    ("가능", "불가능"),
    ("필요", "불필요"),
)


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db
        self._repair_knowledge_fts()

    @staticmethod
    def _fts_query(text: str) -> str:
        tokens = re.findall(r"[0-9A-Za-z가-힣_]+", text)
        tokens = [token for token in tokens if len(token) > 1][:12]
        return " OR ".join(f'"{token}"' for token in tokens)

    @staticmethod
    def normalize_rule(text: str) -> str:
        return "".join(re.findall(r"[0-9a-z가-힣]+", text.lower()))

    @staticmethod
    def _has_opposite_terms(left: str, right: str) -> bool:
        left, right = left.lower(), right.lower()
        return any(
            (a in left and b in right) or (b in left and a in right)
            for a, b in OPPOSITE_PAIRS
        )

    @classmethod
    def rule_similarity(cls, left: str, right: str) -> float:
        a, b = cls.normalize_rule(left), cls.normalize_rule(right)
        if not a or not b:
            return 0.0
        if a == b:
            return 1.0
        sequence = SequenceMatcher(None, a, b).ratio()
        ta = set(re.findall(r"[0-9A-Za-z가-힣_]+", left.lower()))
        tb = set(re.findall(r"[0-9A-Za-z가-힣_]+", right.lower()))
        union = ta | tb
        jaccard = len(ta & tb) / len(union) if union else 0.0
        score = max(sequence * 0.75 + jaccard * 0.25, jaccard)
        if cls._has_opposite_terms(left, right):
            return min(score, 0.70)
        return score

    def _repair_knowledge_fts(self) -> None:
        with self.db.connect() as conn:
            conn.execute("DELETE FROM memory_fts WHERE source='knowledge'")
            rows = conn.execute(
                "SELECT id, rule FROM knowledge WHERE status IN ('candidate','validated')"
            ).fetchall()
            conn.executemany(
                "INSERT INTO memory_fts(source, source_id, title, body) VALUES ('knowledge', ?, 'knowledge rule', ?)",
                [(int(row["id"]), row["rule"]) for row in rows],
            )

    @staticmethod
    def _sync_knowledge_fts(conn, knowledge_id: int) -> None:
        conn.execute(
            "DELETE FROM memory_fts WHERE source='knowledge' AND source_id=?",
            (knowledge_id,),
        )
        row = conn.execute(
            "SELECT rule, status FROM knowledge WHERE id=?", (knowledge_id,)
        ).fetchone()
        if row and row["status"] in SEARCHABLE_KNOWLEDGE_STATUSES:
            conn.execute(
                "INSERT INTO memory_fts(source, source_id, title, body) VALUES ('knowledge', ?, 'knowledge rule', ?)",
                (knowledge_id, row["rule"]),
            )

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

    def add_knowledge(
        self, rule: str, confidence: float = 0.5, status: str = "candidate"
    ) -> int:
        rule = rule.strip()
        if not rule:
            raise ValueError("knowledge rule is required")
        if status not in KNOWLEDGE_STATUSES:
            raise ValueError("invalid knowledge status")
        confidence = min(1.0, max(0.0, float(confidence)))
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO knowledge(rule, confidence, status) VALUES (?, ?, ?)",
                (rule, confidence, status),
            )
            knowledge_id = int(cur.lastrowid)
            self._sync_knowledge_fts(conn, knowledge_id)
            return knowledge_id

    def get_knowledge(self, knowledge_id: int) -> dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT id, created_at, rule, confidence, evidence_count, status FROM knowledge WHERE id=?",
                (knowledge_id,),
            ).fetchone()
            if row is None:
                raise KeyError(knowledge_id)
            result = dict(row)
            evidence = conn.execute(
                "SELECT case_id, relation FROM knowledge_evidence WHERE knowledge_id=? ORDER BY case_id",
                (knowledge_id,),
            ).fetchall()
            relations = conn.execute(
                "SELECT target_id, relation, detail FROM knowledge_relations WHERE source_id=? ORDER BY target_id",
                (knowledge_id,),
            ).fetchall()
        result["evidence"] = [dict(item) for item in evidence]
        result["relations"] = [dict(item) for item in relations]
        return result

    def list_knowledge(
        self, limit: int = 50, statuses: list[str] | tuple[str, ...] | None = None
    ) -> list[dict[str, Any]]:
        limit = max(1, min(int(limit), 500))
        statuses = list(statuses or [])
        with self.db.connect() as conn:
            if statuses:
                valid = [status for status in statuses if status in KNOWLEDGE_STATUSES]
                if not valid:
                    return []
                placeholders = ",".join("?" for _ in valid)
                rows = conn.execute(
                    f"SELECT id, created_at, rule, confidence, evidence_count, status FROM knowledge WHERE status IN ({placeholders}) ORDER BY id DESC LIMIT ?",
                    (*valid, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT id, created_at, rule, confidence, evidence_count, status FROM knowledge ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [dict(row) for row in rows]

    def set_knowledge_status(self, knowledge_id: int, status: str) -> dict[str, Any]:
        if status not in KNOWLEDGE_STATUSES:
            raise ValueError("invalid knowledge status")
        with self.db.connect() as conn:
            if conn.execute(
                "SELECT 1 FROM knowledge WHERE id=?", (knowledge_id,)
            ).fetchone() is None:
                raise KeyError(knowledge_id)
            conn.execute(
                "UPDATE knowledge SET status=? WHERE id=?", (status, knowledge_id)
            )
            self._sync_knowledge_fts(conn, knowledge_id)
        return self.get_knowledge(knowledge_id)

    @classmethod
    def _best_similar(cls, rule: str, rows, threshold: float = 0.93):
        best = None
        best_score = 0.0
        for row in rows:
            score = cls.rule_similarity(rule, row["rule"])
            if score > best_score:
                best, best_score = row, score
        if best is not None and best_score >= threshold:
            return {**dict(best), "similarity": best_score}
        return None

    def find_similar_knowledge(
        self, rule: str, threshold: float = 0.93
    ) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, rule, confidence, evidence_count, status FROM knowledge WHERE status IN ('candidate','validated')"
            ).fetchall()
        return self._best_similar(rule, rows, threshold)

    @staticmethod
    def _valid_case_ids(conn, case_ids) -> list[int]:
        unique = set()
        for value in case_ids:
            try:
                case_id = int(value)
            except (TypeError, ValueError):
                continue
            if case_id > 0:
                unique.add(case_id)
        if not unique:
            return []
        ordered = sorted(unique)
        placeholders = ",".join("?" for _ in ordered)
        rows = conn.execute(
            f"SELECT id FROM cases WHERE id IN ({placeholders})", ordered
        ).fetchall()
        return [int(row["id"]) for row in rows]

    @staticmethod
    def _promoted_status(
        status: str, confidence: float, tracked_case_count: int
    ) -> str:
        if status == "validated":
            return status
        if (
            status == "candidate"
            and confidence >= AUTO_VALIDATE_CONFIDENCE
            and tracked_case_count >= AUTO_VALIDATE_EVIDENCE
        ):
            return "validated"
        return status

    def upsert_knowledge_candidate(
        self,
        rule: str,
        confidence: float,
        evidence_case_ids=(),
        relation: str = "new",
        target_knowledge_id: int | None = None,
    ) -> dict[str, Any]:
        rule = rule.strip()
        if not rule:
            raise ValueError("knowledge rule is required")
        confidence = min(1.0, max(0.0, float(confidence)))
        if relation not in {"new", "duplicate", "supports", "conflicts"}:
            relation = "new"

        with self.db.connect() as conn:
            valid_case_ids = self._valid_case_ids(conn, evidence_case_ids)
            target = None
            if target_knowledge_id is not None:
                target = conn.execute(
                    "SELECT id, rule, confidence, evidence_count, status FROM knowledge WHERE id=?",
                    (int(target_knowledge_id),),
                ).fetchone()

            duplicate = None
            if relation != "conflicts":
                if (
                    target is not None
                    and target["status"] in SEARCHABLE_KNOWLEDGE_STATUSES
                    and relation == "duplicate"
                    and self.rule_similarity(rule, target["rule"]) >= 0.72
                ):
                    duplicate = dict(target)
                if duplicate is None:
                    rows = conn.execute(
                        "SELECT id, rule, confidence, evidence_count, status FROM knowledge WHERE status IN ('candidate','validated')"
                    ).fetchall()
                    duplicate = self._best_similar(rule, rows)

            if duplicate is not None:
                knowledge_id = int(duplicate["id"])
                for case_id in valid_case_ids:
                    conn.execute(
                        "INSERT OR IGNORE INTO knowledge_evidence(knowledge_id, case_id, relation) VALUES (?, ?, 'supports')",
                        (knowledge_id, case_id),
                    )
                tracked_count = int(
                    conn.execute(
                        "SELECT COUNT(DISTINCT case_id) AS n FROM knowledge_evidence WHERE knowledge_id=? AND relation='supports'",
                        (knowledge_id,),
                    ).fetchone()["n"]
                )
                evidence_count = max(
                    int(duplicate["evidence_count"]), tracked_count, 1
                )
                merged_confidence = max(float(duplicate["confidence"]), confidence)
                status = self._promoted_status(
                    str(duplicate["status"]), merged_confidence, tracked_count
                )
                conn.execute(
                    "UPDATE knowledge SET confidence=?, evidence_count=?, status=? WHERE id=?",
                    (merged_confidence, evidence_count, status, knowledge_id),
                )
                self._sync_knowledge_fts(conn, knowledge_id)
                return {
                    "action": "merged",
                    "knowledge_id": knowledge_id,
                    "rule": duplicate["rule"],
                    "confidence": merged_confidence,
                    "evidence_count": evidence_count,
                    "tracked_case_count": tracked_count,
                    "status": status,
                }

            status = (
                "conflicted"
                if target is not None and relation == "conflicts"
                else "candidate"
            )
            tracked_count = len(valid_case_ids)
            evidence_count = max(1, tracked_count)
            status = self._promoted_status(status, confidence, tracked_count)
            cur = conn.execute(
                "INSERT INTO knowledge(rule, confidence, evidence_count, status) VALUES (?, ?, ?, ?)",
                (rule, confidence, evidence_count, status),
            )
            knowledge_id = int(cur.lastrowid)
            for case_id in valid_case_ids:
                conn.execute(
                    "INSERT OR IGNORE INTO knowledge_evidence(knowledge_id, case_id, relation) VALUES (?, ?, 'supports')",
                    (knowledge_id, case_id),
                )
            if target is not None and relation in {"supports", "conflicts"}:
                conn.execute(
                    "INSERT OR IGNORE INTO knowledge_relations(source_id, target_id, relation, detail) VALUES (?, ?, ?, ?)",
                    (knowledge_id, int(target["id"]), relation, "reflection"),
                )
            self._sync_knowledge_fts(conn, knowledge_id)
            return {
                "action": "created",
                "knowledge_id": knowledge_id,
                "rule": rule,
                "confidence": confidence,
                "evidence_count": evidence_count,
                "tracked_case_count": tracked_count,
                "status": status,
                "relation": relation,
                "target_knowledge_id": int(target["id"]) if target is not None else None,
            }

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
            if status not in {"resolved", "failed"}:
                return
            existing = conn.execute(
                "SELECT id FROM cases WHERE conversation_id=?", (conversation_id,)
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
                (
                    "case",
                    case_id,
                    row["question"],
                    f"{row['answer']}\nOutcome: {note}\nStatus: {status}",
                ),
            )

    @staticmethod
    def _enrich_row(conn, row: dict[str, Any]) -> dict[str, Any] | None:
        item = dict(row)
        source, source_id = item["source"], int(item["source_id"])
        quality = 1.0
        if source == "knowledge":
            meta = conn.execute(
                "SELECT confidence, evidence_count, status FROM knowledge WHERE id=?",
                (source_id,),
            ).fetchone()
            if meta is None or meta["status"] not in SEARCHABLE_KNOWLEDGE_STATUSES:
                return None
            item.update(
                confidence=float(meta["confidence"]),
                evidence_count=int(meta["evidence_count"]),
                status=meta["status"],
            )
            quality = (
                1.25 + 0.25 * float(meta["confidence"])
                if meta["status"] == "validated"
                else 0.72 + 0.18 * float(meta["confidence"])
            )
        elif source == "case":
            meta = conn.execute(
                "SELECT status FROM cases WHERE id=?", (source_id,)
            ).fetchone()
            quality = 1.14 if meta and meta["status"] == "resolved" else 0.88
        elif source == "conversation":
            meta = conn.execute(
                "SELECT feedback, importance FROM conversations WHERE id=?",
                (source_id,),
            ).fetchone()
            if meta:
                if int(meta["importance"]):
                    quality = 1.16
                elif meta["feedback"] == "resolved":
                    quality = 1.08
                elif meta["feedback"] == "failed":
                    quality = 0.84
        item["memory_quality"] = quality
        return item

    def enrich_result(self, row: dict[str, Any]) -> dict[str, Any] | None:
        with self.db.connect() as conn:
            return self._enrich_row(conn, row)

    def search(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        fts_query = self._fts_query(query)
        if not fts_query:
            return []
        candidate_limit = max(limit * 4, 20)
        with self.db.connect() as conn:
            rows = conn.execute(
                """
                SELECT source, source_id, title, body, bm25(memory_fts) AS rank
                FROM memory_fts
                WHERE memory_fts MATCH ?
                ORDER BY rank ASC
                LIMIT ?
                """,
                (fts_query, candidate_limit),
            ).fetchall()
            enriched = []
            for index, row in enumerate(rows):
                item = self._enrich_row(conn, dict(row))
                if item is None:
                    continue
                item["retrieval_score"] = item["memory_quality"] / (61 + index)
                enriched.append(item)
        enriched.sort(key=lambda item: item["retrieval_score"], reverse=True)
        return enriched[:limit]

    def recent(self, limit: int = 20) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, question, answer, feedback, feedback_note, importance FROM conversations ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]

    def recent_cases(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT id, created_at, problem, solution, outcome, status, tags FROM cases ORDER BY id DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(row) for row in rows]
