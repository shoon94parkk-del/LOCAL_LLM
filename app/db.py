import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    feedback TEXT,
    feedback_note TEXT,
    importance INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS cases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id INTEGER UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    problem TEXT NOT NULL,
    solution TEXT NOT NULL,
    outcome TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    tags TEXT
);

CREATE TABLE IF NOT EXISTS knowledge (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    rule TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0.5,
    evidence_count INTEGER NOT NULL DEFAULT 1,
    status TEXT NOT NULL DEFAULT 'candidate'
);

CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(
    source,
    source_id UNINDEXED,
    title,
    body,
    tokenize='unicode61'
);
"""


class Database:
    def __init__(self, path: str):
        self.path = path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA)
