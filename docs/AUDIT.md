# Transaction integrity and audit review

## Review changes in the app

Sign in as the family administrator and open **Audit history**. Search by person, record name, or transaction reference; filter by record type, action, and date. Dates use Asia/Manila. Review an entry to see the previous and resulting values, source, timestamp, and actor. Changed fields are highlighted.

Choose a transaction reference, or **Show this transaction's changes**, to inspect related entries together. A new loan and all its generated installments share a reference. The same applies to a recurring-bill generation cycle and account administration requests.

The screen is read-only and requires a live connection. Ordinary members cannot access the full audit API; they retain the normal per-bill payment history. Full audit records are never copied into offline snapshots or the service-worker cache.

## What is captured

Database triggers record committed inserts, updates, and deletes for:

- Bills, payments, loans, and recurring schedules.
- Family and NAS display settings.
- Accounts, account role flags, group membership, and explicit permission assignments.
- Device subscription registration/removal and reminder delivery state.

Events include safe before/after snapshots. Account password changes are flagged, but passwords and password hashes are not recorded. Device endpoints and subscription keys, VAPID private keys, Django secrets, session cookies, and request bodies are excluded. Last-login-only updates, worker heartbeats, and session housekeeping are not business changes and do not produce audit events.

Logging begins with the **Audit logging enabled** marker installed by migration 0003. Existing records remain available, but their earlier creation and changes are not retrospectively reconstructed or assigned to a user. A deleted actor or record does not erase its audit snapshot.

## Atomicity

The triggers insert audit rows into the same database and transaction as the changed rows. They do not use an asynchronous log queue or an after-commit callback. If the audit insert fails, the business statement fails too. If a larger operation fails, all changes and their audit entries roll back together.

Mutating application requests use an outer atomic transaction with actor and transaction context. An error response rolls back any partial writes, even if a view caught its own exception. Nested operations use savepoints and retain the outer attribution. Django administration requests use the same attribution mechanism. Worker operations explicitly identify themselves as `worker` and `System`.

PostgreSQL context uses transaction-local settings. SQLite uses an internal context row written and cleared inside the same transaction; its writer lock prevents context leaking between concurrent writers. Application context is cleared after use, so later raw SQL is not attributed to the previous person.

These guarantees cover database changes. A push notification already accepted by an external service cannot be rolled back by a database transaction. A crash in that window may still cause a notification retry, as documented in the operations guide.

## Balance protection

Existing decimal validation, positive-amount constraints, payment request keys, and application bill locks remain. Database triggers additionally reject:

- An inserted or updated payment that would exceed the target bill's amount.
- A bill amount reduced below its already recorded payments.

PostgreSQL payment triggers lock the affected bills before checking totals. This protects concurrent non-API writes as well as ordinary app requests. SQLite serializes writers. A repeated successful payment request returns its existing result without a second payment or audit event.

## Direct database changes and trust boundaries

Normal raw SQL and ORM bulk updates/deletes on audited tables also fire the triggers. Outside an attributed application transaction, the actor is explicitly **Database / unknown actor**, rather than an inferred or fabricated family member.

For raw PostgreSQL work, entries in the same database transaction use the same `db:` transaction reference. Raw SQLite writes without application context receive independent event references; SQLite does not expose a comparable database transaction ID to these triggers.

Audit records cannot be edited or deleted through the app, Django administration, or the audit model's normal update/delete methods. This does not create an independently tamper-proof ledger: a privileged database operator can alter tables, forge context, disable/drop triggers, or change audit rows directly. Access to the NAS, database, and backups must remain restricted. PostgreSQL TRUNCATE, schema operations, database restores, and SQLite file replacement are maintenance operations, not row-level audited transactions. Plan and document maintenance separately.

## System status and migrations

**System status → Audit logging** checks that all required audit and balance triggers are present and enabled. A missing/disabled trigger is reported as an error. Presence checks do not prove that a privileged operator has never altered a trigger definition.

Apply migrations before starting the new web/worker code. The Docker init service already does this. Back up the local database or deployed PostgreSQL database first. To remove this feature, reverse migration 0003 before reversing the table-creation migration; this removes the trigger dependencies in the proper order. Do not delete audit tables while triggers depend on them.

Schema changes to an audited table require review of its frozen trigger definitions and a follow-up migration. Do not silently edit a trigger migration already applied to a deployed database.

## Verification

The audit tests exercise attribution, before/after snapshots, account administration, safe password-change flags, raw SQL auditing, read-only review permissions, filters, grouping, idempotent retries, nested rollback, and missing-trigger status. Fault-injection tests reject audit inserts and fail a loan midway to verify neither partial records nor misleading success logs survive. PostgreSQL tests also submit concurrent non-API payments to verify the database guard.
