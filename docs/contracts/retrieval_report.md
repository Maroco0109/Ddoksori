# RetrievalReport_v2 스키마

Retrieval Agent가 Orchestrator에게 반환하는 검색 결과 리포트입니다.

## 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `relevance` | `float` | X | 전체 관련성 점수 (0.0 ~ 1.0) |
| `coverage` | `list[SlotStatus]` | X | 필수 슬롯 충족 상태 |
| `diversity` | `float` | X | 출처 다양성 점수 (0.0 ~ 1.0) |
| `marginal_gain` | `float` | X | 이전 라운드 대비 증분 |
| `total_chunks` | `int` | X | 반환된 청크 수 |
| `sources_distribution` | `dict[str, int]` | X | 출처별 청크 분포 |

## SlotStatus 하위 스키마

| 필드 | 타입 | 설명 |
|------|------|------|
| `slot_name` | `str` | 슬롯 이름 |
| `status` | `Literal` | `filled`, `partial`, `missing` |
| `evidence_chunk_ids` | `list[str]` | 근거 청크 ID 목록 |
| `confidence` | `float` | 충족 신뢰도 (0.0 ~ 1.0) |

## Sufficiency 판단 기준

Orchestrator는 RetrievalReport를 기반으로 다음을 결정합니다:

| 조건 | 결정 |
|------|------|
| `relevance >= 0.7` AND `모든 slot이 filled` | STOP (답변 생성) |
| `relevance >= 0.5` AND `marginal_gain < 0.1` | STOP (추가 검색 무의미) |
| `coverage에 missing 슬롯 존재` AND `rounds < budget` | CONTINUE (재검색) |
| `relevance < 0.3` | ASK_USER (추가 정보 요청) |

## 예시 Payload

### 충분한 근거 확보

```json
{
  "relevance": 0.82,
  "coverage": [
    {
      "slot_name": "purchase_item",
      "status": "filled",
      "evidence_chunk_ids": ["chunk_001", "chunk_002"],
      "confidence": 0.95
    },
    {
      "slot_name": "dispute_type",
      "status": "filled",
      "evidence_chunk_ids": ["chunk_003"],
      "confidence": 0.88
    }
  ],
  "diversity": 0.75,
  "marginal_gain": 0.15,
  "total_chunks": 8,
  "sources_distribution": {
    "dispute": 3,
    "counsel": 3,
    "law": 2
  }
}
```

### 근거 부족

```json
{
  "relevance": 0.35,
  "coverage": [
    {
      "slot_name": "purchase_item",
      "status": "partial",
      "evidence_chunk_ids": ["chunk_010"],
      "confidence": 0.45
    },
    {
      "slot_name": "dispute_type",
      "status": "missing",
      "evidence_chunk_ids": [],
      "confidence": 0.0
    }
  ],
  "diversity": 0.30,
  "marginal_gain": 0.05,
  "total_chunks": 2,
  "sources_distribution": {
    "counsel": 2
  }
}
```

## 검증

```python
from app.orchestrator import validate_retrieval_report_v2

data = {"relevance": 0.82, "coverage": [...], ...}
is_valid, errors = validate_retrieval_report_v2(data)
```
