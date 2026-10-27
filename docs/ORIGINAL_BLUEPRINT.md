# XCOMIFY CENTRAL COMMAND
## Final master build prompt and implementation contract
Version 2.0 | Prepared 27 October 2026

This is a development specification, not an already implemented application or a security certification. It supersedes earlier informal feature lists where they conflict with the safety rules below. Confirmed business requirements remain binding; proposed technical defaults must be documented and configurable. Read the entire specification before changing existing systems.

## 01. Mission and delivery discipline

Act as the lead architect and implementation team for a private Xcomify web application that manages multiple eBay stores, their separate existing Google Sheets, operational work, and individual monthly PROFIT targets. Build working software in verified milestones, not only a dashboard mockup or another proposal.

Core commitments: two-way Google Sheets read/write; separate profit targets per account; one combined management dashboard; animated target progress; preservation of existing Sheets and Chrome extensions; secure employee access; transparent calculations; recoverable operations.

Use sensible defaults for reversible design choices. Do not repeatedly ask questions already answered here. Before accessing production, changing financial meanings, adding spreadsheet columns, modifying sharing, or authorizing writes, obtain the required owner approval. Missing credentials must block only the affected integration, not independent development.

At each milestone, report implemented, tested, blocked, and deferred features separately. Supply test commands and actual results. Never label mocked data as live, a queued write as completed, or an untested system as production-ready. Do not promise perfect security, lossless synchronization under uncontrolled concurrent edits, unlimited scale, or guaranteed performance.

## 02. Fixed scope and priorities

P0: authentication and owner MFA; store management; per-store permissions; connection/mapping wizard; read-only import; background reconciliation; controlled two-way writes; conflict resolution; accurate profit and data-quality views; monthly targets and restrained animations; orders and tracking visibility; audit history; essential alerts; backups, restoration, and write-stop controls.

P1: employee tasks, configurable reports and exports, recurring report delivery, office display mode, saved views, target pacing, advanced reconciliation, simple rule automation, period closing, and client read-only dashboards.

P2: optional official eBay integrations, a separately approved extension-to-backend connector, explainable AI summaries, advanced forecasting, client profit-sharing statements, and richer workflow automation.

P0 must work before P1 expansion. Do not build a general-purpose automation language or full accounting/ERP platform for the first release. Optional modules must not become hard dependencies for basic sync and targets.

Out of scope without separate approval: purchasing items, cancelling supplier orders, submitting eBay tracking, issuing refunds, contacting customers, collecting marketplace passwords, autonomous financial changes, public registration, payroll, and statutory accounting or tax filing.

## 03. Architecture and deployment shape

Use a TypeScript modular monolith: Next.js/React frontend; NestJS API; a persistent worker process; PostgreSQL as the durable application database; Redis/BullMQ for job delivery; private object storage for reports and backups. Frontend choices: Tailwind, accessible shadcn/ui components, TanStack Query, a maintained chart library, and Motion for animation. Lottie is optional, not necessary for basic progress.

Keep application, API, and worker modules in one maintainable repository. Share validated contracts and financial logic. Use Prisma or an equivalent mature ORM, versioned migrations, OpenAPI, automated tests, and Docker development setup. Verify supported dependency versions against official documentation when implementing; pin versions and commit the lockfile.

Browser -> authenticated API -> scoped services -> PostgreSQL/outbox.
Worker -> validated queued intent -> Google APIs -> read-back verification -> database reconciliation.
Existing extensions -> existing Sheets, unchanged.
Dashboard updates -> authenticated server events or bounded polling, never a public channel.

The database owns users, permissions, targets, application notes, approvals, and audit events. Sheets remain authoritative for mapped operational fields unless field ownership is explicitly changed. Store observed Sheet values separately from pending application proposals. Redis must not be the only record of unfinished business operations.

Run workers on infrastructure that supports persistent background processes. Closing a browser must not stop server sync. This does not change an existing extension's own active-tab or browser-open requirements. Do not describe an in-memory timer or a request that continues after response as reliable scheduling.

## 04. Preserve the current business workflow

Do not change spreadsheet IDs, numeric tab IDs, tab names, headers, column order, formatting, formulas, protected ranges, data validation, or extension code without explicit approval and a rollback plan. Do not add hidden identifier columns as an unannounced workaround.

Preserve the order-copy extension, AliExpress reference/tracking fetcher, Google Sheet tracking updates, and eBay tracking-paste extension as independent tools. Do not assume column J, K, L, or M has the same meaning in every file. Earlier workflows have used different meanings for K; mapping must be verified per connection, not inferred from a generic example.

Record the actual extension version and dependency contract: input columns, output columns, matching keys, tab/header assumptions, status values, and side effects. Obtain authorized extension files or recordings for regression testing; do not claim compatibility solely because a mock matches.

Import eBay order IDs, AliExpress references, tracking numbers, and postcodes as strings. Preserve leading zeros and source formatting. Keep original values alongside normalized matching values. Use eBay order number plus postcode for the existing tracking validation where that workflow requires it, but do not make a corrected postcode create a new financial order.

Keep one canonical parent order per store and eBay order ID where that ID is verified unique. Represent line items, supplier purchases, and shipments separately. One eBay order may have multiple items or suppliers; one supplier shipment may cover several lines. Do not multiply parent earnings when importing repeated rows.

Courier prefix mappings are configurable hints, not proof of carrier identity. Seed only owner-approved mappings such as H0/Evri, JJ/InPost Shops, LR/Royal Mail, QP/Royal Mail and, where still used, GV/Royal Mail. Do not infer delivered status or successful eBay upload from a tracking value alone.

## 05. Private Google authorization and onboarding

All operational Sheets remain Restricted/private. Never require 'Anyone with the link - Editor'. Authorize a named Google identity or a dedicated service account with actual file access. An employee may use authorized app functions without receiving the integration credential; this must not bypass permissions or ownership of the underlying files.

Preferred connection: maintained Google OAuth web-server libraries, explicitly selected files, offline access where needed, and the narrowest workable scope. Evaluate drive.file with an appropriate file-selection flow; merely pasting a Spreadsheet ID is not an OAuth grant. If broader scope is necessary, explain and approve it. No domain-wide delegation by default. [S2, S3]

Use state validation, exact redirect URI matching, secure server-side code exchange, and supported PKCE protection. Encrypt refresh tokens using managed keys. Keep tokens out of browser storage, logs, URLs, and exports. Serialize token refresh per connection, handle invalid_grant, and support disconnect/revocation. Separate Google sign-in identity from the optional Google Sheets integration identity.

The wizard must: identify authorized account and granted scope; select spreadsheet and numeric tab ID; inspect locale/timezone/header; propose mappings; show sampled values and formulas; validate identity/duplicates; classify field ownership; preview import; run read-only reconciliation; and finally offer a separate owner-controlled write-enable gate.

Google scopes apply at spreadsheet-file level, not individual tabs. App permissions and optional Google protected ranges are separate controls. Changing protected ranges requires approval and compatibility testing. App role restrictions do not revoke a user's independently granted Google Editor access. [S2]

## 06. Mapping and source validation

Each mapping version records organization/store/connection, spreadsheet ID, numeric sheet ID, observed tab name, header row, data ranges, expected headers, field types, identity rules, locale, currency, timezone, formula columns, and read/write ownership. Track who approved it and its effective date.

Import both evaluated values and the formula information needed to protect formula cells. Handle blank rows, trailing empty cells, totals, repeated headers, merged cells, array-formula output, hidden/filter rows, numeric date serials, formulas returning empty strings, and formula errors. Do not interpret all blank values as zero.

Do not silently exclude hidden or filtered rows. Define inclusion rules explicitly. Quarantine incompatible schemas instead of guessing. Changing a header, moving a column, losing a tab, encountering an unknown currency, or failing identity validation pauses affected writes and exposes a useful review action.

A row number is a temporary locator, not identity. Re-resolve a unique order and applicable postcode before writing. A non-unique match is a conflict, never permission to pick the first row. Store row fingerprints only as change-detection evidence, not a database-like concurrency guarantee.

## 07. Two-way synchronization without unsafe guarantees

Implement eventually consistent two-way synchronization with field-level controls. Use polling as the baseline, with an initial configurable 2-minute aim and an adaptive 1-5-minute operating range where measured workload and quotas permit. These are design targets, not an SLA. Show last successful scan, freshness, backlog, and stale-data state. [S1]

Apps Script edit triggers must not be the sole change detector: API/script writes do not generally activate them. The default implementation must not require installing Apps Script into existing files. Optional triggers or Drive change notifications may be hints, never substitutes for reconciliation. [S4]

Poll in batches; partition active and historical ranges; periodically perform complete reconciliation so old refunds/corrections are not missed. Fingerprints can reduce processing after reads, but do not magically provide a native changed-rows feed. Formula-result changes matter even when formula text is unchanged.

Respect project and per-user quotas, including shared credentials across stores. Use a quota budget, jitter, exponential backoff, bounded retries, circuit breaking, queue visibility, and fair scheduling. Measure request/payload costs instead of claiming that all stores refresh instantly. [S1]

Field classes:
A. Sheet/extension-owned: import automatically; app edits become review proposals, not blind writes.
B. Application-owned: write only approved existing non-formula cells, or remain database-only when no safe column exists.
C. Shared-edit: enable only after ownership and concurrency safeguards are approved and tested.
D. Computed/protected: read-only.

Two-way capability does not mean unrestricted automatic editing of every cell. Never downgrade the whole product to read-only without explanation; provide genuine write-back for approved fields and a clear proposal workflow for unsafe shared fields.

Use three-way comparison: last confirmed base, latest Sheet value, proposed app value. Merge independent changes; identical values are no-ops; competing changes to the same field require review. Read again immediately before writing, but do not claim this closes the final read/write race.

The documented Sheets write methods do not expose an expected-cell-value compare-and-set parameter. Google also cautions about concurrent collaborator changes. Therefore application locks, timestamps, fingerprints, and post-write verification cannot guarantee zero lost updates from independent writers. Strict protection requires an enforceable single-writer/protected workflow or a safe coordination mechanism covering every writer. If that cannot be achieved without breaking an extension, keep the affected field Sheet-owned and surface a proposal instead. [S5, S6]

## 08. Durable writes, ambiguity, and recovery

Use a database transaction to save a write intent and outbox event. Do not imply a distributed transaction exists between PostgreSQL and Google Sheets. Expose states: proposed, awaiting_approval, queued, validating, submitting, verifying, confirmed, conflict, outcome_unknown, failed, and cancelled.

At execution time, recheck actor authorization, store status, write-enable flag, emergency freeze, mapping version, unique record identity, expected values, and target cell protection. If authorization or mapping changed, stop and require renewed review. Serialize app writers per spreadsheet resource, not only per store, with lease expiry and stale-worker protection.

Write the smallest approved cell set. Never replace a complete row or data range for convenience. Preserve formulas and formatting. Write external IDs as literal text with safe value-input handling; do not interpret customer/supplier content as formulas. Bound bulk changes and show the exact before/after preview.

Give each intent an idempotency key, canonical proposed payload, and scoped audit record. A timeout may occur after the remote write succeeded: reconcile before retrying, particularly before any append. Never assume an HTTP timeout proves nothing changed. Do not offer generic row appends or deletions in P0.

Verify by reading back identity and intended values. A successful verification describes that observed moment, not a perpetual concurrency guarantee. Show pending values separately from confirmed financial values; do not celebrate a target based on an unconfirmed write.

Missing rows become 'not observed' after a successful complete scan; investigate repeated absence before tombstoning. An outage or partial scan is not evidence of deletion. Do not delete remote records, mark refunds, or erase financial history simply because a row disappears.

After database restore, deploy rollback, or prolonged outage, pause writes, reconcile remote state, and inspect pending intents before replay. Undo must be a new validated compensating action; do not overwrite newer legitimate work with a stale backup.

## 09. Profit definitions and financial integrity

Configure and approve a financial definition per store before presenting a number as verified profit. Record whether the source is gross selling revenue, net order earnings, settlement payout, or an existing Sheet profit formula. A bank payout is not automatically order revenue; reserves and timing can differ.

For verified net earnings, subtract only supplier costs, expenses, and adjustments not already included. For gross revenue, subtract mapped fees and costs once. For existing profit formulas, reconcile their meaning before using or replacing them. Never subtract advertising fees or refunds twice because they appear in both source earnings and a separate column.

Provide three distinct views when needed: operational contribution, reconciled business profit, and cash movement. Do not call 'earnings minus product price' fully net business profit if required expenses are excluded or unknown. Never invent gross sales where only net earnings are available.

Preserve the existing rule that AliExpress filler-item costs are excluded from target-item operational profit if that is the active workflow. Show any excluded filler/unallocated costs separately. Do not silently introduce them into legacy targets or hide them from a more complete business-profit view. The owner approves which explicitly named profit basis drives each target.

Handle partial/full refunds, fee credits, supplier refunds, replacement costs, cancelled/unfulfilled orders, multi-item allocation, shipping, advertising, and fixed expenses according to documented inclusion rules. Allocate shared costs once with a visible method. A negative order is valid data, not an import error.

Missing cost means unknown/incomplete, not zero. Maintain confirmed subtotal, provisional subtotal, missing-record count, and financial coverage. Suppress misleading 'target achieved' events when required data is incomplete. Define verified as reconciled against configured sources, not an audit opinion or statutory certification.

Use exact decimal arithmetic and PostgreSQL numeric values; send decimal strings across APIs. Define currency precision and rounding explicitly. Preserve original currency, FX rate, provider, effective date, and conversion policy. Do not add GBP, AUD, USD, EUR, or CAD without conversion; group totals by currency when no approved rate is available.

Prevent duplicate expenses through source keys and reconciliation; do not use amount/date similarity as automatic proof of duplication. Keep financial entries and adjustments append-oriented, with source provenance and a versioned calculation definition. Show 'How calculated' down to source rows and exclusions.

Store event time in UTC and retain source/reporting timezone. Configure store-local month boundaries and date parsing. Choose a refund recognition policy explicitly. Closed periods require authorized reopening or a current-period adjustment, not silent historical rewriting. Record target-basis changes and compare like-for-like periods.

## 10. Store targets, pacing, and animation

Primary target: monthly profit in the store currency and approved profit basis. Support target templates, future scheduling, history, revisions, custom periods, and optional derived daily pacing. Reject negative targets; an unset or zero target shows 'No target', never division by zero.

Attainment = eligible actual profit / positive target * 100.
Remaining = max(target - eligible actual profit, 0).
Overachievement = max(eligible actual profit - target, 0).
Negative profit must remain visible; clamp only the graphic fill, not the numeric result. Above-target values can exceed 100% numerically.

Default pacing uses completed store-local days. Remaining required daily profit uses a clearly labeled remaining-day convention. Simple projections must disclose the observed daily-rate method, exclude incomplete days consistently, and show 'insufficient history' when appropriate. Do not fabricate probability/confidence percentages or imply seasonality from insufficient data.

Visuals: accessible circular rings, horizontal progress, animated counters, 25/50/75/90/100% milestones, restrained trophy/confetti at completion, and an overachievement badge. Keep data readable without animation or color alone; respect reduced-motion preferences and keep sound off by default.

Persist milestone events by store, period, target version, milestone, and basis. Initial imports do not produce a backlog of celebration. Falling below and re-crossing a milestone does not spam notifications. Target reductions/revisions must not manufacture repeated achievement events. Track 'achieved previously' separately from current attainment after refunds.

Combined target progress uses sums on a compatible currency/basis, not an unweighted average of store percentages. Distinguish stores with no target from stores at zero attainment.

## 11. Required screens and product behavior

Main navigation: Overview, Stores, Orders, Profit & Reconciliation, Targets, Tracking, Team & Tasks, Reports, Sync & Conflicts, Notifications, Audit, Settings.

Overview: authorized stores only; profit by currency/basis; target progress; missing costs; operational attention; last sync/freshness; trends; and filters by date, store, marketplace, manager, and currency. Every headline number must drill into its components. Unknown data is not a fake zero.

Store page: verified configuration, mapping, currency/timezone, financial basis, employees, source connection, target history, profit trend, outstanding work, and sync status. Archive instead of destructive deletion. A paused store must not continue silent writes.

Orders: scoped search and pagination; parent/order-item view; eBay ID; supplier references; earnings/cost/profit; tracking; status; source links; proposed versus confirmed changes; missing fields; and audit history. Support multi-package shipments. Do not assume tracking-upload status without actual evidence.

Reconciliation: missing/invalid costs, uncertain fees, orphan supplier references, mismatches, possible duplicate charges, formula errors, unsupported currency, and unresolved changes. Every issue has severity, owner, source evidence, status, and a safe resolution.

Team: invitation, store assignment, role, tasks, workload, attributable app actions, and deactivation. Do not attribute a Sheet edit to an employee unless the source reliably identifies them. No covert surveillance or automatic blame based on aggregate store profit.

Reports: date/basis/currency filters, source freshness, provisional exclusions, CSV and XLSX; PDF/print layouts in P1. Prevent spreadsheet-formula injection on export, limit export scope, and recheck access at download. Keep generated reports private with expiry and access logs.

Office mode: read-only, minimally scoped display session; selected stores; no buyer details, tokens, source credentials, or unnecessary costs. Require authentication/pairing, expiry, revocation, and safe refresh. Never expose a public dashboard merely to simplify TV display.

Design: professional Xcomify text branding until an authorized logo is supplied; navy/blue/neutral palette as a reversible default; light/dark mode; accessible contrast, keyboard navigation, loading/empty/error states, responsive desktop/mobile, saved views, and useful notifications. No fake controls or animated claims of live data.

## 12. Identity, sessions, and permission security

Use a maintained authentication provider/library. Disable public sign-up. Bootstrap the first owner securely without default production passwords. Use expiring single-use invitations, verified identities, and a documented owner recovery process. Owner/admin MFA is mandatory before enabling production writes; prefer passkeys, with an approved TOTP/recovery flow where needed. [S7, S8]

If local passwords are supported, use a modern password-hashing implementation such as Argon2id with reviewed parameters; never reversible encryption or plaintext. Allow password managers and long passphrases, screen weak/compromised passwords appropriately, and use generic login/recovery responses. Rate-limit by relevant account and network signals without easy permanent lockout abuse. [S8, S9]

Use secure HttpOnly cookies, HTTPS, suitable SameSite settings, CSRF defenses for cookie-authenticated mutations, session rotation, server-side revocation, idle/absolute expiry, and reauthentication for sensitive actions. No access/refresh tokens in localStorage. Provide active sessions and 'log out other sessions'. Account deactivation or role reduction must invalidate relevant privileges immediately. [S10]

Roles: Owner, delegated Admin, Store Manager, Operations Employee, Finance/Analyst, Viewer; Client Viewer is P1. Roles are permission presets, not unrestricted global rights. Separate viewing profit, viewing costs, editing order data, changing targets, approving writes, managing integrations, exporting, and managing users.

Enforce deny-by-default, organization/store scope, and action permission on every API, job, search, export, notification, and live-data subscription. Verify object ownership server-side; never trust submitted tenant/store IDs or UI hiding. Protect caches and storage paths with the same isolation. Test with two real test tenants and users who have no overlapping stores. [S11, S12]

Do not allow a user to approve their own high-risk change where an independent approver is configured. For a single-owner business, record an explicit owner override with step-up authentication and a reason rather than inventing a second approver.

## 13. Application, infrastructure, and data security

Use OWASP ASVS Level 2 as the proposed verification baseline, selecting and versioning applicable controls; this is a testing target, not a claim of certification. Maintain a threat model for compromised employee sessions, stolen integration credentials, malicious spreadsheet values, accidental mapping errors, duplicate jobs, cross-store leakage, and supply-chain compromise. [S7]

Validate request schemas and allowed fields; use parameterized database access; escape output; prohibit arbitrary HTML execution; implement a restrictive Content Security Policy and appropriate security headers; bound request size and expensive operations. Default to same-origin APIs and narrow CORS where necessary.

Treat spreadsheet cells, product titles, attachments, and imported notes as untrusted data, never executable instructions. Block formula injection and script execution. Restrict uploaded file type/size, scan supported attachments, store privately, and do not serve executable content inline.

Validate Google IDs/URLs and allowlist outbound service hosts. Do not provide unrestricted URL fetchers, user-defined JavaScript, shell execution, SQL, or arbitrary webhooks in the rule builder. Where webhooks are added later, validate signatures, timestamps, replay protection, destinations, and tenant scope.

Encrypt sensitive credentials with managed key separation and rotation. Keep secrets out of repositories, images, chat, telemetry, and browser bundles. Use environment-specific identities, least-privileged database users, private database/Redis networking, encrypted backups, and non-root runtime containers. Never expose database/queue admin consoles publicly.

Minimize buyer data. Keep postcodes only where required for verified matching, mask them by default, and keep customer details off office displays. Define retention, authorized deletion, backups' retention implications, and legal-hold handling with the owner; do not invent universal jurisdictional retention periods or claim legal compliance automatically.

Record security and business events without plaintext credentials, session tokens, full buyer addresses, or unnecessary personal data. Protect audit records from normal application edits, export integrity evidence to separately controlled storage, and distinguish tamper-evident from genuinely immutable storage. Provide an incident-response and credential-rotation runbook. [S13]

## 14. Audit, approval, and emergency controls

Audit: UTC timestamp, actor or system identity, organization/store, action, object, correlation ID, approval, reason, redacted before/after values, source/mapping version, remote outcome, and verification result. External edits without a trustworthy editor identity are labeled 'external Sheet change', not attributed to the integration owner.

Require step-up authorization for connecting/replacing credentials, enabling write-back, changing mappings, bulk financial edits, exports containing sensitive fields, target-basis changes, restoring backups, and owner/role changes. Apply configurable thresholds and preview consequences.

Provide global and per-store EMERGENCY WRITE STOP. Enforce it in the API and worker immediately before submission, not only in the interface. It stops new outbound mutations and high-risk automations while retaining safe read access and review. An already submitted remote request may still complete; reconcile in-flight work rather than promising recall.

Include revoke-sessions, disconnect-integration, pause-jobs, and read-only recovery controls. Record who activated or cleared them. Disable archived/deactivated stores and users across queued work, not only future requests.

## 15. Notifications, rules, and optional intelligence

P0 in-app alerts: disconnected/expired integration, stale sync, conflicts, missing costs, negative-margin orders, untracked orders with evidence, and verified milestones. P1 adds email and other approved channels with configurable recipients, quiet hours, severity, grouping, acknowledgement, deduplication, retry, and escalation.

Notification payloads and links must obey current store permissions; recheck before sending. 'Queued', 'sent', and 'failed' are distinct delivery states. Never leak buyer information or financial totals into unapproved channels.

Start with explicit, bounded rules: when required supplier cost is absent, open reconciliation task; when sync exceeds configured freshness, alert; when verified target crosses a milestone, record and notify. Persist executions and idempotency keys. Do not make destructive external marketplace actions available implicitly.

Optional AI is P2 and off by default. Use only authorized data, cite contributing records, identify uncertainty, and treat source content as untrusted against prompt injection. No secrets/PII transmission without an approved provider policy. AI may explain a deterministic calculation, not replace the financial engine, change costs, approve writes, or trigger irreversible actions.

## 16. Data model and API contract

Model organizations, users, memberships, sessions, roles/permissions, stores, assignments, connections, mapping versions, source records/snapshots, orders, items, supplier orders, allocations, shipments, financial entries/adjustments, profit definitions, targets/revisions, milestone events, period closes, write intents, outbox, sync runs/checkpoints, conflicts, approvals, tasks, notifications, report runs, and audit events.

Use foreign keys, decimal money types, UTC timestamps, source provenance, scoped uniqueness, and indexes verified with actual query plans. Include organization/store scope on relevant entities. Distinguish audit retention from operational soft deletion. Model n:n fulfillment and cost allocations explicitly.

API groups: /auth, /sessions, /users, /stores, /connections, /mappings, /sync-runs, /write-intents, /conflicts, /orders, /financials, /targets, /reports, /notifications, /audit, /system-controls. Document schemas, permissions, pagination, idempotency, version checks, and error codes. Use optimistic concurrency for app-database edits without implying it extends to Google cell writes.

Repository: apps/web, apps/api, apps/worker, packages/contracts, packages/finance, packages/sheets-adapter, packages/security, database/migrations, tests, infra, and docs. Keep platform SDK access behind adapters and use contract tests plus an isolated authorized Google test spreadsheet.

## 17. Reliability, backups, and observability

Implement independent development, test/staging, and production environments. Use synthetic/anonymized fixtures outside production. Monitor sync age, queue age, active leases, Google quota errors, authorization failures, write/conflict rates, financial completeness, report latency, and backup status. Public health endpoints must not disclose business data or secrets.

Treat 10-50 stores and substantial order history as a benchmark scenario, not demonstrated capacity. Measure with declared fixture sizes and concurrency. Adapt polling to workload; use pagination and indexed summaries rather than sending all orders to the browser. Set resource/budget alerts and retention limits for logs/reports.

Proposed production recovery objectives, subject to chosen hosting and testing: database recovery point within 15 minutes and restoration within four hours. Do not advertise these until restoration drills demonstrate them. Daily full backups alone cannot substantiate a 15-minute recovery point; use suitable continuous/PITR capabilities where selected.

Encrypt backups, restrict deletion/access, separate recovery credentials, back up configuration/mappings and required key references, and test restoration on an isolated environment. Never use Google version history as the only database backup. Do not restore an entire Sheet over newer user edits; reconcile and apply approved granular repairs.

After restoration, keep writes disabled until outbox ambiguity, Google state, permissions, mappings, and active integrations have been checked. Document key-loss recovery, provider outage handling, owner unavailability, and how to export the business's data without vendor lock-in.

## 18. Testing and hard release gates

Build unit, integration, authorization, worker-failure, and end-to-end tests. Every safety rule must map to a test or documented manual verification. Critical scenarios:

A01. Same eBay ID in two stores remains isolated; duplicate imports are idempotent.
A02. Multi-item rows do not duplicate parent revenue; shared costs allocate exactly once.
A03. A zero cost is distinct from missing cost; net-earnings fees are not deducted twice.
A04. Partial refund, replacement cost, supplier refund, and closed-period adjustment reconcile.
A05. GBP/AUD are never combined without explicit approved FX.
A06. Target zero/unset, negative profit, >100%, target revision, and refund regression behave correctly.
A07. Initial import and page refresh do not replay celebrations.
A08. Row sort/insert/move, duplicate match, postcode correction, and header/column changes cannot redirect a write silently.
A09. Formulas, array-formula output, protected cells, formatting, and identifiers survive permitted writes.
A10. API-origin changes and old-row/formula changes are found by reconciliation without relying on onEdit.
A11. Independent edits are three-way compared; uncontrolled same-cell races are not falsely certified safe.
A12. Google 429/5xx/timeout, token expiry/revocation, worker crash, duplicate job, and stale lease recover visibly.
A13. A timeout after remote success does not cause duplicate append or financial adjustment.
A14. Partial scans do not delete orders; restored queues do not blindly replay writes.
A15. Removed users, changed roles, paused stores, and emergency freeze block queued mutations.
A16. Cross-store/tenant access fails for direct APIs, guessed IDs, exports, live streams, search, cache, and notifications.
A17. CSRF, XSS, SQL injection, SSRF, formula injection, replay, and credential/log leakage are tested.
A18. Restricted Google sharing remains unchanged; service secrets never reach the browser.
A19. Existing extension workflows pass regression on the approved test copy, including any active-tab limitations.
A20. Backup restore works in isolation and requires reconciliation before write re-enable.
A21. All visible controls work; no production screen silently falls back to demo fixtures.
A22. Reduced motion, keyboard navigation, mobile layout, and office display data minimization pass review.

No production write-back until: sample mapping approved, profit definition approved, private authorization verified, read-only reconciliation accepted, real integration test passed, conflicts reviewed, owner MFA enabled, rollback/restoration tested, and limited-store rollout approved. Unresolved critical security defects block release.

## 19. Implementation sequence and required artifacts

Milestone 0: inventory actual Sheets/extensions when available, settle source/financial meanings, document threat model and field ownership. Missing production access is recorded; continue building with isolated fixtures.
Milestone 1: authenticated empty application, store assignments, secure database, targets, and a clearly separated synthetic development dataset.
Milestone 2: private read-only Google integration, mapping, complete import, reconciliation, orders, source traceability, and sync health.
Milestone 3: one-store, limited-field write-back with durable intents, approvals, read-back, conflict handling, and kill switch.
Milestone 4: validated financial views, target animations, tasks/alerts, exports, and permission tests.
Milestone 5: security review, restore drill, extension regression, load tests, private deployment, and controlled multi-store rollout.
Milestone 6: approved P1 features; P2 only after stable operations.

Deliver a working repository, setup instructions, environment-variable template without secrets, reproducible dependency lockfile, migrations, local Docker configuration, secure production deployment guidance, OAuth setup, mapping/financial specification, permission matrix, OpenAPI, threat model, test coverage/results, backup/incident runbooks, and owner/employee onboarding.

Maintain ADRs for ownership, row identity, concurrency limits, refund timing, FX, authentication, deployment, and recovery. Include a feature-status matrix and a prioritized remaining backlog. Supply an infrastructure estimate based on current verified vendor pricing and stated assumptions; do not invent costs or provide guaranteed delivery dates.

## 20. Execution instruction to the development agent

Begin by summarizing the fixed requirements, reversible defaults, and true production blockers. Produce the minimal build plan and architecture decisions, then implement the first runnable vertical slice. Continue phase by phase with tests; do not stop after producing another long plan.

Do not require the owner to repeat the business model, two-way sync choice, profit-target requirement, or preservation constraint. Ask only for genuinely necessary authorization or unresolved business meaning when it blocks a safe action. Never ask for passwords or private keys in chat.

When credentials are unavailable, leave the real adapter implemented and clearly unconnected; run deterministic adapter tests. Do not silently swap in fake Google results. A preview/demo mode must be unmistakably labeled and unable to write to production.

At completion, state exactly what runs locally, what has been verified against Google, what has not been deployed, and which release gates remain. The final product is successful when the owner can trust the numbers, understand every synchronization outcome, manage access, recover from mistakes, and track each store's profit target without abandoning the existing workflow.

---

## Verified technical references
Consult the latest official versions at implementation. References support platform constraints and security principles, not a claim that this application is already secure or built. Product defaults elsewhere in this brief are design proposals.

[S1] Google Sheets API usage limits: https://developers.google.com/workspace/sheets/api/limits
[S2] Google Sheets API authorization scopes: https://developers.google.com/workspace/sheets/api/scopes
[S3] Google OAuth web-server applications: https://developers.google.com/identity/protocols/oauth2/web-server
[S4] Apps Script installable trigger restrictions: https://developers.google.com/apps-script/guides/triggers/installable
[S5] Google Sheets values.batchUpdate request contract: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets.values/batchUpdate
[S6] Google Sheets batchUpdate collaborative-edit caveat: https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate
[S7] OWASP Application Security Verification Standard: https://owasp.org/www-project-application-security-verification-standard/
[S8] OWASP Authentication Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html
[S9] OWASP Password Storage Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
[S10] OWASP Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
[S11] OWASP Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
[S12] OWASP Multi-Tenant Security Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Multi_Tenant_Security_Cheat_Sheet.html
[S13] OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html
