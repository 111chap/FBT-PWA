# FBT-PWA development workflow

- This repository is the Family Bill Tracker project. Keep work within this project.
- Start changes on a feature branch. Push that branch and open a pull request into `main`; do not push changes directly to `main`.
- Use the installed local pre-push hook. Do not bypass or disable it to publish changes.
- Before merging, verify that the GitHub Actions `test` check passes for the PR's latest commit. A new commit requires a new result. Check for unresolved comments and review the diff. Do not claim local tests substitute for the PR check.
- No independent reviewer approval is required for this solo project. Do not merge a PR unless the user requests or authorizes the merge.
- GitHub branch protection is not currently enforceable for this private repository under the available plan. Local hooks and these instructions are workflow safeguards, not server-side enforcement.
- Keep commit messages concise and on one line. Before committing, verify the effective author and committer are `111chap <apin.chrisdaniel@gmail.com>`. Use repository-local Git configuration only.
- Keep `.env`, private keys, databases, backups, device subscriptions, and real family records out of commits. Use fictional records for demonstrations.
- Preserve transaction/audit atomicity. Test database changes against PostgreSQL and document migrations and backup requirements.
