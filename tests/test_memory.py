from app.db import Database
from app.memory import MemoryStore


def test_memory_search_and_case_promotion(tmp_path):
    db = Database(str(tmp_path / "memory.db"))
    memory = MemoryStore(db)

    conversation_id = memory.add_conversation(
        "Air Dome Zone3 압력을 올리면 C5가 어떻게 변하나?",
        "과거 실험에서는 C5가 감소했다.",
    )

    hits = memory.search("Zone3 C5 압력", limit=5)
    assert hits
    assert hits[0]["source"] == "conversation"

    memory.set_feedback(conversation_id, "resolved", "Zone3 +12kPa에서 C5 -30nm 확인")

    case_hits = memory.search("Zone3 C5 12kPa", limit=10)
    assert any(item["source"] == "case" for item in case_hits)
