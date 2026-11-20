# Security

This application is an early development build for a single household, not a financial transaction service or an audited security product.

## Implemented controls

- Django password hashing, session authentication, CSRF protection, host validation, clickjacking protection, and restrictive content security policy.
- Production HTTPS redirects and secure, HTTP-only session cookies. Trusted proxy mode must only be used with an isolated app port and a proxy that overwrites forwarded headers.
- First-administrator setup requires a private enrollment code and closes after account creation.
- Database-backed login attempt limits: five failed attempts per account in 15 minutes. This also means an attacker can temporarily lock an account; keep the app private to your home network.
- Server configuration changes require the administrator. Family records are shared; Private records are owner-only. Administrator emergency visibility is password-confirmed, logged, read-only, session-scoped, and limited to 10 minutes.
- Payment amounts use decimal arithmetic. PostgreSQL transactions lock the bill while checking its current balance. Payment references make retries idempotent.
- Push subscriptions use an explicit provider host allowlist to avoid sending requests to arbitrary URLs. The app never fetches a server address entered in settings.
- API responses are not HTTP-cacheable. Offline snapshots require explicit device opt-in, expire after seven days, and are cleared on sign-out and rejected sessions.
- No Docker socket, privileged app container, or published database port.
- Database-triggered audit records commit or roll back with their business writes. Review is administrator-only, with no audit editing API. Passwords and subscription secrets are excluded. See [audit design](docs/AUDIT.md).

- Receipt and QR uploads use decoded/re-encoded still images, size/pixel/upload-count/storage limits, EXIF removal, private authenticated responses, manifest checks, and a dedicated media volume. New application payments require evidence; legacy records remain explicitly identified. Refer to [storage, transaction boundaries and backups](docs/NOTES-RECEIPTS-QR-AND-REMINDERS.md).

## Limits

- Offline snapshots are sensitive local data. They are not encrypted against a person controlling the same unlocked browser profile, and cannot be remotely erased while a device is disconnected.
- Revocation and session expiry cannot be checked offline. A saved copy may be visible until it expires or is removed locally.
- The app does not control NAS administration, DNS, certificate provisioning, router access, or independent backup storage.
- Notifications are best-effort. Push service acceptance does not prove device receipt.
- A short PIN is a convenience credential, not multi-factor authentication. PINs require password-enrolled devices, salted slow hashes, secure cookies, persistent account/network limits, and password fallback. See [PIN controls and privacy boundaries](docs/PRIVACY-PIN-AND-BILL-TYPES.md).
- Application privacy does not protect against NAS/database/backup operators or malicious administrators with account-recovery powers. Security checks reduce risk; they do not establish that the application or household network is risk-free.

## Tests

Run `python manage.py test tests` with the development environment described in README. The suite covers CSRF, authentication, disabled accounts, administrator restrictions, enrollment, login throttling, data caching headers, URL validation, push ownership, CSV formula injection, money validation, payment integrity, recurrence, and worker health. GitHub Actions is configured to run against PostgreSQL.

Run `node --test tests/offline.test.cjs` for saved-copy validation and expiry checks. Browser checks must also verify actual offline navigation, reconnect prompts, storage cleanup, and phone behavior.

Do not publish real bills, database exports, `.env`, private keys, or device subscriptions in an issue. Report a security concern privately to the repository owner through their GitHub profile, using a private contact method if available.
