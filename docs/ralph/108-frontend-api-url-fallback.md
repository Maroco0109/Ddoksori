# Ralph-Loop Report: Issue #108 - Frontend API URL Fallback

## Loop 1: Implementation

### Date
2026-02-04

### Issue
- **GitHub Issue**: #108
- **PR**: #109
- **Branch**: `fix/108-frontend-api-url-fallback`

### Problem Summary
프로덕션 환경에서 프론트엔드 채팅이 작동하지 않음. 브라우저가 `http://localhost:8000`으로 요청을 보냄.

### Root Cause
```javascript
// frontend/src/shared/api/client.ts:7
// frontend/src/features/chat/hooks/useStreamingChat.ts:16
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';
```

- `Dockerfile.prod`에서 `VITE_API_BASE_URL=""`으로 설정
- JavaScript `||` 연산자는 빈 문자열을 **falsy**로 처리
- 결과: fallback인 `http://localhost:8000` 사용

### Fix Applied
```javascript
// || → ?? (nullish coalescing)
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000';
```

### Files Modified
| File | Line | Change |
|------|------|--------|
| `frontend/src/shared/api/client.ts` | 7 | `\|\|` → `??` |
| `frontend/src/features/chat/hooks/useStreamingChat.ts` | 16 | `\|\|` → `??` |

### Status
- [x] Code changes committed
- [x] Branch pushed
- [x] PR #109 created (base: develop)
- [x] PR #109 merged to develop
- [x] PR #110 created (develop → main)
- [x] PR #110 merged to main
- [x] EC2 deployed
- [x] Production verified

### Verification Checklist
1. [x] 로컬 빌드: `VITE_API_BASE_URL="" npm run build` - **PASSED** (2026-02-04)
2. [x] 빌드 결과 확인: `grep -o 'localhost:8000' dist/assets/*.js` → **결과 없음 (0 matches)**
3. [x] EC2 배포: Deploy to Staging workflow **SUCCESS** (1m23s)
4. [x] 프로덕션 테스트: `https://ddoksori.duckdns.org/chat/stream` **SSE 정상 작동**

---

## Loop 2: CI Verification

### Date
2026-02-05

### CI Check Results
| Check | Status | Notes |
|-------|--------|-------|
| backend-test | **FAIL** | 기존 테스트 이슈 (우리 변경과 무관) |
| backend-lint | PASS | - |
| frontend-build | PASS | - |
| frontend-lint | PASS | - |
| claude-review | PENDING | 대기 중 |

### backend-test 실패 분석

**실패 원인**: `clarify` 노드가 최근 백엔드에 추가되었지만 테스트가 업데이트되지 않음

**실패 테스트 목록** (18개):
```
- test_fast_path.py::test_greeting_skips_retrieval
- test_fast_path.py::test_mode_classification (3개)
- test_selective_retrieval.py::test_query_analysis_has_retriever_types_field
- test_supervisor.py::TestSupervisorRuleBasedOrder (5개)
- test_supervisor.py::TestSupervisorTimeoutFallback
- test_supervisor.py::TestSupervisorErrorFallback
- test_supervisor.py::TestSupervisorJSONParseFallback (2개)
- test_supervisor.py::TestSupervisorLLMDecision (2개)
- test_mas_architecture.py::test_create_graph_v2 (노드 수 14→15)
- test_mock_scenarios.py::test_query_analysis_output_has_required_keys
```

**결론**:
- 이 실패들은 **프론트엔드 변경과 무관**
- 백엔드 `clarify` 노드 추가로 인한 기존 테스트 불일치
- 별도 Issue로 처리 권장

### 결정 필요 사항
1. backend-test 실패 무시하고 PR merge 진행?
2. 백엔드 테스트 수정 후 merge?
3. 실패 테스트 skip 처리 후 merge?

---

## Loop 3: Test Fixes & Final Deployment

### Date
2026-02-05

### Decision
사용자 선택: **테스트 수정** (clarify 노드 관련 18개 테스트 업데이트)

### Test Fixes Applied
| File | Changes |
|------|---------|
| `test_mas_architecture.py` | 노드 수 14→15, `clarify` 추가 |
| `test_supervisor.py` | `chat_type="general"` 사용하여 clarify 우회 |
| `test_fast_path.py` | 동일 |
| `test_selective_retrieval.py` | 동일 |
| `test_mock_scenarios.py` | 동일 |

### CI Results (Final)
| Check | PR #109 | PR #110 |
|-------|---------|---------|
| backend-lint | ✅ PASS | ✅ PASS |
| backend-test | ✅ PASS | ✅ PASS |
| frontend-build | ✅ PASS | ✅ PASS |
| frontend-lint | ✅ PASS | ✅ PASS |
| claude-review | ✅ PASS (LGTM) | ✅ PASS |

### Claude Review Summary
- **결과**: LGTM (Approve)
- **점수**: 4.3/5
- **긍정적**: 버그 수정 정확, 보안 취약점 없음, 코드 품질 우수
- **제안**: 프론트엔드 테스트 추가 (Follow-up)

### Deployment Verification
```bash
# Workflow Results
Build and Push: SUCCESS (1m13s)
Lint: SUCCESS (19s)
Test: SUCCESS (2m54s)
Deploy to Staging: SUCCESS (1m23s)

# Production Test
curl -X POST "https://ddoksori.duckdns.org/chat/stream" \
  -H "Content-Type: application/json" \
  -d '{"message": "안녕하세요", "chat_type": "general"}'

# Response: SSE stream working ✅
# Answer: "안녕하세요! 저는 소비자 분쟁 상담을 도와드리는 똑소리입니다..."
```

### Final Status
- **Issue #108**: CLOSED (main merge 시 자동 종료)
- **PR #109**: MERGED to develop
- **PR #110**: MERGED to main
- **Production**: ✅ VERIFIED

---

## Notes for Future Loops
- ✅ 이슈 완료 - 동일 수정 불필요
- clarify 노드 관련 테스트 업데이트 완료
- github-workflow 스킬 업데이트됨 (CI 자동 검증 기반)
