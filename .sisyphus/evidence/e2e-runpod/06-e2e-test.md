# 최종 E2E 테스트 절차 (Task 06)

## 1. 개요
본 문서는 DDOKSORI 시스템의 전체 흐름을 검증하기 위한 최종 E2E 테스트 절차를 정의한다.
사용자 입력부터 Orchestrator, Runpod(EXAONE LLM), DB/RAG 검색 및 최종 응답 생성까지의 전 과정을 검증한다.

## 2. 테스트 시나리오

### 2.1 시나리오 1: 정상 동작 (Normal Operation)
- **목적**: 모든 연결(Runpod + DB/RDS + Embedding)이 정상일 때의 시스템 흐름 검증
- **실행 방법**: `QUERY_REWRITE_TIMEOUT=2000` 설정 후 복잡한 질의 입력
- **성공 판정**:
    - HTTP 200 응답 및 유효한 답변 생성
    - 백엔드 로그에 `[QueryRewriter] LLM rewrite in` 키워드 포함 (성공 로그)
    - `node_timings`에 `query_analysis`, `retrieval_*`, `generation` 등 주요 노드 기록 확인

### 2.2 시나리오 2: Runpod 불가 시 Fallback (Runpod Fallback)
- **목적**: Runpod 서버 장애 또는 타임아웃 발생 시 시스템이 규칙 기반으로 정상 폴백되는지 검증
- **실행 방법**: `QUERY_REWRITE_TIMEOUT=90` (Mode A) 설정 또는 Runpod URL을 무효한 주소로 변경 후 질의
- **성공 판정**:
    - HTTP 200 응답 및 답변 생성 (시스템 전체 실패가 아님)
    - 백엔드 로그에 `[QueryRewriter] LLM unavailable:` 또는 `[QueryRewriter] Timeout` 키워드 포함
    - 규칙 기반 재작성(Rule-based rewrite) 결과가 검색에 사용됨

### 2.3 시나리오 3: DB/RDS 지연/불가 (DB Failure)
- **목적**: 데이터베이스 연결 문제 발생 시 시스템의 에러 핸들링 및 타임아웃 동작 검증
- **실행 방법**: DB 컨테이너 중지 또는 RDS 보안 그룹 차단 후 질의
- **성공 판정**:
    - 정의된 타임아웃 내에 적절한 에러 메시지 반환 (HTTP 500 등)
    - 로그에 DB 연결 오류(`psycopg2.OperationalError` 등) 기록 확인

## 3. Runpod 호출 트리거 (Query Rewriter)

### 3.1 트리거 조건 (is_complex_query)
`backend/app/llm/query_rewriter.py`의 로직에 따라 다음 조건 중 하나라도 만족하면 Runpod 호출을 시도한다.
1. **법률 용어 포함**: `청약철회`, `하자담보책임`, `손해배상` 등 지정된 법률 용어 포함 시
2. **길이 제한**: 쿼리 길이가 50자 초과 시
3. **격식체 종결 표현**: `여부`, `가능한지`, `인지`, `합니다` 등 공식적인 문체 사용 시

### 3.2 강제 호출 입력 예시
> "전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부"

### 3.3 호출 검증 방법
- 백엔드 로그에서 다음 키워드를 모니터링한다:
    - `[QueryRewriter]`: 재작성기 동작 확인
    - `[ExaoneLLMClient]`: 실제 LLM 클라이언트 호출 및 토큰 사용량 확인

## 4. 실행 절차 및 환경 설정

### 4.1 Mode A: Fallback 검증 (지연 시뮬레이션)
```bash
# .env 또는 환경변수 설정
export QUERY_REWRITE_TIMEOUT=90
# 서버 재시작 후 테스트 수행
```

### 4.2 Mode B: 정상 호출 검증
```bash
# .env 또는 환경변수 설정
export QUERY_REWRITE_TIMEOUT=2000
# 서버 재시작 후 테스트 수행
```

## 5. Debug 관찰 포인트
- **요청 시**: JSON 페이로드에 `"debug": true` 포함
- **응답 확인**:
    - `node_timings`: 각 노드별 `duration_ms` 확인 (start_time/end_time은 비어있을 수 있음)
    - `request_id`: 로그 추적을 위한 고유 ID
    - `total_time_ms`: 전체 처리 시간

## 6. 완전한 /chat 요청 예시 (CURL)
```bash
curl -fsS http://localhost:8000/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "message": "전자상거래 등에서의 소비자보호에 관한 법률 제17조에 따른 청약철회권 행사 가능 여부",
    "chat_type": "dispute",
    "debug": true,
    "top_k": 5
  }'
```

## 7. 타임아웃 및 지연 기준
- **Query Rewrite**: 최대 2000ms (정상), 90ms (Fallback 테스트용)
- **전체 응답 시간**: RAG 포함 5000ms 이내 권장 (LLM 성능 및 네트워크 환경에 따라 변동 가능)

## 8. 증거 수집 절차
1. 테스트 수행 전 백엔드 로그 초기화 또는 마킹
2. CURL 명령어를 통한 요청 실행 및 응답 JSON 저장
3. `docker logs backend` 또는 `app.log`에서 관련 키워드 추출
4. `node_timings` 데이터를 기반으로 병목 지점 분석

## 9. 참조 코드
- `backend/app/api/chat.py`: 엔드포인트 및 디버그 응답 구조
- `backend/app/llm/query_rewriter.py`: 트리거 및 폴백 로직
- `backend/app/orchestrator/graph_mas.py`: 전체 워크플로우 노드 구성
