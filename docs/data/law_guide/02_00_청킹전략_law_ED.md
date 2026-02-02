# 법률 및 시행령 청킹 전략 초안

---

## 1. 개요

### 1.1 대상 데이터
- **문서 유형**: 법률 11개, 시행령 8개 (JSON 파싱 완료)
- **위치**: `raw/01_law_ED/`
- **구조**: 편-장-절-관-조-항-호-목 위계 구조
- **특징**: 조문 간 준용/참조 관계, 법률-시행령 위임 관계

### 1.2 목표
- PostgreSQL + pgvector를 활용한 의미적 검색
- Neo4j를 활용한 조문 간 관계 그래프 구축
- **실제 사례 질문에 대한 법률 조항 검색 최적화**
- 법률 특성을 고려한 효율적인 RAG 시스템 구축

### 1.3 기술 스택
- **임베딩**: OpenAI text-embedding-3-large (MRL 1536 차원)
- **사례 생성**: OpenAI GPT-4o-mini (비용 효율적)
- **벡터 DB**: PostgreSQL + pgvector
- **그래프 DB**: Neo4j

### 1.4 구현 파일
- **이 전략의 구현**: `02_01_chunking_law_ED.py` (법률, 시행령)
- **별도 전략**: `02_02_chunking_guide.py` (소비자분쟁해결기준 등)

---

## 2. 법률 문서의 특수성

### 2.1 위계 구조 (Hierarchy)
```
편 (民法, 商法 등 대형 법전에만 존재)
 └─ 장 (대부분의 법률)
     └─ 절 (일부 법률)
         └─ 관 (款, 매우 드물게 사용)
             └─ 조 (條, 핵심 단위)
                 └─ 항 (項, ①②③)
                     └─ 호 (號, 1. 2. 3.) ← 최소 청킹 단위
                         └─ 목 (目, 가. 나. 다.) ← 호에 포함
```

**중요**:
- **호(號)가 최소 청킹 단위**
- **목(目)은 호에 포함** (별도 청크로 분할하지 않음)

### 2.2 조문 간 참조 관계 (Cross-References)

#### (1) 준용 (準用)
```
"제3조제1항을 준용한다"
→ 다른 조문의 규정을 끌어와 적용
```

#### (2) 위임 (委任)
```
법률: "구체적인 사항은 대통령령으로 정한다"
시행령: "법 제10조제2항에 따라 다음과 같이 정한다"
→ 법률-시행령 연결
```

#### (3) 단순 참조
```
"제5조에 따른 기준을 충족하는 경우"
→ 다른 조문의 내용을 전제로 함
```

---

## 3. 청킹 전략 선택

### 3.1 전략 비교

| 전략 | 적합성 | 이유 |
|------|--------|------|
| **메타데이터 인식 청킹** | ⭐⭐⭐ | 편-장-절-관-조-항-호-목 구조가 명확히 파싱되어 있음 |
| 레이아웃 인식 청킹 | ❌ | 이미 JSON 파싱 완료, 레이아웃 정보 불필요 |
| 의미적 청킹 | △ | 조문 간 논리적 연결은 중요하나, 법률은 조문 단위로 이미 의미 단위가 명확함 |
| 볼린저 밴드 기반 청킹 | ❌ | 법률은 임베딩 유사도보다 구조적 경계가 중요 |

### 3.2 권장: **메타데이터 인식 청킹 + 그래프 보강 + 사례 증강**

**핵심 원칙**:
1. **조(條) 단위를 기본 청크**로 설정
2. **위계 메타데이터** 포함 (편-장-절-관-조 경로)
3. **조문 간 참조 관계**를 Neo4j 그래프로 표현
4. **법률-시행령 연결**을 그래프로 표현
5. **실제 사례 예시**를 합성하여 청크 증강 (RAG 최적화)

---

## 4. 청킹 단위 결정

### 4.1 청킹 유형 (3가지)

| 유형 | 설명 | 예시 | 사용 조건 |
|------|------|------|----------|
| **조_전체** | 조문 전체를 하나의 청크로 | 제1조(목적) 전체 | 조문이 짧고 응집도 높음 |
| **항_분할** | 항(①②③) 단위로 분할 | 제108조①, 제108조② | 긴 조문 + 항으로 구분된 경우 |
| **호_분할** | 호(1.2.3.) 단위로 분할<br>**목(가나다)은 호에 포함!** | 제2조(정의) 1호, 2호<br>(각 호에 목 포함) | 조 다음 바로 호 나열 + 각 호가 독립적 |

### 4.2 왜 "목"은 별도 청크로 분할하지 않는가?

**목을 호에 포함하는 이유**:

| 이유 | 설명 |
|------|------|
| **의미적 완결성** | 목은 호의 세부 조건/항목으로, 호와 분리하면 의미 불완전 |
| **너무 세분화** | 목까지 분할하면 청크가 너무 작아져서 검색 비효율 (목 하나는 보통 20-100자) |
| **법률 인용 관행** | 실무에서는 "제X조제Y호" 단위로 인용<br>"제X조제Y호 가목"까지 세밀하게 인용하는 경우는 상대적으로 드뭄 |
| **적절한 청크 크기** | 호(+목 포함) = 보통 100-500자로 검색에 적절 |
| **맥락 보존** | 목은 호의 하위 항목이므로 함께 있어야 전체 의미 파악 가능 |

**예시**:

```json
// 원본 JSON
{
  "조문번호": "제2조",
  "조문제목": "정의",
  "내용": [
    {"본문": "이 법에서 사용하는 용어의 뜻은 다음과 같다."},
    {
      "호": "5",
      "내용": "\"다단계판매\"란 다음 각 목의 요건을 모두 갖춘 것을 말한다.",
      "세부": [
        {"목": "가", "내용": "판매업자에 속한 판매원이 특정인을 해당 판매업자의 판매원으로 가입하도록 권유"},
        {"목": "나", "내용": "가목에 따른 판매원의 가입이 3단계 이상의 단계적 판매조직을 통하여 이루어지는 것"}
      ]
    }
  ]
}

// 청킹 결과: 5호 전체를 하나의 청크로 (가목, 나목 포함!)
{
  "chunk_id": "방문판매법_제2조_5호",
  "chunk_type": "호_분할",
  "호번호": "5",
  "text": """
제2조(정의)
이 법에서 사용하는 용어의 뜻은 다음과 같다.

5. "다단계판매"란 다음 각 목의 요건을 모두 갖춘 것을 말한다.
   가. 판매업자에 속한 판매원이 특정인을 해당 판매업자의 판매원으로 가입하도록 권유
   나. 가목에 따른 판매원의 가입이 3단계 이상의 단계적 판매조직을 통하여 이루어지는 것
  """
}

// ❌ 잘못된 예: 가목, 나목을 각각 청크로 분할
// → 너무 세분화, 맥락 손실, 검색 비효율
```

### 4.3 청크 크기 기준

**왜 1000자인가?**

| 요소 | 설명 |
|------|------|
| **임베딩 모델 최적 길이** | 대부분의 임베딩 모델은 512-1024 토큰에서 최적 성능 |
| **한국어 토큰 비율** | 한국어 1자 ≈ 1-2 토큰 |
| **계산** | 1000자 ≈ 1000-2000 토큰 (임베딩 모델 최적 범위) |
| **검색 정밀도** | 너무 긴 청크는 여러 주제 포함 → 검색 정밀도 하락 |
| **실험적 조정** | 실제 검색 성능 측정 후 700-1500자 범위에서 조정 가능 |

### 4.4 청크 분할 로직

```python
def determine_chunk_type(조문: dict) -> str:
    """청크 유형 결정"""

    조문_텍스트 = build_article_text(조문)
    조문_길이 = len(조문_텍스트)
    내용 = 조문["내용"]

    # 1순위: 짧은 조문은 무조건 조_전체
    if 조문_길이 < 500:
        return "조_전체"

    # 2순위: 호 분할 (조 다음 바로 호가 나오는 경우)
    # 예: "제4조(소비자의 권리) 소비자는 다음 각 호의 권리를 가진다. 1. ... 2. ..."
    if has_직접_호(내용):
        호_개수 = count_호(내용)
        if 호_개수 >= 3:  # 호가 3개 이상이면 분할
            return "호_분할"

    # 3순위: 항 분할 (긴 조문 + 항 존재)
    if 조문_길이 >= 1000 and has_항(내용):
        return "항_분할"

    # 기본값: 조_전체
    return "조_전체"


def has_직접_호(내용: List[dict]) -> bool:
    """조 다음에 항 없이 바로 호가 나오는지 확인"""
    for item in 내용:
        if "본문" in item:
            continue
        # 항이 아닌 호가 먼저 나오면 True
        if "호" in item and "항번호" not in item:
            return True
        # 항이 먼저 나오면 False
        if "항번호" in item:
            return False
    return False


def count_호(내용: List[dict]) -> int:
    """호의 개수 세기"""
    count = 0
    for item in 내용:
        if "호" in item:
            count += 1
    return count
```

### 4.5 호 분할 시 본문 포함 전략 ⭐ **중요**

**문제**:
```
제4조(소비자의 기본적 권리) 소비자는 다음 각 호의 기본적 권리를 가진다.
1. 물품 또는 용역...
2. 물품등을 선택함에...
```

호를 분할하면 "소비자는 다음 각 호의 기본적 권리를 가진다"라는 **도입 본문**이 손실됨.

**해결책**: 모든 호 청크에 **도입 본문을 포함**

```python
def split_by_호(조문번호, 조문제목, 내용, hierarchy, path) -> List[Dict]:
    """호 단위로 청크 분할 (목 포함!)"""

    chunks = []

    # 1. 도입 본문 추출 (조문번호 + 제목 + 본문들)
    도입_본문 = f"{조문번호}({조문제목})"

    for item in 내용:
        if "본문" in item:
            도입_본문 += "\n" + item["본문"]

    # 2. 각 호를 개별 청크로 생성 (도입 본문 포함!)
    for item in 내용:
        if "호" in item:
            호_번호 = item["호"]
            호_내용 = item["내용"]

            # 호 텍스트 = 도입 본문 + 해당 호 + 목(세부)
            chunk_text = f"{도입_본문}\n\n{호_번호}. {호_내용}"

            # 세부(목) 포함 - 목은 별도 청크로 분할하지 않음!
            if "세부" in item:
                chunk_text += "\n" + format_세부(item["세부"])

            chunk = create_chunk(
                chunk_type="호_분할",
                text=chunk_text,
                호번호=호_번호,
                원문_조문=조문번호,
                hierarchy=hierarchy,
                path=path,
                ...
            )
            chunks.append(chunk)

    return chunks


def format_세부(세부: List[Dict], indent: int = 1) -> str:
    """목/호 세부 내용 포맷팅 (재귀적으로 처리)"""

    lines = []
    prefix = "   " * indent  # 들여쓰기

    for item in 세부:
        if "호" in item:
            lines.append(f'{prefix}{item["호"]}. {item["내용"]}')
        elif "목" in item:
            lines.append(f'{prefix}{item["목"]}. {item["내용"]}')

        # 중첩된 세부 항목 (목 아래에 또 항목이 있는 경우)
        if "세부" in item:
            lines.append(format_세부(item["세부"], indent + 1))

    return "\n".join(lines)
```

**결과 예시**:

```json
// 청크 1: 제4조 1호
{
  "chunk_id": "소비자기본법_제4조_1호",
  "chunk_type": "호_분할",
  "원문_조문": "제4조",
  "호번호": "1",
  "text": """
제4조(소비자의 기본적 권리)
소비자는 다음 각 호의 기본적 권리를 가진다.

1. 물품 또는 용역(이하 "물품등"이라 한다)으로 인한 생명ㆍ신체 또는 재산에 대한 위해로부터 보호받을 권리
  """
}

// 청크 2: 제2조 5호 (목 포함!)
{
  "chunk_id": "방문판매법_제2조_5호",
  "chunk_type": "호_분할",
  "원문_조문": "제2조",
  "호번호": "5",
  "text": """
제2조(정의)
이 법에서 사용하는 용어의 뜻은 다음과 같다.

5. "다단계판매"란 다음 각 목의 요건을 모두 갖춘 것을 말한다.
   가. 판매업자에 속한 판매원이 특정인을 해당 판매업자의 판매원으로 가입하도록 권유
   나. 가목에 따른 판매원의 가입이 3단계 이상의 단계적 판매조직을 통하여 이루어지는 것
  """
}
```

**장점**:
1. 각 호가 **독립적으로 검색 가능** (도입 본문 덕분에 맥락 유지)
2. **목이 호와 함께** 있어서 전체 의미 파악 가능
3. 검색 결과에서 사용자가 **어떤 조문의 몇 호인지 즉시 파악 가능**
4. 호별로 세밀한 검색 가능

**메타데이터 활용**:
```python
# 같은 조의 다른 호들 검색
SELECT * FROM chunks
WHERE 원문_조문 = '제4조'
  AND chunk_type = '호_분할'
ORDER BY 호번호;

# 특정 호 검색
SELECT * FROM chunks
WHERE 원문_조문 = '제4조'
  AND 호번호 = '1';

# 원문 조문의 모든 청크 (조_전체 또는 모든 호)
SELECT * FROM chunks
WHERE 원문_조문 = '제4조';
```

---

## 5. 메타데이터 설계

### 5.1 메타데이터 구조

```json
{
  "chunk_id": "소비자기본법_제4조_1호",
  "법령명": "소비자기본법",
  "법령번호": "법률 제21065호",
  "시행일": "2026-01-02",

  // 위계 정보
  "편": null,
  "장": "제1장 총칙",
  "절": null,
  "관": null,

  // 조문 정보
  "조문번호": "제4조",
  "조문제목": "소비자의 기본적 권리",
  "항번호": null,
  "호번호": "1",  // 호 분할인 경우
  "원문_조문": "제4조",  // 항/호 분할 시 원 조문

  // 청크 타입
  "chunk_type": "호_분할",  // "조_전체" | "항_분할" | "호_분할"

  // 전체 텍스트 (도입 본문 + 해당 호 + 목 포함!)
  "text": "제4조(소비자의 기본적 권리)\n소비자는 다음 각 호의 기본적 권리를 가진다.\n\n1. 물품 또는 용역...",

  // 위계 경로
  "hierarchy_path": "제1장 총칙 > 제4조 소비자의 기본적 권리",

  // 법령 유형
  "법령유형": "법률",
  "모법": null,

  // 참조 관계
  "참조조문": [],
  "준용조문": [],
  "위임대상": [],
  "위임근거": null,

  // RAG 최적화
  "keywords": ["소비자권리", "생명", "신체", "재산", "위해", "보호"],
  "example_cases": [
    "제품 사용 중 다쳐서 보상받고 싶은 경우",
    "위험한 제품으로부터 보호받고 싶은 경우"
  ]
}
```

### 5.2 PostgreSQL 인덱스

```sql
CREATE INDEX idx_법령명 ON chunks(법령명);
CREATE INDEX idx_조문번호 ON chunks(조문번호);
CREATE INDEX idx_원문_조문 ON chunks(원문_조문);  -- 같은 조의 다른 청크 찾기
CREATE INDEX idx_호번호 ON chunks(호번호) WHERE 호번호 IS NOT NULL;
CREATE INDEX idx_chunk_type ON chunks(chunk_type);
CREATE INDEX idx_hierarchy ON chunks USING GIN(to_tsvector('korean', hierarchy_path));
CREATE INDEX idx_참조조문 ON chunks USING GIN(참조조문);
CREATE INDEX idx_keywords ON chunks USING GIN(keywords);
CREATE INDEX idx_example_cases ON chunks USING GIN(to_tsvector('korean', array_to_string(example_cases, ' ')));
CREATE INDEX idx_text_search ON chunks USING GIN(to_tsvector('korean', text));
CREATE INDEX idx_embedding ON chunks USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
```

---

## 6. 실제 사례 → 법률 조항 매핑 전략

### 6.1 문제 정의

**사용자 질문 유형**:
| 사용자 입력 | 목표 법률 조항 | 문제점 |
|------------|--------------|--------|
| "사기를 당했는데 돈을 못 돌려받고 있어" | 민법 제108조 (사기, 강박) | "사기를 당했어"와 "사기나 강박에 의한 의사표시는 취소할 수 있다" 간 의미적 거리 |
| "온라인으로 노트북을 구매했는데, 디자인이 마음에 들지 않아서 환불하고 싶어" | 전자상거래법 제17조 (청약철회) | "환불"과 "청약철회" 용어 차이 |

**핵심 과제**: 일상 언어 ↔ 법률 용어 간 간극(semantic gap) 해소

### 6.2 해결 전략

#### 전략 1: 청크 증강 (Chunk Augmentation)

**OpenAI API를 사용한 사례 생성**:

```python
from openai import OpenAI

client = OpenAI(api_key="YOUR_OPENAI_API_KEY")

CASE_GENERATION_PROMPT = """
다음 법률 조문을 읽고, 일반인이 실제로 겪을 수 있는 구체적인 상황 3가지를 생성해주세요.

[조문 정보]
법령명: {법령명}
조문번호: {조문번호}
조문제목: {조문제목}
조문내용:
{text}

[생성 규칙]
1. 일상적인 언어로 작성 (법률 용어 최소화)
2. "~한 경우", "~하고 싶은 경우" 형식으로 끝나야 함
3. 구체적인 상황 묘사 (예: "온라인으로 노트북을 구매했는데...")
4. 각 사례는 50자 이내로 간결하게
5. 이 조문이 실제로 적용될 수 있는 현실적인 상황이어야 함

[출력 형식]
JSON 형식으로만 답변:
{{
  "사례들": ["사례1", "사례2", "사례3"]
}}
"""

def generate_example_cases(chunk: dict) -> List[str]:
    """OpenAI API로 사례 예시 생성"""

    prompt = CASE_GENERATION_PROMPT.format(
        법령명=chunk["법령명"],
        조문번호=chunk["조문번호"],
        조문제목=chunk["조문제목"],
        text=chunk["text"]
    )

    response = client.chat.completions.create(
        model="gpt-4o-mini",  # 비용 효율적
        messages=[
            {"role": "system", "content": "당신은 법률 조문을 일반인이 이해할 수 있는 실제 사례로 변환하는 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.7,
        response_format={"type": "json_object"}
    )

    result = json.loads(response.choices[0].message.content)
    return result.get("사례들", [])


def is_high_priority(chunk: dict) -> bool:
    """우선순위 조문 판단 (사례 생성 대상)"""

    # 소비자 보호 관련
    if any(keyword in chunk["법령명"] for keyword in ["소비자", "전자상거래", "방문판매", "약관", "할부"]):
        return True

    # 민법 주요 조문
    if chunk["법령명"] == "민법":
        주요_키워드 = ["계약", "취소", "해제", "손해배상", "사기", "강박", "착오", "불법행위"]
        if any(kw in chunk["text"] for kw in 주요_키워드):
            return True

    return False
```

#### 전략 2: 쿼리 확장 (Query Expansion)

```python
def expand_user_query(user_query: str) -> dict:
    """사용자 질문을 법률 용어로 확장"""

    prompt = f"""
사용자의 질문을 분석하여 다음 정보를 JSON 형식으로 추출해주세요:

사용자 질문: "{user_query}"

추출할 정보:
1. keywords: 핵심 키워드 3-5개 (일상 언어)
2. estimated_laws: 관련 법령명 추정 (최대 3개)
3. legal_terms: 예상되는 법률 용어 3-5개
4. situation_type: 상황 유형 (계약분쟁, 소비자피해, 손해배상 등)

JSON 형식:
{{
  "keywords": ["키워드1", "키워드2", ...],
  "estimated_laws": ["법령명1", ...],
  "legal_terms": ["법률용어1", ...],
  "situation_type": "상황유형"
}}
"""

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "당신은 사용자의 질문을 분석하여 관련 법률 정보를 추출하는 전문가입니다."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
        response_format={"type": "json_object"}
    )

    return json.loads(response.choices[0].message.content)
```

#### 전략 3: 하이브리드 검색

```python
def search_law_for_case(user_query: str, top_k: int = 5) -> List[Dict]:
    """실제 사례에 대한 법률 조항 검색"""

    # 1. 쿼리 확장
    expanded = expand_user_query(user_query)

    results_pool = []

    # 2. 사례 예시 검색 (가장 중요!)
    case_results = db.execute("""
        SELECT *,
               ts_rank(to_tsvector('korean', array_to_string(example_cases, ' ')),
                       plainto_tsquery('korean', %s)) as case_rank
        FROM chunks
        WHERE example_cases IS NOT NULL
          AND array_length(example_cases, 1) > 0
          AND to_tsvector('korean', array_to_string(example_cases, ' '))
              @@ plainto_tsquery('korean', %s)
        ORDER BY case_rank DESC
        LIMIT %s
    """, (user_query, user_query, top_k * 2))
    results_pool.extend(add_weight(case_results, weight=3.0))

    # 3. 벡터 검색
    query_embedding = embed(user_query)
    vector_results = db.execute("""
        SELECT *, 1 - (embedding <=> %s) as similarity
        FROM chunks
        WHERE 법령명 = ANY(%s)
        ORDER BY embedding <=> %s
        LIMIT %s
    """, (query_embedding, expanded["estimated_laws"], query_embedding, top_k))
    results_pool.extend(add_weight(vector_results, weight=2.0))

    # 4. Weighted RRF 병합
    merged = weighted_reciprocal_rank_fusion(results_pool, k=60)

    # 5. LLM 리랭킹
    reranked = rerank_with_llm(user_query, merged[:top_k * 3], top_k)

    return reranked
```

---

## 7. 임베딩 전략: OpenAI text-embedding-3-large + MRL

### 7.1 Matryoshka Representation Learning (MRL)

**기본 개념**:
- text-embedding-3-large는 3072 차원 출력
- MRL 기법으로 학습되어 **앞쪽 일부 차원만 사용해도 성능 유지**
- 1536 차원만 사용하면 **저장 공간 50% 절감 + 검색 속도 향상**

**성능 비교**:

| 모델 | 차원 | 저장 용량 (1500 청크) | 검색 속도 | 성능 |
|------|------|---------------------|----------|------|
| text-embedding-3-small | 1536 | ~9MB | 빠름 | 기준 100% |
| text-embedding-3-large (full) | 3072 | ~18MB | 중간 | 105-110% |
| **text-embedding-3-large (MRL 1536)** | **1536** | **~9MB** | **빠름** | **103-107%** ⭐ |

**결론**: MRL을 사용하면 **small 모델과 동일한 용량으로 large 모델의 성능** 획득!

### 7.2 구현 코드

```python
from openai import OpenAI

client = OpenAI(api_key="YOUR_OPENAI_API_KEY")

def embed_text(text: str) -> List[float]:
    """OpenAI text-embedding-3-large with MRL"""

    response = client.embeddings.create(
        model="text-embedding-3-large",
        input=text,
        dimensions=1536,  # MRL: 3072 → 1536 차원으로 축소
        encoding_format="float"
    )

    return response.data[0].embedding


def embed_chunks_batch(chunks: List[Dict]) -> List[Dict]:
    """청크들을 배치 임베딩"""

    # 임베딩할 텍스트 구성: text + example_cases 결합
    for chunk in chunks:
        embed_content = chunk["text"]

        # 사례 예시가 있으면 추가
        if chunk.get("example_cases"):
            cases_text = "\n".join([f"[사례] {case}" for case in chunk["example_cases"]])
            embed_content += "\n\n" + cases_text

        chunk["_embed_content"] = embed_content

    # 배치 임베딩 (최대 100개씩)
    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        texts = [c["_embed_content"] for c in batch]

        response = client.embeddings.create(
            model="text-embedding-3-large",
            input=texts,
            dimensions=1536,  # MRL
            encoding_format="float"
        )

        for j, chunk in enumerate(batch):
            chunk["embedding"] = response.data[j].embedding
            del chunk["_embed_content"]

        print(f"임베딩 진행: {i+len(batch)}/{len(chunks)}")
        time.sleep(0.1)  # Rate limit 방지

    return chunks
```

### 7.3 비용 계산

```python
# 예상 비용 (2026년 1월 기준)
조문_수 = 1500
평균_토큰_수 = 500  # 조문 + 사례
총_토큰 = 조문_수 * 평균_토큰_수

# text-embedding-3-large 비용: $0.13 / 1M tokens
임베딩_비용 = (총_토큰 / 1_000_000) * 0.13

# 사례 생성 비용 (gpt-4o-mini: $0.150 input / $0.600 output per 1M tokens)
우선순위_조문_수 = 150
입력_토큰_per_조문 = 300
출력_토큰_per_조문 = 100
사례_생성_비용 = (우선순위_조문_수 * 입력_토큰_per_조문 / 1_000_000) * 0.150 + \
                 (우선순위_조문_수 * 출력_토큰_per_조문 / 1_000_000) * 0.600

print(f"예상 임베딩 비용: ${임베딩_비용:.2f}")  # 약 $0.10
print(f"예상 사례 생성 비용: ${사례_생성_비용:.3f}")  # 약 $0.016
print(f"총 예상 비용: ${임베딩_비용 + 사례_생성_비용:.2f}")  # 약 $0.12
```

---

## 8. PostgreSQL + pgvector 스키마

```sql
CREATE TABLE chunks (
    chunk_id TEXT PRIMARY KEY,

    -- 기본 정보
    법령명 TEXT NOT NULL,
    법령번호 TEXT,
    시행일 DATE,
    법령유형 TEXT CHECK (법령유형 IN ('법률', '시행령')),
    모법 TEXT,

    -- 위계 정보
    편 TEXT,
    장 TEXT,
    절 TEXT,
    관 TEXT,
    조문번호 TEXT NOT NULL,
    조문제목 TEXT,
    항번호 TEXT,
    호번호 TEXT,  -- 호 분할인 경우

    -- 청크 정보
    chunk_type TEXT CHECK (chunk_type IN ('조_전체', '항_분할', '호_분할')),
    원문_조문 TEXT,
    hierarchy_path TEXT,

    -- 내용
    text TEXT NOT NULL,
    text_length INTEGER,

    -- 참조 관계
    참조조문 TEXT[],
    준용조문 TEXT[],
    위임대상 TEXT[],
    위임근거 TEXT,

    -- RAG 최적화
    keywords TEXT[],
    example_cases TEXT[],

    -- 벡터 임베딩 (MRL 1536 차원)
    embedding vector(1536),

    -- 메타데이터
    metadata JSONB,

    -- 타임스탬프
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 인덱스
CREATE INDEX idx_법령명 ON chunks(법령명);
CREATE INDEX idx_조문번호 ON chunks(조문번호);
CREATE INDEX idx_원문_조문 ON chunks(원문_조문);
CREATE INDEX idx_호번호 ON chunks(호번호) WHERE 호번호 IS NOT NULL;
CREATE INDEX idx_chunk_type ON chunks(chunk_type);
CREATE INDEX idx_keywords ON chunks USING GIN(keywords);
CREATE INDEX idx_example_cases ON chunks USING GIN(to_tsvector('korean', array_to_string(example_cases, ' ')));
CREATE INDEX idx_embedding ON chunks USING ivfflat(embedding vector_cosine_ops) WITH (lists = 100);
```

---

## 9. 청킹 파이프라인

### 9.1 전체 흐름

```
┌─────────────────┐
│ raw/01_law_ED/  │
│ JSON 파일들      │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 1. 조문 추출     │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 2. 청크 분할     │  ← 조_전체 / 항_분할 / 호_분할
│  (호 분할 시     │     (호에 목 포함!)
│   도입 본문 포함) │
└────────┬────────┘
         ▼
┌─────────────────┐
│ 3. 메타데이터    │  ← 키워드, 참조 관계
└────────┬────────┘
         ▼
┌─────────────────┐
│ 4. 사례 생성     │  ← OpenAI gpt-4o-mini
│  (우선순위 150개)│
└────────┬────────┘
         ▼
┌─────────────────┐
│ 5. 임베딩        │  ← OpenAI text-embedding-3-large
│  (MRL 1536)      │     (text + example_cases)
└────────┬────────┘
         ▼
┌─────────────────┬─────────────────┐
│ 6. PostgreSQL    │ 7. Neo4j        │
│    저장          │    그래프 구축   │
└─────────────────┴─────────────────┘
```

---

## 10. 구현 우선순위

### Phase 1: 기본 청킹 (1-2일)
- [ ] JSON 파일 읽기
- [ ] 3가지 청킹 유형 구현
  - [ ] 조_전체
  - [ ] 항_분할
  - [ ] 호_분할 (도입 본문 포함 + **목 포함**)
- [ ] 메타데이터 구축
- [ ] 키워드 추출
- [ ] PostgreSQL 저장
- [ ] **샘플 테스트**: "소비자기본법.json" 제4조 호 분할 확인

### Phase 2: 참조 관계 추출 (1일)
- [ ] 정규식 패턴 구현
- [ ] 준용/참조/위임 추출

### Phase 3: 사례 증강 (1-2일)
- [ ] 우선순위 조문 150개 선정
- [ ] OpenAI gpt-4o-mini로 사례 생성
- [ ] 청크 업데이트

### Phase 4: 임베딩 (1일)
- [ ] OpenAI text-embedding-3-large (MRL 1536)
- [ ] 배치 처리
- [ ] pgvector 저장

### Phase 5: Neo4j (2일)
- [ ] 그래프 구축
- [ ] 관계 생성

### Phase 6: 검색 최적화 (2-3일)
- [ ] 하이브리드 검색
- [ ] 쿼리 확장
- [ ] 리랭킹
- [ ] 실제 사례 테스트 (20개 질문)

---

## 11. 예상 데이터 규모 및 비용

| 항목 | 예상 수량/비용 |
|------|---------------|
| 전체 법령 수 | 19개 (법률 11 + 시행령 8) |
| 총 조문 수 | ~600개 |
| 청크 수 | ~1,500개 (호 분할 포함) |
| 우선순위 사례 생성 | 150개 조문 × 3사례 = 450개 사례 |
| **사례 생성 비용** | **~$0.02** (gpt-4o-mini) |
| **임베딩 비용** | **~$0.10** (text-embedding-3-large MRL) |
| **총 비용** | **~$0.12** |
| PostgreSQL 크기 | ~50MB (임베딩 포함) |
| Neo4j 노드 | ~2,500개 |
| Neo4j 관계 | ~5,000개 |

---

## 12. 핵심 전략 요약

### 청킹 단위
1. **조_전체**: 짧은 조문 (< 500자)
2. **항_분할**: 긴 조문 + 항 존재 (≥ 1000자)
3. **호_분할**: 조 다음 바로 호 나열 (≥ 3개 호)
   - ⭐ **도입 본문 포함**: 각 호 청크에 조문번호+제목+본문 포함
   - ⭐ **목(目)은 호에 포함**: 목을 별도 청크로 분할하지 않음

### RAG 최적화
1. **사례 증강**: OpenAI gpt-4o-mini로 일상 언어 사례 생성
2. **MRL 임베딩**: text-embedding-3-large 1536 차원 (성능+용량 최적화)
3. **하이브리드 검색**: 사례 매칭 + 벡터 검색 + 키워드 검색
4. **리랭킹**: GPT-4o로 최종 정렬

---

**작성일**: 2026-01-19
**구현 파일**: `02_01_chunking_law_ED.py`
**다음 전략**: `02_02_chunking_guide.py` (소비자분쟁해결기준 등)
