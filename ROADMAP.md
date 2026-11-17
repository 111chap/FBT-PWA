# Development roadmap

This roadmap describes planned work. Items are checked only when delivered and verified.

## 1. Repository and requirements

- [x] Document the problem, intended users, scope, and proposed stack.
- [x] Prepare a repository README and attribution.
- [ ] Publish the repository under `111chap`.
- [ ] Confirm NAS model, DSM version, container support, and available memory.
- [ ] Decide whether access is needed outside the home and choose an HTTPS setup.
- [ ] Confirm family permissions, currency, timezone, reminder preferences, and loan rules.

## 2. Application foundation

- [ ] Set up Django, PostgreSQL, and a local Docker Compose development environment.
- [ ] Add sign-in, family membership, and record-level access checks.
- [ ] Add repeatable checks in GitHub Actions.
- [ ] Document local setup using example configuration without secrets.

## 3. Bills and payments

- [ ] Implement bills, due dates, categories, and responsible members.
- [ ] Record partial and full payments, corrections, and attribution.
- [ ] Build the upcoming and overdue dashboard.
- [ ] Test money handling, permissions, and payment status calculations.

## 4. Recurring bills and loans

- [ ] Implement recurring templates and individual bill occurrences.
- [ ] Handle variable bill amounts and month-end dates explicitly.
- [ ] Implement agreed loan schedules and repayment history.
- [ ] Test duplicate occurrence prevention and balance calculations.

## 5. Installation and reminders

- [ ] Add PWA metadata, icons, service worker, and an unavailable-connection screen.
- [ ] Register devices for Web Push and provide notification preferences.
- [ ] Implement persisted reminders, retry handling, and duplicate-send safeguards.
- [ ] Test paid-bill suppression, worker restarts, outages, and expired subscriptions.
- [ ] Verify installation and notifications on actual Android phones and iPhones.

## 6. NAS deployment and portfolio

- [ ] Deploy to the NAS with persistent storage and HTTPS.
- [ ] Configure backups outside the NAS and verify a restore.
- [ ] Trial the application with the family.
- [ ] Add screenshots using fictional data and a short demonstration video.
- [ ] Write a portfolio case study covering the problem, implementation, tradeoffs, and measured results.
- [ ] Update the README with working setup instructions and completed features.
