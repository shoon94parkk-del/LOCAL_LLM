import hashlib
import json
import math
from pathlib import Path
from threading import Lock


class LocalEmbeddings:
    """Loads only an existing local SentenceTransformers-compatible model."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.model = None
        self.lock = Lock()
        self.identity = hashlib.sha256(json.dumps([
            str(Path(cfg.embedding_model_path).resolve()),
            cfg.embedding_query_prefix, cfg.embedding_document_prefix,
        ]).encode()).hexdigest()

    def encode(self, texts, query=False):
        with self.lock:
            if self.model is None:
                path = Path(self.cfg.embedding_model_path)
                if not self.cfg.embedding_model_path or not path.is_dir():
                    raise ValueError('임베딩 모델 폴더를 확인하세요: LOCAL_LLM_EMBEDDING_MODEL_PATH')
                try:
                    from sentence_transformers import SentenceTransformer
                except ImportError as exc:
                    raise RuntimeError('pip install -r requirements-embeddings.txt 실행이 필요합니다') from exc
                self.model = SentenceTransformer(str(path.resolve()), device=self.cfg.embedding_device,
                                                 local_files_only=True, trust_remote_code=False)
            prefix = self.cfg.embedding_query_prefix if query else self.cfg.embedding_document_prefix
            return self.model.encode([prefix + t for t in texts], normalize_embeddings=True).tolist()


def cosine(a, b):
    if not a or len(a) != len(b) or not all(math.isfinite(x) for x in a + b):
        raise ValueError('Invalid embedding dimensions or values; rebuild the index')
    denominator = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    if not denominator:
        raise ValueError('Zero embedding vector')
    return sum(x*y for x, y in zip(a, b)) / denominator


class HybridRetriever:
    def __init__(self, memory, encoder=None):
        self.memory, self.encoder = memory, encoder
        self.lock = Lock()
        with memory.db.connect() as conn:
            conn.execute('CREATE TABLE IF NOT EXISTS embeddings (source TEXT, source_id INTEGER, model TEXT, digest TEXT, vector TEXT, PRIMARY KEY(source, source_id, model))')

    def reindex(self, force=False):
        if self.encoder is None:
            raise ValueError('로컬 임베딩 모드를 먼저 설정하세요')
        with self.lock, self.memory.db.connect() as conn:
            if force:
                conn.execute('DELETE FROM embeddings WHERE model=?', (self.encoder.identity,))
            rows = conn.execute('SELECT source, source_id, title, body FROM memory_fts').fetchall()
            changed = 0
            for row in rows:
                text = row['title'] + '\n' + row['body']
                digest = hashlib.sha256(text.encode()).hexdigest()
                old = conn.execute('SELECT digest FROM embeddings WHERE source=? AND source_id=? AND model=?',
                                   (row['source'], row['source_id'], self.encoder.identity)).fetchone()
                if old and old['digest'] == digest:
                    continue
                vector = self.encoder.encode([text])[0]
                cosine(vector, vector)
                conn.execute('INSERT OR REPLACE INTO embeddings VALUES (?,?,?,?,?)',
                             (row['source'], row['source_id'], self.encoder.identity, digest, json.dumps(vector)))
                changed += 1
            return changed

    def search(self, query, limit=5):
        lexical = self.memory.search(query, max(limit, 20))
        if self.encoder is None:
            return lexical[:limit]
        self.reindex()
        vector = self.encoder.encode([query], query=True)[0]
        with self.memory.db.connect() as conn:
            rows = conn.execute('SELECT f.source, f.source_id, f.title, f.body, e.vector FROM memory_fts f JOIN embeddings e ON f.source=e.source AND f.source_id=e.source_id WHERE e.model=?', (self.encoder.identity,)).fetchall()
        semantic = sorted([dict(r, similarity=cosine(vector, json.loads(r['vector']))) for r in rows],
                          key=lambda r: r['similarity'], reverse=True)[:20]
        merged = {}
        for ranking in (lexical, semantic):
            for i, row in enumerate(ranking):
                key = (row['source'], row['source_id'])
                item = merged.setdefault(key, {k: v for k, v in row.items() if k != 'vector'})
                item['hybrid_score'] = item.get('hybrid_score', 0) + 1 / (60 + i + 1)
        return sorted(merged.values(), key=lambda r: r['hybrid_score'], reverse=True)[:limit]
