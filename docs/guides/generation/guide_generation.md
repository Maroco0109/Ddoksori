# 팀원 C 가이드 - 생성 Agent + 프롬프트 엔지니어링

> **역할**: 답변 생성, 프롬프트 엔지니어링, LLM 품질 관리
> **최종 수정**: 2026-01-16

---

## 1. 역할 개요

팀원 C는 ddoksori 시스템의 **답변 생성 품질**을 담당합니다.

### 주요 책임
- Generation Node 구현 및 개선
- 4섹션 구조화 답변 프롬프트 작성
- 면책 문구 및 출처 인용 관리
- 제한 모드(FSS/K_MEDI/KOPICO) 응답 작성
- Faithfulness(근거 충실도) 분석

---

## 2. 담당 파일 목록

| 파일명 | 경로 | 역할 | 우선순위 |
|--------|------|------|:--------:|
| `generation.py` | `backend/app/orchestrator/nodes/generation.py` | Generation 노드 (LLM 호출) | ★★★ |
| `generator.py` | `backend/rag/generator.py` | RAGGenerator 클래스 (프롬프트 관리) | ★★★ |

---

## 3. 파일별 상세 설명

### 3.1 generation.py - Generation 노드

**위치**: `backend/app/orchestrator/nodes/generation.py`

**역할**: LangGraph 노드로서 LLM 기반 답변 생성

**핵심 함수**:
```python
def generation_node(state: ChatState) -> dict:
    """
    메인 생성 노드

    분기 로직:
    1. query_type == 'general' → 간단한 응답
    2. is_restricted == True → 제한된 응답 (전문가 상담 권유)
    3. 일반 분쟁 → RAGGenerator로 4섹션 답변
    """
```

**분기 처리**:

| 조건 | 처리 방식 | 예시 |
|------|----------|------|
| `query_type == 'general'` | 간단한 대화 응답 | "안녕하세요" → "안녕하세요! 똑소리입니다." |
| `is_restricted == True` | 전문가 상담 권유 | 금융/의료/개인정보 → 해당 기관 안내 |
| `retrieval 없음` | Fallback 응답 | 검색 실패 → 기본 안내 메시지 |
| `일반 분쟁` | 4섹션 구조화 답변 | 헬스장 환불 → 기관+사례+법령+기준 |

**수정 포인트**:
| 위치 | 내용 |
|------|------|
| 라인 ~30-50 | 일반 대화 응답 템플릿 |
| 라인 ~50-80 | 제한 모드 응답 템플릿 |
| 라인 ~80-120 | RAGGenerator 호출 로직 |

---

### 3.2 generator.py - RAGGenerator 클래스

**위치**: `backend/rag/generator.py`

**역할**: LLM 호출, 프롬프트 관리, 4섹션 답변 생성

**핵심 클래스**:
```python
class RAGGenerator:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(model=model, temperature=0.3)

    # 기본 답변 생성
    def generate_answer(self, query: str, chunks: List[dict]) -> str

    # 로깅 포함 생성
    def generate_answer_instrumented(self, query: str, chunks: List[dict]) -> Tuple[str, dict]

    # 4섹션 구조화 답변 ★★★
    def generate_structured_answer(
        self,
        query: str,
        agency_info: dict,
        disputes: List[dict],
        counsels: List[dict],
        laws: List[dict],
        criteria: List[dict]
    ) -> str

    # 기관 추천
    def determine_agency(self, query: str) -> str
```

---

## 4. 프롬프트 작성 가이드

### 4.1 4섹션 구조화 프롬프트

**위치**: `generator.py` - `_get_structured_system_prompt()`

**시스템 프롬프트 구조**:
```
당신은 한국 소비자 분쟁 해결을 돕는 AI 어시스턴트 '똑소리'입니다.

## 역할
- 소비자 분쟁에 대한 정보 제공 (법률 자문 아님)
- 관련 기관, 유사 사례, 법령, 기준 안내

## 응답 형식
1. **추천 기관**: 분쟁 유형에 맞는 기관 안내
2. **유사 사례**: 관련 분쟁조정/상담 사례 요약
3. **관련 법령**: 적용 가능한 법조문 인용
4. **관련 기준**: 분쟁조정기준 안내

## 주의사항
- 법적 판단이나 결론을 내리지 마세요
- 출처를 반드시 표기하세요 [출처: ...]
- 면책 문구를 포함하세요
```

### 4.2 사용자 프롬프트 구조

**위치**: `generator.py` - `_build_structured_prompt()`

```
## 사용자 질문
{query}

## 추천 기관 정보
기관명: {agency_info['name']}
연락처: {agency_info['phone']}
홈페이지: {agency_info['url']}

## 유사 분쟁조정사례
{disputes 요약}

## 유사 상담사례
{counsels 요약}

## 관련 법령
{laws 요약}

## 관련 분쟁조정기준
{criteria 요약}

위 정보를 바탕으로 사용자의 질문에 답변해주세요.
```

### 4.3 면책 문구 템플릿

```
---
**면책 안내**: 이 답변은 참고용 정보이며, 법률 자문이 아닙니다.
구체적인 법적 조언이 필요하시면 변호사 또는 해당 기관에 문의해주세요.
```

### 4.4 출처 인용 형식

```
[출처: 한국소비자원 분쟁조정사례 2024-12345]
[출처: 소비자분쟁해결기준 별표1 - 헬스장]
[출처: 전자상거래법 제17조]
```

---

## 5. 제한 모드 응답

### 5.1 FSS (금융감독원) 응답

```python
RESTRICTED_RESPONSE_FSS = """
금융 관련 분쟁은 전문적인 상담이 필요합니다.

**추천 기관**: 금융감독원 금융소비자보호처
- 전화: 1332
- 홈페이지: https://www.fss.or.kr

금융 분쟁은 복잡한 법률 관계가 얽혀 있어,
전문가의 상담을 받으시는 것이 좋습니다.
"""
```

### 5.2 K_MEDI (의료분쟁조정) 응답

```python
RESTRICTED_RESPONSE_K_MEDI = """
의료 관련 분쟁은 전문 기관의 도움이 필요합니다.

**추천 기관**: 한국의료분쟁조정중재원
- 전화: 1670-2545
- 홈페이지: https://www.k-medi.or.kr

의료 분쟁은 의학적 판단이 필요하므로,
전문 기관에 상담하시기 바랍니다.
"""
```

### 5.3 KOPICO (개인정보분쟁) 응답

```python
RESTRICTED_RESPONSE_KOPICO = """
개인정보 관련 분쟁은 전문 기관의 도움이 필요합니다.

**추천 기관**: 개인정보분쟁조정위원회
- 전화: 1833-6972
- 홈페이지: https://www.kopico.go.kr

개인정보 침해는 개인정보보호법에 따라 처리되므로,
전문 기관에 상담하시기 바랍니다.
"""
```

---

## 6. 테스트 스크립트

### 6.1 Generation 노드 테스트
```bash
conda activate dsr
cd backend
python -m pytest scripts/testing/orchestrator/test_pr2_nodes.py::TestGenerationNode -v -p no:asyncio
```

**테스트 항목**:
| 테스트 | 검증 내용 |
|--------|----------|
| `test_general_greeting_response` | 일반 대화에 "똑소리" 포함 |
| `test_no_retrieval_returns_fallback` | 검색 실패 시 fallback |

### 6.2 API 엔드포인트 테스트
```bash
cd backend
python -m pytest scripts/testing/api/test_api_endpoints.py -v -p no:asyncio
```

**테스트 항목**:
- `/chat` 엔드포인트 정상 응답
- 4섹션 구조 반환 확인
- 스트리밍 응답 확인

### 6.3 대화식 테스트
```bash
python backend/scripts/evaluation/interactive_rag_test.py
```

**사용법**:
```
>>> 헬스장 환불 문제로 도움이 필요합니다
[답변 출력...]

>>> 보험 해지 환불 문의
[제한 모드 응답...]
```

---

## 7. 평가 스크립트

### 7.1 대화식 RAG 테스트
```bash
cd backend
python backend/scripts/evaluation/interactive_rag_test.py
```

**평가 포인트**:
| 항목 | 기준 |
|------|------|
| 4섹션 구조 | 기관+사례+법령+기준 모두 포함 |
| 면책 문구 | 답변 끝에 포함 |
| 출처 표기 | `[출처: ...]` 형식 사용 |
| Faithfulness | 검색 결과와 답변 일치 |

### 7.2 수동 품질 체크리스트

| 체크 항목 | 확인 방법 |
|-----------|----------|
| 4섹션 완성도 | 모든 섹션이 적절히 채워졌는지 |
| 출처 정확도 | 인용된 출처가 실제 검색 결과와 일치하는지 |
| 면책 문구 | 답변에 면책 안내 포함 여부 |
| 제한 모드 | 금융/의료/개인정보 질문 시 적절한 안내 |
| 할루시네이션 | 검색 결과에 없는 정보 생성 여부 |

---

## 8. 완료 기준

| 지표 | 목표 | 확인 방법 |
|------|------|----------|
| 4섹션 응답 구조 | 정상 출력 | `interactive_rag_test.py` |
| 면책 문구 포함 | 100% | 수동 확인 |
| 출처 인용 | 모든 답변에 포함 | 수동 확인 |
| 제한 모드 응답 | 3개 기관 모두 작성 | 수동 확인 |
| Generation 테스트 | 100% 통과 | pytest 실행 |

---

## 9. 주차별 작업

### 1주차
- [ ] 프로젝트 구조 학습
- [ ] Generation 코드 분석
- [ ] 프롬프트 분석
- [ ] 프롬프트 개선안 초안

### 2주차
- [ ] 답변 포맷 개선
- [ ] 프롬프트 튜닝
- [ ] Faithfulness 분석
- [ ] 제한 모드 응답 작성

### 3주차
- [ ] 답변 품질 검증
- [ ] 예외 케이스 처리
- [ ] 문서화

---

## 10. 프롬프트 튜닝 팁

### 10.1 Temperature 조정

```python
# generator.py에서 조정
class RAGGenerator:
    def __init__(self, model: str = "gpt-4o-mini"):
        self.llm = ChatOpenAI(
            model=model,
            temperature=0.3  # 낮을수록 일관성 ↑, 창의성 ↓
        )
```

| Temperature | 특성 |
|-------------|------|
| 0.0 ~ 0.3 | 일관성 높음, 법률 답변에 적합 |
| 0.3 ~ 0.7 | 균형 |
| 0.7 ~ 1.0 | 창의성 높음, 일반 대화에 적합 |

### 10.2 Few-shot 예시 추가

```python
SYSTEM_PROMPT = """
...

## 답변 예시

### 질문: 헬스장 환불을 요청했는데 거절당했습니다.

### 답변:
**1. 추천 기관**
한국소비자원(KCA)에서 상담받으실 수 있습니다.
- 전화: 1372
- 홈페이지: https://www.kca.go.kr

**2. 유사 사례**
[출처: 한국소비자원 2024-12345]
- 헬스장 중도해지 시 위약금 분쟁
- 조정 결과: 잔여 기간 비율 환급

...
"""
```

### 10.3 출처 인용 강화

```python
# 프롬프트에 명시적 지시 추가
CITATION_INSTRUCTION = """
## 출처 인용 규칙
1. 모든 사실 정보에 출처를 표기하세요
2. 형식: [출처: {기관명} {사례번호}] 또는 [출처: {법령명} 제X조]
3. 출처 없이 추측하지 마세요
4. 검색 결과에 없는 정보는 "확인되지 않았습니다"로 답변하세요
"""
```

---

## 11. 참고 문서

| 문서 | 경로 | 설명 |
|------|------|------|
| 프로젝트 계획서 | `/plans/plans.md` | 전체 3주 계획 |
| RAG 아키텍처 | `/docs/guides/system_architecture.md` | 시스템 구조 |
| 구조화 응답 구현 | `/docs/guides/2026-01-13_structured_response_implementation.md` | 4섹션 구현 |
| LangGraph 통합 | `/docs/guides/2026-01-14_frontend_langgraph_integration.md` | 프론트 연동 |

---

## 12. 자주 사용하는 명령어 모음

```bash
# 환경 활성화
conda activate dsr

# Generation 노드 테스트 (backend 디렉토리에서)
cd backend
python -m pytest scripts/testing/orchestrator/test_pr2_nodes.py::TestGenerationNode -v -p no:asyncio

# API 테스트
python -m pytest scripts/testing/api/test_api_endpoints.py -v -p no:asyncio

# 대화식 테스트
python backend/scripts/evaluation/interactive_rag_test.py

# 서버 실행 (개발 모드)
cd backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# API 직접 호출 테스트
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "헬스장 환불 문의"}'
```

---

## 13. 코드 수정 예시

### 13.1 시스템 프롬프트 수정

```python
# generator.py

def _get_structured_system_prompt(self) -> str:
    return """
당신은 한국 소비자 분쟁 해결을 돕는 AI 어시스턴트 '똑소리'입니다.

## 핵심 원칙
1. 정보 제공만 합니다 (법률 자문 아님)
2. 검색 결과에 기반해서만 답변합니다
3. 모든 정보에 출처를 표기합니다
4. 확실하지 않으면 "확인되지 않았습니다"라고 합니다

## 응답 구조
1. **추천 기관**: 분쟁 유형에 맞는 기관
2. **유사 사례**: 관련 분쟁조정/상담 사례
3. **관련 법령**: 적용 가능한 법조문
4. **관련 기준**: 분쟁조정기준

## 면책 안내 (반드시 포함)
---
이 답변은 참고용 정보이며, 법률 자문이 아닙니다.
"""
```

### 13.2 일반 대화 응답 추가

```python
# generation.py

GENERAL_RESPONSES = {
    'greeting': "안녕하세요! 소비자 분쟁 해결을 돕는 똑소리입니다. 어떤 도움이 필요하신가요?",
    'thanks': "도움이 되셨다면 다행입니다! 추가 질문이 있으시면 말씀해주세요.",
    'goodbye': "이용해 주셔서 감사합니다. 좋은 하루 되세요!",
}

def _handle_general_query(self, query: str) -> str:
    query_lower = query.lower()
    if any(g in query_lower for g in ['안녕', '반가워', 'hello']):
        return GENERAL_RESPONSES['greeting']
    elif any(t in query_lower for t in ['감사', '고마워', 'thanks']):
        return GENERAL_RESPONSES['thanks']
    # ...
```

