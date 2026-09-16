import asyncio
import json
import pytest
from fastapi.testclient import TestClient
from app.agent import Agent
from app.config import Settings
from app.db import Database
from app.memory import MemoryStore
from app.embeddings import HybridRetriever, LocalEmbeddings, cosine
from app.main import create_app


def config(tmp_path, **kwargs):
    # Tests that exercise mutating tools opt out explicitly; production default stays protected.
    kwargs.setdefault('agent_require_approval', False)
    return Settings(_env_file=None, db_path=str(tmp_path/'db'), agent_workspace=str(tmp_path/'workspace'), **kwargs)


class SequenceLLM:
    def __init__(self, responses): self.responses = iter(responses)
    async def generate(self, prompt): return next(self.responses)


def test_default_approval_is_enabled():
    assert Settings(_env_file=None).agent_require_approval is True


def test_mock_agent_persists_and_feedback(tmp_path):
    client = TestClient(create_app(config(tmp_path)))
    run = client.post('/api/agent/run', json={'question': '압력 원인 조사'}).json()
    assert run['status'] == 'completed'
    assert run['steps'][0]['action']['tool'] == 'memory_search'
    assert client.get('/api/agent/runs/'+run['id']).json() == run
    assert client.post('/api/feedback/'+str(run['conversation_id']), json={'status':'resolved'}).status_code == 200


def test_agent_recovers_and_writes_report(tmp_path):
    cfg=config(tmp_path)
    memory=MemoryStore(Database(cfg.db_path))
    actions=[{'tool':'read_file','arguments':{'path':'../private.txt'}},
             {'tool':'write_report','arguments':{'content':'# Evidence\nNo data'}},
             {'tool':'finish','arguments':{'answer':'보고서 생성됨'}}]
    agent=Agent(cfg,memory,HybridRetriever(memory),SequenceLLM(map(json.dumps,actions)))
    result=asyncio.run(agent.run('보고서'))
    assert result['status']=='completed'
    assert 'error' in result['steps'][0]
    assert (agent.root/result['steps'][1]['result']['artifact']).read_text(encoding='utf-8').startswith('# Evidence')
    for name in ['../outside','.env',str(tmp_path/'outside')]:
        with pytest.raises(ValueError): agent.path(name)


def test_step_limit_and_malformed_json(tmp_path):
    cfg=config(tmp_path,agent_max_steps=2)
    memory=MemoryStore(Database(cfg.db_path))
    agent=Agent(cfg,memory,HybridRetriever(memory),SequenceLLM(['not json','{"tool":"shell"}']))
    result=asyncio.run(agent.run('test'))
    assert result['status']=='step_limit'
    assert len(result['steps'])==2
    assert all('error' in s for s in result['steps'])


class Encoder:
    identity='test-v1'
    def encode(self,texts,query=False):
        return [[1.,0.] if ('압력' in t or 'pressure' in t) else [0.,1.] for t in texts]


def test_semantic_retrieval_updates_existing_feedback(tmp_path):
    memory=MemoryStore(Database(str(tmp_path/'db')))
    conversation=memory.add_conversation('압력 이상','조정 필요')
    memory.add_conversation('온도','확인')
    retriever=HybridRetriever(memory,Encoder())
    assert retriever.search('pressure')[0]['source_id']==conversation
    assert retriever.reindex()==0
    memory.set_feedback(conversation,'failed','실패')
    assert retriever.reindex()==1
    memory.set_feedback(conversation,'resolved','성공')
    assert retriever.reindex()==1
    assert retriever.reindex(force=True)==3


def test_embedding_path_and_dimensions(tmp_path):
    with pytest.raises(ValueError): LocalEmbeddings(config(tmp_path,embedding_model_path=str(tmp_path/'missing'))).encode(['test'])
    with pytest.raises(ValueError): cosine([1.],[1.,2.])
    with pytest.raises(ValueError): cosine([float('nan')],[1.])
    client=TestClient(create_app(config(tmp_path)))
    assert client.post('/api/diagnostics/embedding').json()['ok'] is False
    assert client.post('/api/embeddings/reindex').status_code==400


def test_glm_does_not_return_while_generating(tmp_path, monkeypatch):
    from app.llm import playwright_adapter as module
    ticks = [0.0]
    monkeypatch.setattr(module.time, 'monotonic', lambda: ticks[0])
    async def sleep(seconds): ticks[0] += seconds
    monkeypatch.setattr(module.asyncio, 'sleep', sleep)
    class Responses:
        async def count(self): return 1
        def nth(self, index): return self
        async def inner_text(self): return 'complete'
    class Stop:
        @property
        def last(self): return self
        async def is_visible(self): return ticks[0] < 3
    class Page:
        def locator(self, selector): return Stop()
    cfg=config(tmp_path,glm_stop_selector='button.stop',glm_stable_seconds=1,glm_timeout_ms=8000)
    result=asyncio.run(module.PlaywrightGLM(cfg)._wait_for_new_response(Responses(),0,Page()))
    assert result=='complete' and ticks[0]>=3.4
    ticks[0]=0
    with pytest.raises(TimeoutError):
        asyncio.run(module.PlaywrightGLM(cfg)._wait_for_new_response(Responses(),1,Page()))


def test_model_load_is_local_only(tmp_path, monkeypatch):
    import sys
    import types
    calls={}
    class Model:
        def __init__(self,path,**kwargs): calls.update(kwargs)
        def encode(self,texts,**kwargs):
            calls['texts']=texts
            class Values:
                def tolist(self): return [[1.,0.]]
            return Values()
    monkeypatch.setitem(sys.modules,'sentence_transformers',types.SimpleNamespace(SentenceTransformer=Model))
    cfg=config(tmp_path,embedding_model_path=str(tmp_path),embedding_query_prefix='query: ')
    assert LocalEmbeddings(cfg).encode(['hello'],query=True)==[[1.,0.]]
    assert calls['local_files_only'] is True
    assert calls['trust_remote_code'] is False
    assert calls['texts']==['query: hello']


def test_skills_and_file_tools(tmp_path):
    from app.agent import Action
    cfg=config(tmp_path,skills_dir=str(tmp_path/'skills'))
    folder=tmp_path/'skills'/'demo'
    folder.mkdir(parents=True)
    (folder/'SKILL.md').write_text('Write and verify a report.',encoding='utf-8')
    memory=MemoryStore(Database(cfg.db_path))
    agent=Agent(cfg,memory,HybridRetriever(memory),SequenceLLM([]))
    assert agent.skills.read('demo').startswith('Write')
    with pytest.raises(ValueError): agent.skills.read('../demo')
    run={'id':'test','steps':[]}
    asyncio.run(agent.execute(Action(tool='write_file',arguments={'path':'nested/result.md','content':'hello'}),run))
    assert asyncio.run(agent.execute(Action(tool='read_file',arguments={'path':'nested/result.md'}),run))=='hello'
    with pytest.raises(FileExistsError):
        asyncio.run(agent.execute(Action(tool='write_file',arguments={'path':'nested/result.md','content':'overwrite'}),run))
    with pytest.raises(ValueError):
        asyncio.run(agent.execute(Action(tool='write_file',arguments={'path':'../outside.md','content':'no'}),run))


def test_bridge_waits_for_matching_response(tmp_path):
    from app.llm.browser_bridge import BrowserBridge
    async def scenario():
        cfg=config(tmp_path, glm_input_selector='#prompt', glm_response_selector='.answer', glm_stop_selector='.stop')
        bridge=BrowserBridge(cfg, timeout=1)
        task=asyncio.create_task(bridge.generate('prompt'))
        await asyncio.sleep(0)
        assert bridge.pending['selectors']['input'] == '#prompt'
        assert bridge.pending['selectors']['response'] == '.answer'
        assert bridge.pending['selectors']['stop'] == '.stop'
        with pytest.raises(ValueError): bridge.complete('wrong','answer')
        bridge.complete(bridge.pending['id'],'actual answer')
        assert await task=='actual answer'
        assert bridge.pending is None
        with pytest.raises(ValueError): bridge.complete('old','duplicate')
    asyncio.run(scenario())


def test_bridge_requires_token(tmp_path):
    cfg=config(tmp_path,glm_mode='browser_bridge',browser_bridge_token='local-test-token')
    client=TestClient(create_app(cfg))
    assert client.get('/api/browser/pending').status_code==403
    assert client.get('/api/browser/pending',headers={'X-Bridge-Token':'local-test-token'}).json()=={'job':None}


def test_health_exposes_approval_state(tmp_path):
    client=TestClient(create_app(config(tmp_path, agent_require_approval=True)))
    health=client.get('/health').json()
    assert health['approval_required'] is True
    assert health['agent_max_steps'] == 8


def test_parse_model_json_prefix_and_windows_path():
    from app.agent import parse_action
    action = parse_action('JSON\n{"tool":"read_file","arguments":{"path":"reports\\run-1.md"}}')
    assert action.tool == 'read_file'
    assert action.arguments['path'] == 'reports/run-1.md'
