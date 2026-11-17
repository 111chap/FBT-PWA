# Solo developer workflow

## Current enforcement

The private repository runs CI on pushes and pull requests. GitHub currently rejects enabling branch protection with a plan restriction. Repository visibility has not been changed.

The local pre-push hook blocks pushes, force pushes, and deletions targeting `main` from an installed checkout. It allows feature branches. GitHub's merge button, API writes, other checkouts, and bypassed hooks are not controlled by this local safeguard. Passing CI is therefore a manual merge requirement until server-side protection is available.

## Install the local safeguard

Run this once in each new clone:

```sh
git config --local core.hooksPath .githooks
```

This setting is local to this repository. Before installing it in a clone with an existing custom hook path, review that configuration so other hooks are not accidentally replaced. The initial development checkout has it installed as part of workflow setup.

## Make a change

Start from an up-to-date `main`, then create a branch:

```sh
git switch main
git pull --ff-only
git switch -c feature/short-description
```

Use `fix/short-description` for a bug or `chore/short-description` for maintenance. For issue work, include its number in the branch or PR description.

Implement and test the change, commit it, and push the feature branch:

```sh
git add <specific-files>
git commit -m "Describe the change"
git push -u origin HEAD
```

Open a PR into `main` on GitHub. The PR template asks for the problem, resulting behavior, and verification evidence. No second person is required to approve a solo PR.

## Merge only the tested revision

1. Wait for **Application and security checks / test** on the PR's latest commit.
2. Review its diff and relevant QA results. Resolve any blocking discussion.
3. If code changes, wait for the new commit's checks; an older successful run does not cover the new revision.
4. If `main` advanced, update the feature branch from it and run CI again before merging.
5. Merge using GitHub's **Squash and merge** when appropriate. Delete the completed feature branch through GitHub, then fast-forward the local `main`.

CI currently checks Django configuration, migration consistency, the backend/security suite against PostgreSQL, offline snapshot validation, and Python compilation. GitHub enforces none of these as merge requirements until protection is enabled; do not interpret a visible merge button as a passing test result.

## When branch protection becomes available

Configure `main` under repository Settings → Branches (or equivalent branch rules):

| Setting | Desired value |
| --- | --- |
| Require a pull request before merging | On |
| Required approving reviews | 0 / approval requirement off |
| Require status checks | `test`, from GitHub Actions |
| Require branches to be up to date | On |
| Apply rules to administrators / disallow bypass | On |
| Allow force pushes | Off |
| Allow branch deletion | Off |
| Require conversation resolution | On |

Enabling these rules should be a separate verified operation once GitHub permits it. Do not purchase a plan or change the repository's visibility automatically. There is no need for CODEOWNERS approval or another mandatory reviewer for this solo workflow.
