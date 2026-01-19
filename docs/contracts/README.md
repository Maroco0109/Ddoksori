# 에이전트 I/O 계약 (Contracts)

이 디렉토리는 똑소리 MAS(Multi-Agent System)의 에이전트 간 통신 스키마를 정의합니다.

## 스키마 목록

| 스키마 | 용도 | 생산자 | 소비자 |
|--------|------|--------|--------|
| [QueryAnalysisResult_v2](./query_analysis.md) | 질의 분석 결과 | Query Analysis Agent | Orchestrator |
| [SearchPlan](./search_plan.md) | 검색 계획 | Orchestrator | Retrieval Agent |
| [RetrievalReport_v2](./retrieval_report.md) | 검색 결과 리포트 | Retrieval Agent | Orchestrator |
| [GenerationOutput](./generation_output.md) | 답변 생성 결과 | Generation Agent | Reviewer, User |
| [ReviewReport_v2](./review_report.md) | 검토 결과 | Review Agent | Orchestrator |

## 스키마 버전 관리

- `_v2` 접미사: Sprint 0에서 정의된 새 스키마
- 기존 스키마(접미사 없음): 호환성을 위해 유지
- Sprint 5 완료 후 기존 스키마를 `_v2`로 대체 예정

## 검증

모든 에이전트 출력은 `backend/app/orchestrator/validators.py`의 검증 함수로 검증됩니다.

```python
from app.orchestrator import validate_query_analysis_result_v2, get_validator

# 개별 검증
is_valid, errors = validate_query_analysis_result_v2(data)

# 일괄 검증
validator = get_validator(strict=True)
results = validator.validate_all_agent_outputs(
    query_analysis=qa_data,
    search_plan=sp_data,
)
```

## 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `STRICT_SCHEMA_VALIDATION` | `false` | `true`시 검증 실패 시 예외 발생 |
