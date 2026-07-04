# M5-5 answer 생성품질 LLM-judge (계획서)

- 작성일: 2026-07-04
- 모듈: `M5-5` answer 품질 LLM-judge (run 답변에 품질 점수 산출)
- 선행: `M5-1`(`workflow_runs.answer` 영속화), `M5-3`(`quality_eval_v1.jsonl` = key_points/must_not 라벨), `M5-4/M5-4b`(judge 패턴 + 교훈)
- 상위 계획: §M5 (품질 평가) — 로드맵 표 M5-5
- 성격: **측정·채점 파이프라인.** 신규 프레임워크 없음(기존 `/chat` 적재 경로 + M5-4 judge 스크립트 스타일 재사용). DB/스키마 변경 없음.

## 0. 한 줄 요약

goldenset 12쿼리(`quality_eval_v1.jsonl`)를 **A / B-frontier**로 `/chat` 실행해 `workflow_runs.answer`+`retrieval_events`에 적재하고, 그 (query, answer, contexts, key_points, must_not)를 읽어 **faithfulness / coverage / safety** 3지표로 채점한다. B-exaone는 RunPod 준비 시 동일 스크립트로 추가한다(부분 착수). M5-4b 교훈대로 **binary/coarse 채점 + rubric 명확화**, judge-human 검증은 M5-6로 분리.

## 1. 배경 (왜 실행·적재가 선행인가)

- M5-4까지 완료로 **검색 품질**은 수치화됨(nDCG/hit/MRR + judge 교차검증). 남은 축은 **답변 품질**.
- 현재 모니터링 DB에는 goldenset 12쿼리의 답변이 없다(M5-4 발견: 25 run 중 answer 2건, 전혀 다른 smoke 쿼리). 즉 채점 이전에 **goldenset을 실제 실행해 answer를 적재**하는 단계가 반드시 선행.
- 재사용: `/chat`이 이미 A/B를 실행하고 `workflow_runs.answer`(M5-1)·`retrieval_events`(M3)에 per-request 적재 → SQL로 A/B 비교 가능. 별도 오프라인 러너를 새로 만들 필요 없음.

## 2. 범위

### 목표
- goldenset 12쿼리를 A / B-frontier로 실행·적재(`variant`, `answer`, retrieval contexts).
- 답변 채점 3지표 산출:
  - **faithfulness**: 답변 주장이 검색된 contexts에 근거하는가(reference-free, LLM judge, coarse). 근거 없는 진술=hallucination 신호.
  - **coverage**: `key_points` 충족률(포인트별 0/1 의미일치 → 비율). "담아야 할 핵심 사실"을 얼마나 포함했나.
  - **safety**: `must_not` 위반 여부(규칙 매칭 1차 + judge 보조, 위반 category별 binary). 기존 legal_review 가드레일 어휘 재사용.
- A vs B-frontier 답변품질 비교표(포트폴리오용 measurable numbers) + results 문서.

### 비목표
- **B-exaone 채점**: RunPod EXAONE pod 게이트 → pod 준비 후 동일 스크립트 재실행으로 컬럼 추가(부분 착수 경계).
- **judge-human 일치도 검증**(답변측) = **M5-6**. 본 모듈은 점수 산출까지.
- DB/스키마 변경, 라이브 대시보드 연동(M6), retriever/프롬프트 개선(측정만).
- 쿼리셋 확장(12쿼리 고정), RAGAS 프레임워크 복구(별도 백로그).

## 3. 재사용 자산 (신규 프레임워크 금지)

| 자산 | 역할 | M5-5에서 |
| --- | --- | --- |
| `backend/app/api/chat.py` (`/chat`) | A/B 실행 + `answer`/`retrieval_events` 적재(M5-1/M3) | goldenset 12쿼리 실행·적재 경로 |
| `app.variant_b.agent.run_b` | B 답변 반환(`{"answer",...}`) | /chat이 감싸는 B 실행부(간접) |
| `workflow_runs.answer` + `retrieval_events` | (query, answer, contexts) 소스 | 채점 입력 join |
| `judge_retrieval_relevance.py` | OpenAI judge 패턴(temp0, JSON-only, kappa/집계) | `judge_answer_quality.py` 뼈대 |
| `ab_compare.py::write_report` | A/B 합본 markdown 표 생성 | 답변품질 표 렌더 패턴 |
| legal_review 가드레일 위반 어휘 | `must_not` 규칙 매칭 | safety 1차(rule-based) |

- 확인됨: `run_b`는 `answer` 텍스트 반환(agent.py:181–184). `/chat`은 A/B per-request 적재(M3 백본). 채점기는 M5-4 judge와 동일하게 **OpenAI만** 사용(pod 불필요).

## 4. 작업 단계 (Impl 단계에서 수행)

1. **실행·적재**: goldenset 12쿼리를 `/chat`으로 A / B-frontier 실행 → `workflow_runs`에 (variant, query, answer) + `retrieval_events` 적재. goldenset run을 식별할 태그/필터 방법 확정(예: 전용 session/label). *impl 시 `/chat` variant 파라미터·적재 경로 재확인.*
2. **채점 로그 빌드**: `build_answer_eval_log.py` — DB(workflow_runs+retrieval_events) ⨝ `quality_eval_v1.jsonl` → `{id, query, variant, answer, contexts[], key_points[], must_not[]}` jsonl.
3. **채점**: `judge_answer_quality.py` — 레코드별 faithfulness(coarse 0–2 또는 binary)·coverage(key_point별 0/1)·safety(must_not category별 위반 0/1; 규칙+judge). temp 0, JSON-only, rubric 프롬프트 명시.
4. **집계·비교표**: variant별 평균(faithfulness, coverage_ratio, safety_pass_rate) → A vs B-frontier 표(+ exaone은 pod 시 열 추가 명시).
5. **문서화**: `M5-5-answer-generation-quality-results.md` — 지표 정의·rubric·A/B 표·caveat·M5-6 인계.

## 5. 산출물 (Impl PR 예정)

- `backend/scripts/evaluation/build_answer_eval_log.py`
- `backend/scripts/evaluation/judge_answer_quality.py`
- `backend/data/golden_set/quality_answer_log.jsonl` (실행·적재 결과 join)
- `backend/data/golden_set/quality_answer_scores.json` + A/B 표 `.md`
- `docs/plans/modules/M5-5-answer-generation-quality-results.md`

## 6. 완료 기준 / 검증

- [ ] goldenset 12쿼리가 A / B-frontier로 실행·적재됨(`workflow_runs.answer` 채워짐, retrieval contexts 연결).
- [ ] faithfulness/coverage/safety 3지표를 variant별로 산출(최소 A + B-frontier; exaone은 pod 게이트로 명시).
- [ ] A vs B-frontier 답변품질 비교표 + rubric·caveat 문서화.
- [ ] 채점기 결정성(temp 0, JSON-only) + must_not 규칙매칭 재현.
- [ ] DB/스키마 변경 없음, `quality_eval_v1.jsonl` 불변, 채점은 OpenAI만(pod 불필요).

## 7. caveat

- **M5-4b 교훈**: graded(0/1/2) judge는 등급경계 불안정 → **binary/coarse 선호**, rubric 명확화. 절대점수보다 A/B **상대 비교**에 무게.
- **judge 신뢰도 미검증**: 본 모듈은 점수 산출까지. judge가 human과 얼마나 맞는지는 **M5-6**에서 검증(그 전엔 확정 지표로 과신 금지).
- **소량셋(12)**: 분산 큼 → per-query 표도 함께 제시, 통계적 단정 회피.
- **faithfulness는 contexts 기준**: 검색이 빈약하면(낮은 nDCG) 답변이 옳아도 낮게 나올 수 있음 → M5-4 retrieval 지표와 **함께** 해석.
- **safety 이중화**: 규칙(어휘)만으론 우회 놓침, judge만으론 변동 → 둘 병행, 불일치는 기록.

## 8. Next gate → M5-6

- M5-6: `judge_answer_quality` 점수 vs human(소량 재라벨/스팟체크) 일치도(agreement/kappa) → judge 신뢰도 수치화. binary/coarse 우선.
- pod 준비 시: 동일 `build_answer_eval_log.py`/`judge_answer_quality.py`로 **B-exaone 열 추가**(코드 변경 없이 재실행) → A/B/B 3열 완성.
