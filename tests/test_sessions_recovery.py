import asyncio
import json

from fastapi.testclient import TestClient

from app.agent import Agent
from app.config import Settings
from app.db import Database
from app.embeddings import HybridRetriever
from app.main import create_app
from app.memory import MemoryStore
from app.sessions import SessionStore


class RecordingLLM:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.prompts = []

    async def generate(self, prompt):
        self.prompts.append(prompt)
        return next(self.responses)


def cfg(tmp_path, **kwargs):
    kwargs.setdefault("agent_require_approval", False)
    return Settings(
        _env_file=None,
        db_path=str(tmp_path / "db.sqlite"),
        agent_workspace=str(tmp_path / "workspace"),
        **kwargs,
    )


def test_session_store_persists_messages(tmp_path):
    store = SessionStore(Database(str(tmp_path / "db.sqlite")))
    session = store.create("Air Dome 분석")
    store.add_message(session["id"], "user", "첫 질문")
    store.add_message(session["id"], "assistant", "첫 답변")

    loaded = store.get(session["id"])
    assert loaded["title"] == "Air Dome 분석"
    assert [item["role"] for item in loaded["messages"]] == ["user", "assistant"]
    assert [item["content"] for item in loaded["messages"]] == ["첫 질문", "첫 답변"]


def test_agent_includes_previous_session_messages_in_followup_prompt(tmp_path):
    config = cfg(tmp_path)
    db = Database(config.db_path)
    memory = MemoryStore(db)
    sessions = SessionStore(db)
    session = sessions.create("압력 분석")
    sessions.add_message(session["id"], "user", "Zone 3 압력을 올렸다")
    sessions.add_message(session["id"], "assistant", "C5 변화를 확인해라")

    llm = RecordingLLM([
        json.dumps({"tool": "finish", "arguments": {"answer": "후속 분석 완료"}}, ensure_ascii=False)
    ])
    agent = Agent(config, memory, HybridRetriever(memory), llm, sessions=sessions)
    result = asyncio.run(agent.run("그 다음 뭘 볼까?", session_id=session["id"]))

    assert result["status"] == "completed"
    assert result["session_id"] == session["id"]
    assert "Zone 3 압력을 올렸다" in llm.prompts[0]
    assert "C5 변화를 확인해라" in llm.prompts[0]
    loaded = sessions.get(session["id"])
    assert loaded["messages"][-2]["content"] == "그 다음 뭘 볼까?"
    assert loaded["messages"][-1]["content"] == "후속 분석 완료"


def test_agent_marks_stale_running_runs_interrupted_on_startup(tmp_path):
    config = cfg(tmp_path)
    db = Database(config.db_path)
    memory = MemoryStore(db)
    with db.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS agent_runs (id TEXT PRIMARY KEY, payload TEXT NOT NULL)"
        )
        conn.execute(
            "INSERT INTO agent_runs(id, payload) VALUES (?, ?)",
            ("stale", json.dumps({"id": "stale", "goal": "test", "status": "running", "steps": [], "answer": ""})),
        )

    agent = Agent(config, memory, HybridRetriever(memory), RecordingLLM([]))
    recovered = agent.get("stale")
    assert recovered["status"] == "interrupted"
    assert "interrupted_at" in recovered


def test_session_api_creates_and_reuses_session(tmp_path):
    client = TestClient(create_app(cfg(tmp_path)))
    created = client.post("/api/sessions", json={"title": "본더 조사"})
    assert created.status_code == 200
    session_id = created.json()["id"]

    run = client.post(
        "/api/agent/run",
        json={"question": "Edge void 조사", "session_id": session_id},
    )
    assert run.status_code == 200
    assert run.json()["session_id"] == session_id

    loaded = client.get(f"/api/sessions/{session_id}")
    assert loaded.status_code == 200
    messages = loaded.json()["messages"]
    assert messages[0]["role"] == "user"
    assert messages[-1]["role"] == "assistant"
