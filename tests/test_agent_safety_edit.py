import asyncio

import pytest

from app.agent import Action, Agent
from app.config import Settings
from app.db import Database
from app.embeddings import HybridRetriever
from app.memory import MemoryStore


class NoopLLM:
    async def generate(self, prompt):
        raise AssertionError("LLM should not be called")


def build_agent(tmp_path, *, approval=False):
    cfg = Settings(
        _env_file=None,
        db_path=str(tmp_path / "db.sqlite"),
        agent_workspace=str(tmp_path / "workspace"),
        agent_require_approval=approval,
    )
    memory = MemoryStore(Database(cfg.db_path))
    return Agent(cfg, memory, HybridRetriever(memory), NoopLLM())


def test_edit_file_replaces_one_exact_region_and_returns_diff(tmp_path):
    agent = build_agent(tmp_path)
    target = agent.root / "note.md"
    target.write_text("before\nZone 3 pressure\nafter\n", encoding="utf-8")
    result = asyncio.run(
        agent.execute(
            Action(
                tool="edit_file",
                arguments={
                    "path": "note.md",
                    "old_text": "Zone 3 pressure",
                    "new_text": "Zone 5 pressure",
                },
            ),
            {"id": "edit", "steps": []},
        )
    )

    assert target.read_text(encoding="utf-8") == "before\nZone 5 pressure\nafter\n"
    assert result["verified"] is True
    assert result["before_sha256"] != result["after_sha256"]
    assert "-Zone 3 pressure" in result["diff"]
    assert "+Zone 5 pressure" in result["diff"]


def test_edit_file_rejects_ambiguous_or_missing_match(tmp_path):
    agent = build_agent(tmp_path)
    target = agent.root / "note.txt"
    target.write_text("same\nsame\n", encoding="utf-8")

    with pytest.raises(ValueError, match="정확히 한 번"):
        asyncio.run(
            agent.execute(
                Action(tool="edit_file", arguments={"path": "note.txt", "old_text": "same", "new_text": "new"}),
                {"id": "edit", "steps": []},
            )
        )
    with pytest.raises(ValueError, match="찾지 못"):
        asyncio.run(
            agent.execute(
                Action(tool="edit_file", arguments={"path": "note.txt", "old_text": "missing", "new_text": "new"}),
                {"id": "edit", "steps": []},
            )
        )


def test_edit_file_requires_agent_approval_before_execution(tmp_path):
    agent = build_agent(tmp_path, approval=True)
    target = agent.root / "note.md"
    target.write_text("old", encoding="utf-8")

    class EditLLM:
        async def generate(self, prompt):
            return '{"tool":"edit_file","arguments":{"path":"note.md","old_text":"old","new_text":"new"}}'

    agent.llm = EditLLM()
    result = asyncio.run(agent.run("기존 파일 수정"))
    assert result["status"] == "awaiting_approval"
    assert result["pending_action"]["tool"] == "edit_file"
    assert target.read_text(encoding="utf-8") == "old"


def test_run_command_blocks_inline_module_shell_and_outside_scripts(tmp_path):
    agent = build_agent(tmp_path)
    run = {"id": "cmd", "steps": []}
    blocked = [
        "python -c print(1)",
        "python -m http.server",
        "python script.py & whoami",
        "git status",
        "python ../outside.py",
    ]
    for command in blocked:
        with pytest.raises(ValueError):
            asyncio.run(agent.execute(Action(tool="run_command", arguments={"command": command}), run))


def test_run_command_allows_version_and_workspace_python_script(tmp_path):
    agent = build_agent(tmp_path)
    script = agent.root / "check.py"
    script.write_text("print('workspace-ok')", encoding="utf-8")
    run = {"id": "cmd", "steps": []}

    version = asyncio.run(agent.execute(Action(tool="run_command", arguments={"command": "python --version"}), run))
    assert version["returncode"] == 0

    result = asyncio.run(agent.execute(Action(tool="run_command", arguments={"command": "python check.py"}), run))
    assert result["returncode"] == 0
    assert "workspace-ok" in result["stdout"]
