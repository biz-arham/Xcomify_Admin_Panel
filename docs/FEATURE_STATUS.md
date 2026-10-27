# Delivery status - v1.0.0

Status describes code delivered and verification performed. **Runnable local release; not the complete enterprise scope or a security certification.**

| Area | Delivered | Verification / limit |
|---|---|---|
| Real persistent backend | FastAPI + SQLAlchemy + SQLite | Running locally; API tests pass |
| Original TypeScript stack | Not delivered | Explicitly replaced with Python/local-first architecture |
| Multi-store dashboard | Store isolation, filters, currency groups, trends | Synthetic desktop/mobile rendering |
| Profit | Decimal inputs, unknown cost, net-earnings formula, adjustments, filler option | Automated tests; real source meanings not yet approved |
| Targets | Month, version check, >100%, negatives, progress, milestone records | Automated tests and browser target editing |
| Animations | Rings, bars, one-time completion confetti, reduced motion | Browser checks; no repeated success on refresh |
| Roles | Owner/admin/manager/operations/finance/viewer with store assignments | API cross-store and cross-tenant tests |
| Authentication | Private bootstrap, local password, TOTP, recovery, sessions | Automated tests; not a third-party identity-provider certification |
| Invitations | Single-use expiring links, owner chooses stores/role | Automated tests; email delivery/identity verification absent |
| Google OAuth | Server code exchange, PKCE/state, encrypted tokens, disconnect | Code + deterministic HTTP contract checks; no live authorization |
| Google discovery | Paste ID, inspect tabs and sample headers | Real adapter implemented; no Google Picker/service account workflow |
| Scope | `spreadsheets` file-level OAuth scope | Broader than `drive.file`; owner must review before consent |
| Two-way sync | Controlled existing-cell writes; explicit proposal and owner/admin approval | Fake-adapter fault/identity tests; no live Google write verified |
| Compatibility | No extension modifications, IDs/headers/formulas preserved by design | Actual extension packages and Sheet structures not supplied; regression blocked |
| Row identity | Unique store+eBay ID, postcode pre-write, row relocation | Automated tests |
| Multi-item orders | Duplicate rows quarantined; parent earnings counted once | Full lines/supplier allocations and multi-parcel editing deferred |
| Large histories | Full chunked scans, configured cap, pagination | No 10-50 store load benchmark; not claimed scalable beyond measurements |
| Worker | Persistent DB jobs, one elected worker, read retries, no blind write retries | Deterministic worker/crash tests; no hosted uptime claim |
| Conflict control | Field ownership, three-way comparison, formula/array/protection checks | No zero-lost-update guarantee against independent writers |
| Audit | Append-only through API, actor/action/reason, scoped reading | Database administrator can modify data; not immutable/tamper-evident storage |
| Backup | Encrypted SQLite snapshot, integrity check, empty-directory restore | Actual automated restore drill |
| Automatic backup/PITR | Not implemented in local app | Operator scheduling / production PostgreSQL service required |
| Period close | Snapshot and edit lock | Tests; reopening/migration interface deferred |
| Tasks | Assignment, due date, status | API/UI implementation; not payroll or surveillance |
| Tracking | Missing tracking view and record edits | No courier tracking events, delivery proof or eBay submission |
| Reporting | CSV with formula-injection protection, browser print | No XLSX renderer, scheduled email delivery or custom report builder |
| Focus display | Same logged-in session, read-only visual target layout | Not a separately paired/limited TV device session; do not use on untrusted TV |
| Notifications | In-app sync issues, milestones, acknowledgement | No email/Telegram/Slack channel or general rules builder |
| FX | Currency-separated totals | No automatic FX conversion/rates |
| AI/external market actions | Not implemented | No model calls, buying, refunds, cancellations or automatic tracking upload |
| Deployment | Local launcher, Docker/PostgreSQL template | Linux verified; Windows launcher, container build and cloud deployment unexecuted |
| Security assessment | Concrete controls and adversarial regression tests | No external penetration test, complete ASVS verification or compliance certification |

## Release-blocking live checks

Real Sheet mapping and financial definition approval; authorized Google test file; actual extension version regression; proof of an enforceable single writer for application-owned cells; actual quota/latency measurements; MFA; isolated backup/restore drill; independent review of chosen hosted environment. Owner checkboxes record the owner's decision, not automatically proved facts.

## Remaining backlog in priority order

1. Verify a real private test Sheet, including formula outputs and the exact extension files; approve field meanings and ownership.
2. Run PostgreSQL/container staging tests, implement managed secret storage, upstream proxy controls and production backup/PITR; review OAuth deployment/consent.
3. Add parent/line/supplier allocation model, signed source snapshots, target revision table/history UI and migration tooling where needed.
4. Add managed identity/email verification/invitations/recovery, richer exports, scheduled reports and separately scoped display sessions.
5. Introduce budgeted incremental/full reconciliation strategy and benchmark large sheets. Add advanced rules, official marketplace integrations and optional grounded AI only after a separate authorization.
