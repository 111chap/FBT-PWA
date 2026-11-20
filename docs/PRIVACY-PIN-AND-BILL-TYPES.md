# Private bills, PIN login, and one-time bills

This release implements issues #28, #30, and #27. It requires migration
`0006_privacy_pin_bill_types` before starting the updated web and worker containers.

## Before updating the NAS

1. Stop web and worker to pause writes and reminders; leave PostgreSQL running for backup.
2. Back up PostgreSQL with `pg_dump -Fc` and copy the existing `.env` to a protected
   location outside the NAS. Test restoration separately with reminders disabled.
3. Preserve the existing `.env`, Compose project name, database volume, hostname,
   reverse proxy, and certificate. This release adds no environment settings,
   router rules, external services, or media volumes.
4. Replace application files, rebuild the app image, run init/migrations successfully,
   then recreate/start web and worker. A restart alone may reuse an old image.
5. Check database, worker, and audit status. Refresh each installed app on home Wi-Fi.
   `/sw.js` now identifies `fbt-shell-v20`. Refresh saved bills as well.

The migration preserves existing records as **Family** and assigns ownership to
their original creators. Loan installments gain the Loan type. Existing utilities
stay Utilities even when they do not repeat. Amounts, dates, payments, and existing
audit entries are preserved. It does not infer privacy from the primary payer.

Once private records, PIN settings, emergency grants, or one-time bills exist,
the migration refuses a destructive downgrade. Restore the matching pre-upgrade
database and application version instead of dropping security fields. A source-only
rollback cannot safely undo the schema changes. PIN hashes and device verifiers
are in PostgreSQL; `.env` contains the key used to bind device verifiers. Protect both
backup files. Changing `DJANGO_SECRET_KEY` invalidates device credentials and sessions.

## Private and family records

New Utilities, Loan, and One-time entries default to **Private**. Choose **Family**
and review before saving to share with the household. Private entries belong to
their creator and use that owner as primary payer; choose Family to assign another
member. Owners can correct their private records with the existing review/reason workflow.
Family administrators retain correction access to shared records.

Loans and monthly schedules carry their ownership and visibility into every
installment or generated bill. Change sharing using **Change sharing** in the
bill/loan details. Linked installments change through their parent loan/schedule,
not independently. Only the owner can change sharing. Sharing exposes notes and
payment history too. Making a record private also assigns its payer to the owner.
Ownership cannot be transferred through the API. Disabled owners do not silently
transfer or share records; protected ownership prevents deleting a referenced owner.

Server access checks cover snapshots, direct IDs, corrections, payment recording,
exports, loan totals, schedules, audit queries, and Django admin. Private reminders
are sent only to the owner; family reminders go to opted-in active members.
Notification text contains no private bill name or amount. Mandatory receipts and
receipt downloads are not part of this release; future endpoints must reuse the
same access policy.

Privacy is enforced by the application. Administrators with account-recovery privileges can reset account passwords; those changes are audited. This feature does not protect against a malicious administrator. It does not hide data from someone with
NAS, database, or backup access, and is not end-to-end encryption. Offline snapshots
are unencrypted browser storage on the trusted device. A readable account-scope cookie contains only the public account ID and is not an authentication credential. It prevents loading another account's saved copy after switching accounts, including if the connection drops before the first snapshot. Refreshed snapshots remove
newly inaccessible records; previously downloaded copies cannot be remotely erased
while offline. Sign out on shared devices and use the phone's screen lock.

## Emergency access

In **Setup & devices → Emergency visibility**, an administrator supplies their
current password, a reason, and confirmation. Access lasts **10 minutes**, applies
only to that browser session, and shows a visible read-only banner with an exit button.
PIN authentication cannot replace this password check. All business writes are
blocked while this mode is active. Ordinary APIs and Django admin continue to use
normal visibility; the separate emergency reader returns private records only while
the grant is active. Reloading the app returns to the normal view.

Emergency records are explicitly rejected by offline storage. Losing connection or
reaching the display expiry reloads the public shell and returns to the user's normal
snapshot. A browser that already received information cannot be made to forget it
by the server. Activation, private record reads, exit, and expiry are recorded in the
same transaction as the access metadata. The worker records expired idle grants.
Owners can review their access history under Setup & devices; administrators can
review access logs. No emergency export/download endpoint is provided.

## PIN sign-in

PINs are disabled by default. Sign in with a password, then open **Setup & devices →
Manage PIN & trusted devices**. Supply the current password, choose a non-obvious
6–8 digit PIN, enter it twice, and confirm. That device is enrolled for **30 days**.
Sign out, then use the PIN link on the login page. Other devices require password
login and explicit enrollment. Only one account is enrolled per browser profile;
enrolling another account revokes the browser's earlier credential.

PINs use Django's salted slow password hasher. Devices use a random 256-bit credential
in a Secure, HttpOnly, SameSite=Strict cookie; only an HMAC verifier is stored. Neither
PIN hashes nor device credential values appear in audit records or snapshots.
Five wrong PIN guesses trigger a 15-minute account cooldown, doubling on subsequent
blocks up to four hours. Account locks serialize concurrent attempts across devices
and IP addresses; counters survive restarts. A separate 60-attempt/15-minute network
limit affects PIN attempts only. Password login remains available during PIN cooldowns.
Password re-authentication for settings/emergency actions is also limited to five
failures per account per 15 minutes.

Changing/resetting the PIN revokes all PIN devices and enrolls the current device.
Disable revokes all devices and removes the PIN hash. **Revoke all trusted devices**
keeps the PIN but requires password enrollment on every device again. Password changes
invalidate all previously enrolled device credentials. Administrators cannot read a PIN;
their existing password-reset workflow invalidates enrolled devices, after which the
account owner can sign in and reset/disable the PIN. PIN changes/revocation do not revoke
already authenticated sessions; changing the account password invalidates those sessions.
Disabled/deleted accounts cannot use PIN sign-in. Successful sign-in rotates the session.

A short PIN is easier to guess than a strong password. Device enrollment and throttling
reduce that risk; they do not eliminate it. PIN login requires the live NAS and trusted
HTTPS. It neither unlocks nor encrypts offline copies. Failed PIN and re-authentication
outcomes intentionally use HTTP 200 with an error message so failure counters and their
audit events commit; rejected financial writes still roll back with their audit context.

The design follows [Django authentication](https://docs.djangoproject.com/en/5.2/topics/auth/default/)
and [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).

## One-time bills and validation

Choose Utilities for service bills (optionally recurring), Loan for monthly installments,
or One-time bill for a single obligation. One-time bills have no repetition/schedule controls
and support ordinary partial payments. Type and visibility are independent; type is shown
in lists, details, history, filters, and CSV exports.

Tests include PostgreSQL migration preservation and downgrade refusal, database constraints,
cross-account API/admin/export/audit denial, parent/child privacy, emergency expiry and
session isolation, reminders, PIN storage/limits/revocation/CSRF/session rotation, concurrent
guessing, atomic rollback, one-time partial payments, offline emergency rejection, and mobile
browser flows. Passing checks is evidence for the tested behaviors, not a guarantee that
the app or household network has no vulnerabilities. Physical-device push delivery and
the household's backup restoration remain deployment checks.
