# 채팅 모드 이원화 + Guardrail + Generator claim_evidence_map

**작성일**: 2026-01-19
**담당**: AI/MAS System Engineer
**상태**: 완료

## 개요

Sprint 계획의 Sprint 1-2 요구사항에 따라 구현된 기능:
1. **OpenAI Moderation Guardrail**: 입력/출력 유해성 검사
2. **채팅 모드 이원화**: 일반 채팅(Simple Graph) vs 분쟁 채팅(V2 Graph)
3. **Generator claim_evidence_map**: 답변의 주장-근거 매핑

### 목표

- 유해 콘텐츠 필터링 (OpenAI Moderation API)
- `chat_type`에 따른 그래프 분기 (general: 간소화, dispute: 풀 파이프라인)
- 답변 생성 시 `claim_evidence_map`으로 근거 추적 가능

## 아키텍처

### 채팅 모드별 그래프 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│                     chat_type == 'general'                          │
│  ┌──────────────┐    ┌─────────────────┐    ┌────────────┐          │
│  │ Input        │ →  │ Query Analysis  │ →  │ Retrieval  │ →        │
│  │ Guardrail    │    │ (NO_RETRIEVAL/  │    │ (optional) │          │
│  └──────────────┘    │ NEED_RAG only)  │    └────────────┘          │
│         ↓ blocked           ↓                      ↓                │
│        END          ┌───────────────┐     ┌────────────────┐        │
│                     │  Generation   │  →  │ Output         │ → END  │
│                     └───────────────┘     │ Guardrail      │        │
│                                           └────────────────┘        │
│  - Checkpointer 없음 (싱글턴, 대화 기억 X)                           │
│  - NEED_USER_CLARIFICATION 미지원                                   │
│  - Review 에이전트 없음                                              │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                     chat_type == 'dispute'                          │
│  ┌──────────────┐    ┌─────────────────┐    ┌────────────┐          │
│  │ Input        │ →  │ Query Analysis  │ →  │ Search     │ →        │
│  │ Guardrail    │    │ (3 modes)       │    │ Plan       │          │
│  └──────────────┘    └─────────────────┘    └────────────┘          │
│         ↓ blocked           ↓                      ↓                │
│        END          ┌───────────────┐     ┌────────────────┐        │
│                     │  Retrieval    │  →  │ Sufficiency    │        │
│                     └───────────────┘     └────────────────┘        │
│                           ↓                      ↓                  │
│                     ┌───────────────┐     ┌────────────────┐        │
│                     │  Generation   │  →  │ Review         │        │
│                     └───────────────┘     └────────────────┘        │
│                                                  ↓                  │
│                     ┌───────────────┐     ┌────────────────┐        │
│                     │ ask_          │     │ Output         │ → END  │
│                     │ clarification │     │ Guardrail      │        │
│                     └───────────────┘     └────────────────┘        │
│  - Checkpointer 사용 (멀티턴)                                        │
│  - 모든 모드 지원 (NO_RETRIEVAL, NEED_RAG, NEED_USER_CLARIFICATION)  │
│  - Review 에이전트 포함                                              │
└─────────────────────────────────────────────────────────────────────┘
```

## 구현 내용

### 1. OpenAI Moderation Guardrail

#### moderation.py (`backend/app/guardrail/moderation.py`)

```python
from openai import OpenAI

MODERATION_ENABLED = os.getenv('MODERATION_ENABLED', 'false').lower() == 'true'
MODERATION_MODEL = os.getenv('MODERATION_MODEL', 'omni-moderation-latest')

def check_input(text: str) -> ModerationResult:
    """입력 텍스트 유해성 검사"""
    if not MODERATION_ENABLED:
        return {'flagged': False, 'blocked': False, ...}
    
    response = client.moderations.create(
        model=MODERATION_MODEL,
        input=text
    )
    # 카테고리 중 하나라도 flagged → blocked
    return {
        'flagged': result.flagged,
        'categories': categories_dict,
        'blocked': result.flagged,
        'fallback_message': FALLBACK_MESSAGE if result.flagged else None
    }

def check_output(text: str) -> ModerationResult:
    """출력 텍스트 유해성 검사 (동일 로직)"""
```

#### nodes.py (`backend/app/guardrail/nodes.py`)

```python
def input_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph 입력 Guardrail 노드"""
    if not MODERATION_ENABLED:
        return {}
    
    user_query = state.get('user_query', '')
    result = check_input(user_query)
    
    if result['blocked']:
        return {
            'guardrail_blocked': True,
            'guardrail_type': 'input',
            'final_answer': result['fallback_message'],
        }
    return {'guardrail_blocked': False}

def output_guardrail_node(state: Dict[str, Any]) -> Dict[str, Any]:
    """LangGraph 출력 Guardrail 노드"""
    # 동일 구조
```

### 2. 채팅 모드 이원화

#### SimpleState (`backend/app/orchestrator/state.py`)

```python
class SimpleState(TypedDict):
    user_query: str
    mode: RoutingMode  # 'NO_RETRIEVAL' | 'NEED_RAG' only
    query_analysis_v2: Optional[QueryAnalysisResult_v2]
    retrieval: Optional[RetrievalResult]
    final_answer: Optional[str]
    guardrail_blocked: bool
    guardrail_type: Optional[str]
```

#### Simple Graph (`backend/app/orchestrator/graph.py`)

```python
def create_simple_chat_graph() -> StateGraph:
    graph = StateGraph(SimpleState)
    
    graph.add_node('input_guardrail', input_guardrail_node)
    graph.add_node('query_analysis', _simple_query_analysis_node)
    graph.add_node('retrieval', _simple_retrieval_node)
    graph.add_node('generation', _simple_generation_node)
    graph.add_node('output_guardrail', output_guardrail_node)
    
    graph.set_entry_point('input_guardrail')
    
    # input_guardrail → (blocked) END | (pass) query_analysis
    graph.add_conditional_edges('input_guardrail', _route_simple_after_guardrail, ...)
    
    # query_analysis → (NO_RETRIEVAL) generation | (NEED_RAG) retrieval
    graph.add_conditional_edges('query_analysis', _route_simple_after_query_analysis, ...)
    
    graph.add_edge('retrieval', 'generation')
    graph.add_edge('generation', 'output_guardrail')
    graph.add_edge('output_guardrail', END)
    
    return graph
```

#### V2 Graph 수정 (`create_v2_chat_graph()`)

```python
def create_v2_chat_graph() -> StateGraph:
    graph = StateGraph(ChatState_v2)
    
    # Guardrail 노드 추가
    graph.add_node('input_guardrail', input_guardrail_node)
    graph.add_node('output_guardrail', output_guardrail_node)
    
    # ... 기존 노드들 ...
    
    graph.set_entry_point('input_guardrail')  # 진입점 변경
    
    # input_guardrail → query_analysis 또는 END
    graph.add_conditional_edges('input_guardrail', _route_after_input_guardrail_v2, ...)
    
    # review → output_guardrail (기존 END → output_guardrail)
    graph.add_conditional_edges('review', _route_after_review_v2_wrapper, {
        'generation': 'generation',
        'retrieval': 'retrieval',
        'output_guardrail': 'output_guardrail',  # 변경
    })
    
    graph.add_edge('output_guardrail', END)
```

#### main.py 분기 로직

```python
from app.orchestrator import get_graph_for_chat_type, create_simple_state

@app.post("/chat")
async def chat(request: ChatRequest):
    graph = get_graph_for_chat_type(request.chat_type)
    
    if request.chat_type == 'general':
        initial_state = create_simple_state(user_query=request.message)
        final_state = await asyncio.to_thread(graph.invoke, initial_state)
    else:
        initial_state = create_initial_state(
            user_query=request.message,
            chat_type=request.chat_type,
            onboarding=request.onboarding,
        )
        config = {"configurable": {"thread_id": session_id}}
        final_state = await asyncio.to_thread(graph.invoke, initial_state, config)
```

### 3. Generator claim_evidence_map

#### ClaimEvidenceMapping 스키마 (`state.py`)

```python
class ClaimEvidenceMapping(TypedDict):
    claim: str                    # 답변 내 주장 문장
    evidence_chunk_ids: List[str] # 근거 청크 ID 목록
    evidence_texts: List[str]     # 근거 텍스트 (미리보기)
    grounded: bool                # 근거 존재 여부
```

#### _extract_claim_evidence_map (`generator.py`)

```python
def _extract_claim_evidence_map(
    self,
    answer: str,
    disputes: List[Dict],
    counsels: List[Dict],
    laws: List[Dict],
    criteria: List[Dict]
) -> List[Dict[str, Any]]:
    """답변 문장별 근거 청크 매핑"""
    all_chunks = disputes + counsels + laws + criteria
    chunk_map = {c.get('chunk_id', c.get('unit_id')): c for c in all_chunks}
    
    claim_evidence_map = []
    sentences = re.split(r'[.!?]\s+', answer)
    
    for sentence in sentences:
        if len(sentence) < 15:
            continue
        
        matched_chunks = []
        for chunk_id, chunk in chunk_map.items():
            content = chunk.get('content', chunk.get('text', ''))
            
            # 단어 겹침 + 핵심 용어 매칭
            sentence_words = set(sentence.lower().split())
            content_words = set(content.lower().split())
            overlap = len(sentence_words & content_words)
            
            key_terms = ['소비자', '분쟁', '환불', '조정', '법', '기준']
            key_match = sum(1 for t in key_terms if t in sentence and t in content)
            
            score = overlap + (key_match * 2)
            if score >= 2:
                matched_chunks.append({'chunk_id': chunk_id, 'text': content[:200], 'score': score})
        
        if matched_chunks:
            top_matches = sorted(matched_chunks, key=lambda x: x['score'], reverse=True)[:2]
            claim_evidence_map.append({
                'claim': sentence,
                'evidence_chunk_ids': [m['chunk_id'] for m in top_matches],
                'evidence_texts': [m['text'] for m in top_matches],
                'grounded': True
            })
    
    return claim_evidence_map
```

## 환경 변수 설정

```bash
# .env 파일

# Guardrail 활성화 (기본: false)
MODERATION_ENABLED=true

# Moderation 모델 (기본: omni-moderation-latest)
MODERATION_MODEL=omni-moderation-latest
```

## 테스트

### Guardrail 테스트

```bash
PYTHONPATH=/home/maroco/LLM/backend \
python -c "
from app.guardrail.moderation import check_input, check_output, MODERATION_ENABLED
from app.guardrail.nodes import input_guardrail_node, output_guardrail_node

print('MODERATION_ENABLED:', MODERATION_ENABLED)

# 노드 테스트
state = {'user_query': '헬스장 환불 문의'}
result = input_guardrail_node(state)
print('Input guardrail:', result)
"
```

### 그래프 테스트

```bash
PYTHONPATH=/home/maroco/LLM/backend \
python -c "
from app.orchestrator.graph import get_graph_for_chat_type

general_graph = get_graph_for_chat_type('general')
dispute_graph = get_graph_for_chat_type('dispute')

print('General graph nodes:', list(general_graph.nodes.keys()))
print('Dispute graph nodes:', list(dispute_graph.nodes.keys()))
"
```

### claim_evidence_map 테스트

```bash
PYTHONPATH=/home/maroco/LLM/backend \
python -c "
from app.agents.answer_generation.tools.generator import RAGGenerator

gen = RAGGenerator(use_llm=False)
answer = '한국소비자원에서 분쟁조정을 신청할 수 있습니다.'
disputes = [{'chunk_id': 'c1', 'content': '한국소비자원 분쟁조정 신청 절차'}]

result = gen._extract_claim_evidence_map(answer, disputes, [], [], [])
print('claim_evidence_map:', result)
"
```

## 파일 구조

```
backend/app/
├── guardrail/
│   ├── __init__.py           # NEW
│   ├── moderation.py         # NEW: OpenAI Moderation API
│   └── nodes.py              # NEW: LangGraph 노드
├── orchestrator/
│   ├── __init__.py           # 수정: exports 추가
│   ├── graph.py              # 수정: Guardrail 노드, Simple Graph
│   ├── state.py              # 수정: SimpleState, claim_evidence_map
│   └── routing.py            # 수정: output_guardrail 라우팅
├── agents/
│   └── answer_generation/
│       ├── agent.py          # 수정: claim_evidence_map 반환
│       └── tools/
│           └── generator.py  # 수정: _extract_claim_evidence_map()
└── main.py                   # 수정: chat_type 분기 로직
```

## 그래프 노드 비교

| 노드 | Simple Graph | V2 Graph |
|------|--------------|----------|
| input_guardrail | O | O |
| query_analysis | O | O |
| search_plan | X | O |
| retrieval | O | O |
| sufficiency | X | O |
| generation | O | O |
| review | X | O |
| ask_clarification | X | O |
| output_guardrail | O | O |

## 관련 Sprint

- Sprint 1: Guardrail + Query Analysis (입력/출력 Guardrail 구현)
- Sprint 2: Orchestrator + 채팅 모드 이원화
- Sprint 4: Generator 출력 단일화 (claim_evidence_map)
