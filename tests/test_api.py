from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_chat_feedback_retrieval_and_reflection(tmp_path):
    cfg = Settings(db_path=str(tmp_path / "api.db"), glm_mode="mock", top_k_context=5)
    client = TestClient(create_app(cfg))

    first = client.post("/api/chat", json={"question": "Edge void 원인 분석 테스트"})
    assert first.status_code == 200
    first_data = first.json()
    assert first_data["conversation_id"] > 0
    assert "MOCK GLM RESPONSE" in first_data["answer"]

    feedback = client.post(
        f"/api/feedback/{first_data['conversation_id']}",
        json={"status": "resolved", "note": "vent timing 조정 후 개선"},
    )
    assert feedback.status_code == 200

    second = client.post("/api/chat", json={"question": "Edge void vent timing 과거 사례 알려줘"})
    assert second.status_code == 200
    second_data = second.json()
    assert second_data["memory_hits"]
    assert any(item["source"] in {"conversation", "case"} for item in second_data["memory_hits"])

    reflection = client.post("/api/reflection")
    assert reflection.status_code == 200
    reflection_data = reflection.json()
    assert reflection_data["case_count"] == 1
    assert len(reflection_data["created"]) == 1

    knowledge_search = client.get("/api/memory/search", params={"q": "실제 해결 실패 결과"})
    assert knowledge_search.status_code == 200
    assert any(item["source"] == "knowledge" for item in knowledge_search.json()["items"])

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["glm_mode"] == "mock"
