# Notes, installments, personal totals, reminders, QR and receipts

This release implements #29 and #31–#36. Apply migration
`0007_notes_receipts_and_qr` with web and worker paused, after a verified backup.
No bank connection, payment execution, or automatic verification is added.

## Updating an existing NAS

Before the first upgrade from 0006, use your existing database/`.env` backup task
and keep a copy outside the NAS. No receipt images existed in that version.
Keep the same PostgreSQL volume, secrets, hostname and certificate.

Upload the new source and **updated compose.yaml**, preserving `.env` and backups.
Check Container Manager's **YAML Configurations** actually contains the new
`media_data` named volume and the `/app/media` mounts for web and worker; replacing
a file in File Station alone may not update a project's saved YAML. Rebuild the
image and recreate containers from this configuration. A simple restart is insufficient.
Wait for init/migration success before starting web/worker. Do not delete volumes.

The dedicated media volume is created automatically and initialized for app UID
10001 by the image. Other app filesystem paths stay read-only; the app has no Docker
socket or additional capabilities. Images persist through container/image rebuilds.
With project name `fbt`, Docker normally names it `fbt_media_data`. It is managed by
Container Manager, **not** a public website folder or a Windows reference path.
Use `docker volume inspect fbt_media_data` from a permitted NAS terminal if the NAS
administrator needs its physical location. Do not edit raw files directly.

Refresh installed apps on home Wi-Fi; `/sw.js` is `fbt-shell-v21`. Check System status
for database, worker, audit and private image storage. Verify an ordinary member's
access, a fictional receipt payment, notes, and a notification test. Back up again
using the new complete backup procedure after the upgrade.

The migration keeps old payment IDs, amounts, dates, balances and payer/recorder
assignments. Existing payments are explicitly legacy entries without receipts; no
fake evidence is generated. Shared parent descriptions start blank, preserving
all existing occurrence/installment-specific notes. The migration does not guess
that conflicting child notes represent a shared description. Audit trigger v5 replaces
v4 atomically, with database evidence constraints for new application payments.

Once shared-note/evidence history exists, downgrade is refused. Restore the matching
application version, database, `.env` and images instead of dropping fields. Keep the
source version/archive associated with each backup. Running old code against the new
database is not a supported rollback.

## Notes and installment lists

All creation entry points offer optional notes/details, with a 500-character limit
and multiline review. Recurring bill notes belong to the schedule; loan descriptions
belong to the loan. Each occurrence/installment retains its separate notes.
Use **Edit description** to add, edit or clear the current shared description, including
on old or fully paid loans. It appears across past/current/future views. Historical
screens label it as the **current** description; earlier values remain in audit history.
Editing text never regenerates installments or recalculates money.

Bills & payments selects the earliest unpaid, non-removed installment per loan by
due date then ID **before** filtering. Partial/overdue installments stay selected;
full payment advances to the next, and corrections can reopen an earlier row.
Loan details retain the entire schedule. Totals and reminders always use all eligible
records, not the shortened presentation. The same calculation works offline.

The existing unpaid card contains **Your total unpaid balance**, **Due this month**,
and a separately labelled **Shared family unpaid** figure. Personal responsibility
uses the assigned primary payer, never the creator or recorder. Current-month totals
use Manila calendar due dates and include every relevant installment. Other members'
private debt read in emergency mode is excluded from these ordinary/personal totals.

## Reminder schedule

Notifications are eligible 7, 3, 1 and 0 days before the individual due date, then daily
while overdue. The notification window remains 09:00–20:00 Asia/Manila. The first
eligible worker cycle sends that day's reminder, with up to three attempts per device,
bill and calendar day. Paid, removed or cancelled obligations are skipped. Cancelling
a recurring schedule suppresses automatic reminders for its occurrences; amounts
already owed remain recorded. Private reminders go only to the owner; Family reminders
go to active opted-in members. Messages contain no bill names or amounts.

After downtime, only the current day's eligibility is evaluated; missed milestones
are not replayed as a burst. Provider acceptance is not proof of phone delivery.
Persistent suppression and worker locks prevent ordinary duplicate scheduling;
a crash after provider acceptance but before database commit can still result in a
retry because the provider and PostgreSQL cannot share one transaction.

## Recording and reviewing payment evidence

Select a receipt/screenshot from the phone's camera/gallery or file picker, wait for
upload/validation and preview, then review and confirm the payment. Native picker
choices vary by phone/browser. Every new partial/full/loan payment requires one image,
including administrator-recorded payments. A receipt proves that an image was supplied;
it does **not** establish that a transfer is authentic or reached the correct recipient.

Images are decoded and re-encoded as JPEG, PNG or WebP, correcting EXIF orientation and
removing metadata/location. Animated images, SVG, GIF, HEIC, invalid files, trailing
payloads and excessive dimensions are rejected. Limits default to 8 MB input, 20 million
pixels, maximum 12,000 pixels on either edge, and 16 MB cleaned output. A QR is normalized
losslessly to PNG to avoid JPEG damage. Pixels are not resized, cropped or inverted.

The server assigns names such as:
`2026-11-20_21-00-00_PHT_loan_payment-1042_<random-id>.png`.
The prefix is upload time in Manila; stored timestamps are UTC. Payment date stays
separate. Filenames contain no names or bill titles and do not change after title edits.
Raw client filenames and decoded QR account payloads are not stored in audit logs.

**View receipt** shows current and retained earlier evidence. Authorized owners/admins
can replace evidence, including adding it to a legacy payment, with reason and confirmation.
Replacing or logically deleting/correcting a payment does not erase earlier files.
No application feature permanently deletes retained evidence. Changes are audited.
Private images require fresh permission checks on every request; emergency reads
are logged for the owner. There are no public static/media URLs. Images are excluded
from service-worker/offline snapshots; reconnect to review them.

Uploads first create bounded, private staged files. Validated bytes are flushed and
fsynced before metadata/payment commit. Final filenames are created without replacing
existing evidence. PostgreSQL metadata, payment and audit writes share one transaction.
Filesystem storage is not a PostgreSQL transaction: failed requests/crashes can leave
unreferenced staged files, but must not commit a new payment without valid finalized
evidence metadata. Unused uploads/orphans are cleaned after 48 hours; uploads expire for
attachment after 24 hours. Cleanup never deletes referenced retained files. A disk failure,
operator deletion, or incomplete restore after commit can still make evidence unavailable;
opening a file verifies its size/hash and fails closed on damage.

The private media budget defaults to 2 GB, 100 uploads/user/day and 20 pending uploads/user.
Optional `.env` settings are `FBT_MEDIA_MAX_BYTES`, `FBT_UPLOAD_MAX_BYTES`,
`FBT_IMAGE_MAX_PIXELS`, `FBT_UPLOADS_PER_DAY`, and `FBT_PENDING_UPLOADS`.
Recreate services after changing settings. These limits do not reserve NAS disk space
or replace a filesystem quota. Monitor NAS free space; no new payment can complete when
its receipt cannot be stored. Retained evidence uses storage until an explicit retention
policy is introduced; do not manually delete files to reclaim space.

## Household QR

In Setup & devices, the administrator uploads and verifies one household QR with a
recipient label. The real image is uploaded privately after deployment, never put in
GitHub or copied from a developer's Windows path at runtime. **Pay using QR** opens the
complete image with its quiet area/aspect ratio intact, including in dark mode. A download
option supports payment apps that can import a gallery image; compatibility varies.
The recipient is explicitly configured and may differ from the provider or primary payer.
Confirm the recipient in your external payment app before paying.

Opening/scanning/downloading the QR changes no balances. Pay externally, then record the
payment with evidence. Configuration changes require administrator confirmation, an
optimistic version check and an audit reason. Replaced/removed QR URLs stop serving the
old destination. Open dialogs refresh configuration periodically and hide images when
connection is lost. An already downloaded image cannot be recalled; always recheck the
recipient. No QR is saved for offline use automatically.

## Complete backups and isolated recovery

**Database dump + `.env` alone is no longer a complete backup.** Keep the entire
database, matching private media archive, settings, Compose file, dependency lock and
matching source version together. Store a protected copy off the NAS; RAID is insufficient.
Your previous manual `FBT-backup` task must be updated to include media.

After deploying this release, a permitted NAS terminal or manual Task Scheduler script can run:

```sh
sh /volume1/docker/fbt/tools/backup_nas.sh /volume1/docker/fbt
```

It pauses web/worker, dumps PostgreSQL, copies settings/configuration, verifies retained
image hashes, archives the media volume and restarts services after successful backup.
It creates a new `backups/<UTC timestamp>/` folder and never overwrites an existing one.
Run it manually with the task's Enabled/schedule option off unless you deliberately
choose a schedule. Docker access may require the NAS administrator/root; it does not
enable SSH or grant Docker access to the app. On failure inspect the log, leave the
incomplete folder untrusted, and check whether web/worker need restarting.

To validate recovery, use a **separate Compose project**, for example `fbt-restore`,
with separate empty database/media volumes and no published web port. Verify you have
selected the restore project, not `fbt`. Keep its worker stopped to prevent duplicate
reminders. Use a protected copy of the backup's settings and matching app version.

1. Start only the restore database. Restore `fbt.dump` into that empty database.
2. Restore `media.tar` into the restore project's empty `/app/media` volume.
3. Run `python manage.py verify_media` in a one-off restore web container using that
   database and media volume. Every retained image must match its manifest.
4. Check accounts, bills, balances, notes, current QR, receipts and retained revisions
   through an isolated local endpoint before treating recovery as successful.
5. Do not replace the live database/volumes until the NAS administrator has selected
   the intended recovery point. Copying code alone does not undo migrations.

Development verification uses only fictional images/records and isolated PostgreSQL,
including database/media restore and persistence across container recreation. Deployment
still requires checking the actual NAS's free space, backup destination, certificate and
physical-device push delivery. Tests reduce risk; they cannot guarantee zero risk.
