# 회사 PC 연결 가이드

## 1. 설치

Python 3.11 이상, 저장소 루트에서 실행합니다. 기존 `.env`가 있다면 덮어쓰지 마세요.

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

현재 `requirements.txt`에는 Selenium과 클립보드 전송용 pyperclip이 포함되어 있습니다.

Playwright 방식도 사용할 경우에만 추가로 한 번 실행합니다.

```bat
playwright install chromium
```

인터넷이 차단된 PC에서는 승인된 사내 패키지 저장소 또는 같은 OS/Python용 wheel이 필요합니다. Selenium은 Chrome을 먼저, 실패하면 Edge를 시도합니다. 브라우저 드라이버 자동 준비가 사내망에서 막히는 경우에는 회사 환경에 맞는 WebDriver를 별도로 설치해야 합니다.

## 2. 회사 권장: Selenium 모드

현재 회사 환경에서는 Selenium 모드를 우선 사용합니다. 실제 사내 URL은 공개 저장소에 커밋하지 말고 회사 PC의 `.env`에만 보관하세요.

가장 간단한 설정 방법:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_company_selenium.ps1 -GlmUrl "http://YOUR-INTERNAL-LLM:8501/"
```

스크립트가 아래 값을 `.env`에 설정합니다.

```dotenv
LOCAL_LLM_GLM_MODE=selenium
LOCAL_LLM_GLM_URL=http://YOUR-INTERNAL-LLM:8501/
LOCAL_LLM_GLM_TIMEOUT_MS=1800000
LOCAL_LLM_EMBEDDING_MODE=disabled
```

그리고 `data\workspace\memory` 폴더도 자동 생성합니다. 과거 업무자료와 기억용 Markdown/TXT/CSV 파일은 우선 이 폴더에 넣어두면 Agent가 작업 파일로 읽을 수 있습니다.

### Selenium 동작 방식

- 브라우저는 앱 시작 시가 아니라 첫 GLM 요청 때 생성됩니다.
- Chrome을 우선 시도하고 실패하면 Edge를 시도합니다.
- 프롬프트는 시스템 클립보드에 복사한 뒤 입력창에 `Ctrl+V`로 붙여넣습니다.
- Selenium 호출은 `asyncio.to_thread`와 Lock으로 직렬화되어 Agent의 async 인터페이스를 막지 않습니다.
- 모든 요청에 답변 마지막 `[[END]]` 마커를 요구합니다.
- 응답이 안정됐는데 `[[END]]`가 없으면 잘림으로 보고 자동으로 이어쓰기를 요청합니다.
- 이어쓰기 내용은 가능한 중복 구간을 제거한 뒤 하나의 답변으로 합칩니다.

### DOM selector

기본 설정은 일반 textarea와 Streamlit 채팅 UI를 함께 고려합니다.

```dotenv
LOCAL_LLM_GLM_INPUT_SELECTOR=textarea
LOCAL_LLM_GLM_SUBMIT_SELECTOR=
LOCAL_LLM_GLM_RESPONSE_SELECTOR=[data-message-author-role='assistant'], [data-testid='stChatMessage']
LOCAL_LLM_GLM_STOP_SELECTOR=
LOCAL_LLM_GLM_STABLE_SECONDS=5
```

회사 페이지 구조가 다르면 개발자 도구에서 실제 selector를 확인한 뒤 `.env` 값만 바꾸세요.

- `INPUT`: 질문 입력 영역
- `SUBMIT`: 전송 버튼. 비우면 Enter 전송
- `RESPONSE`: 답변 또는 채팅 메시지 블록
- `STOP`: 생성 중에만 보이는 중지 버튼. 있으면 설정 권장

## 3. 다른 연결 방식

### Browser Bridge

이미 회사 브라우저 로그인 세션을 그대로 재사용해야 할 때 적합합니다.

```dotenv
LOCAL_LLM_GLM_MODE=browser_bridge
LOCAL_LLM_BROWSER_BRIDGE_TOKEN=충분히-긴-임의-로컬-토큰
```

```bat
copy browser-extension\config.example.js browser-extension\config.js
```

`browser-extension/config.js`에 `.env`와 같은 토큰 및 사내 GLM origin을 입력합니다. 이 파일은 gitignore되어 저장소에 올라가지 않습니다.

### Playwright

```dotenv
LOCAL_LLM_GLM_MODE=playwright
LOCAL_LLM_GLM_URL=https://실제-사내-주소/
LOCAL_LLM_GLM_USER_DATA_DIR=.browser-profile
LOCAL_LLM_GLM_HEADLESS=false
```

Playwright profile을 쓰는 앱/CLI는 동시에 실행하지 않는 것을 권장합니다.

## 4. 로컬 임베딩

현재는 다음처럼 꺼둬도 됩니다.

```dotenv
LOCAL_LLM_EMBEDDING_MODE=disabled
```

모델을 준비한 뒤:

```dotenv
LOCAL_LLM_EMBEDDING_MODE=local
LOCAL_LLM_EMBEDDING_MODEL_PATH=C:/company/models/your-embedding-model
LOCAL_LLM_EMBEDDING_DEVICE=cpu
```

SentenceTransformers로 로드 가능한 로컬 모델 폴더를 지원합니다. 자동 모델 다운로드는 하지 않습니다.

## 5. 실행

```bat
.venv\Scripts\activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

메인 화면에서는 질문과 Agent 실행을 구분하지 않습니다. 요청을 한 번 입력하면 Agent가 관련 기억과 Skill을 확인하고 필요한 도구를 선택합니다.

예:

> experiment.txt를 읽고 관련 과거 사례를 검색해서 Air Dome 이상 원인과 추가 확인 항목을 보고서로 만들어줘.

## 6. 입력/파일 길이

회사 업무용 긴 문서를 고려해 다음 제한을 24만 글자로 올렸습니다.

- 채팅 질문: 최대 240,000자
- `read_file`: 최대 240,000자
- `write_file`: 최대 240,000자
- `write_report`: 최대 240,000자
- Agent가 다음 GLM 호출에 반영하는 도구 결과: 최대 240,000자

`read_file`은 현재 UTF-8 텍스트 파일용입니다. XLSX/PDF 등은 별도 reader가 필요합니다.

## 7. 승인과 작업 폴더

기본값:

```dotenv
LOCAL_LLM_AGENT_REQUIRE_APPROVAL=true
LOCAL_LLM_AGENT_WORKSPACE=data/workspace
```

읽기와 기억 검색은 자동 실행할 수 있지만 파일 생성·명령 실행·Git commit·Skill 생성 등 변경 작업은 사용자 승인 후 실행합니다.

작업 폴더 밖 접근과 숨김 파일 접근은 차단합니다. 기존 파일 덮어쓰기도 기본 차단합니다.

## 8. 기억과 자기개선

완료된 Agent 답변 아래에서 `해결됨 / 실패 / 중요지식`을 기록할 수 있습니다. 해결/실패 대화는 case로 승격됩니다.

Reflection은 누적 case를 비교해 Knowledge를 만들며, 중복은 합치고 충돌 후보는 격리합니다. 검증된 Knowledge는 검색에서 더 높은 우선순위를 받습니다. 이는 모델 가중치 재학습이 아니라 Memory/Knowledge 기반 자기개선입니다.

## 9. 상태 확인

- `GET /health`: GLM mode, 승인 보호 상태, Agent 최대 step
- `GET /api/agent/runs`: 최근 Agent 실행
- `GET /api/workspace`: 작업 폴더
- `GET /api/skills`: 설치된 Skill

회사 GLM의 실제 DOM 구조와 WebDriver 동작은 회사 PC에서 최종 확인해야 합니다.
