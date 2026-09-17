from fastapi.testclient import TestClient

from app.config import Settings
from app.db import Database
from app.document_memory import DocumentMemory
from app.main import create_app
from app.memory import MemoryStore


def test_document_memory_indexes_updates_and_removes_files(tmp_path):
    workspace = tmp_path / "workspace"
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True)
    db = Database(str(tmp_path / "memory.db"))
    memory = MemoryStore(db)
    importer = DocumentMemory(db, memory_dir)

    note = memory_dir / "wafer.md"
    note.write_text("Air Dome zephyr calibration uses Zone 3 pressure.", encoding="utf-8")
    first = importer.sync()
    assert first["added"] == 1
    assert first["chunks"] >= 1
    hits = memory.search("zephyr calibration", 5)
    assert any(item["source"] == "document" and "wafer.md" in item["title"] for item in hits)

    note.write_text("Air Dome nebula calibration uses Zone 5 pressure.", encoding="utf-8")
    second = importer.sync()
    assert second["updated"] == 1
    assert not any(item["source"] == "document" for item in memory.search("zephyr calibration", 5))
    assert any(item["source"] == "document" for item in memory.search("nebula calibration", 5))

    note.unlink()
    third = importer.sync()
    assert third["removed"] == 1
    assert not any(item["source"] == "document" for item in memory.search("nebula calibration", 5))


def test_document_memory_chunks_large_text_without_losing_searchability(tmp_path):
    memory_dir = tmp_path / "workspace" / "memory"
    memory_dir.mkdir(parents=True)
    db = Database(str(tmp_path / "memory.db"))
    memory = MemoryStore(db)
    importer = DocumentMemory(db, memory_dir, chunk_chars=1000, overlap_chars=100)
    text = ("front matter " * 200) + " singularity-marker-cobalt " + ("tail matter " * 200)
    (memory_dir / "large.txt").write_text(text, encoding="utf-8")

    result = importer.sync()
    assert result["chunks"] > 1
    hits = memory.search("singularity marker cobalt", 5)
    assert any(item["source"] == "document" for item in hits)


def test_app_startup_and_import_endpoint_sync_workspace_memory(tmp_path):
    workspace = tmp_path / "workspace"
    memory_dir = workspace / "memory"
    memory_dir.mkdir(parents=True)
    (memory_dir / "profile.md").write_text("personal-context-aurora wafer bonder engineer", encoding="utf-8")
    cfg = Settings(
        _env_file=None,
        db_path=str(tmp_path / "app.db"),
        agent_workspace=str(workspace),
        glm_mode="mock",
        agent_require_approval=False,
    )
    client = TestClient(create_app(cfg))

    startup_hits = client.get("/api/memory/search", params={"q": "personal context aurora"}).json()["items"]
    assert any(item["source"] == "document" for item in startup_hits)

    (memory_dir / "later.md").write_text("later-memory-pulsar experimental note", encoding="utf-8")
    imported = client.post("/api/memory/import")
    assert imported.status_code == 200
    assert imported.json()["added"] == 1
    later_hits = client.get("/api/memory/search", params={"q": "later memory pulsar"}).json()["items"]
    assert any(item["source"] == "document" for item in later_hits)
