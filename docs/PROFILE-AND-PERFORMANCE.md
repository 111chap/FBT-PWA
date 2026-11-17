# Account access and responsive performance

## Profile scope

The upper-right account button shows the current user's initials and username.
Long names truncate on the button, while its accessible name and the profile
dialog retain the full username. The header stays visible while scrolling;
section anchors leave room for its actual height, including wrapped mobile
headers. The sidebar retains its visible sign-out action.

The profile shows the signed-in username, family name, and family administrator
or member role. **No fields are editable.** Account changes remain in the
existing validated administration flows with their existing audit behavior.
The profile adds no API or database writes and never receives passwords,
email addresses, or other members' private account data. Family member names
already present for payer selection remain part of the shared family snapshot.

Sign out opens the existing confirmation. Cancel and Escape keep the session.
Administrators can open administration while connected; members do not receive
that control. Offline profiles identify their information as a saved copy,
disable administration navigation, and follow the snapshot's existing seven-day
expiry and account-isolation rules. No new profile data is stored separately.
The Django administrator pages retain their original appearance.

## Measured bottlenecks and changes

The benchmark uses an isolated fictional household: **2,000 bills, 1,000
payments, one 120-installment loan, and 1,000 outstanding bills**. No real QA
records are read or modified. It measures a real browser and an authenticated
snapshot request; timings are observations, not universal performance promises.

Before optimization, startup built all 1,000 outstanding bill rows, even on the
overview screen. Every keystroke rebuilt those rows and recreated currency/date
formatters. The baseline median filter dispatch took **175.9 ms**, worst
**290.5 ms**. Paid-history navigation took **231 ms**.

The app now:

- Builds only the active record view. Hidden bills, loans, and history do not
  render during overview startup.
- Shows **25 bills or loans per page**, matching paid history's existing page
  size. Filtering and sorting operate on the complete saved dataset before
  pagination, reset to page one, and continue to update immediately.
- Reuses currency and date formatters instead of constructing them per cell.
- Keeps table scrolling inside local containers and form/account controls
  inside the viewport. The family page clips accidental outer overflow without
  removing horizontal scrolling from the record tables or mobile sort chips.
- Preserves bounded server-side audit pagination (25 events per request).

The first optimized measurement reduced median filter dispatch to **1.0 ms**,
worst **1.9 ms**, and history navigation to **34 ms**. Initial ready time changed
from **1,923.7 ms to 1,881.3 ms**, a small difference that should not be treated
as a reliable startup speedup. The meaningful gain is bounded DOM work and
interaction latency. Query count remained **9**, with an approximately
**822 KB** snapshot; neither grows by issuing a query per bill or payment.

These local measurements used SQLite and the installed Chrome browser on the
same machine. CI repeats the current benchmark against PostgreSQL 17 and its
locked Playwright Chromium. Machine, database, browser, and network differences
make the CI timings unsuitable for direct comparison with the local baseline.
Current raw metrics are uploaded in the browser QA artifacts.
The committed [before/after measurements](PERFORMANCE-MEASUREMENTS.json) also
include the final local run: 1.0 ms median filter dispatch, 1.8 ms worst, and
38 ms history navigation. Initial-ready and server timings vary between runs.

## Full snapshots and practical limits

The complete financial snapshot is intentionally retained so shared searching,
sorting, detail review, and opt-in offline review continue to cover all family
records. Pagination bounds rendered rows; it does **not** silently truncate
financial history. The snapshot's bytes and in-memory data still scale with
household history. This is not an enterprise-scale, constant-memory data API.
The measured 2,000-bill case is the regression fixture, not a hard data limit.
Audit history is independently paginated on the server and is never added to
offline snapshots. Private data is never placed in the public service-worker
cache; opt-in IndexedDB storage, expiry, logout clearing, and reconnect/update
prompts retain their existing behavior. Shell v15 includes the profile assets.

## Verification matrix

The automated browser suite checks administrators and ordinary members with
long usernames, long family names, and long bill titles at:

| Width × height | Purpose |
| --- | --- |
| 320 × 568 | Small phone |
| 390 × 844 | Typical phone |
| 768 × 1024 | Tablet |
| 1024 × 480 | Short laptop window |
| 1366 × 768 | Desktop/laptop |

Overview, bills, loans, paid history, setup, status, audit (admin only), profile,
forms, and dialogs are covered. Checks include keyboard opening/Escape/focus
return, touch opening, visible account/sign-out controls, local table scrolling,
live filters, paging, role isolation, offline reload, and reconnect recovery.
Existing suites cover transaction confirmations, permissions, security, audit
atomicity, concurrent writes, and snapshot expiry. Screenshots use fictional
records. Safari/iOS hardware has not been tested in this environment.

Reproduce with `FBT_DEBUG=1 FBT_BROWSER_TESTS=1 python manage.py test
tests.test_performance tests.test_profile tests.test_browser`. Set
`FBT_BROWSER_EXECUTABLE` when using an installed browser locally. The benchmark
baseline was captured before the optimizations with
`FBT_BENCHMARK_LABEL=baseline`; that label bypasses only the new pagination
assertion for measuring the earlier revision. Do not use it for CI validation.

There are no migrations, new production dependencies, or changes to financial
write/audit transactions. Continue the documented backup-before-update process.
