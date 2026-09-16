import asyncio
import secrets
from fastapi import FastAPI, HTTPException, Header, Response
from app.llm.browser_bridge import BrowserBridge
from app.agent import Agent
from app.embeddings import LocalEmbeddings, HybridRetriever
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.config import Settings, settings as default_settings
from app.db import Database
from app.llm import MockLLM, PlaywrightGLM
from app.memory import MemoryStore
from app.prompt_builder import build_prompt
from app.reflection import run_reflection


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)


class AgentRequest(ChatRequest):
    skill: str | None = None


class BridgeResponse(BaseModel):
    answer: str = Field(default='', max_length=200000)
    error: str = Field(default='', max_length=1000)


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
    retriever = HybridRetriever(memory, LocalEmbeddings(cfg) if cfg.embedding_mode == "local" else None)
    llm = PlaywrightGLM(cfg) if cfg.glm_mode.lower() == "playwright" else MockLLM()
    if cfg.glm_mode == 'browser_bridge':
        if not cfg.browser_bridge_token:
            raise ValueError('브라우저 연결 토큰 설정이 필요합니다')
        llm = BrowserBridge(cfg.glm_timeout_ms / 1000)

    agent = Agent(cfg, memory, retriever, llm)
    app = FastAPI(title=cfg.app_name)
    app.state.settings = cfg
    app.state.memory = memory
    app.state.llm = llm

    def bridge_auth(token):
        if not isinstance(llm, BrowserBridge):
            raise HTTPException(409, 'browser_bridge 모드가 아닙니다')
        if not secrets.compare_digest(token or '', cfg.browser_bridge_token):
            raise HTTPException(403, '브라우저 연결 토큰이 올바르지 않습니다')

    @app.get('/api/browser/status')
    async def browser_status(x_bridge_token: str | None = Header(default=None)):
        bridge_auth(x_bridge_token)
        return {'connected_mode': True, 'pending': llm.pending is not None, 'job_id': llm.pending['id'] if llm.pending else None}

    @app.get('/api/browser/pending')
    async def browser_pending(x_bridge_token: str | None = Header(default=None)):
        bridge_auth(x_bridge_token)
        return {'job': llm.pending}

    @app.post('/api/browser/result/{job_id}')
    async def browser_result(job_id: str, payload: BridgeResponse, x_bridge_token: str | None = Header(default=None)):
        bridge_auth(x_bridge_token)
        try:
            llm.complete(job_id, payload.answer, payload.error)
        except ValueError as exc:
            raise HTTPException(409, str(exc))
        return {'ok': True}

    @app.get("/health")
    async def health() -> dict:
        return {"ok": True, "glm_mode": cfg.glm_mode, "db_path": cfg.db_path}

    @app.post("/api/chat")
    async def chat(payload: ChatRequest) -> dict:
        try:
            memories = await asyncio.to_thread(retriever.search, payload.question, cfg.top_k_context)
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
        return {"items": await asyncio.to_thread(retriever.search, q, max(1, min(limit, 20)))}

    @app.get("/api/history")
    async def history(limit: int = 20) -> dict:
        return {"items": memory.recent(max(1, min(limit, 100)))}

    @app.post("/api/knowledge")
    async def knowledge(payload: KnowledgeRequest) -> dict:
        knowledge_id = memory.add_knowledge(payload.rule, payload.confidence, payload.status)
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

    @app.get("/api/skills")
    async def skills() -> dict:
        return {"items": agent.skills.list(), "allowed_roots": [str(p) for p in agent.allowed_roots]}

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
            rows = conn.execute("SELECT payload FROM agent_runs ORDER BY rowid DESC LIMIT ?", (limit,)).fetchall()
        import json
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
            return {"ok": True, "dimensions": len(vectors[0]), "mode": cfg.embedding_mode}
        except Exception as exc:
            return {"ok": False, "message": str(exc)}

    @app.get("/", response_class=HTMLResponse)
    async def home() -> str:
        return INDEX_HTML

    @app.get("/favicon.ico")
    async def favicon() -> Response:
        return Response(status_code=204)

    return app


INDEX_HTML = r"""
<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>LOCAL_LLM Memory Agent</title>
<style>
body{font-family:Arial,sans-serif;max-width:980px;margin:32px auto;padding:0 16px;background:#f6f7f9;color:#171717}
.card{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin-bottom:14px}
textarea,input{width:100%;box-sizing:border-box;padding:12px;border:1px solid #bbb;border-radius:8px}
textarea{min-height:100px}button{padding:10px 14px;margin:8px 6px 0 0;border:0;border-radius:8px;cursor:pointer}
.primary{background:#111;color:white}.answer{white-space:pre-wrap}.muted{color:#666;font-size:13px}.memory{font-size:14px;border-top:1px solid #eee;padding-top:8px;margin-top:8px}
</style>
</head>
<body>
<h1>LOCAL_LLM Memory Agent</h1>
<p class="muted">한 단계마다 Gemini가 다음 행동을 정하므로 파일 읽기·쓰기·검증 요청은 3~6회 질문처럼 보일 수 있습니다. 최대 8단계이며 같은 호출 3회 반복 시 안전하게 중단합니다.</p>
<div class="card"><h3>처음 사용하는 방법</h3>
<ol><li>Skill을 선택하거나 <b>자동 선택</b>을 둡니다.</li><li>작업 폴더에 참고할 UTF-8 텍스트 파일을 넣습니다.</li><li>구체적으로 요청합니다. 예: <code>experiment.txt를 읽고 원인 가설 보고서를 새 파일로 만들어줘</code></li><li><b>에이전트 실행</b>을 누르고, 생성된 파일과 답변을 확인합니다.</li></ol>
<p class="muted">에이전트는 최대 8단계로 memory_search, list_files, read_file, create_directory, write_file, write_report를 실행할 수 있습니다. 기존 파일 덮어쓰기·삭제·임의 셸 실행은 차단됩니다.</p></div>
<div class="card">
<textarea id="q" placeholder="예: Air Dome Zone 3 압력을 올렸는데 C5가 반대로 움직였어. 원인이 뭘까?"></textarea>
<button class="primary" onclick="ask()">질문하기</button>
<label>Skill <select id="skill"><option value="">자동 선택</option></select></label>
<button onclick="runAgent(this)">에이전트 실행</button>
<pre id="agentResult" style="white-space:pre-wrap"></pre>
</div>
<div class="card" id="result" style="display:none">
<h3>답변</h3><div id="answer" class="answer"></div>
<div id="memories"></div>
<input id="note" placeholder="실제 결과/메모 (선택)" />
<button onclick="feedback('resolved')">✓ 해결됨</button>
<button onclick="feedback('failed')">✕ 실패</button>
<button onclick="feedback('important')">★ 중요지식</button>
</div>
<div class="card">
<h3>연결 진단</h3><button onclick="diagnose()">로컬 임베딩 진단</button><button onclick="reindex()">기억 임베딩 갱신</button><pre id="diagnostic"></pre>
<h3>자기개선 Reflection</h3>
<p class="muted">누적된 해결/실패 case를 GLM이 다시 비교해 재사용 가능한 knowledge candidate를 만듭니다.</p>
<button onclick="reflectNow()">Reflection 실행</button>
<div id="reflection" class="answer"></div>
</div>
<script>
let currentId=null;
fetch('/api/skills').then(r=>r.json()).then(d=>{d.items.forEach(s=>{const o=document.createElement('option');o.value=s.name;o.textContent=s.name;document.getElementById('skill').appendChild(o);});});
async function request(url,body){
 const r=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 if(!r.ok)throw new Error(await r.text()); return r.json();
}
async function runAgent(button){
 const question=document.getElementById('q').value.trim(); if(!question)return;
 button.disabled=true; const box=document.getElementById('agentResult');box.textContent='계획 및 도구 실행 중...';
 try {const d=await request('/api/agent/run',{question,skill:document.getElementById('skill').value||null});currentId=d.conversation_id||null;
 box.textContent='실행 상태: '+d.status+' / ID: '+d.id+'\n'+d.steps.map((s,i)=>'단계 '+(i+1)+': '+JSON.stringify(s)).join('\n')+'\n'+(d.answer||d.error||'');
 if(d.conversation_id){document.getElementById('result').style.display='block';document.getElementById('answer').textContent=d.answer;document.getElementById('memories').textContent='';}
 }catch(e){box.textContent=e.message;}finally{button.disabled=false;}
}
async function diagnose(){try{document.getElementById('diagnostic').textContent=JSON.stringify(await request('/api/diagnostics/embedding',{}),null,2);}catch(e){document.getElementById('diagnostic').textContent=e.message;}}
async function reindex(){try{document.getElementById('diagnostic').textContent=JSON.stringify(await request('/api/embeddings/reindex',{}));}catch(e){document.getElementById('diagnostic').textContent=e.message;}}

async function ask(){
  const question=document.getElementById('q').value.trim(); if(!question)return;
  const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question})});
  if(!r.ok){alert(await r.text());return;}
  const d=await r.json(); currentId=d.conversation_id;
  document.getElementById('result').style.display='block'; document.getElementById('answer').textContent=d.answer;
  const m=document.getElementById('memories'); m.innerHTML='<h4>자동으로 참고한 과거 기록 '+d.memory_hits.length+'개</h4>';
  d.memory_hits.forEach(x=>{const e=document.createElement('div');e.className='memory';e.textContent='['+x.source+'] '+x.title;m.appendChild(e);});
}
async function feedback(status){
  if(!currentId)return; const note=document.getElementById('note').value;
  const r=await fetch('/api/feedback/'+currentId,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({status,note})});
  if(r.ok) alert('저장되었습니다: '+status); else alert('저장 실패');
}
async function reflectNow(){
  const box=document.getElementById('reflection'); box.textContent='분석 중...';
  const r=await fetch('/api/reflection',{method:'POST'}); const d=await r.json();
  box.textContent='분석 case: '+d.case_count+'개 / 생성 knowledge: '+d.created.length+'개\n'+d.created.map(x=>'• '+x.rule+' (confidence '+x.confidence+')').join('\n');
}
</script>
</body>
</html>
"""


app = create_app()
