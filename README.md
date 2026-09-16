# LOCAL_LLM Memory Agent

사내에서 API 없이 웹사이트 형태로만 사용할 수 있는 GLM을 `Playwright + SQLite Memory` 앞단으로 감싸서, 사용할수록 과거 대화/사례/지식 규칙을 재활용하는 로컬 엔지니어링 에이전트입니다.

## 현재 MVP 기능

- 질문/답변 자동 저장
- SQLite FTS5 기반 과거 대화·사례·지식 검색
- 질문 전 관련 기억 TOP-K 자동 검색
- 검색 결과를 GLM 프롬프트에 자동 삽입
- `해결됨 / 실패 / 중요지식` 피드백 저장
- 해결/실패 대화를 별도 case로 승격
- 누적 case를 GLM이 재분석해 `knowledge candidate`를 만드는 Reflection
- 매일 Reflection을 실행할 수 있는 스크립트
- 실제 GLM 없이 검증 가능한 mock 모드
- 회사 GLM 웹사이트용 Playwright adapter
- 간단한 로컬 웹 UI
- GitHub Actions 자동 테스트

## 구조

```text
Browser -> FastAPI -> Memory Retriever -> Prompt Builder -> GLM Adapter
                         |                                  |
                         +---------- SQLite FTS5 <----------+
                                      ^
                                      |
                         Case -> Reflection -> Knowledge

GLM Adapter
  - mock
  - playwright -> 사내 GLM Web
```

## Windows 설치

```bat
git clone https://github.com/shoon94parkk-del/LOCAL_LLM.git
cd LOCAL_LLM
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Playwright 실제 웹 연결을 쓸 경우 한 번만 실행합니다.

```bat
playwright install chromium
```

## 먼저 mock 모드로 실행

`.env`에서 아래 상태를 유지합니다.

```env
LOCAL_LLM_GLM_MODE=mock
```

실행:

```bat
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000` 접속 후 질문을 입력합니다.

첫 질문은 memory hit가 0개일 수 있습니다. 답변 후 `해결됨`을 누르고 실제 결과를 메모한 다음 비슷한 두 번째 질문을 하면, 첫 질문 또는 승격된 case가 자동으로 검색되어 GLM용 프롬프트에 포함됩니다.

## 자기개선 Reflection

`해결됨` 또는 `실패` 피드백이 들어간 대화는 case가 됩니다. Reflection은 최근 case들을 GLM에 다시 보내 공통 패턴/조건 차이를 분석하고 `knowledge candidate`를 생성합니다.

웹 화면에서 `Reflection 실행` 버튼을 눌러 실행하거나 API로 호출할 수 있습니다.

```text
POST /api/reflection
```

또는 CLI:

```bat
python scripts\daily_reflection.py
```

Windows 작업 스케줄러에 위 명령을 하루 1회 등록하면 매일 자동 Reflection이 가능합니다. 회사 GLM을 실제로 사용할 때는 `.env`의 `LOCAL_LLM_GLM_MODE=playwright` 설정을 그대로 사용합니다.

## 회사 GLM 웹사이트 연결

`.env`를 아래처럼 변경합니다. 회사 URL/DOM selector는 저장소에 직접 커밋하지 않는 것을 권장합니다.

```env
LOCAL_LLM_GLM_MODE=playwright
LOCAL_LLM_GLM_URL=https://YOUR_INTERNAL_GLM/
LOCAL_LLM_GLM_INPUT_SELECTOR=textarea
LOCAL_LLM_GLM_SUBMIT_SELECTOR=
LOCAL_LLM_GLM_RESPONSE_SELECTOR=[data-message-author-role='assistant']
LOCAL_LLM_GLM_USER_DATA_DIR=.browser-profile
LOCAL_LLM_GLM_HEADLESS=false
```

- `GLM_INPUT_SELECTOR`: 질문 입력창 CSS selector
- `GLM_SUBMIT_SELECTOR`: 전송 버튼 selector. 비워두면 Enter로 전송
- `GLM_RESPONSE_SELECTOR`: assistant 답변 블록 selector
- `.browser-profile`: 로그인 세션을 유지하는 로컬 Chromium profile

회사 GLM 페이지의 실제 selector를 확인한 뒤 위 3개 값만 맞추면 됩니다.

## API

- `POST /api/chat` : 기억 검색 -> 프롬프트 조립 -> GLM 호출 -> 대화 저장
- `POST /api/feedback/{conversation_id}` : resolved / failed / important 저장
- `POST /api/reflection` : case 재분석 -> knowledge candidate 생성
- `GET /api/memory/search?q=...` : 기억 검색 확인
- `GET /api/history` : 최근 대화
- `POST /api/knowledge` : 수동 지식 규칙 추가
- `GET /health` : 상태 확인

예시:

```json
POST /api/chat
{
  "question": "Air Dome Zone3 압력을 올렸는데 C5가 반대로 움직였어. 왜 그럴까?"
}
```

## 테스트

```bat
pytest -q
```

현재 테스트는 다음 흐름을 확인합니다.

1. 질문/답변 저장
2. FTS5 검색
3. `resolved` 피드백
4. case 자동 생성
5. 다음 유사 질문에서 과거 memory 재검색
6. Reflection으로 knowledge candidate 생성
7. 생성된 knowledge가 다시 검색되는지 확인
8. FastAPI chat/feedback/reflection/health API

## 다음 단계

1. Knowledge confidence/evidence 자동 누적 및 충돌 관리
2. FTS5 + embedding hybrid 검색
3. 과거 문제를 이용한 Eval set 자동 생성
4. GLM 답변 품질 추세 대시보드
5. 반복 작업을 Skill 파일로 자동 승격
