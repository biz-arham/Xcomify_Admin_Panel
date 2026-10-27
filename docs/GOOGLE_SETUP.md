# Connect private Google Sheets

**Live integration has not been tested against your account.** Start with a private test copy you own, not an operational store. Do not send Google passwords, client secrets or private keys in chat. No Apps Script is required by this implementation.

## 1. Configure your own OAuth client

In Google Cloud, select/create a project, enable **Google Sheets API**, configure the OAuth consent screen/audience and add the authorized test user where relevant. Create an OAuth **Web application** client. Register this exact local redirect:

```text
http://localhost:8787/api/google/callback
```

For a hosted app, register the exact HTTPS origin plus `/api/google/callback`. Local and hosted callbacks are not interchangeable. Set the same exact origin in `XCOMIFY_BASE_URL`. The app accepts only that Host and mutation Origin. Avoid switching between `localhost` and `127.0.0.1` in the browser.

Copy `.env.example` to `.env`. Enter the client ID and secret **on your own computer**. Restart the application. Settings will then enable **Connect Google**. Sign in to the Google identity that can access the private spreadsheet and review the consent screen.

This edition requests `https://www.googleapis.com/auth/spreadsheets`, not narrowly selected `drive.file`. It supports pasted Spreadsheet IDs but does not implement Google Picker. The token can access the authorized identity's accessible Sheets within the granted scope; application mapping and role permissions restrict app actions, not Google's underlying grant. Choose a dedicated least-privilege identity and share only intended files privately where possible. No domain-wide delegation or public sharing is required.

External OAuth apps in Google's Testing publishing state may receive seven-day refresh tokens for these scopes. Google account/publishing policy can require verification or reconnection. Check the official OAuth documentation and your own console rather than promising permanent unattended access.

## 2. Map a store safely

Create a store with currency/timezone. In **Stores > Sheet mapping**, select the connection, paste the Spreadsheet ID, inspect the file, select its numeric tab ID and set the real header row. Read sampled headers and values. Map at least exact eBay order ID, sold date, already-net order earnings and supplier cost. Postcode is recommended/required for the existing tracking match workflow.

Assign only one field to each column. Optional unmapped deductions mean no separate additional deduction, which must match the financial-definition approval. A mapped blank required deduction is a source issue. A blank supplier cost remains unknown. All mapped amounts use plain decimal cell values; text currency symbols/separators are not guessed. Google numeric cells use evaluated values. IDs remain text; an already rounded huge numeric ID cannot be repaired by this app.

Pick the correct date interpretation. The adapter recognizes ISO dates, `Sold 27 Oct 2026`, Google date serials and explicitly chosen day-first/month-first slash dates. There is no universal J/K/L/M layout. A row number is not identity.

Preview first; inspect issues and sample values. Saving the mapping is an application database change, not permission to write Google cells. Run **Sync now**, reconcile totals with the Sheet and confirm the owner-approved profit basis. Do not feed bank settlement payouts into net-order-earnings without proving the meaning.

The adapter scans all allocated grid rows in chunks of 1,000, with an approved maximum and a 101-column protection-review limit. It refuses over-cap files instead of silently dropping rows. A very sparse giant allocated grid can therefore require review or adapter tuning. Full scans include old corrections, not only the bottom rows. Hidden rows are not silently ignored.

## 3. Enable narrowly scoped write-back

The default is read-only import. For each intended editable column, establish an **actual enforceable single-writer** arrangement that includes all independent Sheet editors and extensions. Merely selecting `app-owned` does not prevent Google editors from writing. Leave extension-owned/formula/shared fields Sheet-owned when this cannot be achieved without breaking the existing workflow.

Enable owner MFA, complete an isolated real Sheet write/read-back, verify backup recovery and review the per-store Write gate. Approve the operational facts truthfully. Clear the global write-stop only after reviewing the same controls. The app does not change Google protection or sharing itself.

An order edit creates a proposal. Authorized approval requires a recent MFA-verified session and a reason. The worker re-resolves order ID/postcode, compares the base and current values, verifies mapping/formula/protected/merged/array constraints, submits **one existing cell**, then reads it back. A queued proposal is not a completed change. No row appends/deletions or structure changes are implemented.

Independent edits can still happen between read and write: Sheets is not a database transaction with an expected-cell-value lock. On conflict or unknown outcome, review/reconcile; never assume a timeout means nothing changed. Use **Emergency write stop** to prevent new submissions. Already sent requests may finish.

## 4. Recovery and permissions

401/403/auth revocation: reconnect the authorized identity and recheck private file access/API setup. 429/transient failures: bounded retries/backoff for reads. A missing tab/header or ambiguous ID pauses affected writes. Disconnect deletes the app's saved credential and disables writes; revoke the app in Google Account security as well to revoke the external grant.

App employee access and direct Google Editor access are different controls. Removing an app employee does not remove their independent Google sharing permission. Remove both when appropriate.

## Official references

- https://developers.google.com/identity/protocols/oauth2/web-server
- https://developers.google.com/identity/protocols/oauth2
- https://developers.google.com/workspace/sheets/api/scopes
- https://developers.google.com/workspace/sheets/api/limits
- https://developers.google.com/workspace/sheets/api/reference/rest/v4/spreadsheets/batchUpdate

Google quotas are shared across calls/identities/projects. The two-minute setting is a scheduling aim, not a guaranteed refresh SLA. Check current project quotas, pricing and consent requirements in Google's console. This package makes no promise of zero hosting/API costs.
