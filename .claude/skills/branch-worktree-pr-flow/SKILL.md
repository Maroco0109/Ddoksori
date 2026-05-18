---
name: branch-worktree-pr-flow
description: Use for every repo-tracked change, implementation, refactor, documentation edit, commit, PR, or cleanup in DDOKSORI. Enforces main-develop-feature branch discipline, git worktree isolation, PR-based integration, and post-merge branch/worktree cleanup.
---

# Branch Worktree PR Flow

Purpose: prevent direct commits to `main`, encourage `main -> develop -> feature/*` flow, and keep each roadmap module isolated in its own worktree.

## Non-negotiable rules

- Never commit directly to `main`.
- Never commit directly to `develop` unless the user explicitly asks for a direct develop hotfix.
- Treat `develop` as the development default branch.
- Treat PRs into `main` as version/release-level changes that require extra caution.
- For every repo-tracked mutation, create or use a dedicated `feature/*` branch and a separate git worktree.
- Work on exactly one roadmap module at a time when the roadmap applies.
- After a PR is merged, clean up the feature branch and worktree.

## Standard workflow

### 1. Before editing

1. Identify the active roadmap module, if any.
2. Check current branch and dirty state:
   ```bash
   git status --short
   git branch --show-current
   git worktree list
   ```
3. If currently on `main` or `develop`, do not edit there.
4. Fetch current refs when network/auth allows:
   ```bash
   git fetch origin develop main --prune
   ```

### 2. Create feature branch and worktree

Prefer branching from `origin/develop`; fallback to local `develop` only if needed.

```bash
BRANCH="feature/<module-id>-<short-slug>"
WORKTREE="../Ddoksori-worktrees/<module-id>-<short-slug>"
mkdir -p ../Ddoksori-worktrees
git worktree add -b "$BRANCH" "$WORKTREE" origin/develop
```

If the branch already exists, attach it instead:

```bash
git worktree add "$WORKTREE" "$BRANCH"
```

Then perform all edits, tests, and commits inside `$WORKTREE`.

### 3. Implement only the active module

- Keep the diff scoped to the active module.
- Do not bundle unrelated cleanup, refactors, or future modules.
- If a new idea appears, record it as backlog/follow-up instead of implementing it.

### 4. Commit and PR

Commit from the feature worktree only. Follow the repository's Lore commit protocol if present.

Open PRs to `develop` by default. The PR message must explain both **what changed** and **why it changed** so future reviewers understand the intent, not only the diff.

```bash
git push -u origin "$BRANCH"
gh pr create --base develop --head "$BRANCH" --title "..." --body-file /tmp/pr-body.md
```

Minimum PR body sections:

```md
## What changed
- ...

## Why
- ...

## Validation
- ...
```

Only target `main` for explicit release/version PRs.

### 5. After PR merge

Confirm the PR is merged before cleanup:

```bash
gh pr view --json state,mergedAt,baseRefName,headRefName
```

After confirmed merged:

```bash
git worktree remove "$WORKTREE"
git branch -d "$BRANCH"
git push origin --delete "$BRANCH"
git fetch --prune
```

If local branch deletion fails because it is not recognized as merged, inspect first. Do not force-delete unless the merge is verified.

## Report format

When starting work, report:

```md
## Branch/worktree plan
- Base branch: develop
- Feature branch:
- Worktree path:
- Active module:
- PR target: develop
```

When finishing work, report:

```md
## PR/cleanup status
- Feature branch:
- Worktree path:
- PR:
- Merge status:
- Cleanup performed:
```
