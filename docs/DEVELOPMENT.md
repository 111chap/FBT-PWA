# Local development

Python 3.12 and Node.js 22 or newer are suitable. PostgreSQL 17 is the deployment database; SQLite is supported only for a quick local preview. No frontend package installation is required.

## Windows PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
New-Item -ItemType Directory -Path data -Force
$env:FBT_DEBUG = '1'
.\.venv\Scripts\python.exe manage.py migrate
$env:FBT_SETUP_TOKEN = 'choose-a-long-local-development-setup-code'
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8787
```

Open `http://127.0.0.1:8787/` and create the first account using that development setup code. For NAS deployment use the configuration generator and `compose.yaml`; never use `FBT_DEBUG=1` on the NAS.

The app does not automatically load `.env` in a direct Python process. Compose loads it for containers; local PowerShell examples set environment variables explicitly. See `.env.example` for configuration names.

## macOS or Linux

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.lock
mkdir -p data
export FBT_DEBUG=1
export FBT_SETUP_TOKEN=choose-a-long-local-development-setup-code
.venv/bin/python manage.py migrate
.venv/bin/python manage.py runserver 127.0.0.1:8787
```

## Optional fictional demo

On a new local SQLite database, set `FBT_DEMO_PASSWORD` to a development-only password of at least 12 characters, then run:

```sh
python manage.py seed_demo
```

Use the virtual environment's Python executable. Sign in as `demo` with the password you chose. This command refuses to run against PostgreSQL, with production settings, or alongside non-demo accounts. It does not ship an automatic production login.

## Worker and notifications

In a second terminal with the same environment, run:

```sh
python manage.py reminder_worker
```

Or run one cycle with `python manage.py reminder_worker --once`. Set VAPID values and contact information to test real push delivery. The guide generates these for deployment; `python manage.py generate_push_keys` can generate a replacement key pair for a fresh configuration. Replacing existing keys requires re-subscribing devices.

Localhost is treated as a secure context for service workers. A phone using a plain HTTP LAN IP is not equivalent: use trusted HTTPS for phone installation and push testing.

## Automated checks

With `FBT_DEBUG=1` in a fresh shell:

```sh
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test tests
node --test tests/offline.test.cjs
node --check static/app.js
node --check static/setup.js
```

Tests use a temporary database. The simultaneous-payment test runs only against PostgreSQL, because SQLite does not provide equivalent row locking. CI is configured with PostgreSQL.

To use the Docker test environment without publishing the web port:

```sh
docker compose run --rm -e FBT_DEBUG=1 web python manage.py test tests
```

This still requires a private `.env`. It starts database and migration dependencies. Use a separate project name and configuration when a real deployment already exists.

## Browser acceptance checks

Use fictional records and verify:

1. First-run enrollment, sign-in, sign-out, and an ordinary member account.
2. Add a bill and record a partial payment. Confirm the balance and payment history.
3. Create three installments starting January 31. Confirm February's shorter date and March's restored anchor.
4. Save a local offline copy, stop the server, and reload `/app/`. Confirm the timestamp, saved records, and disabled payment controls.
5. Restart the server. Within about 30 seconds, confirm the update prompt. Refresh and verify controls become available.
6. Sign out, stop the server, and reopen `/app/`. No saved family records should remain.
7. On a 390px phone-sized viewport, review bills, details, setup, and system status without page-wide horizontal scrolling.
8. Test push receipt on physical Android and iPhone devices after trusted HTTPS deployment.

## Implementation notes

The first version uses Django templates for authentication and a public app shell with small, self-hosted JavaScript modules. HTMX is not needed for the snapshot-based offline interface. IndexedDB keeps opt-in private snapshots separate from the public service-worker shell cache. All payment writes require the live server.
