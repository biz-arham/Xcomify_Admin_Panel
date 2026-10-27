# Operating and recovering the workspace

## Everyday operation

Use the normal launcher for real empty data, the demo launcher for isolated synthetic records. Close one before starting the other because both default to port 8787. Do not open `index.html` directly: the UI requires its authenticated backend. Keep the server process and computer running; a hosted persistent server is required for unattended 24/7 operation. A Chrome extension retains its own browser/tab requirements; this app does not change them.

Create a store, set currency/timezone, approve verified net-earnings meanings, and set a monthly profit target. Local records and CSV import are available before a Google connection. CSV import does not append Google rows. Read source records using a verified per-store mapping rather than default columns.

Dates recognize store-local monthly periods. Amounts are decimal strings in the API. Negative profit is valid; negative cost/refund inputs need review. Blank cost is missing. Filler expenses remain excluded from operational target-item profit unless explicitly enabled. Currency groups stay separate; there is no automatic FX provider. The report is an operational contribution view, not audited net business accounts.

Multi-row duplicates are quarantined/count parent earnings once; their contribution is excluded until reviewed. This release does not allocate multi-item/supplier costs for you. Do not force a false unique mapping just to clear the warning. Formula/array/merged/protected cells remain read-only.

Financial closing stores a snapshot for a complete previous month and blocks in-app historical edits. Later source discrepancies create review issues, not a silent rewrite of the closing report. Reopening and formal restatement require a separate reviewed migration; no reopen button is implied.

## Background work

The embedded worker is a persistent server task backed by `jobs`, `write_intents` and a database lease. A standalone process is available through `python -m xcomify.worker`. Never make Redis/in-memory timers the only record of uncompleted writes. Read retries are bounded; remote mutations are not blindly retried. Check last sync, errors and job age instead of assuming the configured interval was achieved.

Global/per-store write-stop blocks new remote submissions; it cannot recall a request already accepted by Google. Paused stores and removed actor/approver permissions block queued writes. A change during read validation cancels submission. `outcome_unknown` means review the remote value, not click repeat until it seems successful.

## Local encrypted backup

Settings provides a backup action/download. CLI:

```bash
python scripts/backup.py
```

A consistent SQLite snapshot is encrypted into `.data/backups/*.xcbak`. Keep `.data/backup-recovery.key` separately in an offline/private vault. It is not a user password. The backup contains the application encryption key inside its encrypted payload so Google/MFA ciphertext can be restored. Never send backups/keys to someone without authorization. OS-protect both; the local database itself is not transparently encrypted.

No automatic schedule is installed. Use an operator-approved Task Scheduler/systemd job invoking the backup script, copy encrypted backups to private off-device storage and monitor results. Do not claim a 15-minute recovery point from daily backups. Production PostgreSQL must use its own `pg_dump`/PITR managed runbook; the local backup API intentionally refuses PostgreSQL.

## Restore drill

Stop the application and worker. Choose a **new empty directory**; existing workspace data is never overwritten automatically.

```bash
python scripts/restore.py --backup /path/to/backup.xcbak --key /path/to/backup-recovery.key --destination /path/to/new-empty-workspace --confirm READ_ONLY_RESTORE
```

Read `python scripts/restore.py --help` for the exact command contract before use. Set `XCOMIFY_DATA_DIR` to that restored directory and ensure `DATABASE_URL` is absent or correctly points at the restored SQLite database. Normal local startup then uses its restored key and database. Start read-only, sign in, reconcile the actual Google state, inspect uncertain intents, verify mappings and only then re-enable controlled writes. Restored sessions are revoked, pending jobs cancelled and outbound writes disabled. Record the drill outcome and timing; no guaranteed recovery time is asserted.

For demo backups, test a normal restored local workspace with writes kept frozen; a demo organization remains prohibited from Google operations. Never redirect real startup to demo folders without understanding the organization flags.

## Owner password/MFA recovery

Use saved one-use recovery codes first. There is no email reset link in this edition. If owner credentials/MFA are lost, an authorized filesystem/database administrator can stop all servers and run:

```bash
python scripts/owner_recovery.py
```

It asks for the existing owner's email and a new password using a hidden local prompt, disables old MFA, freezes writes, cancels pending work and revokes workspace sessions. Re-enroll MFA and reconcile remote work before enabling writes. This privileged offline command is not exposed over HTTP and cannot create a hidden second owner. Protect filesystem access accordingly.

## Update / troubleshooting

Back up before replacing application files. Preserve `.data`, the original local encryption key, filled `.env` and backup key privately. Do not carry `.venv` between incompatible Python/OS versions. The launcher reinstalls pinned packages when the lock changes. Newer database schema versions refuse older application startup.

Port already in use: close the other launcher/process. Setup fails: inspect the terminal; check supported Python and package-network access. Login lost after invite/permission changes: reauthenticate, as privileges revoke sessions intentionally. A current TOTP code cannot be reused; wait for the next time step or use a saved one-use recovery code.

Google failures: see GOOGLE_SETUP.md. A header-change/protection conflict is not a prompt to disable safeguards. Missing long numeric IDs may already be rounded in the source; correct them as verified text through your authorized existing process. Preserve extensions and file sharing; no automated restructuring is performed.
