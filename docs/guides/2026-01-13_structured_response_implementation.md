# 2026-01-13 LLM 응답 구조화 개선 구현

## 변경사항 요약

- **4섹션 구조화 응답 시스템 구현**
- **전문 검색기(Specialized Retrievers) 추가**
- **criteria 데이터 DB 적재 완료**

---

## 1. 구현 배경

소비자 분쟁 조정 RAG 챗봇의 응답을 4개 섹션으로 구조화하여 사용자에게 더 명확하고 체계적인 정보를 제공하기 위함.

## 2. 4섹션 응답 구조

```
┌─────────────────────────────────────────────────────────┐
│ 섹션 1: 추천 기관 (Domain)                              │
│   - KCA (한국소비자원): 일반 소비자-기업 분쟁           │
│   - ECMC (전자거래분쟁조정위원회): 개인간 거래          │
│   - KCDRC (콘텐츠분쟁조정위원회): 게임/영화/앱 등       │
├─────────────────────────────────────────────────────────┤
│ 섹션 2: 유사 사례 (Similar Cases)                       │
│   - 분쟁조정사례 (법적 효력 있음)                       │
│   - 상담사례 (참고용)                                   │
├─────────────────────────────────────────────────────────┤
│ 섹션 3: 관련 법령 (Related Laws)                        │
│   - 2단계 검색: 항/호/목 → 상위 조문                    │
│   - 법령명 + 조항 경로 표시                             │
├─────────────────────────────────────────────────────────┤
│ 섹션 4: 관련 기준 (Related Criteria)                    │
│   - 별표1~4, 전자상거래/콘텐츠 지침                     │
│   - 품목별 해결기준, 보증기간, 내용연수                 │
└─────────────────────────────────────────────────────────┘
```

## 3. 신규/수정 파일

### 3.1 신규 파일

| 파일 | 설명 |
|------|------|
| `backend/rag/specialized_retrievers.py` | 전문 검색기 모듈 |

### 3.2 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `backend/rag/generator.py` | 4섹션 구조화 응답 생성 메서드 추가 |
| `backend/rag/hybrid_retriever.py` | `search_by_doc_type`, `search_all_sections` 메서드 추가 |
| `backend/rag/__init__.py` | 신규 클래스 export 추가 |
| `backend/app/main.py` | Pydantic 응답 모델 및 `/chat` 엔드포인트 수정 |

## 4. 핵심 클래스 설명

### 4.1 LawRetriever
```python
# 법령 2단계 검색
# 1단계: chunks 테이블에서 벡터 검색 (법령 chunk만 필터링)
# 2단계: law_units, laws 테이블과 조인하여 메타데이터 추가

results = law_retriever.search_two_stage("소비자 보호", top_k=3)
# 결과: 법령명, 조항 경로(제14조 제1항), 본문, 유사도
```

### 4.2 CriteriaRetriever
```python
# 분쟁조정기준 검색
# chunks 테이블에서 벡터 검색 후 criteria_units와 조인

results = criteria_retriever.search_two_stage("TV 수리 보증기간", top_k=3)
# 결과: 별표명, 카테고리, 품목, 해결기준, 유사도
```

### 4.3 CaseRetriever
```python
# 사례 분리 검색
results = case_retriever.search_both("게임 환불", dispute_k=3, counsel_k=3)
# 결과: {'disputes': [...], 'counsels': [...]}
```

### 4.4 AgencyClassifier
```python
# 키워드 기반 기관 추천
result = classifier.classify("게임 아이템 환불")
# 결과: {'agency': 'KCDRC', 'reason': '콘텐츠 관련 분쟁...'}
```

### 4.5 StructuredRetriever
```python
# 4개 섹션 통합 검색
results = structured_retriever.search_all_sections(
    query="게임 환불",
    dispute_k=3, counsel_k=3, law_k=3, criteria_k=3
)
# 결과: {'agency': {...}, 'disputes': [...], 'counsels': [...],
#        'laws': [...], 'criteria': [...]}
```

## 5. API 응답 형식

### 5.1 `/chat` 엔드포인트 응답

```json
{
  "answer": "LLM 생성 답변...",
  "chunks_used": 12,
  "model": "gpt-4o-mini",
  "sources": [...],
  "has_sufficient_evidence": true,
  "clarifying_questions": [],

  "domain": {
    "agency": "KCDRC",
    "agency_info": {
      "name": "콘텐츠분쟁조정위원회",
      "full_name": "콘텐츠분쟁조정위원회",
      "description": "콘텐츠(게임, 영화, 음악 등) 관련 분쟁 조정",
      "url": "https://www.kcdrc.kr"
    },
    "dispute_type": "contents",
    "reason": "콘텐츠 관련 분쟁으로 판단됩니다 (키워드: 게임)",
    "confidence": 0.7
  },

  "similar_cases": {
    "disputes": [
      {"doc_id": "...", "doc_title": "...", "similarity": 0.68, ...}
    ],
    "counsels": [...]
  },

  "related_laws": [
    {"law_name": "소비자기본법", "article_path": "제21조 제2항", ...}
  ],

  "related_criteria": [
    {"source_label": "별표2 해결기준", "category": "...", "item": "...", ...}
  ]
}
```

## 6. 데이터베이스 테이블 현황

| 테이블 | 건수 | 설명 |
|--------|------|------|
| `criteria_units` | 507건 | 분쟁조정기준 구조화 데이터 |
| `law_units` | 11,321건 | 법령 계층 구조 (조/항/호/목) |
| `chunks` (criteria) | 507건 | criteria 임베딩 (벡터 검색용) |
| `chunks` (law) | 5,427건 | 법령 임베딩 (벡터 검색용) |

## 7. 기관 추천 키워드

### KCDRC (콘텐츠분쟁조정위원회)
```
게임, 영화, 콘텐츠, 앱, 어플, 음악, 웹툰, 만화, 동영상, 스트리밍,
OTT, 넷플릭스, 왓챠, 인앱, 결제, 아이템, 캐시, 다이아, 디지털, 구독, VOD
```

### ECMC (전자거래분쟁조정위원회)
```
중고, 직거래, 당근, 당근마켓, 번개장터, 중고나라, 개인간, 개인거래
```

### KCA (한국소비자원)
```
기본값 - 위 키워드에 해당하지 않는 일반 소비자-기업 분쟁
```

## 8. 테스트 방법

```bash
# 1. 서버 시작
cd /home/maroco/LLM/backend
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# 2. API 테스트
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "게임 환불하고 싶어요", "top_k": 3}'
```

## 9. 향후 개선 사항

- [ ] 법령/기준 2단계 검색 성능 최적화 (병렬 검색)
- [ ] 기관 추천 로직 고도화 (LLM 기반 분류)
- [ ] criteria_units 테이블에 직접 임베딩 저장 (현재는 chunks 테이블 조인)
- [ ] 응답 캐싱 구현

---

## 관련 파일

- 구현 계획: `/.claude/plans/structured-response-implementation.md`
- 스키마 설계: `/docs/guides/스키마_설계_근거.md`
- 시스템 아키텍처: `/docs/guides/system_architecture.md`
