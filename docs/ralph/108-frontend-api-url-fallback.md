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
- [ ] PR merged
- [ ] EC2 deployed
- [ ] Production verified

### Verification Checklist
1. [x] 로컬 빌드: `VITE_API_BASE_URL="" npm run build` - **PASSED** (2026-02-04)
2. [x] 빌드 결과 확인: `grep -o 'localhost:8000' dist/assets/*.js` → **결과 없음 (0 matches)**
3. [ ] EC2 배포 후 브라우저 테스트
4. [ ] Network 탭에서 상대 경로 요청 확인

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

## Notes for Future Loops
- 이 문서를 검토하여 동일한 수정을 반복하지 않도록 함
- PR #109 머지 및 배포 상태 업데이트 필요
- **backend-test 실패는 clarify 노드 관련 - 별도 Issue 필요**
