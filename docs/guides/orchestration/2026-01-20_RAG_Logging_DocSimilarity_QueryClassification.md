# RAG 로깅 개선 + 문서 수준 유사도 + 쿼리 분류 개선

**작성일**: 2026-01-20
**담당**: AI/MAS System Engineer
**상태**: 완료

## 개요

RAG 파이프라인 로그 분석을 통해 발견된 문제점들을 해결하기 위한 5단계 개선 작업:

1. **에이전트 I/O 로깅 확장**: 각 노드의 입력/출력 상태 추적
2. **분쟁조정사례 메타데이터 추출**: 품목, 금액, 일시, 조정결과 실시간 추출
3. **문서 수준 유사도 검색**: 개별 청크가 아닌 문서 전체의 관련성 평가
4. **쿼리 분류 개선**: 시스템 관련 질문 감지 (system_meta 타입)
5. **Recursion Limit 버그 수정**: 무한 루프 방지

### 문제 발견 (로그 분석)

- `122724_fb92a3b2.json`: Recursion limit of 25 reached 에러
- `123748_4773d195.json`: "네 모델명이 뭐야?" 질문에 불필요한 검색 실행
- 로그에 에이전트 간 데이터 전달 내용이 없음
- 분쟁조정사례에 구체적인 메타데이터(품목, 금액) 누락

## 아키텍처

### Phase 1: 에이전트 I/O 로깅

```
┌────────────────────────────────────────────────────────────────┐
│                    NodeTimingLog 구조                           │
├────────────────────────────────────────────────────────────────┤
│  node_name: str           # 노드 이름                           │
│  duration_ms: float       # 실행 시간                           │
│  start_time: str          # 시작 시간 (ISO)                     │
│  end_time: str            # 종료 시간 (ISO)                     │
│  ─────────────────────────────────────────────────────────────  │
│  input_snapshot: Dict     # [NEW] 노드 입력 상태 스냅샷          │
│  output_snapshot: Dict    # [NEW] 노드 출력 상태 스냅샷          │
│  state_changes: List[str] # [NEW] 변경된 필드 목록               │
│                           #   +field: 새로 추가                  │
│                           #   ~field: 값 변경                    │
└────────────────────────────────────────────────────────────────┘
```

### Phase 3: 문서 수준 유사도 검색

```
기존 방식 (청크 단위):
┌──────────────────────────────────────────────────────────────┐
│  Query → 청크1(0.85) → 청크2(0.72) → 청크3(0.68) → ...        │
│         (DocA)        (DocB)        (DocA)                   │
│  → 청크1, 청크2, 청크3 반환 (서로 다른 문서의 조각들)           │
└──────────────────────────────────────────────────────────────┘

개선된 방식 (문서 단위):
┌──────────────────────────────────────────────────────────────┐
│  Query → 후보 청크 15개 검색 (top_k * 5)                       │
│        ↓                                                      │
│  doc_id별 그룹화:                                             │
│    DocA: [0.85, 0.68, 0.55] → avg=0.69                       │
│    DocB: [0.72, 0.60]       → avg=0.66                       │
│    DocC: [0.70, 0.65, 0.62] → avg=0.66                       │
│        ↓                                                      │
│  평균 유사도 순 정렬 → DocA, DocC, DocB                        │
│        ↓                                                      │
│  각 문서의 best_chunk 반환                                     │
└──────────────────────────────────────────────────────────────┘
```

### Phase 4: 쿼리 분류 흐름

```
┌─────────────────────────────────────────────────────────────────┐
│                      Query Classification                        │
├─────────────────────────────────────────────────────────────────┤
│  "네 모델명이 뭐야?" ──→ system_meta ──→ NO_RETRIEVAL           │
│  "안녕하세요"        ──→ general     ──→ NO_RETRIEVAL           │
│  "헬스장 환불 가능?" ──→ dispute     ──→ NEED_RAG               │
│  "소비자보호법 몇조?" ──→ law        ──→ NEED_RAG               │
│  "분쟁조정기준 알려줘" ──→ criteria  ──→ NEED_RAG               │
└─────────────────────────────────────────────────────────────────┘

NO_RETRIEVAL 모드 (ReAct 그래프):
  query_analysis → generation → review → END
  (react_think, react_act 건너뜀)
```

## 구현 내용

### Phase 1: 에이전트 I/O 로깅 확장

#### NODE_SNAPSHOT_FIELDS (`graph.py`)

```python
NODE_SNAPSHOT_FIELDS = {
    'query_analysis': {
        'input': ['user_query', 'onboarding', 'chat_type'],
        'output': ['query_analysis', 'mode', 'query_analysis_v2'],
    },
    'retrieval': {
        'input': ['user_query', 'query_analysis', 'onboarding'],
        'output': ['retrieval', 'sources'],
    },
    'react_think': {
        'input': ['user_query', 'retrieval', 'react_steps', 'iteration_count'],
        'output': ['last_thought', 'last_action', 'should_continue', 'iteration_count'],
    },
    'generation': {
        'input': ['user_query', 'retrieval', 'query_analysis', 'react_steps'],
        'output': ['final_answer', 'draft_answer'],
    },
    # ... 기타 노드
}
```

#### 스냅샷 헬퍼 함수 (`graph.py`)

```python
def _snapshot_state(state: Dict[str, Any], fields: list) -> Dict[str, Any]:
    """상태에서 지정된 필드만 추출하여 스냅샷 생성"""
    snapshot = {}
    for field in fields:
        if field in state:
            value = state[field]
            if hasattr(value, '__dict__'):
                snapshot[field] = str(value)[:500]  # 객체: 500자 제한
            elif isinstance(value, (list, dict)):
                serialized = json.dumps(value, ensure_ascii=False, default=str)
                snapshot[field] = json.loads(serialized[:2000])  # 2KB 제한
            else:
                snapshot[field] = value
    return snapshot

def _detect_state_changes(input_state: Dict, output: Dict) -> list:
    """출력에서 변경/추가된 필드 목록 반환"""
    changes = []
    for key in output.keys():
        if key.startswith('_'):
            continue
        if key not in input_state:
            changes.append(f"+{key}")  # 새로 추가
        elif input_state.get(key) != output.get(key):
            changes.append(f"~{key}")  # 값 변경
    return changes
```

#### NodeTimingLog 확장 (`logger.py`)

```python
@dataclass
class NodeTimingLog:
    """노드 실행 시간 로그 (I/O 추적 포함)"""
    node_name: str
    duration_ms: float
    start_time: str
    end_time: str
    # Phase 1 개선
    input_snapshot: Optional[Dict] = None
    output_snapshot: Optional[Dict] = None
    state_changes: List[str] = field(default_factory=list)
```

### Phase 2: 분쟁조정사례 메타데이터 추출

#### DisputeLog 확장 (`logger.py`)

```python
@dataclass
class DisputeLog:
    """분쟁조정 사례 로그 (메타데이터 포함)"""
    chunk_id: str
    doc_id: str
    doc_title: str
    source_org: str
    decision_date: Optional[str]
    similarity: float
    content_preview: str
    # Phase 2: 실시간 LLM 추출 메타데이터
    product_item: Optional[str] = None        # 품목 (예: "키보드")
    dispute_amount: Optional[str] = None      # 금액 (예: "120,000원")
    transaction_date: Optional[str] = None    # 거래 일자
    mediation_result: Optional[str] = None    # 조정결과 (예: "인용")
```

#### extract_dispute_metadata (`specialized_retrievers.py`)

```python
def extract_dispute_metadata(self, disputes: List[Dict]) -> List[Dict]:
    """분쟁조정사례에서 메타데이터 추출 (실시간 LLM)"""
    client = ExaoneLLMClient()

    system_prompt = """당신은 분쟁조정사례에서 핵심 정보를 추출하는 전문가입니다.
주어진 텍스트에서 다음 정보를 추출하여 JSON 형식으로 반환하세요:
- product_item: 분쟁 대상 품목
- dispute_amount: 분쟁 금액
- transaction_date: 거래/구매 일자
- mediation_result: 조정 결과"""

    for dispute in disputes:
        content = dispute.get('content', '')[:1500]
        response = client.generate(system_prompt, f"텍스트:\n{content}")
        metadata = self._parse_metadata_json(response)
        if metadata:
            dispute.update(metadata)

    return disputes
```

### Phase 3: 문서 수준 유사도 검색

#### DocumentLevelResult (`specialized_retrievers.py`)

```python
@dataclass
class DocumentLevelResult:
    """문서 수준 유사도 검색 결과"""
    doc_id: str
    doc_title: str
    source_org: str
    avg_similarity: float      # 모든 청크의 평균 유사도
    max_similarity: float      # 가장 높은 청크 유사도
    min_similarity: float      # 가장 낮은 청크 유사도
    chunk_count: int           # 검색된 청크 수
    total_doc_chunks: int      # 문서 전체 청크 수
    best_chunk: Dict           # 가장 유사한 청크 정보
    all_chunks: List[Dict]     # 검색된 모든 청크
```

#### _aggregate_by_document (`specialized_retrievers.py`)

```python
def _aggregate_by_document(self, chunks: List[Dict], top_k: int) -> List[DocumentLevelResult]:
    """청크들을 문서별로 그룹화하고 평균 유사도 계산"""
    doc_chunks = defaultdict(list)

    for chunk in chunks:
        doc_chunks[chunk['doc_id']].append(chunk)

    doc_results = []
    for doc_id, chunks_list in doc_chunks.items():
        similarities = [c['similarity'] for c in chunks_list]
        doc_results.append(DocumentLevelResult(
            doc_id=doc_id,
            avg_similarity=sum(similarities) / len(similarities),
            max_similarity=max(similarities),
            best_chunk=max(chunks_list, key=lambda c: c['similarity']),
            ...
        ))

    return sorted(doc_results, key=lambda d: d.avg_similarity, reverse=True)[:top_k]
```

#### chunk_relations 마이그레이션

```python
# migrate_chunk_relations.py 실행 결과
# - next_chunk 관계: 1,517개
# - prev_chunk 관계: 1,517개
# - 총 3,034개 관계 추가

# 샘플 관계:
# ECMC_00051_10:facts:0000 --[next_chunk]--> ECMC_00051_10:facts:0001
# ECMC_00051_10:facts:0001 --[next_chunk]--> ECMC_00051_10:facts:0002
```

### Phase 4: 쿼리 분류 개선

#### system_meta 키워드/패턴 (`agent.py`)

```python
SYSTEM_META_KEYWORDS = [
    "모델명", "모델 이름", "어떤 모델", "버전", "네 이름", "니 이름",
    "만든 사람", "개발자", "누가 만들", "네가 뭐야", "니가 뭐야",
    "뭐하는 ai", "어떤 ai", "어떤 봇", "챗봇", "ai야",
    "gpt", "chatgpt", "클로드", "claude", "exaone", "llm",
]

SYSTEM_META_PATTERNS = [
    r'(네가?|니가?|당신|너|넌)\s*(누구|뭐|무엇)',
    r'(무슨|어떤|뭔)\s*(모델|AI|봇|챗봇)',
    r'모델\s*이?름|모델명',
]
```

#### _classify_query_type 수정 (`agent.py`)

```python
def _classify_query_type(query: str) -> Literal['dispute', 'general', 'law', 'criteria', 'system_meta']:
    # Phase 4: 시스템 관련 질문
    if _is_system_meta_query(query):
        return 'system_meta'

    # ... 기존 분류 로직 ...
```

#### ReAct 그래프 라우팅 수정 (`graph.py`)

```python
def _route_after_query_analysis_react(state: ChatState) -> Literal['ask_clarification', 'react_think', 'generation']:
    mode = state.get('mode', 'NEED_RAG')

    # NO_RETRIEVAL 모드는 검색 없이 바로 생성
    if mode == 'NO_RETRIEVAL':
        return 'generation'

    query_type = query_analysis.get('query_type')
    if query_type in ('general', 'system_meta'):
        return 'generation'

    # ... 기존 로직 ...
```

### Phase 5: Recursion Limit 버그 수정

#### recursion_limit 설정 (`main.py`)

```python
GRAPH_RECURSION_LIMIT = 50  # 기본 25 → 50

if request.chat_type == 'general':
    simple_config = {"recursion_limit": GRAPH_RECURSION_LIMIT}
    final_state = await asyncio.to_thread(graph.invoke, initial_state, simple_config)
else:
    config = {
        "configurable": {"thread_id": session_id},
        "recursion_limit": GRAPH_RECURSION_LIMIT
    }
    final_state = await asyncio.to_thread(graph.invoke, initial_state, config)
```

#### MAX_TOTAL_ITERATIONS 안전장치 (`routing.py`)

```python
MAX_TOTAL_ITERATIONS = 15  # search_round + retry_count 합산 최대값

def route_after_sufficiency(state: ChatState_v2) -> str:
    search_round = state.get('search_round', 0)
    retry_count = state.get('retry_count', 0)
    total_iterations = search_round + retry_count

    if total_iterations >= MAX_TOTAL_ITERATIONS:
        logger.warning(f"MAX_TOTAL_ITERATIONS reached, forcing generation")
        return 'generation'

    # ... 기존 로직 ...
```

## 환경 변수 설정

```bash
# .env 파일

# 문서 수준 유사도 검색 활성화 (기본: true)
ENABLE_DOCUMENT_LEVEL_SIMILARITY=true

# 후보 청크 배수 (top_k * N개 검색, 기본: 5)
DOCUMENT_SIMILARITY_CANDIDATE_MULTIPLIER=5

# 메타데이터 추출 활성화 (기본: true)
ENABLE_DISPUTE_METADATA_EXTRACTION=true
```

## 테스트

### 로그 출력 확인

```bash
# 새 로그 파일 확인
cat /home/maroco/LLM/backend/app/logs/rag/2026-01-20/HHMMSS_*.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
for node in d.get('node_timings', []):
    print(f\"Node: {node['node_name']}\")
    print(f\"  Input: {list(node.get('input_snapshot', {}).keys())}\")
    print(f\"  Output: {list(node.get('output_snapshot', {}).keys())}\")
    print(f\"  Changes: {node.get('state_changes', [])}\")
"
```

### system_meta 쿼리 분류 테스트

```python
# 테스트 결과
# "네 모델명이 뭐야?" → is_meta=True, type=system_meta
# "니가 뭐야?"        → is_meta=True, type=system_meta
# "안녕"             → is_meta=False, type=general
# "노트북 환불"       → is_meta=False, type=dispute
```

## 파일 구조

```
backend/
├── app/
│   ├── common/
│   │   └── logger.py              # 수정: NodeTimingLog, DisputeLog 확장
│   ├── orchestrator/
│   │   ├── graph.py               # 수정: NODE_SNAPSHOT_FIELDS, ReAct 라우팅
│   │   ├── state.py               # 수정: query_type에 system_meta 추가
│   │   └── routing.py             # 수정: MAX_TOTAL_ITERATIONS
│   ├── agents/
│   │   ├── query_analysis/
│   │   │   └── agent.py           # 수정: system_meta 감지
│   │   └── retrieval/
│   │       └── tools/
│   │           └── specialized_retrievers.py  # 수정: 문서 수준 유사도
│   └── main.py                    # 수정: recursion_limit 설정
├── scripts/
│   └── data_loading/
│       └── migrate_chunk_relations.py  # 신규: chunk_relations 마이그레이션
```

## 로그 출력 예시

```json
{
  "query": "헬스장 환불 가능한가요?",
  "node_timings": [
    {
      "node_name": "query_analysis",
      "duration_ms": 1.28,
      "input_snapshot": {
        "user_query": "헬스장 환불 가능한가요?",
        "chat_type": "dispute"
      },
      "output_snapshot": {
        "query_analysis": {"query_type": "dispute", "keywords": ["헬스장", "환불"]},
        "mode": "NEED_RAG"
      },
      "state_changes": ["~query_analysis", "+query_analysis_v2", "+mode"]
    },
    {
      "node_name": "retrieval",
      "duration_ms": 2317.03,
      "input_snapshot": {
        "user_query": "헬스장 환불 가능한가요?",
        "query_analysis": {...}
      },
      "output_snapshot": {
        "retrieval": {
          "disputes": [...],  // 문서 수준 유사도로 선택된 사례
          "counsels": [...]
        }
      },
      "state_changes": ["~retrieval", "~sources"]
    }
  ],
  "structured_retrieval": {
    "disputes": [
      {
        "doc_id": "KCA_00123",
        "doc_title": "헬스장 회원권 환불 분쟁",
        "similarity": 0.72,
        "product_item": "헬스장 회원권",      // Phase 2: LLM 추출
        "dispute_amount": "890,000원",        // Phase 2: LLM 추출
        "mediation_result": "조정성립"        // Phase 2: LLM 추출
      }
    ]
  }
}
```

## 성능 영향

| 항목 | 변경 전 | 변경 후 | 비고 |
|------|---------|---------|------|
| 로그 파일 크기 | ~8KB | ~20KB | I/O 스냅샷 추가 |
| 검색 시간 | ~2.3s | ~2.5s | 후보 청크 증가 |
| 메타데이터 추출 | N/A | +1~2s | LLM 호출 (비활성화 가능) |
| Recursion 에러 | 발생 | 방지 | limit 50 + 안전장치 |

## 관련 이슈

- 로그 분석에서 발견된 Recursion limit 에러 해결
- "네 모델명이 뭐야?" 불필요 검색 방지
- 분쟁조정사례 메타데이터 부재 해결
- 에이전트 간 데이터 흐름 가시성 확보
