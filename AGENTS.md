# LOCAL_LLM agent rules

This repository is a local/company engineering agent that wraps web-only LLMs. Repository memory is authoritative.

## Read before editing
1. `docs/project-memory.md`
2. `docs/regression-guardrails.md`
3. `docs/decision-log.md`
4. `README.md`
5. `docs/COMPANY_SETUP.md`
6. Tests closest to the changed component

## Required workflow
1. Search prior commits/tests for the same behavior before editing.
2. Keep company-specific URL/selectors/cookies/profile paths out of Git.
3. Use mocks/synthetic text in tests; never add real company data.
4. Preserve approval gates and bounded/resumable execution for side-effecting tools.
5. Add/update pytest coverage for behavioral changes.
6. Run `pytest -q`.
7. Update decision log and memory/guardrails when architecture or safety rules change.

## Current company integration contract
- Company LLM may be available only through a web UI; do not assume an API exists.
- Supported adapters: `mock | playwright | selenium | browser_bridge`.
- Current company-recommended path is Selenium.
- Runtime config belongs in local `.env`.
- Browser profiles, cookies, internal URLs, selectors, and credentials are local-only.

## Never regress
- Selenium WebDriver access is serialized because it is not thread-safe.
- Long-running browser work stays off the async event loop.
- `[[END]]` is used to detect response truncation and bounded continuation.
- File/tool mutations retain approval gates and allowed-root restrictions.
- Existing-file overwrite/delete/arbitrary shell execution are not silently enabled.
- Memory promotion keeps evidence, conflict isolation, and validation thresholds.
- Embeddings remain optional/local and must not auto-download models in restricted environments.
