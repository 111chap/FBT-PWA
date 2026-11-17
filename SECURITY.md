# Security

This application is an early development build for a single household, not a financial transaction service or an audited security product.

## Implemented controls

- Django password hashing, session authentication, CSRF protection, host validation, clickjacking protection, and restrictive content security policy.
- Production HTTPS redirects and secure, HTTP-only session cookies. Trusted proxy mode must only be used with an isolated app port and a proxy that overwrites forwarded headers.
- First-administrator setup requires a private enrollment code and closes after account creation.
- Database-backed login attempt limits: five failed attempts per account in 15 minutes. This also means an attacker can temporarily lock an account; keep the app private to your home network.
- Server configuration changes require the administrator. Ordinary members intentionally share all family bills.
- Payment amounts use decimal arithmetic. PostgreSQL transactions lock the bill while checking its current balance. Payment references make retries idempotent.
- Push subscriptions use an explicit provider host allowlist to avoid sending requests to arbitrary URLs. The app never fetches a server address entered in settings.
- API responses are not HTTP-cacheable. Offline snapshots require explicit device opt-in, expire after seven days, and are cleared on sign-out and rejected sessions.
- No Docker socket, privileged app container, or published database port.
- Database-triggered audit records commit or roll back with their business writes. Review is administrator-only, with no audit editing API. Passwords and subscription secrets are excluded. See [audit design](docs/AUDIT.md).

## Limits

- Offline snapshots are sensitive local data. They are not encrypted against a person controlling the same unlocked browser profile, and cannot be remotely erased while a device is disconnected.
- Revocation and session expiry cannot be checked offline. A saved copy may be visible until it expires or is removed locally.
- The app does not control NAS administration, DNS, certificate provisioning, router access, or independent backup storage.
- Notifications are best-effort. Push service acceptance does not prove device receipt.
- Multi-factor authentication, per-bill visibility restrictions, and configurable reminder policies are not implemented in this first version. Audit history is read-only; payment correction workflows are still pending.

## Tests

Run `python manage.py test tests` with the development environment described in README. The suite covers CSRF, authentication, disabled accounts, administrator restrictions, enrollment, login throttling, data caching headers, URL validation, push ownership, CSV formula injection, money validation, payment integrity, recurrence, and worker health. GitHub Actions is configured to run against PostgreSQL.

Run `node --test tests/offline.test.cjs` for saved-copy validation and expiry checks. Browser checks must also verify actual offline navigation, reconnect prompts, storage cleanup, and phone behavior.

Do not publish real bills, database exports, `.env`, private keys, or device subscriptions in an issue. Report a security concern privately to the repository owner through their GitHub profile, using a private contact method if available.
