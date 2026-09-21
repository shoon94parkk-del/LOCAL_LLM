from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")

def test_durable_project_memory_contract():
    for path in (
        "AGENTS.md",
        "docs/project-memory.md",
        "docs/regression-guardrails.md",
        "docs/decision-log.md",
    ):
        assert (ROOT / path).exists(), path

    agents = read("AGENTS.md")
    memory = read("docs/project-memory.md")
    guard = read("docs/regression-guardrails.md")

    for path in ("docs/project-memory.md", "docs/regression-guardrails.md", "docs/decision-log.md"):
        assert path in agents

    for token in ("selenium", "[[END]]", "SQLite FTS5", "240,000", "mock"):
        assert token in memory, token
    for token in ("Internal LLM URL", "serialized", "approval", "conflicting Knowledge", "No silent internet model download"):
        assert token in guard, token
