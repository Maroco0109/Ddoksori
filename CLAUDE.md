# DDOKSORI Claude Instructions

Canonical roadmap: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`.
Required workflow skill: `.claude/skills/branch-worktree-pr-flow/SKILL.md`.

## Always use branch/worktree PR flow for repo changes

For every repo-tracked mutation, including code edits, documentation edits, refactors, commits, PRs, branch/worktree operations, and cleanup:

1. Use `.claude/skills/branch-worktree-pr-flow/SKILL.md`.
2. Do not commit directly to `main`.
3. Do not commit directly to `develop` unless explicitly requested as a direct develop hotfix.
4. Use `develop` as the development default branch.
5. Create a dedicated `feature/*` branch from `develop` for each module.
6. Create a separate git worktree for that feature branch and work there.
7. Open PRs to `develop` by default.
8. Treat PRs to `main` as release/version PRs requiring explicit user intent and extra caution.
9. After the PR is confirmed merged, remove the feature branch and worktree.

## Modular roadmap execution

- Execute only one roadmap module at a time.
- Do not proceed to the next module until the current module is verified and the user has discussed/accepted the result.
- Do not implement beyond the roadmap or the active module's completion criteria.
- If a new idea appears, record it as backlog/follow-up instead of implementing it immediately.

## Current project objective

The immediate objective is not chatbot answer-quality optimization alone.

The objective is to build a measurement and monitoring system that compares the current Agent/RAG/LLM system with future improved versions. Portfolio value requires measurable numbers: retrieval quality, latency, pass/fail rates, guardrail/security outcomes, fallback rates, model/provider usage, and before/after regression comparisons.

## gstack

gstack (Garry's Stack) provides a fast headless browser plus a suite of engineering/design/planning skills. It is installed per-machine, not committed to this repo (the browser binary is large and platform-specific, and the generated skill trees are huge). Each teammate installs it themselves:

```bash
git clone --single-branch --depth 1 https://github.com/garrytan/gstack.git ~/.claude/skills/gstack && cd ~/.claude/skills/gstack && ./setup
```

(Requires `bun`.)

### Web browsing

- Use the `/browse` skill from gstack for ALL web browsing.
- NEVER use `mcp__claude-in-chrome__*` tools.

### Available gstack skills

`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/design-shotgun`, `/design-html`, `/review`, `/ship`, `/land-and-deploy`, `/canary`, `/benchmark`, `/browse`, `/connect-chrome`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/setup-deploy`, `/setup-gbrain`, `/retro`, `/investigate`, `/document-release`, `/document-generate`, `/codex`, `/cso`, `/autoplan`, `/plan-devex-review`, `/devex-review`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`, `/learn`
