# 내일 회사에서 연결하는 순서

이 문서는 GitHub 원격 저장소를 다시 업데이트하지 않고, 다운로드한 로컬 프로젝트에서 작업하는 기준입니다. 내일 AI에게 이 파일과 프로젝트 폴더를 함께 보여주면 됩니다.

## 0. 어떤 코드를 받을지

최신 기능은 `feat/local-agent-embedding` 브랜치에 있습니다. GitHub에서 ZIP을 받을 때 이 브랜치를 선택하거나 PR #1의 Files/Code 화면에서 해당 브랜치 ZIP을 받으세요. `main`만 받으면 에이전트·Gemini 브리지·Skill 확장이 빠질 수 있습니다.

받은 폴더를 회사 PC의 예를 들어 `C:\Work\LOCAL_LLM`에 압축 해제합니다. 이후 수정은 그 폴더에서만 합니다. 회사 GitHub에 push할 필요는 없습니다.

## 1. Python 환경

PowerShell에서 프로젝트 폴더로 이동합니다.

```powershell
cd C:\Work\LOCAL_LLM
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
playwright install chromium
Copy-Item .env.example .env
```

인터넷이 차단되어 있으면 회사가 승인한 패키지 저장소에서 wheel을 받아 설치합니다. `playwright install chromium`도 승인된 사내 설치 파일이 필요할 수 있습니다.

## 2. 회사 GLM 웹 연결

`.env`에서 다음 값을 수정합니다. URL과 selector는 회사마다 다르므로 예시를 그대로 쓰지 않습니다.

```dotenv
LOCAL_LLM_GLM_MODE=playwright
LOCAL_LLM_GLM_URL=https://회사-GLM-주소/
LOCAL_LLM_GLM_INPUT_SELECTOR=실제_입력창_CSS
LOCAL_LLM_GLM_SUBMIT_SELECTOR=실제_전송버튼_CSS
LOCAL_LLM_GLM_RESPONSE_SELECTOR=실제_assistant_답변_CSS
LOCAL_LLM_GLM_STOP_SELECTOR=생성중일_때_보이는_중지버튼_CSS
LOCAL_LLM_GLM_USER_DATA_DIR=.browser-profile
LOCAL_LLM_GLM_HEADLESS=false
LOCAL_LLM_GLM_TIMEOUT_MS=180000
```

회사 GLM 페이지를 브라우저로 열고 개발자 도구에서 다음을 확인합니다.

* 입력창: 질문을 입력할 수 있는 `textarea` 또는 `contenteditable` 요소
* 전송 버튼: 클릭 가능한 버튼. 비워두면 입력창에 Enter를 보냅니다.
* 답변: 사용자 메시지가 아니라 assistant 답변 블록만 선택하는 CSS
* 중지 버튼: 답변 생성 중에만 보이는 요소. 없으면 빈 값으로 둘 수 있지만 스트리밍 종료 오판 가능성이 있습니다.

selector는 저장소에 커밋하지 않습니다. 확인용 CLI를 실행합니다.

```powershell
.venv\Scripts\python scripts\connect_company.py
```

브라우저가 뜨면 회사 계정으로 직접 로그인하고, 터미널에서 Enter를 누릅니다. 출력된 입력창·전송·답변 selector 일치 개수를 확인합니다. 실제 질문 전송은 다음 명령으로 별도 실행합니다.

```powershell
.venv\Scripts\python scripts\connect_company.py --send-test
```

로그인 정보, 쿠키, 회사 업무 데이터는 AI 채팅이나 Git에 붙여 넣지 않습니다. `.browser-profile`은 개인 로컬 상태입니다.

## 3. 임베딩 모델 연결

현재 어댑터는 **SentenceTransformers 형식의 완전한 모델 폴더**를 로컬에서만 읽습니다. 가중치, tokenizer, config가 폴더 안에 있어야 하며 자동 다운로드는 하지 않습니다.

먼저 회사 모델을 판별합니다.

* 폴더 안에 `config.json`, tokenizer 파일, 모델 가중치가 있으면 SentenceTransformers 호환 가능성이 있습니다.
* `.gguf` 한 파일이면 현재 어댑터 대상이 아닙니다.
* `.onnx` 한 파일 또는 전용 사내 런타임 모델이면 모델 담당자에게 Python 로딩 방법을 확인해야 합니다.

SentenceTransformers 폴더라면 `.env`에 설정합니다.

```dotenv
LOCAL_LLM_EMBEDDING_MODE=local
LOCAL_LLM_EMBEDDING_MODEL_PATH=C:/company/models/embedding-model
LOCAL_LLM_EMBEDDING_DEVICE=cpu
```

E5 계열처럼 접두어를 요구하는 모델 설명이 있을 때만 다음을 설정합니다.

```dotenv
LOCAL_LLM_EMBEDDING_QUERY_PREFIX=query: 
LOCAL_LLM_EMBEDDING_DOCUMENT_PREFIX=passage: 
```

그 다음 임베딩 의존성을 설치합니다.

```powershell
python -m pip install -r requirements-embeddings.txt
```

서버 실행 후 `로컬 임베딩 진단` 버튼을 누르고 차원이 표시되는지 확인합니다. 이어서 `기억 임베딩 갱신`을 누릅니다. 모델 파일을 교체했으면 다음 API로 강제 재색인합니다.

```powershell
Invoke-RestMethod -Method Post 'http://127.0.0.1:8000/api/embeddings/reindex?force=true'
```

오류가 나면 임베딩을 억지로 키워드 검색으로 바꾸지 말고 `LOCAL_LLM_EMBEDDING_MODE=disabled`로 되돌린 후 모델 형식을 확인합니다.

## 4. 서버와 첫 검증

`.env`에 회사 GLM과 임베딩 설정을 저장한 뒤 실행합니다.

```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

다른 PowerShell 창에서 상태를 확인합니다.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/api/skills
```

브라우저에서 `http://127.0.0.1:8000`을 열고 다음 순서로 테스트합니다.

1. `report-writer` Skill 선택
2. 짧고 민감하지 않은 테스트 질문 입력
3. `에이전트 실행` 클릭
4. Plan 단계와 실행 단계 확인
5. 파일 생성 승인창이 나오면 승인
6. 생성된 Markdown 파일과 최종 답변 확인
7. 같은 주제의 두 번째 질문을 보내 memory hit가 생기는지 확인
8. 실제 결과를 확인한 뒤 `해결됨` 또는 `실패` 피드백 저장

추천 테스트 문장:

```text
report-writer를 사용해서 작업 폴더에 있는 test.txt를 읽고
핵심 사실 3개를 새 Markdown 파일로 저장해줘.
저장한 파일을 다시 읽어서 내용이 같은지 확인한 뒤 최종 답변해줘.
```

## 5. AI에게 코드 수정을 요청하는 형식

내일 AI에게는 아래 정보를 한 번에 전달합니다.

```text
이 폴더는 LOCAL_LLM 프로젝트입니다.
GitHub push는 하지 말고 로컬 파일만 수정하세요.

회사 GLM:
- URL: [실제 URL]
- 입력창 selector: [값]
- 전송 selector: [값 또는 Enter]
- assistant 답변 selector: [값]
- 생성중 중지 selector: [값 또는 없음]

임베딩:
- 모델 형식: [SentenceTransformers/GGUF/ONNX/기타]
- 모델 폴더: [로컬 절대 경로]
- 모델 차원: [알면 입력]
- query/document prefix 요구 여부: [내용]

먼저 현재 파일과 테스트를 읽고, 필요한 최소 파일만 수정하세요.
실제 회사 데이터는 테스트에 사용하지 말고 mock 또는 짧은 샘플로 검증하세요.
수정 후 pytest, 임베딩 진단, GLM 연결 테스트 결과와 남은 한계를 보고하세요.
```

## 6. 실패할 때 보는 위치

* 입력창을 못 찾음: `LOCAL_LLM_GLM_INPUT_SELECTOR` 확인
* 전송 후 답변 0개: response selector가 assistant 블록인지 확인
* 스트리밍 중 timeout: stop selector 또는 timeout 확인
* 임베딩 로딩 실패: 모델 폴더 형식과 `requirements-embeddings.txt` 설치 확인
* 파일 권한 오류: `LOCAL_LLM_AGENT_WORKSPACE`와 `LOCAL_LLM_AGENT_ALLOWED_ROOTS` 확인
* 같은 질문 반복: 현재 실행 ID와 단계별 오류를 확인하고 최신 코드를 재실행

## 7. 회사 환경에서의 범위

기본 에이전트는 지정된 폴더 안에서 텍스트 파일을 읽고 새 파일을 만듭니다. 기존 파일 덮어쓰기, 삭제, 임의 셸 명령은 차단합니다. 터미널과 Git 도구는 승인 설정과 허용 명령 범위 안에서만 사용합니다. 설비 조작·메일 전송·회사 시스템 변경은 별도 승인 설계 없이는 수행하지 않습니다.
