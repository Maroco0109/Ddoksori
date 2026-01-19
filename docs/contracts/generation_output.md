# GenerationOutput 스키마

Generation Agent가 생성한 답변 출력입니다.

## 필드 정의

| 필드 | 타입 | 필수 | 설명 |
|------|------|------|------|
| `final_answer` | `str` | X | 사용자에게 표시할 최종 답변 |
| `claim_evidence_map` | `list[ClaimEvidenceMapping]` | X | 주장-근거 매핑 (Reviewer용) |
| `assumptions` | `list[str]` | X | 답변 생성 시 가정한 내용 |
| `citations` | `list[dict]` | X | 인용 출처 목록 |

## ClaimEvidenceMapping 하위 스키마

| 필드 | 타입 | 설명 |
|------|------|------|
| `claim` | `str` | 답변 내 주장 문장 |
| `evidence_chunk_ids` | `list[str]` | 근거 청크 ID 목록 |
| `evidence_texts` | `list[str]` | 근거 텍스트 발췌 |
| `grounded` | `bool` | 근거 충분 여부 |

## Citation 구조

```json
{
  "index": 1,
  "source_type": "dispute",
  "source_id": "doc_12345",
  "title": "노트북 불량 환불 사례",
  "snippet": "소비자가 구매 후 7일 이내...",
  "url": "https://..."
}
```

## 예시 Payload

### 근거 기반 답변

```json
{
  "final_answer": "## 기관 추천\n\n한국소비자원(KCA)에 분쟁조정을 신청하시는 것이 적합합니다.\n\n**이유**: 사업자와 소비자 간 전자제품 하자 분쟁은 KCA의 주요 처리 영역입니다 [1].\n\n## 유사 사례\n\n1. **노트북 화면 불량 환불 사례** [2]: 구매 후 14일 이내 화면 결함 발생, 전액 환불 결정\n\n## 법적 근거\n\n- 전자상거래법 제17조 (청약철회) [3]\n\n## 다음 행동\n\n1. 구매 영수증 및 불량 증거 사진 준비\n2. KCA 홈페이지에서 분쟁조정 신청",
  "claim_evidence_map": [
    {
      "claim": "사업자와 소비자 간 전자제품 하자 분쟁은 KCA의 주요 처리 영역입니다",
      "evidence_chunk_ids": ["chunk_001"],
      "evidence_texts": ["한국소비자원은 전자제품, 가전제품 관련 소비자 피해 구제를..."],
      "grounded": true
    },
    {
      "claim": "구매 후 14일 이내 화면 결함 발생, 전액 환불 결정",
      "evidence_chunk_ids": ["chunk_002", "chunk_003"],
      "evidence_texts": ["2023년 유사 사례에서 14일 이내 불량 발견 시...", "위원회는 전액 환불을 결정..."],
      "grounded": true
    }
  ],
  "assumptions": [
    "구매일로부터 14일 이내인 것으로 가정",
    "제품이 정상 사용 중 불량이 발생한 것으로 가정"
  ],
  "citations": [
    {
      "index": 1,
      "source_type": "counsel",
      "source_id": "counsel_5678",
      "title": "KCA 업무 범위 안내",
      "snippet": "한국소비자원은 전자제품, 가전제품 관련..."
    },
    {
      "index": 2,
      "source_type": "dispute",
      "source_id": "dispute_1234",
      "title": "노트북 화면 불량 환불 사례",
      "snippet": "2023년 유사 사례에서..."
    },
    {
      "index": 3,
      "source_type": "law",
      "source_id": "law_ecommerce_17",
      "title": "전자상거래법 제17조",
      "snippet": "소비자는 계약 체결일로부터 7일 이내..."
    }
  ]
}
```

## 검증

```python
from app.orchestrator import validate_generation_output

data = {"final_answer": "...", "claim_evidence_map": [...], ...}
is_valid, errors = validate_generation_output(data)
```
