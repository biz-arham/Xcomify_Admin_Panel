# Architecture and design decisions

## Scope

This build is a local-first vertical application, not a hosted SaaS deployment. Core operational features work against a persistent database. External Google credentials and source approval remain explicit owner-controlled inputs. No live account universe or financial history was invented.

```text
Browser UI (same origin)
        |
FastAPI routes -> authentication / CSRF / scoped permissions
        |
SQLAlchemy database: stores, observed orders, targets, jobs, intents, audit
        |
Persistent elected worker -> fixed-host Google adapter -> private spreadsheet
        |                                               |
        +--------- verified result / conflicts <--------+

Existing Chrome extensions -------------> same existing spreadsheet
```

## Authority and consistency

The app owns users, assignments, notes, targets, tasks, local financial adjustments, approvals and audit. Observed mapped Google fields follow the source. Pending proposals are separate from confirmed values. The database owns only explicitly owner-approved app fields under a real single-writer contract. This is eventual consistency, not a distributed transaction between Google and the database.

A unique order key is `(store_id, ebay_id)`. A postcode is a write validation guard, not a second financial identity that duplicates an order after address correction. Row positions are re-resolved. Full snapshots reconcile changed old rows and mark absent records unobserved without deleting them. Duplicate/multi-item rows become review issues; allocation is deferred, not silently guessed.

Writes preserve the smallest cell and use stringValue for IDs/tracking/text. Numeric values cross Google's JSON number interface but are verified back against the application's decimal representation; financial calculations remain decimal on the server. Formula/spill/merged/protected cases are conservatively blocked. Google cannot be made transactional by the app's database lease; external independent writers must be coordinated.

## Queue and crash recovery

`jobs` and `write_intents` are the durable queue/outbox. API creation and queue insertion occur in the same application transaction; no Redis durability assumption exists. The worker lease serializes this release's workers globally. Read jobs retry bounded transient failures. Write states differentiate proposed, queued, validating, submitting, verifying, confirmed, conflict, unknown, failed and cancelled. A crash after submission produces `outcome_unknown`, not a blind repeat.

An idempotency key and canonical proposal detect repeated application requests. Every execution rechecks permission, owner/MFA approval, current mapping, freeze/status and identity before sending. A stale worker lease cancels submission. An already submitted request cannot be recalled.

This intentionally serial architecture sacrifices throughput for a small, understandable local deployment. Full scans and per-store aggregations may be expensive for many large stores. No 10-50-store benchmark or guaranteed two-minute synchronization is asserted. Large grids fail safely above their configured cap rather than silently truncating.

## Financial definitions

The implemented input basis is already-net order earnings. No gross revenue, withheld settlement funds or additional marketplace fee deductions are inferred. Profit is net earnings minus supplier costs, extra expenses and separately represented refunds, plus supplier credits; filler cost is optional by store. Additional entries are explicit signed profit adjustments. Missing/invalid inputs are incomplete, never zero. Owner approval defines the meaning; it is not independent financial assurance.

Only supported two-decimal currencies are exposed by the UI. Server computations use Decimal and exact SQLite text/PostgreSQL numeric storage. APIs carry money as strings. Displayed graphs use browser Number for visualization only; they are not authoritative accounting arithmetic. Different currencies and incompatible profit bases are never totaled into one verified amount without a specified conversion policy; automatic FX is not included.

Closed months return their stored closing snapshot. Later source discrepancies stay review issues; no silent historical rewrite. In-app reopen/restatement remains a future reviewed feature.

## Identity and authorization

Role presets are enforced on the server and coupled to store assignments. The owner is organization-scoped, not globally authorized across other organizations. Another organization can be constructed in tests to verify isolation, but public multi-tenant onboarding/billing is not offered. Google integration identity is separate from app login. Direct Google Editor permissions remain outside app permissions.

Bootstrap requires a high-entropy local setup code. All real workspaces begin empty; demo uses a separate database path and cannot connect/write Google. The front end never quietly substitutes synthetic data after an API error. Local theme storage is optional. Secret storage, session handling and production limits are detailed in SECURITY.md.

## API and schema

`docs/openapi.json` is generated from the delivered application. Owner-authenticated `/api/openapi` provides the same contract. Financial/target conflict checks use database versions without implying a Google cell version. Initial DDL references are in `schema/`; schema installation uses SQLAlchemy metadata. The v1 marker blocks accidental downgrade from newer versions but is not a full future migration framework.

## Explicit deviations from the previous master prompt

FastAPI/SQLAlchemy/vanilla UI replaces the requested TypeScript stack. Local SQLite replaces a mandatory managed PostgreSQL dependency for the first runnable package. A transactional database queue replaces Redis/BullMQ. Custom TOTP/session logic uses maintained cryptographic/password libraries instead of a managed auth provider. Broader Sheets OAuth replaces a selected-file Picker flow. Full multitab line/supplier allocation, signed immutable audit, managed secrets, configured FX, paired TV sessions and advanced reports/automation are not claimed delivered. See FEATURE_STATUS.md.
