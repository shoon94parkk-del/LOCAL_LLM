# P2 Agent Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the current LOCAL_LLM MVP into a durable single-user company Agent with multi-turn sessions, crash recovery, automatic document memory ingestion, safe file editing, hardened command execution, and executable regression evals.

**Architecture:** Preserve FastAPI, SQLite, Agent, MemoryStore, and existing GLM adapters. Add focused Session and DocumentMemory services, extend Agent run metadata and tools, then expose thin API/UI integrations.

**Tech Stack:** Python 3.11, FastAPI, SQLite/FTS5, pytest, existing Selenium/Playwright adapters.

**Spec:** `docs/superpowers/specs/2026-09-17-agent-completion-design.md`

## Global Constraints

- Existing API behavior remains backward compatible.
- Existing Selenium/Playwright/Browser Bridge adapters remain supported.
- Mutating tools require approval by default.
- No OS-level sandbox claim.
- Actual company GLM DOM cannot be verified in CI.

---

### Task 1: Persistent multi-turn sessions and run recovery

**Files:**
- Modify: `app/db.py`
- Create: `app/sessions.py`
- Modify: `app/agent.py`
- Modify: `app/main.py`
- Test: `tests/test_sessions_recovery.py`

**Interfaces:**
- Produces: `SessionStore.create()`, `SessionStore.add_message()`, `SessionStore.messages()`, `SessionStore.list()`.
- Agent `run(..., session_id=None)` stores session id and injects recent messages.

- [ ] Write tests for session creation, message persistence, multi-turn context, and running->interrupted startup recovery.
- [ ] Run focused tests and confirm they fail for missing session support.
- [ ] Add `sessions` and `session_messages` schema.
- [ ] Implement SessionStore.
- [ ] Extend Agent run payload and resume states.
- [ ] Add session API endpoints and optional `session_id` to AgentRequest.
- [ ] Run focused and existing tests.

### Task 2: Automatic workspace memory document ingestion

**Files:**
- Modify: `app/db.py`
- Create: `app/document_memory.py`
- Modify: `app/main.py`
- Modify: `app/memory.py`
- Test: `tests/test_document_memory.py`

**Interfaces:**
- Produces: `DocumentMemory.sync() -> dict` with scanned/added/updated/removed/chunks.
- Adds `source='document'` rows to `memory_fts`.

- [ ] Write tests for new file indexing, modified file replacement, deleted file cleanup, and retrieval.
- [ ] Run tests and verify RED.
- [ ] Add document tables and chunk indexing implementation.
- [ ] Sync at app startup and before chat/agent request.
- [ ] Add `POST /api/memory/import`.
- [ ] Run focused and full tests.

### Task 3: Safe existing-file editing and command hardening

**Files:**
- Modify: `app/agent.py`
- Test: `tests/test_agent_safety_edit.py`

**Interfaces:**
- Produces Agent tool `edit_file(path, old_text, new_text)`.
- `run_command` accepts workspace-local `.py` scripts only for Python execution and blocks inline/module execution.

- [ ] Write tests for exact single replacement, duplicate match rejection, approval requirement, `python -c` rejection, and outside-workspace script rejection.
- [ ] Run focused tests and verify RED.
- [ ] Implement `edit_file` with hashes, unified diff, and verification.
- [ ] Harden `run_command` parsing.
- [ ] Update Agent tool prompt/capabilities.
- [ ] Run focused and full tests.

### Task 4: Session-first UI and document import controls

**Files:**
- Modify: `app/web_ui.py`
- Test: `tests/test_ui_contract.py`

**Interfaces:**
- UI calls `/api/sessions`, keeps `currentSessionId`, and passes it to `/api/agent/run`.
- Settings exposes `/api/memory/import`.

- [ ] Add contract tests for required endpoint strings and session_id payload use.
- [ ] Run test and verify RED.
- [ ] Update sidebar/new chat/send/load behavior around Sessions.
- [ ] Add memory import button/status.
- [ ] Run focused and full tests.

### Task 5: Executable eval runner and documentation

**Files:**
- Create: `app/evals.py`
- Create: `scripts/run_evals.py`
- Modify: `README.md`
- Modify: `docs/COMPANY_SETUP.md`
- Test: `tests/test_evals.py`

**Interfaces:**
- Produces `run_static_evals(path, capabilities) -> dict`.
- CLI exits nonzero when scenario tool requirements reference unsupported capabilities.

- [ ] Write tests for passing and failing capability checks.
- [ ] Run focused tests and verify RED.
- [ ] Implement eval loader/checker and CLI.
- [ ] Document sessions, memory folder auto-ingest, safe edit, recovery, eval command, and sandbox limitation.
- [ ] Run complete `pytest -q` in GitHub Actions.
- [ ] Merge only after the branch CI is green.
