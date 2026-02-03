| 단계 | 목표/산출물 | 네가 구현할 것 (핵심 작업) | 네가 “정해야 하는 것”(필수 결정) | Codex가 잘하는 일(위임 포인트) | 체크/완료 기준 |
| --- | --- | --- | --- | --- | --- |
| 1 | **품목 후보 선정 규칙** | 질의분석에서 넘어온 `keywords` 중 “품목 후보”만 뽑는 1차 룰 추가(LLM 호출 전) | LLM에 넘길 후보 키워드 개수(상위 N?), 제외 리스트(법령명/절차 키워드 등) | 제외 규칙 정규식/stopword 리스트 초안 생성 | `candidate_items` 배열 생성됨 (빈 배열 가능) |
| 2 | **품목 → (대/중/소) 분류 모듈** | LLM 호출 모듈 작성(프롬프트 + JSON 출력 파싱) 또는 최소 fallback 구현 | LLM 출력 포맷(JSON), unknown 처리 정책(unknown이면 broad search? or stop?) | 프롬프트 문구/JSON schema 강제, 파싱 실패 대비 코드 | `classification = {major,middle,minor,confidence}` 확보 |
| 3 | **카테고리 필터 스펙 정의** | DB에서 어디를 필터링할지 확정: `metadata` 컬럼 구조/키명 결정 | metadata 키 이름(예: `major_category`, `middle_category`, `minor_category`), NULL 처리, 다중값(배열?) 여부 | SQL WHERE 절/JSONB 조건 설계 | “어떤 컬럼/키로 필터링할지”가 고정됨 |
| 4 | **dense 검색 SQL 수정(핵심)** | 기존 유사도 검색 함수에 **category 필터 파라미터** 추가 및 WHERE 조건 반영 | 함수 시그니처 변경 vs 새 함수 생성(권장: 새 함수 `search_criteria_dense(...)`) | SQL 함수 초안 작성(파라미터/조건/인덱스 고려) | category 조건 걸고도 결과가 반환됨 |
| 5 | **criteria 노드 통합** | 기존 criteria 노드에 (1) 후보품목→(2) LLM 분류→(3) SQL 호출을 연결 | top_k, min_score, fallback 경로(분류 실패/결과 없음) | 파이썬 코드 연결/에러핸들/로깅 코드 | 노드 end-to-end 실행됨 |
| 6 | **중복/품질 후처리(최소)** | 같은 chunk_id 반복 제거, top_k 안정화, “분류 근거”를 함께 반환(로그/메타) | dedup 기준(chunk_id? text?), 반환에 category 포함 여부 | dedup 함수/정렬/슬라이싱 코드 | 결과가 깔끔하고 재현됨 |
| 7 | **테스트 10개 + 디버그** | 10개 시나리오 테스트(정상/unknown/오탐) + 로그 확인 | 테스트 케이스 목록(위스키/보리/소비자보호법 포함) | pytest 스타일 스모크 테스트 코드, 샘플 입력/출력 생성 | 10개 중 8개 이상 기대 동작 |
| 8 | **문서화 1페이지** | 팀 공유용 “로직 요약 + 한계 + fallback” 1p 작성 | 한계(LLM 분류 오류, 품목 미검출 등)와 대응 | README/MD 문서 템플릿 | 구현 + 설명이 같이 남음 |