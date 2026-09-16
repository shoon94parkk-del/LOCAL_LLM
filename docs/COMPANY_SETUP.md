# 회사 PC 연결 가이드

## 1. 설치

Python 3.11 이상, 저장소 루트에서 실행합니다. 기존 `.env`는 덮어쓰지 마세요.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pip install -r requirements-embeddings.txt
copy .env.example .env
```

Playwright 방식도 사용할 경우 한 번만 실행합니다.

```bat
playwright install chromium
```

인터넷이 차단된 PC는 승인된 사내 패키지 저장소 또는 같은 OS/Python용 wheel 및 Playwright 브라우저 설치 파일이 필요합니다.

## 2. GLM 연결 방식

LOCAL_LLM은 `playwright`와 `browser_bridge` 두 방식 모두 같은 GLM selector 설정을 사용합니다.

```dotenv
LOCAL_LLM_GLM_INPUT_SELECTOR=textarea
LOCAL_LLM_GLM_SUBMIT_SELECTOR=
LOCAL_LLM_GLM_RESPONSE_SELECTOR=실제-답변-블록-selector
LOCAL_LLM_GLM_STOP_SELECTOR=실제-생성중-중지버튼-selector
LOCAL_LLM_GLM_STABLE_SECONDS=5
```

- `INPUT`: 질문 입력 영역
- `SUBMIT`: 전송 버튼. 비우면 Enter 전송을 시도
- `RESPONSE`: assistant 답변 영역
- `STOP`: 생성 중에만 보이는 중지 버튼. 설정 권장

### A. Browser Bridge 권장

이미 회사 브라우저에서 GLM 5.3 Flash에 로그인해 사용하는 환경이면 이 방식이 가장 단순합니다.

`.env`:

```dotenv
LOCAL_LLM_GLM_MODE=browser_bridge
LOCAL_LLM_BROWSER_BRIDGE_TOKEN=충분히-긴-임의-로컬-토큰
```

확장 프로그램 설정:

```bat
copy browser-extension\config.example.js browser-extension\config.js
```

`browser-extension/config.js`를 열어 `.env`와 같은 토큰 및 사내 GLM origin을 입력합니다.

```js
const BRIDGE_TOKEN = '동일한-토큰';
const GLM_WEB_ORIGIN = 'https://사내-GLM-호스트';
```

`config.js`는 gitignore되어 저장소에 올라가지 않습니다.

Chrome/Edge의 확장 프로그램 개발자 모드에서 `browser-extension` 폴더를 압축해제 확장 프로그램으로 로드합니다. 사내 GLM 페이지에서 우하단 **LOCAL Agent 연결 시작**을 눌러 연결합니다.

확장 프로그램은 여러 웹페이지에 content script가 로드될 수 있지만, 실제 LOCAL Agent 동작은 `GLM_WEB_ORIGIN`과 정확히 일치하는 origin에서만 허용합니다. GLM DOM selector는 확장 프로그램에 하드코딩하지 않고 LOCAL_LLM 서버가 `.env` 값을 매 요청 전달합니다.

### B. Playwright

```dotenv
LOCAL_LLM_GLM_MODE=playwright
LOCAL_LLM_GLM_URL=https://실제-사내-주소/
LOCAL_LLM_GLM_USER_DATA_DIR=.browser-profile
LOCAL_LLM_GLM_HEADLESS=false
```

회사 페이지에서 개발자 도구 또는 `playwright codegen 사내URL`로 selector를 확인하세요.

앱과 daily_reflection을 종료한 상태에서:

```bat
python scripts\connect_company.py
python scripts\connect_company.py --send-test
```

같은 `.browser-profile`을 쓰는 앱/CLI는 동시에 실행하지 마세요.

## 3. 로컬 임베딩

```dotenv
LOCAL_LLM_EMBEDDING_MODE=local
LOCAL_LLM_EMBEDDING_MODEL_PATH=C:/company/models/your-embedding-model
LOCAL_LLM_EMBEDDING_DEVICE=cpu
```

SentenceTransformers로 로드 가능한 완전한 모델 폴더를 지원합니다. 자동 다운로드와 모델의 임의 Python 코드 실행은 비활성화됩니다.

E5 등 모델 설명이 요구하는 경우에만 접두어를 설정하세요.

```dotenv
LOCAL_LLM_EMBEDDING_QUERY_PREFIX="query: "
LOCAL_LLM_EMBEDDING_DOCUMENT_PREFIX="passage: "
```

UI의 **도구 · 설정 → 임베딩 진단**에서 연결을 확인하고 필요하면 기억 재색인을 실행합니다.

## 4. 실행

```bat
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

메인 화면에서는 `질문하기`와 `에이전트 실행`을 구분하지 않습니다. 요청을 한 번 입력하면 Agent가 관련 기억과 Skill을 확인하고 필요한 도구를 선택합니다.

예:

> experiment.txt를 읽고 관련 과거 사례를 검색해서 Air Dome 이상 원인과 추가 확인 항목을 보고서로 만들어줘.

실행 과정은 채팅 안의 타임라인으로 표시됩니다. 상세 JSON 기록은 **상세 실행 로그**를 펼쳤을 때만 보입니다.

## 5. 승인과 작업 폴더

기본값은 다음과 같습니다.

```dotenv
LOCAL_LLM_AGENT_REQUIRE_APPROVAL=true
LOCAL_LLM_AGENT_WORKSPACE=data/workspace
```

읽기와 기억 검색은 자동 실행할 수 있지만, 파일 생성·명령 실행·Git commit 등 변경 도구는 승인 카드가 나타난 뒤 사용자가 승인해야 진행합니다.

작업 폴더 밖 접근과 숨김 파일 접근은 차단합니다. 기존 파일 덮어쓰기도 기본 차단합니다. `run_command`는 python/py/git으로 제한되어 있으며 승인 보호를 끄는 것은 권장하지 않습니다.

## 6. 기억과 자기개선

완료된 Agent 답변 아래에서 `해결됨 / 실패 / 중요지식`을 기록할 수 있습니다. 해결/실패 대화는 case로 승격됩니다.

Reflection은 **도구 · 설정** 패널에서 수동 실행할 수 있습니다. 현재 Reflection은 knowledge candidate를 만드는 단계이며 모델 재학습은 아닙니다.

## 7. 상태 확인

- `GET /health`: GLM mode, 승인 보호 상태, Agent 최대 step
- `GET /api/agent/runs`: 최근 Agent 실행
- `GET /api/agent/runs/{id}`: 한 실행의 상세 기록
- `GET /api/workspace`: 작업 폴더
- `GET /api/skills`: 설치된 Skill

Mock은 실제 사내 GLM 없이 Agent 흐름을 검증하는 용도입니다. 회사 GLM의 JSON 준수와 실제 selector는 회사 PC에서 최종 검증해야 합니다.
