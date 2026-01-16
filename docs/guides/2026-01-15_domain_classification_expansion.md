# 2026-01-15 도메인 설정 세분화 (S2-4)

## 변경사항 요약

기존 3개 기관(KCA, ECMC, KCDRC)에 **금융분쟁조정(FSS)** 및 **의료분쟁조정(K-Medi)** 도메인을 추가하고, 해당 도메인에 대해서는 **전문가 상담 권유** 모드로 제한된 답변을 제공합니다.

---

## 1. 신규 기관 추가

| 기관 코드 | 기관명 | 분쟁 유형 | 제한 모드 |
|-----------|--------|-----------|-----------|
| `FSS` | 금융감독원 금융분쟁조정위원회 | 보험, 은행, 증권, 카드 등 | O |
| `K_MEDI` | 한국의료분쟁조정중재원 | 의료사고, 진료비 등 | O |
| `KCA` | 한국소비자원 | 일반 소비자 분쟁 | X |
| `ECMC` | 전자거래분쟁조정위원회 | 개인간 거래 | X |
| `KCDRC` | 콘텐츠분쟁조정위원회 | 게임, 영화, 음악 등 | X |

---

## 2. 파일 구조

### 2.1 신규 파일 (Backend)

```
backend/app/domain/
├── __init__.py          # 모듈 export
├── config.py            # 기관 정보, 키워드 상수
└── classifier.py        # 도메인 분류 로직

backend/scripts/testing/domain/
├── __init__.py
├── golden_set.py        # 50개 테스트 케이스
└── test_domain_classification.py  # 분류 정확도 테스트
```

### 2.2 수정 파일

| 파일 | 변경 내용 |
|------|----------|
| `backend/app/orchestrator/nodes/generation.py` | 제한 모드 응답 분기 추가 |
| `frontend/src/shared/types/chat.types.ts` | `AgencyInfo`, `is_restricted` 타입 추가 |
| `frontend/src/features/chat/components/MessageBubble.tsx` | 제한 모드 UI 컴포넌트 |
| `frontend/src/features/chat/ChatPage.tsx` | 제한 모드 응답 처리 |

---

## 3. 핵심 코드

### 3.1 기관 정보 설정 (`config.py`)

```python
AGENCY_INFO: Dict[AgencyCode, AgencyInfoDict] = {
    'FSS': {
        'name': '금융감독원',
        'full_name': '금융감독원 금융분쟁조정위원회',
        'description': '금융 관련 분쟁 조정 (보험, 은행, 증권, 카드 등)',
        'url': 'https://www.fss.or.kr',
        'is_restricted': True,
        'restriction_reason': '금융 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
    'K_MEDI': {
        'name': '한국의료분쟁조정중재원',
        'full_name': '한국의료분쟁조정중재원',
        'description': '의료 관련 분쟁 조정 (의료사고, 진료비 등)',
        'url': 'https://www.k-medi.or.kr',
        'is_restricted': True,
        'restriction_reason': '의료 분쟁은 복잡하고 전문적인 영역으로, 전문가 상담 후 진행을 권장합니다.',
    },
    # ... 기존 KCA, ECMC, KCDRC
}
```

### 3.2 키워드 기반 분류 (`classifier.py`)

```python
FINANCE_KEYWORDS = [
    "보험", "대출", "적금", "예금", "펀드", "주식", "증권",
    "카드", "신용카드", "리볼빙", "이자", "금리", "보험금", ...
]

MEDICAL_KEYWORDS = [
    "수술", "진료", "치료", "입원", "오진", "의료사고",
    "병원", "의원", "의료비", "진료비", "합병증", ...
]

class DomainClassifier:
    FINANCE_THRESHOLD = 2   # 금융 키워드 2개 이상
    MEDICAL_THRESHOLD = 2   # 의료 키워드 2개 이상
    
    def classify(self, query: str) -> ClassificationResult:
        # 우선순위: FSS > K_MEDI > KCDRC > ECMC > KCA
        ...
```

### 3.3 제한 모드 응답 생성 (`generation.py`)

```python
def generation_node(state: ChatState) -> Dict:
    classification = classify_domain(user_query)
    
    if classification.is_restricted:
        return _build_restricted_response(user_query, classification, retrieval)
    
    # 기존 RAG 응답 생성 로직
    ...

def _build_restricted_response(...) -> Dict:
    return {
        'draft_answer': RESTRICTED_RESPONSE_TEMPLATE.format(...),
        'final_answer': answer,
        'is_restricted': True,
        'agency_code': agency_code,
    }
```

### 3.4 Frontend 제한 모드 UI (`MessageBubble.tsx`)

```tsx
if (isAI && isRestricted && message.agencyInfo) {
  return (
    <div className="border-2 border-amber-400 shadow-lg">
      <div className="bg-amber-50 flex items-center gap-2">
        <AlertTriangle className="text-amber-600" />
        <span>전문가 상담이 필요한 영역입니다</span>
      </div>
      
      <div className="bg-white">
        <p>{message.agencyInfo.full_name}</p>
        <a href={message.agencyInfo.url}>공식 웹사이트 방문</a>
        <MarkdownRenderer content={message.content} />
      </div>
    </div>
  );
}
```

---

## 4. 분류 정확도 테스트

### 4.1 Golden Set 구성

| 기관 | 테스트 케이스 수 |
|------|------------------|
| FSS | 12개 |
| K_MEDI | 12개 |
| KCDRC | 8개 |
| ECMC | 6개 |
| KCA | 12개 |
| **총합** | **50개** |

### 4.2 테스트 결과

```
======================================================================
DOMAIN CLASSIFICATION ACCURACY REPORT
======================================================================

FSS (금융감독원) RESTRICTED
  Accuracy: 100.00% (12/12) [PASS]

K_MEDI (한국의료분쟁조정중재원) RESTRICTED
  Accuracy: 100.00% (12/12) [PASS]

KCDRC (콘텐츠분쟁조정위원회)
  Accuracy: 87.50% (7/8) [PASS]

ECMC (전자거래분쟁조정위원회)
  Accuracy: 100.00% (6/6) [PASS]

KCA (한국소비자원)
  Accuracy: 100.00% (12/12) [PASS]

----------------------------------------------------------------------
OVERALL: 98.00% (49/50)
======================================================================
```

### 4.3 테스트 실행 방법

```bash
cd backend
python scripts/testing/domain/test_domain_classification.py
```

---

## 5. API 응답 변경

### 5.1 ChatAPIResponse 확장

```typescript
interface ChatAPIResponse {
  session_id: string;
  answer: string;
  chunks_used: number;
  model: string;
  sources: SourceMetadata[];
  has_sufficient_evidence: boolean;
  clarifying_questions: string[];
  // S2-4 신규 필드
  is_restricted?: boolean;
  agency_code?: string;
  agency_info?: AgencyInfo;
}

interface AgencyInfo {
  name: string;
  full_name: string;
  description: string;
  url: string;
  is_restricted?: boolean;
  restriction_reason?: string;
}
```

### 5.2 제한 모드 응답 예시

```json
{
  "answer": "본 답변은 정보 제공 목적이며...\n\n## 주의: 전문가 상담이 필요한 영역입니다...",
  "is_restricted": true,
  "agency_code": "FSS",
  "agency_info": {
    "name": "금융감독원",
    "full_name": "금융감독원 금융분쟁조정위원회",
    "description": "금융 관련 분쟁 조정 (보험, 은행, 증권, 카드 등)",
    "url": "https://www.fss.or.kr",
    "is_restricted": true,
    "restriction_reason": "금융 분쟁은 복잡하고 전문적인 영역으로..."
  }
}
```

---

## 6. 기대 효과

### 6.1 사용자 경험 개선

| 항목 | 기대 효과 |
|------|----------|
| **적절한 기관 안내** | 금융/의료 분쟁 시 전문 기관으로 즉시 안내 |
| **리스크 감소** | 복잡한 전문 영역에 대해 부정확한 조언 방지 |
| **신뢰도 향상** | 서비스 한계를 명확히 고지하여 사용자 신뢰 확보 |

### 6.2 서비스 안정성

| 항목 | 기대 효과 |
|------|----------|
| **법적 리스크 감소** | 금융/의료 자문에 대한 면책 강화 |
| **명확한 책임 범위** | 정보 제공 vs 법률 자문의 경계 명확화 |
| **에스컬레이션 경로** | 전문가 상담 → 기관 신청 경로 제시 |

### 6.3 확장성

| 항목 | 기대 효과 |
|------|----------|
| **모듈화된 구조** | `domain/` 모듈로 기관 추가 용이 |
| **키워드 기반** | 새 도메인 추가 시 키워드만 정의하면 됨 |
| **테스트 자동화** | Golden Set으로 분류 정확도 지속 모니터링 |

---

## 7. 향후 개선 사항

1. **키워드 학습**: 사용자 피드백 기반 키워드 자동 학습
2. **LLM 분류 보조**: 키워드만으로 판단 어려운 경우 LLM 호출
3. **기관별 데이터 추가**: FSS/K-Medi 관련 사례 데이터 수집 시 RAG 연동
4. **사용자 피드백**: "분류가 잘못됐나요?" 피드백 버튼 추가

---

## 8. 관련 PR

| PR | 내용 | 상태 |
|----|------|------|
| S2-1 | 질의분석 에이전트 | 완료 |
| S2-2 | 검토 에이전트 | 완료 |
| S2-3 | 오케스트레이터 + 상태관리 | 완료 |
| **S2-4** | **도메인 설정 세분화** | **완료** |
| S2-5 | 기관별 가이드 생성 | 예정 |
| S2-6 | Backend 서버화/배포 | 예정 |
