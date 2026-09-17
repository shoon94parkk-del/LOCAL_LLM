# P2 Agent Completion Design

## Goal

회사 PC에서 1인이 실제 업무에 지속적으로 사용할 수 있는 로컬 Agent로 완성도를 끌어올린다. 기존 FastAPI + SQLite Memory + GLM Web Adapter 구조는 유지하고, 빠져 있는 대화 지속성·복구성·지식 자동 흡수·안전한 수정·회귀평가를 추가한다.

## Completion criteria

1. 같은 작업에서 후속 질문을 이어가는 멀티턴 Session이 존재한다.
2. Agent가 중간에 종료되거나 앱이 재시작돼도 실행 기록이 보존되고 interrupted 상태로 복구할 수 있다.
3. `data/workspace/memory`에 텍스트 자료를 넣으면 앱 시작/질문 시 자동으로 색인되어 검색된다.
4. Agent가 기존 파일을 수정할 때 전체 덮어쓰기 대신 정확한 구간 치환과 검증 결과를 남긴다.
5. 범용 `run_command`의 위험한 Python inline 실행을 차단하고, 명시적 승인 경계를 유지한다.
6. `evals/scenarios.json`을 실제 회귀 점검에 사용하는 실행기가 존재한다.
7. 기존 Selenium/Playwright/Browser Bridge와 P1 Knowledge lifecycle은 깨지지 않는다.

## Architecture

### 1. Session layer

`app/sessions.py`가 SQLite의 `sessions`, `session_messages`를 관리한다. UI의 새 작업은 실제 Session을 만들고, Agent run은 `session_id`를 가진다. Agent prompt에는 최근 Session 메시지가 제한된 길이로 포함된다. 완료 시 assistant 답변을 Session에 기록한다.

### 2. Run recovery

현재 `agent_runs` JSON 저장 방식을 유지하되 각 run에 `session_id`, `created_at`, `updated_at`을 기록한다. Agent 초기화 시 `running` 상태로 남은 run을 `interrupted`로 바꾼다. `resume()`은 interrupted 상태도 허용한다. 매 도구 실행 뒤 저장하는 기존 checkpoint 성격은 유지한다.

### 3. Document Memory ingest

`app/document_memory.py`가 `data/workspace/memory`를 스캔한다. `.md`, `.txt`, `.csv`, `.json`, `.yaml`, `.yml` 파일을 대상으로 SHA-256 해시를 비교해 변경 파일만 재색인한다. 문서는 일정 크기 chunk로 나눠 `documents`, `document_chunks`에 저장하고 `memory_fts` source=`document`로 넣는다. 삭제된 파일은 DB/FTS에서도 제거한다.

앱 시작 시 한 번 sync하고, `/api/chat` 및 `/api/agent/run` 전에 가벼운 sync를 수행한다. 따라서 앱 실행 중 파일을 복사해도 다음 질문부터 검색 가능하다.

### 4. Safe file edit

새 도구 `edit_file(path, old_text, new_text)`를 추가한다. `old_text`가 파일에 정확히 한 번 존재할 때만 치환하고, 변경 전후 SHA-256과 unified diff를 결과에 남긴다. 승인 대상 mutating tool이다. 기존 `write_file`은 새 파일 전용 정책을 유지한다.

### 5. Command hardening

`run_command`는 `python -c`, `python -m`, shell metacharacter, 외부 경로 스크립트를 거부한다. Python 실행은 workspace 내부 `.py` 파일 실행만 허용한다. Git 조회는 전용 `git_status`, `git_diff`, `git_log`를 사용하고, 변경 작업은 승인된 전용 도구만 사용한다. 이것은 OS-level sandbox가 아니므로 문서에 그 한계를 명시한다.

### 6. Eval runner

`app/evals.py`와 `scripts/run_evals.py`를 추가한다. `evals/scenarios.json`의 tool 이름이 실제 capability와 일치하는지, 안전 시나리오가 직접 도구 실행에서 차단되는지, 핵심 API/Session/Memory import가 작동하는지를 자동 점검하고 JSON/콘솔 요약을 반환한다. CI에서도 pytest 기반 핵심 회귀 테스트를 계속 사용한다.

## API additions

- `POST /api/sessions` -> Session 생성
- `GET /api/sessions?limit=N` -> 최근 Session
- `GET /api/sessions/{id}` -> 메시지 + 관련 run
- `POST /api/memory/import` -> memory 폴더 즉시 sync
- 기존 `POST /api/agent/run`에 `session_id` optional 추가

기존 API는 하위 호환을 유지한다. `session_id`가 없으면 서버가 새 Session을 생성한다.

## UI

왼쪽 최근 목록을 개별 run이 아니라 Session 중심으로 바꾼다. 같은 Session에서 후속 질문을 보내면 이전 대화가 유지된다. Memory import 상태는 설정 패널에서 파일 수/변경 수를 확인할 수 있게 한다.

## Safety

- Mutating tools는 기본 승인 필요.
- `edit_file`도 승인 대상.
- workspace 밖 파일 접근 금지.
- `run_command`는 inline Python 및 shell escape 차단.
- Memory 문서 내용은 명령이 아닌 참고 데이터로 취급한다.
- 실제 OS-level process sandbox는 이번 범위에 포함하지 않는다.

## Testing

- Session 생성/메시지 이어쓰기/Agent prompt context 테스트
- 재시작 시 running -> interrupted 복구 테스트
- memory 폴더 신규/변경/삭제 sync 테스트
- edit_file unique replacement/중복 거부/승인 테스트
- run_command inline Python/외부 스크립트 차단 테스트
- Eval runner가 scenarios를 읽고 capability mismatch를 탐지하는 테스트
- 기존 전체 pytest 회귀 테스트
