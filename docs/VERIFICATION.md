# Verification record

Checked on November 17, 2026 using fictional household records. These are local results, not a claim of deployment to the family's NAS.

## Automated

| Check | Result |
| --- | --- |
| Django / PostgreSQL tests in Docker | 39 passed; test database cleanup completed successfully |
| Offline snapshot validation tests in Node | 5 passed |
| Django model migration drift | No changes detected |
| Django application checks | No issues |
| JavaScript syntax checks | Passed for app, setup generator, and service worker |
| Docker Compose configuration | Validated |
| Production Docker image build | Completed successfully with pinned Python dependencies |
| Production startup | Database healthy, migrations completed, web and worker started |
| Production liveness through trusted proxy header | HTTP 200 |
| Production first-run enrollment page | HTTP 200 |
| Production deployment check | No errors; two intentional HSTS policy warnings described below |

The backend suite includes authentication, CSRF, disabled accounts, administrator restrictions, first-run setup, database-backed login throttling, no-store headers, private push endpoint prevention, push subscription ownership, CSV formula injection, money validation, idempotent payment retries, overpayment rejection, PostgreSQL concurrent payments, monthly date anchoring, recurrence duplication prevention, paid-bill reminder suppression, retry limits, quiet hours, real worker heartbeat age, and generated VAPID key consistency.

HSTS is enabled for the app hostname. The deployment deliberately does not enable include-subdomains or browser preload because those choices affect domain names beyond the app. Django reports warnings W005 and W021; a domain administrator may choose a broader policy after confirming all affected subdomains support HTTPS.

## Browser acceptance

Verified with the local preview:

- Signed into a fictional family workspace.
- Added a bill through the UI.
- Recorded a partial payment and verified the reduced balance and per-bill payment history.
- Created a three-installment loan starting January 31; automated checks verified February 28 and March 31 with an exact total.
- Viewed component status with a real database result and worker heartbeat, with missing push configuration clearly identified.
- Enabled offline viewing, stopped the server, and reloaded the installed shell route. Saved records remained visible with their timestamp and disabled payment controls.
- Restarted the server and observed the update prompt. Payment controls stayed disabled until the saved copy was refreshed.
- Signed out, stopped the server, and reopened the shell. No saved financial records remained.
- Checked a 390px-wide layout, including stacked bill cards, payment controls, bill details, and mobile sign-out, without page-wide horizontal overflow.
- Opened the first-time setup guide and downloaded a generated settings file. The browser saved it as `env.txt`; the guide explicitly instructs users to rename it to `.env` without the `.txt` suffix.

Screenshots of the fictional interface are saved locally under ignored `tmp/previews/`.

## Still requires deployment / device testing

- The actual Synology DS923+, installed DSM, NAS permissions, resource usage, and persistent volumes.
- Home DNS, a trusted certificate, and the specific NAS reverse proxy configuration.
- Actual iPhone and Android installation and push receipt, including Focus / notification settings.
- A backup restored into a separate environment.
- Accessibility testing with assistive technology and a broader browser matrix.

GitHub Actions is configured but has not executed remotely because repository publication is still awaiting explicit public-visibility approval.
