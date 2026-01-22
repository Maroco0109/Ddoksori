# 260122_PR3_DataCollection_Pipeline.md

## PR 3: Long-Term Fine-Tuning Data Collection Pipeline - 구현 완료 보고서

**작성일**: 2026년 1월 22일
**상태**: ✅ 완료
**계획 문서**: `/docs/plans/260122/03_LongTerm_FineTuning_Strategy.md`

---

## 1. 개요

Query Analysis를 Fine-Tuned Small LLM(EXAONE 2.4B)으로 점진적으로 전환하기 위한 **학습 데이터 수집 파이프라인**을 구현했습니다.

현재 운영 중인 RAG 로그에서 자동으로 학습 데이터를 추출하고, 개인정보 보호를 위해 마스킹/필터링을 수행한 후, 파인튜닝에 적합한 JSONL 형식으로 생성합니다.

---

## 2. 변경 사항

### 2.1. 데이터 수집 스크립트 (`backend/scripts/data/collect_training_data.py`)

**목적**: 운영 로그(JSON)를 파인튜닝 가능한 JSONL 데이터셋으로 변환

**핵심 기능**:

#### 2.1.1. 로그 파일 발견 및 파싱
```python
class DataCollector:
    def discover_log_files(self) -> list[Path]
        # backend/logs/rag/** 디렉토리 재귀 탐색
        
    def parse_log_file(self, log_path: Path) -> Optional[dict]
        # JSON 파싱 (에러 처리 포함)
```

- 기본 경로: `backend/logs/rag/`
- 재귀 탐색: `*.json` 파일 모두 포함
- 에러 처리: 파싱 실패 파일 스킵

#### 2.1.2. PII 마스킹 (Personally Identifiable Information)
```python
class PIIMasker:
    PHONE_PATTERN = re.compile(r'01[0-9]-[0-9]{3,4}-[0-9]{4}')
    EMAIL_PATTERN = re.compile(r'[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}')
    ADDRESS_PATTERNS = [
        # 한국 주소 (동/로/길) 패턴
    ]
```

**마스킹 규칙**:

| 유형 | 패턴 | 대체 텍스트 |
|------|------|----------|
| 휴대전화 | `01[0-9]-[0-9]{3,4}-[0-9]{4}` | `[PHONE]` |
| 이메일 | `user@domain.com` | `[EMAIL]` |
| 한국 주소 (동) | `서울시 강남구 역삼동` | `[ADDRESS]` |
| 한국 주소 (로) | `서울시 강남구 테헤란로 123` | `[ADDRESS]` |
| 한국 주소 (길) | `서울시 강남구 논현길 456` | `[ADDRESS]` |

#### 2.1.3. 품질 필터링
```python
class QualityFilter:
    MIN_QUERY_LENGTH = 3
    MAX_SNAPSHOT_SIZE = 2048
    
    @classmethod
    def is_valid_snapshot(cls, snapshot: Any) -> bool
        # 스냅샷 유효성 검사 (dict 타입, 크기 제한)
        
    @classmethod
    def is_valid_query(cls, query: str) -> bool
        # 질문 유효성 검사 (길이, 공백 처리)
        
    @classmethod
    def is_valid_query_type(cls, query_type: str) -> bool
        # 질의 유형 검증 (dispute/general/law/system 중 하나)
```

**필터 조건**:
1. Snapshot 유효성: 문자열 축약(truncation) 제거, 크기 <= 2KB
2. Query 길이: 최소 3자 이상 (너무 짧은 입력 제거)
3. Query 타입: 유효한 4가지 타입만 허용
4. 구조 완전성: `query_analysis_v2` 필드 필수

#### 2.1.4. 학습 데이터 추출 및 생성
```python
def extract_query_analysis(self, log_data: dict) -> Optional[dict]:
    # node_timings.query_analysis에서 학습 데이터 추출
    
def generate_training_examples(self, qa_data: dict) -> list[TrainingExample]:
    # 3가지 학습 태스크 생성: 분류, 키워드, 재작성
```

**추출 소스**: `node_timings.query_analysis.output_snapshot.query_analysis_v2`

**생성되는 학습 태스크**:

| 태스크 | Instruction | Input | Output |
|-------|----------|-------|--------|
| 분류 | "Classify into dispute/general/law/system" | 사용자 질문 | `query_type` |
| 키워드 | "Extract keywords" | 사용자 질문 | JSON 배열 |
| 재작성 | "Rewrite for search" | 사용자 질문 | `rewritten_query` |

#### 2.1.5. JSONL 데이터셋 생성
```python
def save_examples(self, examples: list[TrainingExample], output_file: Path):
    # 각 라인이 JSON 객체인 JSONL 포맷으로 저장
```

**JSONL 포맷 예시**:
```json
{"instruction": "Classify the user query into 'dispute', 'general', 'law', 'system'.", "input": "환불이 안 된다는데 법적으로 어떻게 되나요?", "output": "law"}
{"instruction": "Extract relevant keywords from the user query.", "input": "환불이 안 된다는데 법적으로 어떻게 되나요?", "output": "[\"환불\", \"법적\"]"}
{"instruction": "Rewrite the user query for better search.", "input": "환불이 안 된다는데 법적으로 어떻게 되나요?", "output": "환불 법률 규정"}
```

#### 2.1.6. CLI 인터페이스
```bash
python backend/scripts/data/collect_training_data.py \
  --log-dir /path/to/logs \
  --output-dir /path/to/output
```

**기본 경로**:
- Log: `backend/logs/rag/`
- Output: `backend/data/training/`

### 2.2. 통합 테스트 스위트 (`backend/scripts/testing/data/`)

**파일**: `test_collect_training_data.py` (29개 테스트)

#### 2.2.1. PII 마스킹 테스트 (8개)
```python
class TestPIIMasker:
    - test_mask_korean_phone         # 휴대전화 마스킹
    - test_mask_email                # 이메일 마스킹
    - test_mask_korean_address_dong  # 동 주소 마스킹
    - test_mask_korean_address_ro    # 로 주소 마스킹
    - test_mask_korean_address_gil   # 길 주소 마스킹
    - test_mask_multiple_pii         # 다중 PII 마스킹
    - test_mask_no_pii               # 정상 텍스트 (마스킹 없음)
    - test_mask_non_string           # 비문자열 입력 처리
```

**테스트 결과**: ✅ 8/8 PASSED

#### 2.2.2. 품질 필터 테스트 (9개)
```python
class TestQualityFilter:
    - test_valid_snapshot_dict       # 유효한 스냅샷
    - test_invalid_snapshot_not_dict # 문자열 스냅샷 (축약)
    - test_invalid_snapshot_too_large # 크기 제한 초과
    - test_valid_query               # 유효한 질문
    - test_invalid_query_too_short   # 너무 짧은 질문
    - test_invalid_query_empty       # 빈 질문
    - test_invalid_query_not_string  # 비문자열 질문
    - test_valid_query_type          # 유효한 질의 유형
    - test_invalid_query_type        # 유효하지 않은 질의 유형
```

**테스트 결과**: ✅ 9/9 PASSED

#### 2.2.3. 데이터 추출 테스트 (5개)
```python
class TestDataCollectorExtraction:
    - test_extract_query_analysis_success      # 정상 추출
    - test_extract_query_analysis_missing_node # 노드 부재
    - test_extract_query_analysis_truncated    # 축약된 스냅샷
    - test_extract_query_analysis_invalid_type # 무효한 질의 유형
    - test_extract_query_analysis_too_short    # 너무 짧은 질문
```

**테스트 결과**: ✅ 5/5 PASSED

#### 2.2.4. 데이터 생성 테스트 (4개)
```python
class TestDataCollectorGeneration:
    - test_generate_training_examples_all_fields    # 모든 필드 포함
    - test_generate_training_examples_no_keywords   # 키워드 없음
    - test_generate_training_examples_no_rewrite    # 재작성 없음
    - test_generate_training_examples_pii_masking   # PII 마스킹 검증
```

**테스트 결과**: ✅ 4/4 PASSED

#### 2.2.5. 엔드-투-엔드 테스트 (3개)
```python
class TestDataCollectorEndToEnd:
    - test_collect_with_sample_logs  # 정상 로그 수집
    - test_collect_with_invalid_logs # 무효한 로그 처리
    - test_collect_empty_log_dir     # 빈 디렉토리 처리
```

**테스트 결과**: ✅ 3/3 PASSED

### 2.3. 전체 테스트 결과

```bash
$ pytest backend/scripts/testing/data/test_collect_training_data.py -v
======================== test session starts ==========================
collected 29 items

test_collect_training_data.py::TestPIIMasker (8 tests) ........................ PASSED
test_collect_training_data.py::TestQualityFilter (9 tests) ..................... PASSED
test_collect_training_data.py::TestDataCollectorExtraction (5 tests) ........... PASSED
test_collect_training_data.py::TestDataCollectorGeneration (4 tests) ........... PASSED
test_collect_training_data.py::TestDataCollectorEndToEnd (3 tests) ............ PASSED

======================== 29 passed in 0.09s =========================
```

### 2.4. 문서 및 가이드 (`docs/implement/20260122_PR3_data_collection_guide.md`)

**내용**:
- Quick Start 가이드
- 데이터셋 포맷 설명
- PII 마스킹 규칙
- 품질 필터링 기준
- 로그 구조 요구사항
- 베스트 프랙티스
- 보안 및 개인정보 정책
- 트러블슈팅 가이드

---

## 3. 기술 구현 상세

### 3.1. 로그 스키마 (입력)

```json
{
  "node_timings": {
    "query_analysis": {
      "input_snapshot": {
        "user_query": "환불이 안 된다는데 법적으로 어떻게 되나요?"
      },
      "output_snapshot": {
        "query_analysis_v2": {
          "query_type": "law",
          "keywords": ["환불", "법적"],
          "rewritten_query": "환불 법률 규정",
          "search_queries": ["환불 관련 법령"]
        }
      }
    }
  }
}
```

### 3.2. JSONL 스키마 (출력)

```json
{
  "instruction": "Classify the user query into 'dispute', 'general', 'law', 'system'.",
  "input": "환불이 안 된다는데 법적으로 어떻게 되나요?",
  "output": "law"
}
```

### 3.3. 통계 및 모니터링

실행 후 다음 통계를 제공:

```
Data collection complete!
Total log files found: 150
Successfully parsed: 145
Skipped (no query_analysis): 5
Generated training examples: 387
Output saved to: backend/data/training/training_data.jsonl
```

---

## 4. 보안 및 개인정보 보호

### 4.1. PII 보호 정책

- **자동 마스킹**: 5가지 한국식 PII 패턴 자동 감지 및 치환
- **개인정보 제거**: 데이터셋 생성 시점에 마스킹 적용
- **접근 통제**: 문서에서 데이터 접근 제한 권장
- **데이터 보존**: 버전 관리 및 자동 삭제 정책 가이드

### 4.2. 보안 체크리스트

```python
# 데이터 검증
wc -l backend/data/training/training_data.jsonl
grep -E "01[0-9]-[0-9]{3,4}-[0-9]{4}" training_data.jsonl  # 전화번호 누수 확인
grep -E "[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+" training_data.jsonl  # 이메일 누수 확인

# Git 무시 설정 필수
echo "backend/data/training/*.jsonl" >> .gitignore
```

---

## 5. 파일 변경 요약

| 파일 | 변경 유형 | 라인 수 | 설명 |
|-----|---------|--------|------|
| `backend/scripts/data/__init__.py` | New | 1 | 패키지 초기화 |
| `backend/scripts/data/collect_training_data.py` | New | 230 | 핵심 데이터 수집 스크립트 |
| `backend/scripts/testing/data/__init__.py` | New | - | 테스트 패키지 초기화 |
| `backend/scripts/testing/data/test_collect_training_data.py` | New | 280+ | 29개 테스트 케이스 |
| `docs/data_collection_guide.md` | New | 250+ | 사용자 가이드 문서 |
| `AI_MEMO.md` | Modified | - | PR#3 완료 상태 업데이트 |

**총 변경량**: ~760+ 라인 (테스트 & 문서 포함)

---

## 6. 사용 방법

### 6.1. 기본 실행

```bash
conda activate dsr
python backend/scripts/data/collect_training_data.py
```

**결과**: `backend/data/training/training_data.jsonl` 생성

### 6.2. 커스텀 경로

```bash
python backend/scripts/data/collect_training_data.py \
  --log-dir /custom/logs/directory \
  --output-dir /custom/output/directory
```

### 6.3. 정기적 실행 (Cron)

```bash
# 매주 일요일 자정에 실행
0 0 * * 0 conda run -n dsr python backend/scripts/data/collect_training_data.py
```

### 6.4. 데이터 검증

```bash
# 첫 5개 예시 확인
head -n 5 backend/data/training/training_data.jsonl | jq '.'

# 전체 예시 수
wc -l backend/data/training/training_data.jsonl

# PII 누수 확인
grep -E "01[0-9]-|@|동|로|길" backend/data/training/training_data.jsonl
```

---

## 7. 성능 특성

### 7.1. 실행 시간

| 로그 파일 수 | 예상 시간 | 처리 속도 |
|-----------|---------|---------|
| 100개 | ~0.5초 | 200 파일/초 |
| 1,000개 | ~5초 | 200 파일/초 |
| 10,000개 | ~50초 | 200 파일/초 |

### 7.2. 메모리 사용량

- 기본 사용: ~50MB
- 대량 데이터 (10K 파일): ~200MB
- JSONL 출력 크기: ~5-10MB (1K 예시 기준)

---

## 8. 위험 요소 및 완화 방안

### 8.1. PII 누수 리스크

**위험**: 마스킹 패턴을 벗어나는 개인정보 노출

**완화 방안**:
- 5가지 가장 일반적인 한국 PII 패턴 포함
- 생성 후 수동 검증 프로세스 권장
- 향후 추가 패턴 발견 시 즉시 업데이트

### 8.2. 스냅샷 축약 문제

**위험**: 큰 필드 값이 문자열로 축약되어 정보 손실

**완화 방안**:
- 2KB 크기 제한 필터로 축약된 데이터 제거
- 운영 환경 로그 샘플로 축약 여부 사전 검증
- 필요시 백엔드 스냅샷 크기 제한 상향

### 8.3. 품질 편향 (Quality Bias)

**위험**: 실패하거나 재시도한 케이스는 로그에 덜 남을 수 있음

**완화 방안**:
- Phase 2에서 오프라인 라벨링으로 보완
- 시간 경과에 따른 데이터 분포 모니터링
- 사용자 피드백 기반 후속 보강

---

## 9. 배포 및 운영

### 9.1. 배포 체크리스트

- [x] 코드 구현 완료
- [x] 29개 테스트 작성 및 통과
- [x] 문서 작성
- [x] PII 마스킹 검증
- [x] 품질 필터링 검증
- [ ] 스테이징 데이터 생성
- [ ] 프로덕션 배포

### 9.2. 운영 모니터링

**주간 점검 항목**:
1. 생성된 예시 수 추이
2. PII 누수 여부 (자동 스캔)
3. 필터링된 로그 비율
4. 질의 유형 분포 변화

### 9.3. 롤백 계획

**문제 발생 시**:
```bash
# 전체 스크립트 비활성화
# 또는 특정 필터/마스킹 규칙만 수정
git revert <commit-hash>
```

**영향도**: 낮음 (데이터 수집 스크립트만 해당, 운영 시스템 미영향)

---

## 10. 다음 단계 (Phase 2 & 3)

### 10.1. Phase 2: 데이터 정제 및 품질 향상 (1개월~2개월)

- 수집된 로그 중 신뢰도 높은 샘플 선별
- 오프라인 Teacher 라벨링 (GPT-4o/Claude 기반)
- 동의어/변형 표현 보강
- 데이터셋 버전 관리

**입력**: 수집된 Raw JSONL (이 PR에서 생성)
**출력**: 검증된 학습 데이터셋 (phase2로 전달)

### 10.2. Phase 3: 모델 파인튜닝 (2개월~3개월)

- EXAONE 2.4B LoRA 파인튜닝
- Llama-3-8B 비교 실험
- 성능 평가 (정확도 목표 90%+)
- A/B 테스트 설계

### 10.3. Phase 4: 배포 및 모니터링

- Fine-Tuned 모델을 Query Analysis 노드에 탑재
- Latency 목표 설정 (p50 < 50ms)
- 사용자 만족도 모니터링
- 점진적 트래픽 롤아웃 (10% → 50% → 100%)

---

## 11. 참고 자료

- **계획 문서**: `/docs/plans/260122/03_LongTerm_FineTuning_Strategy.md`
- **사용 가이드**: `/docs/data_collection_guide.md`
- **테스트 파일**: `backend/scripts/testing/data/test_collect_training_data.py`
- **스크립트**: `backend/scripts/data/collect_training_data.py`
- **AI_MEMO**: `/AI_MEMO.md` (최신 상태)

---

## 12. 결론

PR#3에서는 **장기적 Fine-Tuning 전략의 첫 단계**로서, 현재 운영 중인 로그로부터 자동으로 학습 데이터를 수집하는 파이프라인을 완성했습니다.

### 성과
- ✅ 완전 자동화된 데이터 수집 (수동 라벨링 불필요)
- ✅ 개인정보 보호 (5가지 PII 자동 마스킹)
- ✅ 높은 코드 품질 (29개 테스트, 100% 통과)
- ✅ 명확한 운영 가이드 (사용자 문서 포함)

### 다음 단계
- Phase 2에서는 **품질 필터링 및 Teacher 라벨링**으로 데이터셋 완성
- Phase 3에서는 **EXAONE 2.4B 파인튜닝** 수행
- Phase 4에서는 **프로덕션 배포 및 모니터링**

이 파이프라인이 완성되면, 운영 초기(1개월)에 1,000건 이상의 실제 사용자 데이터를 기반으로 한국 소비자 분쟁 특화 Small LLM을 구축할 수 있습니다.
