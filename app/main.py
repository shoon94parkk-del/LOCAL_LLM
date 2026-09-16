import asyncio
import json
import secrets
import subprocess

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.agent import Agent
from app.config import Settings, settings as default_settings
from app.db import Database
from app.embeddings import HybridRetriever, LocalEmbeddings
from app.llm import MockLLM, PlaywrightGLM
from app.llm.browser_bridge import BrowserBridge
from app.memory import MemoryStore
from app.prompt_builder import build_prompt
from app.reflection import run_reflection
from app.web_ui import INDEX_HTML


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)


class AgentRequest(ChatRequest):
    skill: str | None = None


class BridgeResponse(BaseModel):
    answer: str = Field(default="", max_length=200000)
    error: str = Field(default="", max_length=1000)


class FeedbackRequest(BaseModel):
    status: str
    note: str = ""


class KnowledgeRequest(BaseModel):
    rule: str = Field(min_length=1)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: str = "candidate"


def create_app(settings: Settings | None = None) -> FastAPI:
    cfg = settings or default_settings
    cfg.ensure_paths()
    db = Database(cfg.db_path)
    memory = MemoryStore(db)

    if cfg.glm_mode not in {"mock", "playwright", "browser_bridge"}:
        raise ValueError("Unknown GLM mode")
    if cfg.embedding_mode not in {"disabled", "local"}:
        raise ValueError("Unknown embedding mode")

    retriever = HybridRetriever(
        memory,
        LocalEmbeddings(cfg) if cfg.embedding_mode == "local" else None,
    )
    llm = PlaywrightGLM(cfg) if cfg.glm_mode == "playwright" else MockLLM()
    if cfg.glm_mode == "browser_bridge":
        if not cfg.browser_bridge_token:
            raise ValueError("브라우저 연결 토큰 설정이 필요합니다")
        llm = BrowserBridge(cfg, cfg.glm_timeout_ms / 1000)

    agent = Agent(cfg, memory, retriever, llm)
    app = FastAPI(title=cfg.app_name)
    app.state.settings = cfg
    app.state.memory = memory
    app.state.llm = llm

    def bridge_auth(token: str | None) -> None:
        if not isinstance(llm, BrowserBridge):
            raise HTTPException(409, "browser_bridge 모드가 아닙니다")
        if not secrets.compare_digest(token or "", cfg.browser_bridge_token):
            raise HTTPException(403, "브라우저 연결 토큰이 올바르지 않습니다")

    @app.get("/api/browser/status")
    async def browser_status(x_bridge_token: str | None = Header(default=None)) -> dict:
        bridge_auth(x_bridge_token)
        return {
            "connected_mode": True,
            "pending": llm.pending is not None,
            "job_id": llm.pending["id"] if llm.pending else None,
        }

    @app.get("/api/browser/pending")
    async def browser_pending(x_bridge_token: str | None = Header(default=None)) -> dict:
        bridge_auth(x_bridge_token)
        return {"job": llm.pending}

    @app.post("/api/browser/result/{job_id}")
    async def browser_result(
        job_id: str,
        payload: BridgeResponse,
        x_bridge_token: str | None = Header(default=None),
    ) -> dict:
        bridge_auth(x_bridge_token)
        try:
            llm.complete(job_id, payload.answer, payload.error)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {"ok": True}

    @app.get("/health")
    async def health() -> dict:
        return {
            "ok": True,
            "glm_mode": cfg.glm_mode,
            "db_path": cfg.db_path,
            "approval_required": cfg.agent_require_approval,
            "agent_max_steps": cfg.agent_max_steps,
        }

    @app.post("/api/chat")
    async def chat(payload: ChatRequest) -> dict:
        """Compatibility endpoint. The primary UI now routes requests through the agent."""
        try:
            memories = await asyncio.to_thread(
                retriever.search, payload.question, cfg.top_k_context
            )
            prompt = build_prompt(payload.question, memories)
            answer = await llm.generate(prompt)
        except Exception as exc:
            raise HTTPException(503, "GLM/임베딩 연결 오류: " + str(exc)[:500])
        conversation_id = memory.add_conversation(payload.question, answer)
        return {
            "conversation_id": conversation_id,
            "answer": answer,
            "memory_hits": memories,
        }

    @app.post("/api/feedback/{conversation_id}")
    async def feedback(conversation_id: int, payload: FeedbackRequest) -> dict:
        try:
            memory.set_feedback(conversation_id, payload.status, payload.note)
        except KeyError:
            raise HTTPException(status_code=404, detail="conversation not found")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return {"ok": True}

    @app.get("/api/memory/search")
    async def memory_search(q: str, limit: int = 5) -> dict:
        return {
            "items": await asyncio.to_thread(
                retriever.search, q, max(1, min(limit, 20))
            )
        }

    @app.get("/api/history")
    async def history(limit: int = 20) -> dict:
        return {"items": memory.recent(max(1, min(limit, 100)))}

    @app.post("/api/knowledge")
    async def knowledge(payload: KnowledgeRequest) -> dict:
        knowledge_id = memory.add_knowledge(
            payload.rule, payload.confidence, payload.status
        )
        return {"knowledge_id": knowledge_id}

    @app.post("/api/reflection")
    async def reflection(limit: int = 50) -> dict:
        return await run_reflection(memory, llm, max(1, min(limit, 200)))

    @app.post("/api/agent/run")
    async def agent_run(payload: AgentRequest) -> dict:
        try:
            return await agent.run(payload.question, payload.skill)
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/agent/plan")
    async def agent_plan(payload: AgentRequest) -> dict:
        return {
            "goal": payload.question,
            "steps": [
                "관련 기억과 Skill 확인",
                "필요한 파일·폴더·Git·터미널 도구 실행",
                "도구 결과 검증",
                "근거와 생성 파일을 포함한 최종 답변",
            ],
            "approval_required": cfg.agent_require_approval,
        }

    @app.post("/api/agent/runs/{run_id}/approve")
    async def agent_approve(run_id: str) -> dict:
        try:
            return await agent.resume(run_id, approve=True)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/agent/runs/{run_id}/deny")
    async def agent_deny(run_id: str) -> dict:
        try:
            return await agent.resume(run_id, approve=False)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/agent/runs/{run_id}/resume")
    async def agent_resume(run_id: str) -> dict:
        try:
            return await agent.resume(run_id, approve=True)
        except (KeyError, ValueError) as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/skills")
    async def skills() -> dict:
        return {
            "items": agent.skills.list(),
            "allowed_roots": [str(p) for p in agent.allowed_roots],
        }

    @app.get("/api/capabilities")
    async def capabilities() -> dict:
        return {
            "tools": [
                "memory_search",
                "read_file",
                "write_file",
                "create_directory",
                "run_command",
                "git_status",
                "git_diff",
                "git_log",
                "git_commit",
                "write_report",
                "save_skill",
            ],
            "approval_required": cfg.agent_require_approval,
            "workspace": str(agent.root),
        }

    @app.get("/api/workspace")
    async def workspace() -> dict:
        files = [p.name for p in agent.root.iterdir() if not p.name.startswith(".")]
        return {"path": str(agent.root), "files": files[:100]}

    @app.post("/api/workspace/open")
    async def open_workspace() -> dict:
        await asyncio.to_thread(
            subprocess.Popen, ["explorer.exe", str(agent.root)], shell=False
        )
        return {"ok": True, "path": str(agent.root)}

    @app.get("/api/agent/runs/{run_id}")
    async def agent_history(run_id: str) -> dict:
        try:
            return agent.get(run_id)
        except KeyError:
            raise HTTPException(404, "run not found")

    @app.get("/api/agent/runs")
    async def agent_runs(limit: int = 20) -> dict:
        limit = max(1, min(limit, 100))
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT payload FROM agent_runs ORDER BY rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        return {"items": [json.loads(row["payload"]) for row in rows]}

    @app.post("/api/embeddings/reindex")
    async def reindex(force: bool = False) -> dict:
        try:
            return {"indexed": await asyncio.to_thread(retriever.reindex, force)}
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/diagnostics/embedding")
    async def diagnose_embedding() -> dict:
        if retriever.encoder is None:
            return {"ok": False, "message": "임베딩이 꺼져 있습니다"}
        try:
            vectors = await asyncio.to_thread(retriever.encoder.encode, ["연결 진단"])
            return {
                "ok": True,
                "dimensions": len(vectors[0]),
                "mode": cfg.embedding_mode,
            }
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return INDEX_HTML

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    return app


app = create_app()
