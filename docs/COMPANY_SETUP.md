# 회사 PC 연결 가이드

## 설치

Python 3.11 이상, 저장소 루트에서 실행합니다. 기존 .env는 덮어쓰지 마세요.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-embeddings.txt
playwright install chromium
copy .env.example .env
```

인터넷이 차단된 PC는 승인된 사내 패키지 저장소 또는 같은 OS/Python용 wheel 및 Playwright 브라우저 설치 파일이 필요합니다. 모델 파일과 sentence-transformers/PyTorch 라이브러리는 별개입니다.

## 로컬 임베딩

```dotenv
LOCAL_LLM_EMBEDDING_MODE=local
LOCAL_LLM_EMBEDDING_MODEL_PATH=C:/company/models/your-embedding-model
LOCAL_LLM_EMBEDDING_DEVICE=cpu
```

SentenceTransformers로 로드 가능한 완전한 모델 폴더(가중치, tokenizer, config 등)를 지원합니다. GGUF/ONNX 파일 하나나 전용 런타임 모델은 지원하지 않으므로 모델명·폴더 구조 확인 후 별도 어댑터가 필요할 수 있습니다. 자동 다운로드와 모델의 임의 Python 코드 실행은 비활성화됩니다.

E5 등 모델 설명이 요구하는 경우에만 접두어를 설정하세요.

```dotenv
LOCAL_LLM_EMBEDDING_QUERY_PREFIX="query: "
LOCAL_LLM_EMBEDDING_DOCUMENT_PREFIX="passage: "
```

서버 실행 후 **로컬 임베딩 진단**에서 차원을 확인하고 **기억 임베딩 갱신**을 누르세요. 검색할 때 새 기록과 변경된 사례는 자동으로 임베딩됩니다. 기존 DB 기록은 보존합니다. 같은 경로의 모델 가중치를 교체했다면 `POST /api/embeddings/reindex?force=true`로 재색인하세요.

오류 발생 시 키워드 검색으로 몰래 바꾸지 않습니다. 임베딩 없이 사용할 때는 `LOCAL_LLM_EMBEDDING_MODE=disabled`로 바꾸고 재시작하세요. 현재 SQLite 벡터를 전체 비교하므로 소규모 개인 기억 저장소용입니다.

## GLM 웹 연결

```dotenv
LOCAL_LLM_GLM_MODE=playwright
LOCAL_LLM_GLM_URL=https://실제-사내-주소/
LOCAL_LLM_GLM_INPUT_SELECTOR=textarea
LOCAL_LLM_GLM_SUBMIT_SELECTOR=
LOCAL_LLM_GLM_RESPONSE_SELECTOR=실제-답변-블록-selector
LOCAL_LLM_GLM_STOP_SELECTOR=실제-생성중-중지버튼-selector
LOCAL_LLM_GLM_HEADLESS=false
```

회사 페이지에서 개발자 도구 또는 `playwright codegen 사내URL`로 selector를 확인하세요. 답변 selector는 assistant 답변만 선택해야 합니다. 전송 selector가 비면 Enter로 전송합니다.

앱과 daily_reflection을 종료한 상태에서:

```bat
python scripts\connect_company.py
python scripts\connect_company.py --send-test
```

첫 명령은 로그인과 selector 일치 개수만 확인합니다. 두 번째는 로그인 확인 후 테스트 질문을 실제 전송합니다. 같은 `.browser-profile`을 쓰는 앱/CLI는 동시에 실행하지 마세요. 앱 내부 GLM 호출은 순차 실행됩니다.

응답 개수가 늘고 텍스트가 안정되면 반환합니다. 생성 중 표시 selector를 설정하면 표시가 사라질 때까지 기다립니다. 미설정 시 긴 스트리밍 중단을 완료로 오인할 수 있습니다. 기존 답변 블록을 재사용하는 사이트는 회사에서 어댑터 조정이 필요합니다.

## 실행

```bat
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

http://127.0.0.1:8000 에서 사용합니다. 분석할 UTF-8 텍스트 파일을 `data/workspace`에 두고 요청하세요.

> experiment.txt를 읽고 관련 과거 사례를 검색해 원인 가설과 추가 확인 항목을 보고서로 만들어줘.

**에이전트 실행**은 계획 → 도구 실행 → 결과 검토를 최대 8회 반복합니다. 도구는 memory_search, list_files, read_file, write_report, finish입니다. 보고서는 `data/workspace/reports`의 새 Markdown 파일로 생성하며 덮어쓰지 않습니다. 작업 폴더 밖 접근과 숨김 파일 읽기를 차단합니다. 임의 셸 실행, 설비 조작, 이메일 전송은 제공하지 않습니다.

`GET /api/agent/runs/{id}`로 저장된 실행 기록을 조회합니다. completed는 모델이 최종 답변을 제출했다는 뜻입니다. 실제 결과를 확인한 뒤 해결됨/실패 피드백을 남기세요. step_limit은 횟수 소진, failed는 실행 오류입니다. 서버 강제 종료 시 running으로 남을 수 있고 자동 재개는 지원하지 않습니다.

Mock은 기억 검색과 테스트 응답만 수행합니다. 회사 GLM의 JSON 준수, 실제 모델 로딩과 검색 품질은 회사에서 검증해야 합니다. Reflection은 후보 지식을 생성하며 모델 재학습이 아닙니다. 서버는 개인 PC의 loopback 실행용입니다.

추가 API: `POST /api/agent/run` (question 필드), `POST /api/diagnostics/embedding`, `POST /api/embeddings/reindex?force=false`.
