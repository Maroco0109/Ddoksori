# PR-T4 Review: API 에러 응답/스트리밍 스키마 동기화

**작성일**: 2026-01-23  
**검토 대상 문서**: `docs/plans/260123/test-improvement-plan.md` 의 PR-T4 섹션  
**목표(원문)**: API 에러 응답 형식 변경에 따른 테스트 불일치 해소 (4개 fail)

---

## 1) 현재 코드베이스 적합성 검토

### A. `/chat/stream` Content-Type 기대값 수정

- **코드베이스 현황**: `backend/app/main.py` 의 `/chat/stream`은 `StreamingResponse(..., media_type="text/event-stream")` 로 구현되어 있음.
- **원 계획**: 테스트에서 `text/plain` 기대 → `text/event-stream`으로 수정.
- **판정**: ✅ 매우 적합
  - 현재 구현은 “SSE 스트리밍”으로 설계되어 있고, Content-Type도 명확히 `text/event-stream`을 반환함.
  - 테스트 기대값이 outdated인 상태.

### B. “Validation Error 422 vs 500” 원인 가설

- **원 계획**: `get_retriever` 의존성이 validation 전에 실행되어 `422`가 `500`으로 바뀐다고 서술.
- **코드베이스 관찰**:
  - `/search`는 `request: SearchRequest`로 body validation이 선행되어야 하며, validation 실패 시 FastAPI가 `422`를 반환하는 것이 일반 동작.
  - 현재 테스트(`backend/scripts/testing/api/test_api_error_handling.py`)도 `/search` 입력 검증에서 `422`만 확인.
- **판정**: ⚠️ “가능성은 있으나, 현 코드/테스트만 보면 근거가 약함”
  - 실제로 `422→500`이 발생하려면, (a) 서버가 validation 전에 외부 의존성을 수행하거나, (b) 테스트가 “validation 실패 케이스”가 아니라 “정상 schema + 내부 예외 케이스”를 보고 있어야 함.
  - 현재 repo의 API 테스트 파일 구성상(PR-T1에서 DB seed를 넣고, API는 httpx로 외부 서버 호출), PR-T4의 핵심 이슈는 **Content-Type 불일치 1건**일 가능성이 높음.

### C. “에러 응답 검증 완화”의 적합성

- **원 계획**: `test_api_error_handling.py`에서 메시지 문자열 대신 필드 존재 여부로 검증 완화.
- **코드베이스 현황**: `backend/scripts/testing/api/test_api_error_handling.py`는 현재 “메시지 문자열 비교”를 하지 않음(상태코드 중심).
- **판정**: ⚠️ 현재 테스트 코드 기준으로는 ‘불필요하거나 다른 파일에 대한 계획’일 가능성이 큼.

---

## 2) 테스트 계획 적합성 검토

### A. `/chat/stream` 테스트 수정 범위

- **원 계획**: `test_api_endpoints.py`에서 `text/plain` → `text/event-stream`으로 수정.
- **현재 테스트 코드**: `backend/scripts/testing/api/test_api_endpoints.py` 의 `test_chat_stream_endpoint`가 실제로 `text/plain`을 기대함.
- **판정**: ✅ 적합
  - 단순히 Content-Type만 맞추면 “테스트 실패 1건”은 바로 해소될 가능성이 큼.

### B. SSE 테스트의 안정성(추가 권장)

현재 테스트는 “chunk를 5개 읽는다” 정도만 검증함. SSE 특성상 다음을 추가/조정하면 flakiness를 줄일 수 있음:

- `Content-Type` 검증을 `"text/event-stream" in header` 형태로 유지 (charset 포함 대비)
- 첫 몇 개 chunk 중 **`data:` 라인이 실제로 오는지**만 가볍게 확인(구조 검증은 과도하게 하면 flaky).

### C. “422 vs 500” 검증 계획

원 계획의 422/500 문제는 실제 재현 확인이 먼저 필요함.

- 권장 확인 커맨드(서버가 떠 있는 상태에서):
  - `conda run -n dsr pytest backend/scripts/testing/api/test_api_error_handling.py -v`
  - 만약 여기서 `422`가 아닌 `500`이 나오면, 그때 “validation 이전 의존성 실행”을 구체적으로 추적하는 게 맞음.

---

## 결론 및 수정 권장안(Updated PR-T4 Plan)

### 목표(현실화)

- **1차 목표**: `/chat/stream` Content-Type 테스트 기대값을 `text/event-stream`으로 동기화하여 fail 해소.
- **2차 목표(조건부)**: 실제로 `422→500` 문제가 재현될 때만, retriever 초기화/의존성 실행 순서 개선을 수행.

### 작업 항목(권장)

1. `backend/scripts/testing/api/test_api_endpoints.py`
   - `test_chat_stream_endpoint`에서 `"text/plain"` 기대를 `"text/event-stream"`으로 변경.
2. (선택) `backend/scripts/testing/api/test_api_endpoints.py`
   - SSE body chunk 중 `data:` 프리픽스 존재 여부 정도의 최소 검증 추가.
3. (조건부) `backend/app/main.py`
   - `422→500`가 실제 재현되는 경우에만: dependency/init 동작 순서 문제를 재현 케이스 기준으로 수정.

### 완료 기준(권장)

- `pytest backend/scripts/testing/api/test_api_endpoints.py -v`에서 `/chat/stream` 관련 fail 해소.
- `pytest backend/scripts/testing/api/test_api_error_handling.py -v`가 안정적으로 `422`를 반환(환경에 따라 DB/API 서버 가용성은 별도 전제).

---

## Notes

- 이 PR은 “API 설계 변경”이 아니라 “테스트 기대값 동기화” 성격이 강함.
- `test-improvement-plan.md`에 기재된 PR-T4의 일부 항목(특히 422→500, 에러 응답 문자열 검증 완화)은, 현재 코드/테스트 스냅샷만 보면 **과대 범위**일 가능성이 있어, **실제 fail 로그 기반으로 범위를 재조정**하는 것이 안전함.
