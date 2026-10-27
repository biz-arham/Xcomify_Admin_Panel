# Security controls and limitations

## Implemented controls

Private owner bootstrap with a generated local code; no public registration or default production password. Argon2id hashing (64 MiB, three iterations, two lanes), long-password support, generic credential failures and bounded login attempts. TOTP uses standard SHA-1/30-second/six-digit codes, rejects reused time steps and provides single-use hashed recovery codes. Save recovery codes offline. A custom maintained-library-based authentication implementation is present; it has not received an independent authentication audit.

Opaque session cookie, hash stored server-side, HttpOnly/SameSite Lax, Secure + `__Host-` in HTTPS production, 12-hour absolute/60-minute idle expiry, recent-password verification for sensitive actions, database CSRF token plus exact Origin/custom-header enforcement, JSON-only mutations and bounded request bodies. No authentication or Google tokens are placed in localStorage. Optional browser theme storage can be unavailable without breaking the application.

Deny-by-default role/action/store authorization, tenant/store checks on APIs, redacted cost data, scope-checked exports, current privileges rechecked before queued writes, deactivation/session revocation and per-store/global write-stop. Owner has all stores in their organization; other roles require assignments. Reports, search and notifications follow the same scope.

Encrypted Google credentials using Fernet; server-only code exchange and PKCE/state; fixed Google outbound hosts; no arbitrary URL fetcher, shell, SQL or rule-code evaluator. HTTPS is mandatory in production mode. Local mode binds loopback and is not intended as an externally shared server.

DOM escaping, restrictive script CSP, no third-party frontend CDN, parametrized ORM access, CSV formula-injection handling, formula/protection checks on Google cells and audit records without credential payloads. Buyer data is minimized; no addresses/emails are needed for ordinary order operation. Postcodes are masked in normal views and used for identity verification. Database files still need OS access protection and disk encryption where appropriate.

## Important limits

This is **not** an ASVS certification, external penetration test, legal/compliance opinion or guarantee of perfect security. Dependencies are pinned to the tested environment, not proven vulnerability-free. Scan them against your current advisory database before production and review updates with regression tests.

OAuth scope is broader than selected-file `drive.file`; no Google Picker, managed KMS/HSM, SSO/passkeys, automated email identity verification or external abuse-monitoring service is implemented. Local Fernet keys are stored on the same machine, protected by file permissions; compromise of that machine/user can expose keys. Windows ACLs and full-disk protection require operator setup. Local business database content is not encrypted by SQLite; backup bundles and protected credential values are encrypted.

Audit records cannot be edited through normal endpoints but a database administrator can change them. No signed append-only external audit store is claimed. Monetary calculations are two-decimal currency operational reporting, not a full ledger, statutory accounting system or bank reconciliation product. Inference may still be possible from profit and earnings even when direct cost columns are hidden.

Rate limits are application/database-based; production requires a reviewed reverse proxy, per-client throttling, request timeouts and resource budgets. Without trusted proxy/IP configuration, the application may see the proxy as one client. Do not set arbitrary trusted-forwarded headers. One owner exists initially; no public support account or hidden recovery endpoint is installed.

**Shared Google cell concurrency:** fingerprints and read-back do not provide compare-and-set semantics. Single-writer ownership must be enforceable outside the UI. Leave uncontrolled shared cells read-only/proposed. One cell per intent, no remote append/delete, explicit approval and unknown-outcome reconciliation reduce harm; they do not certify lossless synchronization against every independent writer.

## Threat model

| Threat | Implemented barrier | Residual / operator responsibility |
|---|---|---|
| Stolen employee login | TOTP option, limited assignments, session revocation | Endpoint security, enable MFA for all sensitive roles |
| Guessed order/store IDs | Backend organization/store authorization | Continue authorization tests for new endpoints |
| Forged cross-site writes | Cookie flags, Origin + CSRF token, custom header | HTTPS, secure DNS/proxy and browser environment |
| Malicious titles/CSV cells | DOM escaping, text-only sheet writes, CSV guard | External spreadsheet applications differ; inspect exports |
| Wrong Sheet mapping | Header checks, preview, exact identity, safe approval | Owner must verify real columns and profit meanings |
| Concurrent edits | Ownership, three-way compare, one-cell writes | Enforce a real single writer; no CAS guarantee |
| Interrupted request/worker | Durable state, no automatic write replay | Inspect outcome_unknown and reconcile |
| Stolen integration credential | Encryption, no frontend exposure | Dedicated least-privilege Google identity, key rotation |
| Local device compromise | OS file permissions, encrypted backup | Disk encryption, machine/user security, separate recovery key |
| Restore stale work | Freeze/revoke/cancel after restore | Complete remote reconciliation before reenabling writes |
| Dependency compromise | Pinned versions, small dependency set | Current advisory scan, verified packages/images and patch process |

## Incident response

Activate global write-stop. Stop workers if remote outcomes are uncertain. Revoke sessions, deactivate compromised users and disconnect affected Google credentials; separately revoke the Google grant. Preserve redacted audit/job evidence and a protected backup. Investigate from a copy. Rotate credentials/keys using a reviewed migration (do not simply replace the Fernet key and lose existing ciphertext). Restore only into an empty private workspace, reconcile external state and re-enable one approved store at a time.

## Primary guidance consulted

https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html
https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html
https://owasp.org/www-project-application-security-verification-standard/
