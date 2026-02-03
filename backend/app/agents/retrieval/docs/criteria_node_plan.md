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

---

## 현재 요청 플랜 (분리 관리)

| 단계 | 목표/산출물 | 네가 구현할 것 (핵심 작업) | 네가 “정해야 하는 것”(필수 결정) | Codex가 잘하는 일(위임 포인트) | 체크/완료 기준 |
| --- | --- | --- | --- | --- | --- |
| 9 | **변경 최소화(키워드 확장)** | Query Analysis에서 `keywords`에 `onboarding.purchase_item`을 append하여 criteria가 품목 키워드를 받게 함 | 중복/공백 처리 규칙(동일 키워드 재추가 방지) | 안전한 append 로직/중복 제거 코드 | retrieval로 넘어온 keywords에 purchase_item 포함 확인 |
| 10 | **criteria 사전 매핑 + LLM 보정** | criteria 노드에서 keywords 복사본으로 룰 기반 매핑 → 매핑된 키워드는 후보에서 제거 → 매핑 실패 키워드만 LLM 분류 | LLM 프롬프트(분류 불필요 키워드 제외 지시), 분류 대상/제외 규칙 | 프롬프트/파싱/에러 처리 | 매핑 성공/실패 분리 로직 동작 |
| 11 | **카테고리 메타데이터 저장** | 키워드별 (section/category/subcategory) 매핑 결과를 구조화해 보관 | 결과 저장 위치(state? retrieval_task_input?) | 데이터 구조 설계 | 각 키워드의 분류 결과가 누락 없이 저장됨 |
| 12 | **분류 필터 적용 검색** | criteria 검색에서 분류 결과로 메타데이터 필터를 적용한 DB 조회 수행 | 메타데이터 필터 키 명칭/검색 함수 변경 여부 | 검색 호출부 수정 | 분류 기반 필터가 실제 검색에 적용됨 |
| 13 | **다중 세트 병합 TopK** | 매핑 세트가 2개 이상일 때 세트별 검색 → 결과 병합/중복 제거 → 최종 top_k | 병합 기준(유사도/중복 제거 키) | 병합 로직/정렬 | 다중 세트에서도 안정적 top_k 반환 |

---

## 오늘 변경 요약 (2026-02-03)

| 파일 | 변경 내용 |
| --- | --- |
| `backend/app/agents/query_analysis/agent.py` | 온보딩 `purchase_item`을 `keywords`에 추가하여 retrieval에 전달되도록 수정 (v1/v2 모두) |
| `backend/app/agents/retrieval/docs/criteria_node_plan.md` | “현재 요청 플랜” 섹션을 분리 추가 |
| `backend/app/agents/retrieval/tools/specialized_retrievers.py` | `criteria_search()` 추가(하이브리드 RRF + metadata 필터), 기본 `document_type`를 `시행규칙/별표`로 설정 |
| `backend/app/agents/retrieval/criteria_agent.py` | 룰 매핑 + LLM 분류(OpenAI) + 분류 세트별 검색/병합, 분류 결과를 `keyword_category_map`으로 응답에 포함 |
| `backend/scripts/debug/run_query_analysis.py` | 쿼리 분석 단독 실행 스크립트 추가 |

## 내일 할 일

1. `criteria_search()` 내부 SQL에서 rrf_k 값을 config에서 읽도록 변경
2. 실제 DB 스키마에 맞춰 metadata 키 확인 후 필터 조건 최종 점검
3. criteria 검색 결과에 대한 정확도 확인 (위스키/양주 등 매핑 케이스)
4. 필요 시 LLM 분류 프롬프트 개선 및 제외 키워드 목록 보강
