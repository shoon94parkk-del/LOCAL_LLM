# LOCAL_LLM Memory Agent

사내에서 API 없이 웹사이트 형태로만 사용할 수 있는 LLM을 Selenium/Playwright/Browser Bridge와 SQLite Memory 앞단으로 감싸서, 사용할수록 과거 대화·사례·검증 지식을 재활용하는 로컬 엔지니어링 에이전트입니다.

## 현재 기능

- Chat-first Agent UI
- 질문/답변 자동 저장
- SQLite FTS5 기반 과거 대화·사례·Knowledge 검색
- 선택적 로컬 embedding hybrid 검색
- 해결/실패/중요지식 피드백
- case → Reflection → Knowledge candidate
- 중복 Knowledge 병합, 충돌 격리, 근거 Case 추적
- 검증된 Knowledge 검색 우선순위 상승
- 작업 폴더 파일 읽기/생성, 보고서, 제한된 Python/Git 도구
- 변경 작업 사용자 승인
- Skill 읽기/생성
- 회사 GLM 연결: Selenium / Playwright / Browser Bridge
- GitHub Actions 자동 테스트

## 구조

```text
Browser -> FastAPI -> Agent -> Memory Retriever -> GLM Adapter
                       |          |                |
                       |          +-- SQLite FTS5 -+
                       |          +-- Embedding(optional)
                       |
                       +-- Files / Reports / Python / Git / Skills

Case -> Reflection -> Candidate Knowledge -> validation/conflict handling

GLM Adapter
  - mock
  - selenium      -> 회사 GLM Web (현재 회사 권장)
  - playwright    -> 회사 GLM Web
  - browser_bridge-> 이미 열린 회사 브라우저
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

## 회사 PC: Selenium 연결

실제 사내 URL은 공개 GitHub에 넣지 말고 로컬 `.env`에만 저장합니다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_company_selenium.ps1 -GlmUrl "http://YOUR-INTERNAL-LLM:8501/"
```

이 스크립트는 로컬 `.env`를 다음 방향으로 설정합니다.

```env
LOCAL_LLM_GLM_MODE=selenium
LOCAL_LLM_GLM_URL=http://YOUR-INTERNAL-LLM:8501/
LOCAL_LLM_GLM_TIMEOUT_MS=1800000
LOCAL_LLM_EMBEDDING_MODE=disabled
```

Selenium adapter는 브라우저를 첫 요청 때 띄우고, 클립보드 `Ctrl+V`로 프롬프트를 입력합니다. 답변 끝의 `[[END]]` 마커를 확인해 응답 잘림을 감지하고, 마커가 없으면 자동 이어쓰기를 시도합니다. Chrome을 먼저 사용하고 실패하면 Edge를 시도합니다.

실행:

```bat
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

브라우저에서 `http://127.0.0.1:8000`을 엽니다.

상세 회사 설정은 [회사 PC 연결 가이드](docs/COMPANY_SETUP.md)를 참고하세요.

## 긴 문서 지원

회사 업무용 긴 텍스트를 위해 다음 제한을 24만 글자로 높였습니다.

- 채팅 질문: 240,000자
- `read_file`: 240,000자
- `write_file`: 240,000자
- `write_report`: 240,000자
- 다음 Agent step에 전달되는 도구 결과: 240,000자

현재 직접 읽는 파일은 UTF-8 텍스트 계열(TXT/MD/CSV/JSON/PY/JS/HTML/CSS/YAML)입니다. XLSX/PDF 등은 별도 reader 확장이 필요합니다.

## Memory 자료 폴더

개인 업무 기억이나 과거 자료는 우선 아래에 정리하는 것을 권장합니다.

```text
data/workspace/memory/
```

`setup_company_selenium.ps1`도 이 폴더를 자동 생성합니다. 단, 현재는 폴더에 파일을 넣는 것만으로 Memory DB에 자동 색인되지는 않으며 Agent가 작업 파일로 읽어 활용합니다.

실제 Memory DB는 `data/memory.db`이며 직접 편집하지 않습니다.

## 자기개선

사용자가 완료 답변에 `해결됨 / 실패 / 중요지식` 피드백을 남기면 사례가 누적됩니다. Reflection은 실제 Case를 비교해 재사용 가능한 Knowledge를 만들고, 동일 지식은 병합하며 충돌하는 지식은 격리합니다. 서로 다른 실제 Case 근거와 confidence 기준을 만족한 Knowledge는 validated로 승격되어 검색 우선순위가 높아집니다.

이는 현재 모델 가중치 재학습이 아니라 Memory/Knowledge 기반 자기개선입니다.

## 테스트

```bat
pytest -q
```

GitHub Actions에서도 동일 테스트를 실행합니다.
