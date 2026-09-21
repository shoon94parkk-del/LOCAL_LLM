from __future__ import annotations

import hashlib
from pathlib import Path

from app.db import Database


SUPPORTED_SUFFIXES = {".md", ".txt", ".csv", ".json", ".yaml", ".yml"}


class DocumentMemory:
    def __init__(
        self,
        db: Database,
        root: str | Path,
        *,
        chunk_chars: int = 6000,
        overlap_chars: int = 600,
        max_file_chars: int = 5_000_000,
    ):
        self.db = db
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.chunk_chars = max(500, int(chunk_chars))
        self.overlap_chars = max(0, min(int(overlap_chars), self.chunk_chars // 2))
        self.max_file_chars = max(self.chunk_chars, int(max_file_chars))

    def _iter_files(self):
        for path in sorted(self.root.rglob("*")):
            if not path.is_file() or path.is_symlink():
                continue
            try:
                relative = path.relative_to(self.root)
            except ValueError:
                continue
            if any(part.startswith(".") for part in relative.parts):
                continue
            if path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            yield path, relative.as_posix()

    def _read(self, path: Path) -> str:
        with path.open("r", encoding="utf-8") as source:
            content = source.read(self.max_file_chars + 1)
        if len(content) > self.max_file_chars:
            raise ValueError(f"memory file too large: {path.name}")
        return content

    def _chunks(self, content: str) -> list[str]:
        if not content:
            return []
        chunks = []
        start = 0
        length = len(content)
        while start < length:
            end = min(length, start + self.chunk_chars)
            chunk = content[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= length:
                break
            start = end - self.overlap_chars
        return chunks

    @staticmethod
    def _delete_document_index(conn, document_id: int) -> None:
        rows = conn.execute(
            "SELECT id FROM document_chunks WHERE document_id=?", (document_id,)
        ).fetchall()
        chunk_ids = [int(row["id"]) for row in rows]
        if chunk_ids:
            placeholders = ",".join("?" for _ in chunk_ids)
            conn.execute(
                f"DELETE FROM memory_fts WHERE source='document' AND source_id IN ({placeholders})",
                chunk_ids,
            )
        conn.execute("DELETE FROM document_chunks WHERE document_id=?", (document_id,))

    def _index_chunks(self, conn, document_id: int, title: str, chunks: list[str]) -> int:
        for index, chunk in enumerate(chunks):
            cur = conn.execute(
                "INSERT INTO document_chunks(document_id, chunk_index, content) VALUES (?, ?, ?)",
                (document_id, index, chunk),
            )
            chunk_id = int(cur.lastrowid)
            conn.execute(
                "INSERT INTO memory_fts(source, source_id, title, body) VALUES ('document', ?, ?, ?)",
                (chunk_id, title, chunk),
            )
        return len(chunks)

    def sync(self) -> dict:
        files = list(self._iter_files())
        seen_paths = set()
        added = updated = removed = chunks_written = skipped = 0

        with self.db.connect() as conn:
            existing_rows = conn.execute(
                "SELECT id, path, digest FROM documents"
            ).fetchall()
            existing = {str(row["path"]): row for row in existing_rows}

            for path, relative in files:
                seen_paths.add(relative)
                try:
                    content = self._read(path)
                except (OSError, UnicodeDecodeError, ValueError):
                    skipped += 1
                    continue
                digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
                old = existing.get(relative)
                if old is not None and str(old["digest"]) == digest:
                    continue

                pieces = self._chunks(content)
                if old is None:
                    cur = conn.execute(
                        "INSERT INTO documents(path, digest, size) VALUES (?, ?, ?)",
                        (relative, digest, len(content)),
                    )
                    document_id = int(cur.lastrowid)
                    added += 1
                else:
                    document_id = int(old["id"])
                    self._delete_document_index(conn, document_id)
                    conn.execute(
                        "UPDATE documents SET digest=?, size=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                        (digest, len(content), document_id),
                    )
                    updated += 1
                chunks_written += self._index_chunks(
                    conn, document_id, relative, pieces
                )

            for relative, row in existing.items():
                if relative in seen_paths:
                    continue
                document_id = int(row["id"])
                self._delete_document_index(conn, document_id)
                conn.execute("DELETE FROM documents WHERE id=?", (document_id,))
                removed += 1

        return {
            "scanned": len(files),
            "added": added,
            "updated": updated,
            "removed": removed,
            "chunks": chunks_written,
            "skipped": skipped,
            "root": str(self.root),
        }
