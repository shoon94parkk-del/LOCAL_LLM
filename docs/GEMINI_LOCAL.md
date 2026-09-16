# Gemini 웹 + 로컬 Skill/파일 작업

앱의 `browser_bridge` 모드는 Gemini API 키 없이 웹 화면을 사용합니다. `playwright` 사내 GLM 모드는 그대로 유지됩니다.

## 브라우저 확장 연결 (사용자가 직접 설치)

1. .env에서 `LOCAL_LLM_GLM_MODE=browser_bridge`, `LOCAL_LLM_GLM_TIMEOUT_MS=300000`을 설정하고 `LOCAL_LLM_BROWSER_BRIDGE_TOKEN`에 충분히 긴 임의 문자열을 지정합니다. 토큰을 공유하거나 커밋하지 마세요.
2. `python scripts/prepare_browser_extension.py`를 실행합니다. 토큰이 포함된 로컬 확장 폴더 `data/browser-extension`이 만들어집니다.
3. Chrome 또는 Edge의 확장 프로그램 관리에서 개발자 모드를 켜고 **압축해제된 확장 프로그램 로드**로 위 폴더를 선택합니다.
4. Gemini 페이지를 열거나 새로고침하고 화면 우측 하단의 **LOCAL Agent 연결 시작**을 클릭합니다. 한 개의 Gemini 탭에서만 활성화하세요. 필요하면 직접 로그인합니다.
5. `uvicorn app.main:app --host 127.0.0.1 --port 8000`으로 앱을 실행하고 http://127.0.0.1:8000 에서 요청합니다.

화면에 `LOCAL Agent 연결됨`이 표시되면 연결된 상태입니다. 에이전트 요청을 실행하면 확장이 Gemini에 프롬프트를 입력하고, 답변이 끝난 뒤 로컬 앱에 결과를 전달합니다. 연결이 안 되면 Gemini 탭을 새로고침하고 버튼을 다시 누른 뒤, 앱의 `/health`와 브라우저 확장 오류 콘솔을 확인하세요. Gemini의 사용량 제한, 로그인 만료, DOM 변경은 연결 실패 원인이 될 수 있습니다.

브라우저 확장 설치는 별도 사용자 작업입니다. Codex가 브라우저 도구로 중계하는 테스트는 Codex 작업이 진행되는 동안에만 동작합니다. 확장을 설치·활성화해야 Codex 없이 사용할 수 있습니다. 확장 자동화는 Gemini 웹 DOM 변경, 로그인/사용량 제한, 백그라운드 탭 제한에 영향을 받습니다. 확장의 실제 설치 후 흐름은 별도 확인이 필요합니다.

## Skill과 파일 권한

`skills/이름/SKILL.md`에 직접 검토한 작업 지침을 두면 앱이 목록으로 제공합니다. UI에서 선택하면 지침을 프롬프트에 포함하고, 자동 선택 시 모델이 `read_skill` 도구로 지침을 읽을 수 있습니다. 현재 report-writer와 file-organizer가 포함됩니다. Codex 전용 도구를 요구하는 모든 skill이 그대로 호환되는 것은 아닙니다.

파일 권한은 `LOCAL_LLM_AGENT_WORKSPACE`와 추가 `LOCAL_LLM_AGENT_ALLOWED_ROOTS` 폴더 안으로 제한합니다. 예:

```dotenv
LOCAL_LLM_AGENT_WORKSPACE=C:/Users/user/Documents/AgentOutputs
LOCAL_LLM_AGENT_ALLOWED_ROOTS=["D:/ApprovedDocuments"]
```

추가 경로도 읽기·새 파일 생성 모두 허용하므로 필요한 폴더만 지정하세요. 숨김 파일, 경로 이탈, 기존 파일 덮어쓰기는 거절합니다. 도구는 list_files, read_file, create_directory, write_file, write_report, memory_search, list_skills, read_skill입니다. 명령 실행/파일 삭제/기존 파일 수정은 제공하지 않습니다.

Gemini 웹 연결에서는 질문, 선택 skill, 읽은 파일과 검색한 기억이 Gemini에 전달됩니다. 개인 테스트 데이터만 두고 회사 업무 파일은 회사 GLM 모드에서 사용하세요.

검증용 요청: report-writer를 선택하고 '연결 테스트 보고서를 새 Markdown 파일로 만들고 다시 읽어서 확인해줘'라고 요청합니다. 최종 답변뿐 아니라 실행 단계의 artifact와 실제 파일을 확인하세요.

## 바로 써볼 요청 예시

* `report-writer` 선택: `sample.txt를 읽고 핵심 사실 3개와 불확실한 점을 Markdown 보고서로 만들어줘.`
* `file-organizer` 선택: `작업 폴더 파일을 목록화하고 확장자별 개수를 새 보고서로 저장해줘.`
* 자동 선택: `과거의 비슷한 실패 사례를 검색하고, 이번 문제를 확인할 체크리스트 파일을 생성해줘.`

실제 설비 조작, 파일 삭제, 기존 파일 수정, 메일 전송처럼 되돌리기 어려운 작업은 현재 도구에 포함하지 않았습니다. 필요한 경우 새 도구를 별도로 설계하고 권한 범위를 명시해야 합니다.
