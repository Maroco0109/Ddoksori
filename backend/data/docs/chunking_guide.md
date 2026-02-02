# 청킹 가이드라인

본 문서는 Dispute/Counsel 데이터의 청킹 단위, 출처 표준화 형식, 검색 우선순위 등을 정의합니다.

## 1. Counsel 데이터 청킹 단위

Counsel 데이터는 질의응답 구조로 되어 있어 다음과 같이 청킹됩니다:

| 청크 타입 | 설명 | 예시 chunk_id | 검색 우선순위 |
|---------|------|--------------|-------------|
| `problem` | 사용자 질문 부분 | `53321:problem:0000` | 높음 |
| `solution` | 답변 부분 | `53321:solution:0001` | 높음 |
| `full` | 질문+답변 전체 | `53321:full:0002` | 중간 |

### 청킹 규칙

- 각 counsel 사례는 최소 3개의 청크로 구성됩니다:
  1. `problem`: 질문만 포함
  2. `solution`: 답변만 포함
  3. `full`: 질문과 답변을 모두 포함한 전체 텍스트

- `chunk_id` 형식: `{doc_id}:{chunk_type}:{chunk_index:04d}`
  - 예: `53321:problem:0000`, `53321:solution:0001`, `53321:full:0002`

- `chunk_index`는 0부터 시작하며, 동일 문서 내에서 순차적으로 증가합니다.

## 2. Dispute 데이터 청킹 단위

Dispute 데이터는 분쟁조정사례 문서 구조에 따라 다음과 같이 청킹됩니다:

| 청크 타입 | 설명 | 예시 chunk_id | 검색 우선순위 |
|---------|------|--------------|-------------|
| `facts` | 사건개요, 사실관계 | `kca_16713:facts:0001` | 매우 높음 |
| `claims` | 당사자 주장 | `kca_16713:claims:0001` | 높음 |
| `mediation_outcome` | 조정결과, 조정안 | `kca_16713:mediation_outcome:0001` | 높음 |
| `judgment` | 판단, 결정 | `kca_16713:judgment:0001` | 중간 |
| `decision` | 결정문 | `kca_16713:decision:0001` | 중간 |
| 기타 | 기타 섹션 | `kca_16713:{section_type}:0001` | 낮음 |

### 청킹 규칙

- Dispute 데이터는 원본 PDF의 `section_type` 필드를 그대로 `chunk_type`으로 사용합니다.

- `chunk_id` 형식: `{doc_id}:{section_type}:{chunk_index:04d}`
  - 예: `kca_16713:facts:0001`, `ecmc_01279:claims:0001`

- `doc_id` 형식: `{agency}_{case_no}` 또는 `{agency}_{source_pdf}_{case_index}`
  - 예: `kca_16713`, `ecmc_01279`, `kcdrc_00013`

- 각 청크는 `page_start`와 `page_end` 정보를 metadata에 포함합니다.

## 3. 출처 표준화 형식

### 문서 식별자

- **Counsel**: `doc_id` 필드 사용 (예: `53321`)
- **Dispute**: `{agency}_{case_no}` 형식 (예: `kca_16713`)

### 페이지 정보

- **Counsel**: 페이지 정보 없음 (웹 기반 상담사례)
- **Dispute**: `page_start`와 `page_end` 필드 활용
  - 예: `1-41페이지`, `1-5페이지`

### 섹션 정보

- **Counsel**: `chunk_type` 필드 (problem, solution, full)
- **Dispute**: `section_type` 필드 (facts, claims, mediation_outcome 등)

### 출처 표시 형식

검색 결과에서 출처를 표시할 때는 다음 형식을 사용합니다:

#### Counsel 출처 형식
```
{source_org} {doc_type} {doc_id}
```

예시:
- `consumer.go.kr counsel_case 53321`
- `1372 소비자 상담센터 상담사례 53321`

#### Dispute 출처 형식
```
{source_org} {doc_type} {case_no} ({page_start}-{page_end}페이지)
```

예시:
- `KCA mediation_case 16713 (1-41페이지)`
- `ECMC mediation_case 01279 (1-5페이지)`
- `KCDRC mediation_case 00013 (1-1페이지)`

### 출처 정보 포함 필드

검색 결과에 다음 메타데이터를 포함해야 합니다:

- `doc_title`: 문서 제목
- `source_org`: 출처 기관 (KCA, ECMC, KCDRC, consumer.go.kr)
- `doc_type`: 문서 유형 (mediation_case, counsel_case)
- `category_path`: 카테고리 경로 (Counsel만 해당)
- `url`: 원본 URL (Counsel만 해당)
- `metadata`: 기타 메타데이터 (case_no, decision_date, page_start, page_end 등)

## 4. 검색 우선순위

RAG 검색 시 청크 타입별 우선순위를 적용하여 관련성 높은 결과를 우선 반환합니다.

### Counsel 검색 우선순위

1. **높음**: `problem`, `solution`
   - 사용자 질문과 직접 관련된 내용
   - 답변 생성에 가장 유용한 정보

2. **중간**: `full`
   - 전체 컨텍스트가 필요한 경우

### Dispute 검색 우선순위

1. **매우 높음**: `facts`
   - 사건의 핵심 사실관계
   - 유사 사례 비교에 가장 중요

2. **높음**: `claims`, `mediation_outcome`
   - 당사자 주장과 조정 결과
   - 분쟁 해결 방안 파악에 중요

3. **중간**: `judgment`, `decision`
   - 판단 및 결정 내용
   - 법적 근거 파악에 유용

4. **낮음**: 기타 섹션
   - 부가 정보

### 우선순위 적용 방법

검색 결과를 반환할 때:
1. 유사도 점수 계산
2. 청크 타입별 가중치 적용 (우선순위 높을수록 가중치 증가)
3. 최종 점수 = 유사도 점수 × 타입 가중치
4. 최종 점수 기준으로 재정렬

권장 가중치:
- Counsel: `problem`=1.2, `solution`=1.2, `full`=1.0
- Dispute: `facts`=1.3, `claims`=1.1, `mediation_outcome`=1.1, `judgment`=1.0, `decision`=1.0, 기타=0.9

## 5. 청크 관계 (chunk_relations)

현재는 청크 간 관계를 명시적으로 저장하지 않지만, 향후 확장 가능성을 위해 다음 관계 타입을 고려할 수 있습니다:

- `next`: 다음 청크 (순서 관계)
- `prev`: 이전 청크 (순서 관계)
- `related`: 관련 청크 (의미적 연관)
- `cited`: 인용 관계

예시:
- Counsel의 경우: `problem` → `solution` (next 관계)
- Dispute의 경우: `facts` → `claims` → `mediation_outcome` (순서 관계)

## 6. 데이터 품질 관리

### 필수 필드 검증

로드 시 다음 필드가 누락된 경우 경고를 출력하고 건너뜁니다:

- **Counsel**: `doc_id`, `chunk_id`, `text`, `title`
- **Dispute**: `case_no` 또는 `source_pdf`, `text`, `section_type`

### 중복 방지

- `doc_id`는 `documents` 테이블의 PRIMARY KEY
- `chunk_id`는 `chunks` 테이블의 PRIMARY KEY
- ON CONFLICT 처리로 중복 로드 시 업데이트

### 데이터 일관성

- 동일 `doc_id`의 모든 청크는 동일한 `chunk_total` 값을 가져야 함
- `chunk_index`는 0부터 시작하여 `chunk_total - 1`까지 연속적으로 존재해야 함
- `chunk_index < chunk_total` 제약 조건으로 검증

## 7. 참고 사항

- 본 가이드라인은 S1-D1 작업에서 정의된 초안입니다.
- 실제 검색 성능에 따라 우선순위 및 가중치는 조정될 수 있습니다.
- 새로운 데이터 소스 추가 시 본 가이드라인을 확장하여 적용합니다.
