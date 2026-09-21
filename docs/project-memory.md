# LOCAL_LLM project memory

Last updated: 2026-09-22

## Purpose
LOCAL_LLM wraps an internal web-only LLM with an agent, local tools, SQLite Memory, optional local embeddings, skills, and a reflection/knowledge lifecycle. It is designed for restricted company environments where direct model APIs may not exist.

## Core architecture
```
Browser -> FastAPI -> Agent -> Memory Retriever -> GLM Adapter
                       |          |                |
                       |          +-- SQLite FTS5 -+
                       |          +-- Embedding(optional)
                       |
                       +-- Files / Reports / Python / Git / Skills

Case -> Reflection -> Candidate Knowledge -> validation/conflict handling
```

Adapters:
- `mock`
- `selenium` — current company-recommended web-UI path
- `playwright`
- `browser_bridge`

## Company-web integration
- Company URL/selectors are configured only through local `.env`.
- Do not commit internal URLs, selectors, credentials, cookies, or browser profiles.
- Selenium starts Chrome first and may fall back to Edge.
- Prompt entry uses clipboard paste where required.
- Browser/WebDriver work is serialized with a lock because Selenium is not thread-safe.
- Async entrypoints move blocking browser work off the event loop.
- Responses use a `[[END]]` marker; missing marker triggers bounded continuation rather than silently accepting truncation.
- Company DOM/WebDriver compatibility must ultimately be validated on the company PC.

## Agent execution model
- Chat-first UI.
- Bounded multi-step agent execution.
- Side-effecting tool changes require approval according to policy.
- Runs are resumable; failed/retry/plan state is recorded.
- File access is restricted to configured workspace/allowed roots.
- Existing file overwrite/delete and arbitrary shell commands are intentionally constrained.
- Git/Python tools operate only inside explicit allow/approval boundaries.

## Memory/self-improvement
- Conversations and feedback can be promoted into Cases.
- Reflection derives reusable Knowledge candidates from real Cases.
- Duplicate knowledge is merged.
- Conflicting knowledge is isolated instead of overwriting a validated fact.
- Validation/confidence and evidence links determine promotion/search priority.
- This is memory/knowledge-based improvement, not model-weight retraining.
- SQLite database: `data/memory.db`; do not manually edit it.

## Retrieval
- SQLite FTS5 is the baseline.
- Optional local embedding hybrid retrieval is supported.
- Local embedding adapter expects a complete SentenceTransformers-compatible model directory.
- No automatic model download is assumed in restricted environments.
- If model format is unsupported, disable embeddings rather than pretending keyword search is an embedding replacement.
- Reindex is explicit when the local embedding model changes.

## Long-document behavior
Current text limits are intentionally high (240,000 characters) for company engineering documents:
- chat question
- read_file
- write_file
- write_report
- tool-result handoff between Agent steps

Direct file readers currently focus on UTF-8 text formats; PDF/XLSX need dedicated readers.

## Privacy/security
- Use mock/synthetic samples in public tests.
- Do not commit company data or internal browser state.
- `.browser-profile` remains local.
- The public repository must remain runnable in `mock` mode without internal infrastructure.

## Verification
- `pytest -q`
- `GET /health`
- company-PC Selenium selector/send test
- optional local embedding diagnostics/reindex
- tool approval/resume flow with non-sensitive sample files
