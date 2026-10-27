# Verification record

Build date: **27 October 2026**. Environment: Linux, Python **3.13.5**, FastAPI **0.128.2**, SQLAlchemy **2.0.50**, SQLite, pytest **9.0.2**, Chromium and Playwright **1.57.0**. No live eBay or Google account was used.

## Automated application tests

**63 passed, 1 non-failing warning, in 26.43 seconds.** The warning is an httpx test-helper deprecation (`data=` for raw test text) in the intentional invalid-content-type test, not an application failure. Full output: `verification/pytest-results.txt`.

The usual user command is `python -m pytest -q tests`. The build container had an interpreter startup/shutdown hook issue, so the verification runner bypassed that environment hook, invoked `pytest.main` with installed packages and explicitly flushed/exited afterward. The application tests, assertions and runtime code themselves were not replaced. This environment-only runner is intentionally not part of the distributed app.

Coverage includes:

- Private bootstrap, repeat-setup refusal, no public registration/docs, Origin/CSRF/JSON checks and validation error redaction.
- Exact decimal arithmetic, missing versus zero cost, filler policy, approved basis, duplicate IDs, cross-store identity, separate currencies, refunds, credits, idempotent adjustments and closed-period snapshots.
- Zero/unset, negative and above-target attainment; target version conflicts; no initial/revision celebration replay; persisted per-user milestone claims and scope isolation.
- CSV preview/no-write, duplicate validation, leading-zero IDs, formula-injection neutralization and optimistic local edits.
- Two-organization isolation, assigned-store permissions, direct-ID failures, operations financial redaction, viewer raw-cost redaction and export denial.
- Single-use invitation, user deactivation, session revocation, TOTP standard vector/replay protection, atomic one-use recovery code consumption and MFA gates.
- Encrypted credential omission, actual encrypted SQLite backup and restore into a new directory, restored write-stop/session/queue controls, demo database isolation and schema downgrade refusal.
- Deterministic Google adapter simulations: idempotent imports, zero/missing cost, multi-item quarantine, complete absence without deletion, row sorting/relocation, postcode/header/duplicate/formula/array/protected/merged barriers, three-way conflict and equal-value no-op.
- Live-control checks during queued execution: emergency stop, inactive store, removed actor, changed mapping, Sheet ownership, stale lease and cancellation during read.
- Timeout after simulated remote success, failed read-back, persisted worker result and crash-after-submission unknown-state handling.
- HTTP contract check that one-cell Google write uses `userEnteredValue` only and dangerous-looking text is sent as literal `stringValue`.

These are meaningful regressions, **not exhaustive coverage of every requirement in the original enterprise blueprint**. Fake/contract Google tests are not represented as successful live OAuth or Sheet tests.

## UI/browser checks

**14 views rendered without JavaScript page errors** at a desktop viewport of 1536 x 1024. Mobile target layout checked at 390 x 844 with no horizontal document overflow. Screenshots in `verification/screenshots/` show visibly labeled synthetic data.

Verified interactive flows: account setup/login, target revision persisted to the backend, searching for a nonexistent order and clearing it, creating a local order, correcting its supplier cost and observing changed profit, creating a task, switching theme and honoring reduced-motion CSS.

**Harness limitation:** the available Chromium was managed with a policy blocking all URL navigation. Its policy was not changed. The actual application HTML/CSS/JS was loaded into an in-memory page; browser fetch calls were relayed to the running real local HTTP backend with its real cookies. No fabricated API responses or mock UI data were substituted. HTTP Origin/CSRF/cookie/access behavior was tested separately through API tests. Therefore this is UI-to-real-backend interaction verification, not a claim of normal-origin browser transport validation on Windows or a cloud domain.

The blocked-storage browser environment exposed an optional-theme-storage failure, which was fixed with a safe fallback. Tests also led to tightened raw-cost redaction, closed snapshot preservation, cancellation-before-submission checks, demo isolation and atomic recovery-code consumption.

## Additional checks

Python source parsed successfully. `node --check xcomify/static/app.js` passed. OpenAPI generated from the delivered app: 54 distinct API paths. Reference DDL generated for 25 tables on SQLite/PostgreSQL dialects. Generating PostgreSQL DDL is **not** equivalent to running a PostgreSQL database or a container deployment.

## Not verified

Actual Google OAuth/consent/token refresh; private Google test-file read/write; live quotas/latency; your real Sheet formulas/mappings/financial definitions; your actual Chrome extension versions; Windows execution; fresh internet dependency installation; Docker build/PostgreSQL runtime; cloud hosting/TLS/proxy; 10-50-store load capacity; email delivery; independent penetration test; legal/privacy compliance; promised uptime/recovery SLA.

Production write-back requires the owner to complete these applicable integration/release checks, rather than treat screenshots or this test count as authorization.
