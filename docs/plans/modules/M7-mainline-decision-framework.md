# Mainline(A/B) 확정 — 결정 프레임워크 (운영 중 결정)

- 작성일: 2026-07-05
- 상위: 로드맵 §M7(제품 경로 통합). 선행: M7-1~4 완료(제품 경로가 세 variant를 실행·측정).
- 성격: **결정 기록(decision record) + 기준 정의.** 코드 변경 없음.

## 0. 결정 (2026-07-05)

**mainline을 지금 확정하지 않고 "운영하며 데이터로 결정"한다.** 운영 기본값은 **A(MAS)** 유지(현 스트리밍 기본), B-frontier는 opt-in 비교 variant(M7-3 셀렉터), **B-exaone은 프로덕션 mainline 제외**(지연 84s·불안정·유료 파드 상시) — 연구/비교용으로만.

이 문서는 "운영하며 결정"이 막연해지지 않도록 **어떤 기준을, 어떤 데이터로, 어떤 임계에서** 판단할지 고정한다.

## 1. 후보와 제외

- **A (MAS)** — 현 기본. 도메인-핵심 축(충실성·안전·보안) 최고, 리치 스트리밍(토큰+노드).
- **B-frontier (gpt-4o-mini)** — 속도·비용·견고성·단순성 우위, 품질 근접. 안전/보안 소폭 열위, status-only 스트리밍.
- **B-exaone (EXAONE 4.5)** — **제외**(프로덕션). 지연/비용/불안정. 연구 비교로만 유지.

→ 실질 선택은 **A vs B-frontier**.

## 2. 지금까지의 측정 (기준선)

| 기준 | A | B-frontier | 출처 |
| --- | --- | --- | --- |
| faithfulness | **2.00** | 1.92 | M5-5 |
| coverage | 0.575 | 0.551 | M5-5 |
| safety pass | **1.00** | 0.83 | M5-5 |
| 보안 decided | **100%** | 96% | M4-A5 |
| leak_rate | 0% | 0% | M4-A5 |
| error_rate | 0.167※ | **0.00** | M5-5 |
| latency median | 10.2s | **6.4s** | M5-5 |
| 비용 | 중(MAS 다중 호출) | **최저** | M3 llm_calls |

※ #67 픽스 이전 값. 재측정 필요.

## 3. 결정 기준 · 데이터 소스 (운영 중 수집)

각 기준을 **이미 깔린 인프라**에서 어떻게 읽는지 고정한다. (variant 라벨은 M7-1/2로 제품 경로에 적재됨.)

| 기준 | 지표 | 데이터 소스 / 조회 |
| --- | --- | --- |
| **안전(도메인 핵심)** | safety_pass, hallucinated_citation율 | M5 answer 스코어러 재실행(제품 run) / `workflow_runs.answer` + judge |
| **보안(도메인 핵심)** | attack pass-rate, leak_rate | M4-A `score_security_eval.py` 재실행(variant별) |
| **품질** | faithfulness, coverage | M5 judge 재실행 / LangSmith eval(보완) |
| **지연** | p50/p95 latency | M6 Prometheus `chat_request_duration_seconds{variant}` / M3 `workflow_runs.total_time_ms` group by variant |
| **견고성** | error_rate | M6 `chat_requests_total{status="error",variant}` / total |
| **비용** | req당 LLM 호출·토큰 | M3 `llm_calls` group by run→variant / M6 `llm_tokens_total{variant}` |
| **UX** | 스트리밍 품질 | 정성(토큰 vs status), 브라우저 QA |

- **운영 대시보드**: `monitoring/grafana/dashboards/ops_ab.json`(M6-4 A/B 패널)로 지연·에러율·차단율·토큰율을 variant별 상시 관측.
- **LangSmith(보완)**: `variant:A`/`variant:B` 태그로 필터·pairwise 비교(M7-4).

## 4. 결정 규칙 (임계)

**기본은 A 유지.** 아래를 **모두** 만족할 때만 mainline을 B-frontier로 전환한다(안전/보안 후퇴 없는 조건부 전환):

1. **안전·보안 무후퇴**: B-frontier의 safety_pass·보안 decided·leak_rate가 A 대비 **유의하게 낮지 않음**(측정된 goldenset에서 A와 동률 또는 그 이상). 현재 B는 sec-atk-006 순응·safety 0.83로 **미충족** → 이 갭이 개선(가드레일 보강, A7 §4)되어야 함.
2. **품질 근접**: faithfulness·coverage가 A의 일정 범위 내(예: faithfulness 차이 ≤ 0.15).
3. **운영 이점 유의**: latency p95·error_rate·비용에서 B가 **분명히** 우위(현재 충족 방향).
4. **표본 충분**: 위를 **실사용/테스트 N세션 이상**(예: variant별 ≥100 run)에서 재현.

→ 요약: **B가 도메인-핵심(안전·보안)에서 A를 따라잡으면**, 속도·비용·견고성 이점으로 전환 검토. 그 전까지 A 유지.

## 5. 다음 행동 (운영 중)

- **데이터 축적**: 제품/테스트 사용을 `ops_ab.json` + M3 SQL로 variant별 관측(인프라 이미 완비).
- **주기적 재측정**: M5(품질)·M4-A(보안) goldenset을 variant별 재실행해 §2 기준선 갱신(특히 A error_rate는 #67 픽스 후 재측정).
- **B 개선 트리거**: mainline 후보로서 B의 병목은 안전·보안(§4-1). 개선하려면 A7 §4(불법조언 가드레일 범주 + B 스코프 게이트)를 별도 모듈로. 개선 후 재측정 → 전환 규칙 재평가.
- **재검토 시점**: variant별 표본이 임계에 도달하거나 B 개선 모듈 완료 시 본 문서 §4로 재판단.

## 6. 스코프 / caveat

- 본 문서는 **결정을 내리지 않고 결정 규칙을 고정**한다(운영 중 결정). 코드/기본값 변경 없음(A 기본 유지).
- B-exaone은 프로덕션 후보 아님(연구 비교 유지). 파드 비용 발생 시에만 측정.
- 전환은 **되돌릴 수 있는 기본값 변경**(요청 variant/백엔드 default)이라 리스크 낮음.
