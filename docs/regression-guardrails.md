# LOCAL_LLM regression guardrails

Last updated: 2026-09-22

## Company privacy/config
- Internal LLM URL/selectors/cookies/credentials/browser profile never enter Git.
- Real company files/data are not used in public regression tests.
- Repository remains runnable with mock mode.

## Browser adapters
- Do not assume an API exists when the company only exposes a web UI.
- Selenium access remains serialized/thread-safe.
- Blocking WebDriver operations stay off the FastAPI event loop.
- Missing `[[END]]` triggers bounded continuation; do not silently return a known-truncated answer.
- Adapter timeouts and selector failures must surface actionable errors.

## Agent safety
- Side-effecting changes retain explicit approval rules.
- Allowed-root restrictions remain enforced.
- Existing file overwrite/delete/arbitrary shell are not silently enabled.
- Run state remains resumable after approval/failure where designed.
- Prevent repeated/duplicate tool-call loops.

## Memory/knowledge integrity
- Cases retain provenance.
- Duplicate Knowledge may merge; conflicting Knowledge is isolated.
- Unvalidated knowledge does not silently replace validated knowledge.
- Reflection does not claim model-weight training.
- Feedback labels (resolved/failed/important knowledge) remain meaningful inputs to lifecycle.

## Embeddings
- Embeddings remain optional.
- No silent internet model download in restricted environments.
- Unsupported local model formats fail clearly or run with embeddings disabled.
- Model replacement requires explicit reindex rather than mixing vector spaces.

## Compatibility
- Preserve Windows path normalization/escaping behavior.
- Keep long-document limits unless intentionally revisited with tests.
- Public CI uses synthetic/mock paths and must stay green without company network access.
