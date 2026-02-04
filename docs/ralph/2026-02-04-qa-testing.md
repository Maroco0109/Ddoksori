# Ralph-Loop QA Testing Report

**Date**: 2026-02-04
**Test Target**: `https://ddoksori.duckdns.org`
**Branch**: `main` (develop synced)

---

## Summary

| Issue ID | Description | Status | PRs |
|----------|-------------|--------|-----|
| P1-1 | retrieval_law NoneType error | FIXED | Multiple commits |
| P1-2 | retrieval_criteria NoneType error | FIXED | Multiple commits |
| P2-1 | clarifying_questions not provided for short queries | FIXED | Multiple commits |
| P2-2 | followup_questions always empty | FIXED | PR #105 |
| P2-3 | domain field null | FIXED | Previous session |

---

## Issues Found and Fixes

### P1: Retrieval Agent Errors

#### Root Causes
1. **metadata or None bug**: `metadata=metadata or None` converted empty dict `{}` to `None`
2. **Missing attribute**: Retriever classes didn't save `embed_api_url` parameter to `self`
3. **Missing data file**: `Dockerfile.prod` didn't copy `data/` directory

#### Fixes Applied
1. `specialized_retrievers.py`: Changed `metadata=metadata or None` to `metadata=metadata`
2. `specialized_retrievers.py`: Added `self.embed_api_url = embed_api_url` to LawRetriever, CriteriaRetriever, CaseRetriever
3. `Dockerfile.prod`: Added `COPY data/ ./data/`

### P2-1: clarifying_questions Not Provided

#### Root Causes (Multiple)
1. MAS graph didn't have `clarify` node wired
2. `ChatState` schema missing `clarifying_questions` field
3. `KNOWN_GRAPH_NODES` in `chat.py` didn't include `clarify`

#### Fixes Applied
1. `graph_mas.py`: Added clarify node + routing
2. `supervisor.py`: Added programmatic check for short queries (≤5 chars)
3. `state/__init__.py`: Added `clarifying_questions: List[str]` field
4. `chat.py`: Added "clarify" to `KNOWN_GRAPH_NODES`

### P2-2: followup_questions Empty

#### Root Cause
Cache response path in `generation_node_v2` had hardcoded `followup_questions: []`

#### Fix Applied
Added `FollowupQuestionGenerator` call in cache path (agent.py)

---

## Test Results

### Short Query Test (`"환불"`)
```json
{
  "answer": "더 정확한 답변을 드리기 위해 몇 가지 여쭤볼게요:\n1. ...",
  "clarifying_questions": [
    "어떤 제품/서비스에 대한 문의인지 알려주시겠어요?",
    "어떤 문제가 발생했는지 자세히 알려주시겠어요?"
  ]
}
```
**Result**: PASS

### Normal Query Test (노트북 불량 환불)
```json
{
  "followup_questions": [3 questions generated],
  "clarifying_questions": [],
  "answer_len": 608
}
```
**Result**: PASS (followup works, clarifying correctly empty)

### Retrieval Agent Test
```
retrieval_law: PASS - 10 docs, max_sim=0.066
retrieval_criteria: PASS - 10 docs, max_sim=0.077
retrieval_case: PASS - 10 docs, max_sim=0.679
```
**Result**: PASS (all agents working)

---

## Files Modified

| File | Changes |
|------|---------|
| `backend/app/supervisor/graph_mas.py` | Added clarify node + routing |
| `backend/app/supervisor/nodes/supervisor.py` | Added short query check + prompt update |
| `backend/app/supervisor/state/__init__.py` | Added clarifying_questions field |
| `backend/app/api/chat.py` | Added clarify to KNOWN_GRAPH_NODES |
| `backend/app/agents/answer_generation/agent.py` | Added followup generation to cache path |
| `backend/app/agents/retrieval/tools/specialized_retrievers.py` | Fixed embed_api_url attribute |
| `backend/Dockerfile.prod` | Added COPY data/ directive |

---

## Final Verification

All issues resolved. Final test results:

| Feature | Status | Details |
|---------|--------|---------|
| clarifying_questions | PASS | ["어떤 제품/서비스에 대한 문의인지...", "어떤 문제가 발생했는지..."] |
| followup_questions | PASS | 3 questions generated |
| retrieval_law | PASS | 10 docs, no errors |
| retrieval_criteria | PASS | 10 docs, no errors |
| retrieval_case | PASS | 10 docs, max_sim=0.679 |

---

## Commits Made

1. `fix: wire clarify node to MAS graph for short query handling`
2. `fix: add clarifying_questions to ChatState schema`
3. `fix: add clarify node to KNOWN_GRAPH_NODES for SSE streaming`
4. `fix: add missing embed_api_url attribute and data directory copy`
5. `fix: remove embed_api_url from RDSInternalRetriever calls`
