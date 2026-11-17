# Development roadmap

This roadmap describes planned work. Items are checked only when delivered and verified.

## 1. Repository and requirements

- [x] Document the problem, intended users, scope, and proposed stack.
- [x] Prepare a repository README and attribution.
- [x] Publish the repository under `111chap`.
- [ ] Confirm NAS model, DSM version, container support, and available memory.
- [ ] Decide whether access is needed outside the home and choose an HTTPS setup.
- [ ] Confirm family permissions, currency, timezone, reminder preferences, and loan rules.

## 2. Application foundation

- [x] Set up Django, PostgreSQL, and a local Docker Compose development environment.
- [x] Add sign-in and one shared household with administrator-only setup settings.
- [x] Configure repeatable checks in GitHub Actions (remote execution awaits publication).
- [x] Document local setup using example configuration without secrets.

## 3. Bills and payments

- [x] Implement bills, due dates, categories, and responsible members.
- [x] Record partial and full payments with attribution and history.
- [x] Add administrator bill/loan/payment editing and logical deletion, including paid records, with required reasons and atomic audit history.
- [x] Build the upcoming and overdue dashboard.
- [x] Test money handling, permissions, payment status calculations, and concurrent payments.
- [x] Add database-triggered audit history, administrator review, safe before/after snapshots, and rollback tests.

## 4. Recurring bills and loans

- [x] Implement monthly fixed-amount recurring templates and individual bill occurrences.
- [x] Handle month-end dates and explain manual entry for variable bills.
- [x] Implement agreed loan schedules and repayment history.
- [x] Test duplicate occurrence prevention and balance calculations.

## 5. Installation and reminders

- [x] Add PWA metadata, icon, service worker, and timestamped offline bill viewing.
- [x] Add opt-in offline storage and prompt to refresh when the server is reachable again.
- [x] Register devices for Web Push, disable a device, and send a test.
- [ ] Add configurable reminder times and per-bill recipient preferences.
- [x] Implement persisted reminders, retry handling, and duplicate-send safeguards.
- [x] Test paid-bill suppression, worker restarts, and temporary delivery failures.
- [ ] Verify expired subscriptions and real phone delivery against provider services.
- [ ] Verify installation and notifications on actual Android phones and iPhones.

## 6. NAS deployment and portfolio

- [ ] Deploy to the NAS with persistent storage and HTTPS.
- [ ] Configure backups outside the NAS and verify a restore.
- [ ] Trial the application with the family.
- [ ] Add screenshots using fictional data and a short demonstration video.
- [ ] Write a portfolio case study covering the problem, implementation, tradeoffs, and measured results.
- [ ] Update the README with working setup instructions and completed features.
