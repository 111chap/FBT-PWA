# Administrator corrections and deletion

Administrators can open any active bill or loan, including fully paid records,
and choose **Edit** or **Delete**. Paid bills are reachable through Paid bills
history. Each recorded payment has its own edit/delete controls in bill details.
Ordinary members do not receive these controls, and the server independently
enforces administrator access. All corrections require a live connection and a
freshly reviewed version of the record and its relevant parent records.

Modification buttons share consistent sizing and spacing, stacking on smaller
screens. The visible **Change payer** action retains the accessible name
**Change primary payer**. Disabled controls stay readable, with an explanation
when the device is offline or a refresh is required. These visual changes do
not enable unavailable actions or alter authorization/confirmation rules.

## Editable details

| Record | Editable fields | Accounting effect |
| --- | --- | --- |
| Bill / installment | Name, original amount, due date, category, notes, primary payer | Recalculates its unpaid balance; a loan's total follows retained installments |
| Loan | Name and agreed total | Shows an explicit allocation preview across retained installments |
| Payment | Amount and payment date | Recalculates the bill balance and paid-history completion date |

Original creators, payment recorders, and creation timestamps are retained.
Changing an installment's due date is done through that bill; this feature does
not bulk-reschedule a loan or add installments. Deleting individual installments
updates the loan's retained count. A repeating bill correction affects that
occurrence; future monthly bills continue unless their schedule is separately
changed/cancelled. Dates remain subject to the app's 2000–2100 range; payment
dates cannot be in the future. A new payer must be active, while retaining an
already-assigned inactive payer is permitted.

Amounts must remain positive. A bill cannot be reduced below its retained paid
amount, and a payment correction cannot overpay a bill. Correct/delete the
relevant payment first when fixing an incorrectly high paid amount. This applies
to paid records too; paid status never hides the correction controls.

## Loan allocation

An unchanged agreement total preserves the exact existing schedule. When the
total changes, fully paid installments keep their paid amounts where possible.
The remaining agreement is divided in cents across open installments, with any
rounding remainder on the final open installment. Each installment stays positive
and at least its recorded paid amount. If a fully paid loan is increased, only
its final installment reopens for the increase. The form and confirmation show
every affected installment's original and proposed amount. The server calculates
the same plan and rejects totals below the permissible minimum.

Renaming a loan changes its name without overwriting individually named bills.
Changing/deleting a linked bill updates the loan's agreed total and installment
count in the same transaction. Removing its final installment also removes the
loan from family views.

## What Delete means

Deletion is logical removal, not erasure of financial evidence:

- Deleting a bill hides it from outstanding lists, paid history, exports, and
  reminders. Its recorded payments and audit evidence stay in the database.
- Deleting a payment marks it removed and excludes it from the current paid
  amount. The bill can reopen as outstanding/overdue. Its original recorder and
  values remain available in the retained record and audit history.
- Deleting a loan removes the loan and every retained installment from family
  views as one transaction. Linked payment records remain retained.

There is no restore button in this release. Deleted records can be examined in
the read-only administration records and immutable audit history. Historical
audit rows are never deleted by these actions. Logical deletion appears as an
**Updated** audit event with `removed: false → true`; the required reason and
related transaction show its deletion intent. Physical-delete events remain a
separate audit action.

Deleting a payment does not refund money or communicate with a bank. The app
records the family's corrected ledger only. Reminders use the corrected balance
on the next worker pass and retain their existing daily delivery limits.

## Confirmation, concurrency, and logging

Every correction requires a reason. Review shows the old/new fields or deletion
impact, reason, loan allocation where applicable, and a separate final action.
Cancel/Escape does not submit the correction. Deletion uses a red final button.
Drafts exist only in memory; no offline mutation queue is introduced.

The server requires administrator authorization, CSRF protection, confirmation,
a request UUID, and matching optimistic versions. Versions include payment
amounts, payment dates, and logical-removal state. Loan reviews include all
retained installments and their payments. A stale review returns 409 and must
be reopened after refreshing. Repeating an identical request UUID returns its
saved receipt without duplicating changes or audit records; a changed payload
cannot reuse the UUID. A failed/network-uncertain submission retains the key
while the form is open. Close, reconnect, refresh, and inspect history if the
connection was lost before a response arrived.

Actor access is checked under lock. Corrections lock the loan (when present),
recurrence (when present), bill, and payment in a consistent order. Existing
payment recording locks the bill, and PostgreSQL balance triggers enforce the
same accounting limits. Reason, actor, transaction reference, before/after
snapshots, and related row changes commit or roll back together. The reason is
visible and searchable in Audit history. No credentials or payment request keys
are added to audit snapshots.

## Upgrade and backup requirements

1. Stop **both web and worker** processes before upgrading.
2. Take a complete database backup using [OPERATIONS.md](OPERATIONS.md) and
   retain the previous application revision and configuration. Follow the
   documented restore procedure; this change does not claim a physical NAS
   restore has been exercised.
3. Apply migration `0005_financial_corrections`, then restart web and worker.
   It adds logical-removal flags to loans/payments and reason fields to audit
   context/events, and replaces audit/balance triggers in the migration
   transaction. Existing financial rows and audit history remain intact.
4. Check **System status → Audit logging**, refresh family data, and review
   several retained paid/unpaid records. Shell v16 brings the correction assets;
   the private offline snapshot still needs a live refresh for new identifiers
   and versions. Phones may show an old saved view until updated.

Do not edit frozen `_audit_v1`, `_audit_v2`, or `_audit_v3` definitions after
deployment. Future changes require a new migration. PostgreSQL and SQLite are
supported, including SQLite table rebuilds while triggers are temporarily removed
inside the migration transaction.

A schema downgrade is deliberately refused once correction reasons or removed
loan/payment flags exist: dropping these fields could revive removed records or
lose correction context. **Restore the complete pre-upgrade database backup and
matching app revision** to return to the old release. Do not force a downgrade or
delete audit records to bypass this guard.

## Verification

Tests cover administrator/member/CSRF checks; paid bill/loan/payment edits and
removal; stale versions including date-only corrections; identical retries;
invalid/future amounts/dates; positive cent allocation; loan reconciliation;
rollback after an injected mid-transaction failure; raw-database overpayment
guards after a removed payment; concurrent administrators and correction/payment
races on PostgreSQL; migration retention and guarded downgrade; desktop/mobile
browser review/cancel flows; reason review; and offline-disabled controls.

All demonstrations and screenshots use fictional records in isolated test
databases. No new production dependencies are required.
