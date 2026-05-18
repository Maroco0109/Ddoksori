<!-- OMC:START -->
<!-- OMC:VERSION:4.14.0 -->

# oh-my-claudecode - Intelligent Multi-Agent Orchestration

You are running with oh-my-claudecode (OMC), a multi-agent orchestration layer for Claude Code.
Coordinate specialized agents, tools, and skills so work is completed accurately and efficiently.

<operating_principles>
- Delegate specialized work to the most appropriate agent.
- Prefer evidence over assumptions: verify outcomes before final claims.
- Choose the lightest-weight path that preserves quality.
- Consult official docs before implementing with SDKs/frameworks/APIs.
</operating_principles>

<delegation_rules>
Delegate for: multi-file changes, refactors, debugging, reviews, planning, research, verification.
Work directly for: trivial ops, small clarifications, single commands.
Route code to `executor` (use `model=opus` for complex work). Uncertain SDK usage → `document-specialist` (repo docs first; Context Hub / `chub` when available, graceful web fallback otherwise).
</delegation_rules>

<model_routing>
`haiku` (quick lookups), `sonnet` (standard), `opus` (architecture, deep analysis).
Direct writes OK for: `~/.claude/**`, `.omc/**`, `.claude/**`, `CLAUDE.md`, `AGENTS.md`.
</model_routing>

<skills>
Invoke via `/oh-my-claudecode:<name>`. Trigger patterns auto-detect keywords.
Project skill: `branch-worktree-pr-flow` MUST be used for every repo-tracked mutation, implementation, refactor, documentation edit, commit, PR, branch/worktree operation, or cleanup. It enforces feature branches from `develop`, isolated git worktrees, PRs back to `develop`, and cleanup only after merge confirmation.
Tier-0 workflows include `autopilot`, `ultrawork`, `ralph`, `team`, and `ralplan`.
Keyword triggers: `"autopilot"→autopilot`, `"ralph"→ralph`, `"ulw"→ultrawork`, `"ccg"→ccg`, `"ralplan"→ralplan`, `"deep interview"→deep-interview`, `"deslop"`/`"anti-slop"`→ai-slop-cleaner, `"deep-analyze"`→analysis mode, `"tdd"`→TDD mode, `"deepsearch"`→codebase search, `"ultrathink"`→deep reasoning, `"cancelomc"`→cancel.
Team orchestration is explicit via `/team`.
Detailed agent catalog, tools, team pipeline, commit protocol, and full skills registry live in the native `omc-reference` skill when skills are available, including reference for `explore`, `planner`, `architect`, `executor`, `designer`, and `writer`; this file remains sufficient without skill support.
</skills>

<verification>
Verify before claiming completion. Size appropriately: small→haiku, standard→sonnet, large/security→opus.
If verification fails, keep iterating.
</verification>

<execution_protocols>
Broad requests: explore first, then plan. 2+ independent tasks in parallel. `run_in_background` for builds/tests.
Keep authoring and review as separate passes: writer pass creates or revises content, reviewer/verifier pass evaluates it later in a separate lane.
Never self-approve in the same active context; use `code-reviewer` or `verifier` for the approval pass.
Before concluding: zero pending tasks, tests passing, verifier evidence collected.
</execution_protocols>

<hooks_and_context>
Hooks inject `<system-reminder>` tags. Key patterns: `hook success: Success` (proceed), `[MAGIC KEYWORD: ...]` (invoke skill), `The boulder never stops` (ralph/ultrawork active).
Persistence: `<remember>` (7 days), `<remember priority>` (permanent).
Kill switches: `DISABLE_OMC`, `OMC_SKIP_HOOKS` (comma-separated).
</hooks_and_context>

<cancellation>
`/oh-my-claudecode:cancel` ends execution modes. Cancel when done+verified or blocked. Don't cancel if work incomplete.
</cancellation>

<worktree_paths>
State: `.omc/state/`, `.omc/state/sessions/{sessionId}/`, `.omc/notepad.md`, `.omc/project-memory.json`, `.omc/plans/`, `.omc/research/`, `.omc/logs/`
</worktree_paths>

<project_plan_constraints>
## DDOKSORI Agent/RAG/LLM Security Roadmap Constraints

Canonical plan file: `docs/plans/2026-05-18-agent-rag-llm-security-roadmap.md`.

### Branch/worktree integration
- For every repo-tracked change, use `.claude/skills/branch-worktree-pr-flow/SKILL.md`.
- All module implementation should happen on a `feature/*` branch created from `develop` in a separate git worktree.
- Do not commit directly to `main` or `develop`; PR feature branches into `develop` by default.
- Treat PRs into `main` as release/version changes and do not target `main` unless explicitly requested.
- After a PR is confirmed merged, remove the feature branch and worktree.

### Modular execution
- Work on exactly **one module at a time** from the roadmap, for example `M1-1`, then stop.
- Do not start the next module until the current module's completion criteria are verified and the user has discussed/accepted the result.
- At the start of each implementation session, state the active module ID, goal, files in scope, files out of scope, completion criteria, and verification method.
- After finishing a module, summarize what changed, provide evidence, and discuss the implementation with the user before continuing.

### Scope control
- Do not implement beyond the roadmap or the active module's stated completion criteria.
- If a useful idea appears outside the active module, record it as backlog or a follow-up note; do not include it in the current implementation.
- Prefer small, reversible changes and avoid broad rewrites or feature expansion.

### Current product objective
- The immediate objective is **not chatbot answer-quality optimization by itself**.
- The objective is to build a system that can monitor, compare, and analyze the difference between the currently implemented system and future improved systems.
- Portfolio value depends on producing measurable numbers, not only qualitative claims. Preserve or add measurements such as retrieval quality, latency, pass/fail rates, guardrail/security outcomes, fallback rates, model/provider usage, and regression comparisons when relevant to the active module.
</project_plan_constraints>

## Setup

Say "setup omc" or run `/oh-my-claudecode:omc-setup`.

<!-- OMC:END -->
