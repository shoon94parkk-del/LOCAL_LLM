import asyncio

import pytest
from pydantic import ValidationError

from app.agent import Action, Agent
from app.config import Settings
from app.db import Database
from app.embeddings import HybridRetriever
from app.main import ChatRequest, create_app
from app.memory import MemoryStore
from app.llm.selenium_adapter import SeleniumGLM


class CapturingLLM:
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
        db_path=str(tmp_path / "memory.db"),
        agent_workspace=str(tmp_path / "workspace"),
        **kwargs,
    )


def test_chat_request_accepts_240k_characters():
    assert len(ChatRequest(question="x" * 240_000).question) == 240_000
    with pytest.raises(ValidationError):
        ChatRequest(question="x" * 240_001)


def test_agent_text_tools_accept_up_to_240k_characters(tmp_path):
    settings = cfg(tmp_path)
    memory = MemoryStore(Database(settings.db_path))
    agent = Agent(settings, memory, HybridRetriever(memory), CapturingLLM([]))
    run = {"id": "limit-test", "steps": []}

    payload = "가" * 150_000
    result = asyncio.run(
        agent.execute(Action(tool="write_file", arguments={"path": "large.txt", "content": payload}), run)
    )
    assert result["verified"] is True
    assert asyncio.run(agent.execute(Action(tool="read_file", arguments={"path": "large.txt"}), run)) == payload

    report = "나" * 60_000
    report_result = asyncio.run(
        agent.execute(Action(tool="write_report", arguments={"content": report}), run)
    )
    assert report_result["verified"] is True


def test_agent_keeps_tool_results_larger_than_old_12k_limit(tmp_path):
    settings = cfg(tmp_path, agent_max_steps=3)
    memory = MemoryStore(Database(settings.db_path))
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    marker = "TAIL-MARKER-EXPECTED-IN-NEXT-PROMPT"
    (workspace / "long.txt").write_text("a" * 20_000 + marker, encoding="utf-8")

    llm = CapturingLLM(
        [
            '{"tool":"read_file","arguments":{"path":"long.txt"}}',
            '{"tool":"finish","arguments":{"answer":"done"}}',
        ]
    )
    agent = Agent(settings, memory, HybridRetriever(memory), llm)
    result = asyncio.run(agent.run("read it"))

    assert result["status"] == "completed"
    assert marker in llm.prompts[1]


def test_selenium_adapter_is_lazy_and_async_safe(tmp_path):
    adapter = SeleniumGLM(
        "http://internal-llm.local:8501/",
        timeout_ms=1_800_000,
        input_selector="textarea",
        response_selector="[data-testid='stChatMessage']",
    )
    assert adapter.url == "http://internal-llm.local:8501/"
    assert adapter._driver is None

    adapter._generate_sync = lambda prompt: "answer"
    assert asyncio.run(adapter.generate("hello")) == "answer"


def test_create_app_accepts_selenium_mode_without_starting_browser(tmp_path):
    settings = cfg(
        tmp_path,
        glm_mode="selenium",
        glm_url="http://internal-llm.local:8501/",
        glm_timeout_ms=1_800_000,
    )
    app = create_app(settings)
    assert isinstance(app.state.llm, SeleniumGLM)
    assert app.state.llm._driver is None
