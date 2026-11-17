# FBT-PWA — Family Bill Tracker

A self-hosted family bill and loan repayment tracker for Android, iPhone, and desktop browsers. Keep due dates, manual payments, and reminders together on a family NAS.

**Stage: first working development version.** Local browser and Docker/PostgreSQL checks passed. It is not yet deployed to the family NAS or verified on physical phones. See the [verification record](docs/VERIFICATION.md).

## What works

- Shared family accounts, one-time administrator enrollment, and sign-in.
- Guided Utilities/Loan entry, live installment previews, partial/full payments, and CSV export.
- Shared paid-bills history with payer/recorder filters and read-only offline access.
- Clickable bill headings for alphabetical, date, original/unpaid amount, and status sorting.
- Monthly fixed-amount recurring bills and agreed loan installment schedules.
- Dashboard and phone-sized layouts for upcoming, overdue, and paid records.
- System status with actual database checks and worker heartbeat age.
- First-time Synology setup guide with a local private configuration generator.
- Opt-in, read-only offline snapshots with a saved-at timestamp and seven-day expiry.
- A prompt to refresh after the home server becomes reachable again.
- Web Push subscription, device test, and scheduled reminders when configured.
- Security and payment tests, including simultaneous payments against PostgreSQL.
- Administrator audit review with database-triggered history, safe before/after snapshots, and grouped transaction references.

The app does not connect to banks, detect payments, or transfer money. Family members enter records manually.

## Try it locally

See [local development](docs/DEVELOPMENT.md) for the complete Windows and macOS/Linux steps. In brief: create a Python virtual environment, install `requirements.lock`, set `FBT_DEBUG=1`, create the `data` directory, migrate the database, set a development `FBT_SETUP_TOKEN`, and run `python manage.py runserver 127.0.0.1:8787` using the virtual environment.

A fictional preview can be created with `seed_demo`; it is explicitly disabled in production and PostgreSQL deployments. Real credentials and family data must remain outside the repository.

## Install on a NAS

Start with the [visual first-time guide](setup/index.html). Download the project and open that file in a browser, or visit `/setup-guide/` on a running instance. The guide covers:

1. Installing Synology Container Manager and preparing the project folder.
2. Generating a private `.env` file locally.
3. Starting the Docker Compose project.
4. Configuring a trusted HTTPS address and NAS reverse proxy.
5. Creating family accounts and installing the app on phones.
6. Checking component status, saving offline records, and testing reminders.

The intended device is the family's Synology NAS, reported as a DS923+; confirm the model, DSM version, available memory, and home DNS before deployment. The app guides configuration; it does not install Docker or change NAS administration settings remotely.

See [operations and recovery](docs/OPERATIONS.md) for deployment details, backups, and restoration.

See [audit history and atomicity](docs/AUDIT.md) for log coverage, rollback guarantees, and how to review changes.

## Stack

| Component | Implementation |
| --- | --- |
| Application | Python 3.12 and Django 5.2 LTS |
| Interface | Django templates, responsive CSS, self-hosted JavaScript |
| Deployment database | PostgreSQL 17 |
| Local preview database | SQLite |
| Offline installation | Web manifest, service worker, IndexedDB |
| Notifications | Web Push, pywebpush, VAPID |
| Reminders | Separate worker with durable schedules and delivery records |
| NAS hosting | Docker Compose and Synology Container Manager |
| Web server | Waitress and WhiteNoise behind a trusted HTTPS reverse proxy |

Dependency versions are captured in `requirements.lock` for repeatable builds. No external fonts, analytics, frontend CDN, or frontend build tool is needed.

## Offline and privacy

Saving bills offline is a per-account opt-in on each browser profile. The copy is read-only and shows its last update time. A browser with access to that profile can inspect the stored records, so only enable it on trusted, locked devices. Sign-out clears the local copy; offline sign-out also explains that server-session revocation waits for reconnection.

The public service-worker cache contains only shell assets. Authenticated pages and API responses are never placed in that cache. When the home server answers again, the app prompts for an update before allowing payment changes. It checks server reachability, not your Wi-Fi network name.

## Checks

```sh
python manage.py test tests
npm ci
npm test
```

Run with the environment described in [development](docs/DEVELOPMENT.md). [GitHub Actions](https://github.com/111chap/FBT-PWA/actions) runs these checks with PostgreSQL on pushes and pull requests. See [security](SECURITY.md) for implemented controls and limitations.

See [bill entry, sorting, and paid history](docs/BILL-ENTRY-AND-HISTORY.md) for the guided entry and shared history screens.

See [family workflows](docs/FAMILY-WORKFLOWS.md) for review/confirmation, shared settings, monthly lifecycle, filters, payer assignment, and upgrade instructions. CI also installs Chromium and runs real-browser regression checks.

## Remaining work

See the [solo developer workflow](docs/WORKFLOW.md) for feature branches, PRs, local `main` push prevention, and CI-before-merge guidance. GitHub-enforced protection is currently unavailable under the private repository's plan.

Physical iPhone/Android push verification, real NAS deployment, backup restoration, configurable reminder times/recipients, bill editing and payment corrections, and further accessibility testing remain. See [roadmap](ROADMAP.md). The [original outline](FAMILY-BILL-TRACKER-IDEA.md) and [PDF overview](output/pdf/FAMILY-BILL-TRACKER-IDEA.pdf) describe the earlier planning proposal rather than current completion status.

## Author and attribution

Original application idea and project ownership: **Chris Daniel Apin ([111chap](https://github.com/111chap))**.

**Codex** generated the initial technology stack proposal and supporting information, and assisted with implementation and tests based on Chris's requirements.

## License

No open-source license has been selected yet.
