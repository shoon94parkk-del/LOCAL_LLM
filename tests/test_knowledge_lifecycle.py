import asyncio
import json

from app.agent import Agent
from app.config import Settings
from app.db import Database
from app.embeddings import HybridRetriever
from app.memory import MemoryStore
from app.reflection import run_reflection


class SequenceLLM:
    def __init__(self, responses):
        self.responses = iter(responses)

    async def generate(self, prompt):
        return next(self.responses)


def add_case(memory, problem, solution, status="resolved", note="confirmed"):
    conversation_id = memory.add_conversation(problem, solution)
    memory.set_feedback(conversation_id, status, note)
    with memory.db.connect() as conn:
        row = conn.execute(
            "SELECT id FROM cases WHERE conversation_id=?", (conversation_id,)
        ).fetchone()
    return int(row["id"])


def test_candidate_promotes_with_two_distinct_cases_and_does_not_double_count(tmp_path):
    memory = MemoryStore(Database(str(tmp_path / "db")))
    case1 = add_case(memory, "Zone3 압력 상승", "C5 변화 확인")
    case2 = add_case(memory, "Zone3 재시험", "동일 경향 재현")

    first = memory.upsert_knowledge_candidate(
        "Zone3 압력을 올리면 C5 변형이 증가한다",
        0.81,
        [case1, case2],
    )
    assert first["status"] == "validated"
    assert first["evidence_count"] == 2

    repeated = memory.upsert_knowledge_candidate(
        "Zone3 압력을 올리면 C5 변형이 증가한다",
        0.84,
        [case1, case2],
    )
    assert repeated["action"] == "merged"
    assert repeated["knowledge_id"] == first["knowledge_id"]
    assert repeated["evidence_count"] == 2
    assert len(memory.list_knowledge()) == 1


def test_conflicted_knowledge_is_kept_for_review_but_not_retrieved(tmp_path):
    memory = MemoryStore(Database(str(tmp_path / "db")))
    base = memory.add_knowledge(
        "Zone3 압력 상승 시 C5 변형이 증가한다", 0.9, "validated"
    )
    case_id = add_case(memory, "반대 현상", "C5 감소 확인")

    conflict = memory.upsert_knowledge_candidate(
        "Zone3 압력 상승 시 C5 변형이 감소한다",
        0.86,
        [case_id],
        relation="conflicts",
        target_knowledge_id=base,
    )
    assert conflict["status"] == "conflicted"
    assert memory.get_knowledge(conflict["knowledge_id"])["relations"][0]["relation"] == "conflicts"
    hits = memory.search("Zone3 압력 C5", 10)
    assert all(item["source_id"] != conflict["knowledge_id"] for item in hits if item["source"] == "knowledge")
    assert any(item["source_id"] == base for item in hits if item["source"] == "knowledge")


def test_validated_knowledge_is_ranked_above_candidate(tmp_path):
    memory = MemoryStore(Database(str(tmp_path / "db")))
    candidate = memory.add_knowledge("압력 점검 시 센서 로그를 확인한다", 0.4, "candidate")
    validated = memory.add_knowledge("압력 이상 시 센서 로그와 추세를 확인한다", 0.9, "validated")
    hits = [x for x in memory.search("압력 센서 로그", 10) if x["source"] == "knowledge"]
    assert hits[0]["source_id"] == validated
    assert hits[0]["memory_quality"] > next(x for x in hits if x["source_id"] == candidate)["memory_quality"]


def test_reflection_merges_existing_rule_and_tracks_case_evidence(tmp_path):
    memory = MemoryStore(Database(str(tmp_path / "db")))
    case1 = add_case(memory, "압력 문제 A", "로그 확인")
    case2 = add_case(memory, "압력 문제 B", "로그 확인")
    existing = memory.add_knowledge("압력 문제는 센서 로그를 먼저 확인한다", 0.65, "candidate")
    payload = {
        "rules": [
            {
                "rule": "압력 문제는 센서 로그를 먼저 확인한다",
                "confidence": 0.82,
                "evidence_case_ids": [case1, case2],
                "relation": "duplicate",
                "target_knowledge_id": existing,
            }
        ]
    }
    result = asyncio.run(run_reflection(memory, SequenceLLM([json.dumps(payload, ensure_ascii=False)])))
    assert result["created"] == []
    assert result["merged"][0]["knowledge_id"] == existing
    assert result["merged"][0]["status"] == "validated"
    assert result["merged"][0]["evidence_count"] == 2


def test_save_skill_requires_explicit_approval(tmp_path):
    cfg = Settings(
        _env_file=None,
        db_path=str(tmp_path / "db"),
        agent_workspace=str(tmp_path / "workspace"),
        skills_dir=str(tmp_path / "skills"),
        agent_require_approval=True,
    )
    memory = MemoryStore(Database(cfg.db_path))
    action = json.dumps(
        {
            "tool": "save_skill",
            "arguments": {"name": "learned_rule", "content": "Always verify evidence."},
        }
    )
    agent = Agent(cfg, memory, HybridRetriever(memory), SequenceLLM([action]))
    result = asyncio.run(agent.run("새 skill 저장"))
    assert result["status"] == "awaiting_approval"
    assert result["pending_action"]["tool"] == "save_skill"
    assert not (tmp_path / "skills" / "learned_rule" / "SKILL.md").exists()
