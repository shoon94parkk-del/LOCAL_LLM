# LOCAL_LLM decision log

Append-only high-risk decisions.

## 2026-09-22 — Durable project memory
Added repository-level agent rules, architecture memory, regression guardrails, and this log so company integration and safety decisions are not later removed by convenience refactors.

## 2026-09-16 — Selenium becomes the practical company mode
The company LLM is available through a web UI rather than an API. A Selenium adapter was added with clipboard input, DOM polling, serialized WebDriver access, async-safe thread handoff, and `[[END]]` continuation detection.

## 2026-09-16 — Knowledge lifecycle must be evidence-aware
Case -> Reflection -> Knowledge was hardened with duplicate merge, conflict isolation, evidence links, validation state, and retrieval priority. "Self-improvement" means memory/knowledge refinement, not hidden model retraining.

## 2026-09-16 — Chat-first and safer bridge
Agent UX was moved toward chat-first operation and safer browser-bridge behavior. Repeated tool-call loops and malformed JSON/path responses were handled explicitly rather than broadening tool authority.

## 2026-09-16 — Side effects require approval and resumability
File/report/Git/Python actions gained approval gates, bounded execution, visible plan state, retry categories, and resumable runs. Future convenience changes must not bypass these controls.

## 2026-09-16 — Local embeddings are optional
Baseline FTS5 works without embeddings. Local embeddings may improve retrieval when a compatible model exists, but the system must remain functional when embedding mode is disabled.
