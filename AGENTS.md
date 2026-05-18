# DDOKSORI Agent Instructions

Canonical roadmap: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`.


## Branch/worktree PR workflow

Use `.claude/skills/branch-worktree-pr-flow/SKILL.md` for every repo-tracked mutation, including code edits, documentation edits, refactors, commits, PRs, and cleanup.

Rules:

- Do not commit directly to `main`.
- Do not commit directly to `develop` unless the user explicitly requests a direct develop hotfix.
- Use `develop` as the development default branch.
- Create a dedicated `feature/*` branch from `develop` for each module.
- Create a separate git worktree for that feature branch and perform implementation there.
- Open PRs to `develop` by default.
- Treat PRs to `main` as release/version PRs requiring extra caution and explicit user intent.
- After the PR is confirmed merged, remove the feature branch and worktree.

Required start report for mutating work:

```md
## Branch/worktree plan
- Base branch: develop
- Feature branch:
- Worktree path:
- Active module:
- PR target: develop
```

## Modular execution rule

- Execute only **one roadmap module at a time**.
- Use the module IDs from the roadmap, such as `M1-1`, `M1-2`, `M2-1`, etc.
- Do not proceed to the next module until:
  1. the current module's completion criteria are satisfied,
  2. verification evidence is reported,
  3. the user has had a chance to discuss/accept the implementation.

## Required module start format

Before implementing any module, state:

```md
## Current module
- Module ID:
- Goal:
- Files in scope:
- Files out of scope:
- Completion criteria:
- Verification method:
- Next-module gate:
```

## Scope control

- Do not implement beyond `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md` unless the user explicitly changes the plan.
- Do not bundle multiple modules into one implementation pass.
- If a new idea appears, write it as backlog/follow-up instead of implementing it immediately.
- Prefer small, reversible, easy-to-review changes.

## Current project objective

The immediate goal is **not** chatbot answer-quality improvement alone.

The goal is to build a measurement and monitoring system that can compare:

- the currently implemented Agent/RAG/LLM system,
- future improved versions of that system,
- chatbot security behavior under Goldenset tests,
- code security behavior under PR/commit review automation.

Portfolio value requires **numbers**. When relevant to the active module, preserve or produce metrics such as:

- retrieval quality and result counts,
- latency and node timings,
- pass/fail rates,
- guardrail/security finding rates,
- fallback rates,
- model/provider usage,
- before/after regression comparisons.
