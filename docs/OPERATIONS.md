# NAS setup and operations

## Start with the visual guide

Open `setup/index.html` from a downloaded source folder, or visit `/setup-guide/` on a running app. It walks through Synology Container Manager, privately generating `.env`, configuring HTTPS, creating the first account, and installing the app on phones.

The app does not install Docker, inspect arbitrary NAS addresses, modify DNS, or control the Docker daemon. Saving a home server address in Setup & devices is a display setting; the installed app continues using its original origin. To change origins, install the app from the new address, sign in again, and re-enable offline viewing and notifications there.

## Deployment layout

`compose.yaml` runs PostgreSQL 17, a one-time migration service, the web app, and one worker. Only the web service has a host port, bound to `127.0.0.1:8787`. PostgreSQL stays inside the Compose network. The app containers run as an unprivileged user with a read-only filesystem, no added capabilities, and no Docker socket.

Configure a trusted Synology reverse proxy from the app's HTTPS hostname to HTTP `127.0.0.1:8787`. Configure the proxy to overwrite `X-Forwarded-Proto` with `https`. Keep `FBT_TRUST_PROXY=1` only with that trusted proxy and loopback-only port binding. Otherwise a client could claim a connection is secure.

Use the same hostname in `FBT_ALLOWED_HOSTS` and the complete HTTPS origin in `FBT_TRUSTED_ORIGINS`. Do not use wildcards. All family accounts share a single household's records; this is not a multi-tenant service.

## Optional command-line configuration

After installing the Python requirements, the following is an alternative to the guide's settings generator:

```sh
python tools/make_env.py --origin https://YOUR-REAL-APP-HOSTNAME --contact YOUR-EMAIL
```

This creates `.env` only if it does not already exist. It generates random secrets and VAPID keys locally. Keep the file out of version control and backups available only to trusted administrators. Do not change `POSTGRES_PASSWORD` on an existing database merely by editing `.env`; changing a provisioned PostgreSQL role requires a separate coordinated password rotation.

Start with Container Manager's Project workflow or:

```sh
docker compose up --build -d
docker compose ps
```

Visit the configured HTTPS address. Create the first administrator using `FBT_SETUP_TOKEN`. Afterward `/setup/` no longer accepts enrollment. Create ordinary family accounts through Django administration with staff and superuser flags off. Never use the local demo account in production.

## Status checks

System status shows:

- A live signed-in web request.
- A real database query.
- Worker heartbeat age; missing or older than three minutes is unhealthy.
- Whether this request used HTTPS.
- Whether all VAPID settings exist, independently from confirmed device delivery.
- Registered device count for the current account.
- Audit and balance trigger presence, with an error if a required trigger is missing or disabled.
- Manual checks for Container Manager and backup restoration.

The browser cannot inspect components if it cannot reach the server. Docker health checks verify the app liveness endpoint and worker heartbeat. A healthy worker is evidence that its schedule cycle completed, not a guarantee every push notification was received.

Administrators can review committed database changes in **Audit history**. See [audit review and atomicity](AUDIT.md) for before/after snapshots, grouped transaction references, log coverage, and rollback guarantees. Apply migrations before starting the updated web and worker services, and back up first. Earlier activity is not reconstructed.

```sh
docker compose logs --tail=100 web worker init
```

Logs should not include bills, credentials, or subscription endpoints. Remove secrets before sharing diagnostics.

## Reminders and recurrence

The worker runs roughly every minute. It generates monthly fixed-amount bills up to 30 days ahead, retaining the original day-of-month anchor through short months. For variable-amount bills, add each occurrence manually for now.

Notifications are sent at most once per bill per subscription per Manila calendar day, between 09:00 and 20:00, starting three days before the due date and continuing while unpaid. Temporary failures retry up to three times that day. Confirm a device test after subscription. There is no configurable quiet-hour or per-bill recipient UI yet.

Run only one worker. PostgreSQL row locking serializes cycles if another worker starts accidentally. Push delivery cannot be exactly once: a process crash after the push service accepts a message but before the database records success can cause a retry. An offline worker does not replay every missed day's reminders; it checks the current day after recovery.

## Offline behavior and shared devices

Offline viewing is opt-in per browser profile. Only a timestamped, read-only snapshot is kept in IndexedDB. It expires after seven days. The service worker caches only public shell assets; it never caches authenticated pages or API responses.

The app probes its own server every 30 seconds and on a browser online event. Reachability means the app server answered, not that a specific Wi-Fi network name was detected. When it becomes reachable again, the app prompts for an update before allowing mutations. Online additions and payments fetch a new snapshot. A rejected or expired login clears the saved copy and asks for sign-in.

Signing out clears the offline copy and notifies other open tabs. Signing out offline clears local records immediately but cannot revoke the server session until reconnection; the app explicitly explains that limitation. A user on the same unlocked browser profile can inspect stored snapshots. Use device screen locks and avoid enabling offline storage on shared machines. Browser storage may be evicted; it is not a backup.

## Back up

Back up PostgreSQL and `.env` to an access-controlled destination outside the NAS. Set a schedule and retention appropriate for your household. For an administrator comfortable with a terminal:

```sh
mkdir -p backups
docker compose exec -T db pg_dump -U fbt -d fbt -Fc > backups/fbt.dump
```

Use a shell that preserves binary output (for example a shell on the NAS). Older Windows PowerShell versions can corrupt binary redirection; use the NAS or a suitable backup utility instead. CSV export is for portability, not complete restoration. RAID does not replace an independent backup.

## Test a restore

Restore in a separate environment, not over the only live database. Using a separate Compose project and volume, create an empty test database and import the dump:

```sh
docker compose exec -T db pg_restore -U fbt -d fbt --no-owner --no-privileges < backups/fbt.dump
```

This example assumes an empty destination. Verify account access, bills, payment totals, and installment schedules. Disable the reminder worker in the restore environment to prevent duplicate notifications. Do not delete or replace production volumes without a verified backup and explicit recovery plan.

## Updates

Back up first. Review dependency and migration changes, rebuild the project, and allow `init` to complete before the web and worker services start. After changing environment values, recreate containers through the project rebuild workflow. Check status and a notification test afterward. Keep the original `.env` and PostgreSQL volume; a new configuration file can break access to existing data or invalidate push registrations.

## Before trusting real records

- Verify trusted HTTPS on every phone without a certificate exception.
- Run the security and payment tests against PostgreSQL.
- Confirm ordinary members cannot change server settings or enter administration.
- Verify notification delivery on actual iPhone and Android devices.
- Test offline opening, reconnect refresh, and sign-out cleanup.
- Restore a real backup into an isolated test environment.

## References

- [Synology Container Manager projects](https://kb.synology.com/en-global/DSM/help/ContainerManager/docker_project)
- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Service workers and secure contexts](https://developer.mozilla.org/en-US/docs/Web/API/Service_Worker_API/Using_Service_Workers)
- [Apple Home Screen Web Push](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)
