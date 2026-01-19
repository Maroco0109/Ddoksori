# ReviewReport_v2 스키마

Review Agent가 답변을 검토한 결과입니다.

## 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `passed` | `bool` | X | 검토 통과 여부 |
| `issues` | `list[str]` | X | 발견된 문제 목록 |
| `required_more_evidence` | `bool` | X | 추가 근거 필요 여부 |
| `requested_slots` | `list[str]` | X | 요청하는 추가 슬롯 |
| `violation_details` | `list[dict]` | X | 위반 상세 정보 |

## 검토 규칙

| 규칙 ID | 설명 | 심각도 |
|---------|------|--------|
| `R001` | 절대적 표현 사용 금지 ("반드시", "무조건") | HIGH |
| `R002` | 법적 단정 표현 금지 ("위법입니다", "승소합니다") | CRITICAL |
| `R003` | 근거 없는 주장 금지 | HIGH |
| `R004` | 출처 누락 금지 | MEDIUM |
| `R005` | 예측 표현 금지 ("~할 것입니다") | MEDIUM |
| `R006` | 개인정보 노출 금지 | CRITICAL |

## Violation Detail 구조

```json
{
  "rule_id": "R001",
  "severity": "HIGH",
  "location": "paragraph 2, sentence 1",
  "original_text": "반드시 환불받을 수 있습니다",
  "suggestion": "환불받을 가능성이 높습니다"
}
```

## 예시 Payload

### 검토 통과

```json
{
  "passed": true,
  "issues": [],
  "required_more_evidence": false,
  "requested_slots": [],
  "violation_details": []
}
```

### 검토 실패 (위반 발견)

```json
{
  "passed": false,
  "issues": [
    "절대적 표현 사용: '반드시'",
    "법적 단정: '위법입니다'"
  ],
  "required_more_evidence": false,
  "requested_slots": [],
  "violation_details": [
    {
      "rule_id": "R001",
      "severity": "HIGH",
      "location": "paragraph 1",
      "original_text": "반드시 환불받을 수 있습니다",
      "suggestion": "환불받을 가능성이 높습니다"
    },
    {
      "rule_id": "R002",
      "severity": "CRITICAL",
      "location": "paragraph 3",
      "original_text": "이는 위법입니다",
      "suggestion": "이는 법률 위반에 해당할 수 있습니다"
    }
  ]
}
```

### 검토 실패 (근거 부족)

```json
{
  "passed": false,
  "issues": [
    "근거 없는 주장: 환불 기간에 대한 출처 없음"
  ],
  "required_more_evidence": true,
  "requested_slots": ["refund_period_evidence", "law_article"],
  "violation_details": [
    {
      "rule_id": "R003",
      "severity": "HIGH",
      "location": "paragraph 2",
      "original_text": "환불 기간은 30일입니다",
      "suggestion": "관련 법령 또는 분쟁조정기준 인용 필요"
    }
  ]
}
```

## Orchestrator 후속 처리

| 조건 | 결정 |
|------|------|
| `passed == true` | 최종 답변 확정 → User |
| `passed == false` AND `retry_count < 2` | Generator 재호출 (수정 요청) |
| `passed == false` AND `required_more_evidence` | Retriever 재호출 |
| `passed == false` AND `retry_count >= 2` | 안전 답변으로 대체 |

## 검증

```python
from app.orchestrator import validate_review_report_v2

data = {"passed": false, "issues": [...], ...}
is_valid, errors = validate_review_report_v2(data)
```
