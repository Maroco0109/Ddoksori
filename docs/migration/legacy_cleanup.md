# 레거시 코드 정리 가이드

Sprint 5 완료 후 기존 스키마를 `_v2` 스키마로 대체하는 마이그레이션 가이드입니다.

## 마이그레이션 일정

| 단계 | 시점 | 작업 |
|------|------|------|
| 1 | Sprint 0 | `_v2` 스키마 추가, 기존 스키마 유지 |
| 2 | Sprint 1-5 | `_v2` 스키마 점진적 적용 |
| 3 | Sprint 5 완료 | 기존 스키마 deprecated 마킹 |
| 4 | Sprint 5+1주 | 기존 스키마 삭제, `_v2` 접미사 제거 |

## 대상 스키마

| 기존 스키마 | 새 스키마 (_v2) | 최종 이름 |
|-------------|-----------------|-----------|
| `QueryAnalysisResult` | `QueryAnalysisResult_v2` | `QueryAnalysisResult` |
| `RetrievalResult` | `RetrievalReport_v2` | `RetrievalReport` |
| `ReviewResult` | `ReviewReport_v2` | `ReviewReport` |
| `ChatState` | `ChatState_v2` | `ChatState` |

## 단계별 마이그레이션

### 단계 1: Deprecated 마킹 (Sprint 5 완료 시)

```python
# backend/app/orchestrator/state.py

import warnings
from typing import TypedDict

class QueryAnalysisResult(TypedDict, total=False):
    """
    @deprecated: QueryAnalysisResult_v2를 사용하세요.
    Sprint 6에서 삭제 예정.
    """
    def __init_subclass__(cls, **kwargs):
        warnings.warn(
            "QueryAnalysisResult is deprecated. Use QueryAnalysisResult_v2.",
            DeprecationWarning,
            stacklevel=2
        )
        super().__init_subclass__(**kwargs)
    
    # ... 기존 필드 ...
```

### 단계 2: 사용처 업데이트

#### state.py 참조 업데이트

```bash
# 변경 대상 파일 찾기
grep -r "QueryAnalysisResult[^_]" backend/app --include="*.py"
grep -r "RetrievalResult" backend/app --include="*.py"
grep -r "ReviewResult" backend/app --include="*.py"
```

#### 주요 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `agents/query_analysis/agent.py` | `QueryAnalysisResult` → `QueryAnalysisResult_v2` |
| `agents/retrieval/agent.py` | `RetrievalResult` → `RetrievalReport_v2` |
| `agents/legal_review/agent.py` | `ReviewResult` → `ReviewReport_v2` |
| `orchestrator/graph.py` | 라우팅 함수 타입 힌트 업데이트 |

### 단계 3: 스키마 이름 변경

```python
# backend/app/orchestrator/state.py

# 삭제 (기존 스키마)
# class QueryAnalysisResult(TypedDict, total=False): ...
# class RetrievalResult(TypedDict, total=False): ...
# class ReviewResult(TypedDict, total=False): ...

# 이름 변경
QueryAnalysisResult = QueryAnalysisResult_v2
RetrievalReport = RetrievalReport_v2  # 이름도 변경
ReviewReport = ReviewReport_v2

# 또는 직접 클래스 정의 변경
class QueryAnalysisResult(TypedDict, total=False):
    # QueryAnalysisResult_v2의 필드 복사
    mode: RoutingMode
    draft: Optional[str]
    # ...
```

### 단계 4: Export 업데이트

```python
# backend/app/orchestrator/__init__.py

from .state import (
    # 최종 스키마 (접미사 제거)
    QueryAnalysisResult,
    SearchPlan,
    RetrievalReport,
    GenerationOutput,
    ReviewReport,
    ChatState,
    # ...
)

__all__ = [
    'QueryAnalysisResult',
    'SearchPlan',
    'RetrievalReport',
    'GenerationOutput',
    'ReviewReport',
    'ChatState',
    # ...
]
```

## 검증 체크리스트

마이그레이션 완료 후 검증:

- [ ] 모든 테스트 통과 (`pytest`)
- [ ] API 엔드포인트 정상 동작
- [ ] 프론트엔드 연동 정상
- [ ] `_v2` 접미사가 코드에 없음
- [ ] deprecated 경고 없음
- [ ] LSP 에러 없음

## 롤백 계획

문제 발생 시 롤백 절차:

1. Git에서 마이그레이션 전 커밋으로 revert
2. 데이터베이스 스키마 변경이 있었다면 마이그레이션 롤백
3. 배포 롤백

```bash
# 마이그레이션 전 태그 생성 (마이그레이션 시작 전)
git tag pre-schema-migration

# 롤백
git revert --no-commit HEAD~N..HEAD  # N = 마이그레이션 커밋 수
# 또는
git checkout pre-schema-migration
```

## 관련 문서

- [스키마 계약 문서](/docs/contracts/README.md)
- [라우팅 정책](/docs/policies/routing.md)
- [루프 제한 정책](/docs/policies/loop_limits.md)
