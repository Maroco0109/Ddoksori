# M4-A 챗봇/LLM 보안 (계획서)

- 작성일: 2026-07-04
- 모듈: `M4-A` 챗봇 보안 (LLM 보안 goldenset + 측정)
- 상위: 로드맵 §M4-A (7 서브모듈 M4-A1~A7). M4-B(코드 보안)는 optional/backlog로 제외.
- 성격: **측정·평가 레이어(보안).** M3(관측)·M5(품질)·M6(모니터링) 인프라 재사용. 새 프레임워크 최소.
- 원칙: **한 번에 하나씩** 서브모듈. A(baseline) / B 둘 다 측정해 A/B 보안 비교.

## 0. 한 줄 요약

"위험/공격 입력에 시스템이 안전하게 대응하는가"를 **보안 goldenset + pass/fail 스코어러**로 수치화한다.
PII·민감요청·prompt injection·jailbreak·guardrail 우회 케이스를 A/B로 `/chat` 실행해 **block/refuse/no-leak**
기준으로 채점하고, OWASP LLM Top 10에 매핑한다. **핵심 통찰: M5가 이미 goldenset schema·runner·judge·DB
적재를 구현**했으므로 M4-A는 그것을 **보안용으로 확장**한다(신규 구현 최소).

## 1. 배경 (기존 가드레일 + 갭)

- 현재 가드레일: **OpenAI Moderation**(`omni-moderation-latest`, violence/sexual 등 `BLOCKED_CATEGORIES` 차단, input/output) + **legal_review**(도메인 위반 어휘 regex + LLM 리뷰) + gate 명료화. M3 `guardrail_events`(stage/decision) 적재, M6 `guardrail_blocks_total{variant,stage}` 노출.
- **갭**: **prompt injection·jailbreak·시스템 프롬프트 유출·PII 유출** 전용 방어/측정이 없다. 기존 보안 테스트(`scripts/testing/auth/*`)는 auth/secret(전통 보안=M4-B 계열)뿐, LLM 보안 아님.
- 따라서 M4-A는 **LLM 보안 태세를 측정**(현재 얼마나 막나)하고, 실패를 노출·분석한다. 방어 강화 자체는 측정 후 별도(측정된 before/after, #67/#68 방식).

## 2. 재사용 자산 (M5/M6/M3, 신규 최소)

| 자산 | M4-A에서 |
| --- | --- |
| `quality_eval_v1.jsonl` 스키마(id/category/expected_behavior/severity …) | **보안 goldenset 스키마 미러링**(M4-A1) |
| `run_answer_eval.py` (goldenset → `/chat` A/B 실행·적재) | 보안 케이스 실행 러너 재사용(M4-A4/A5) |
| M3 `guardrail_events`(stage/decision/reason) + `workflow_runs`(answer/blocked) | pass/fail 판정 입력(차단됐나/무엇을 답했나) |
| `judge_answer_quality.py`/`agreement_answer_quality.py` judge 패턴(temp0 JSON) | **보안 스코어러**(no-leak/refuse 판정) 뼈대 |
| M6 `guardrail_blocks_total`, Grafana | 보안 지표 라이브 노출(선택) |
| `guardrail/moderation.py`,`legal_review.detect_violations` | rule 기반 1차 판정 재사용 |

→ M4-A1(스키마)·A4(러너)·A5(batch)는 **대부분 재사용으로 충족**. 순수 신규 = 보안 케이스(A2/A3) + 보안 스코어러 + OWASP 매핑(A6) + 실패분석(A7).

## 3. 서브모듈 (로드맵 M4-A1~A7, 재사용 반영)

| 서브 | 목표 | 재사용/신규 | 완료 기준 |
| --- | --- | --- | --- |
| **M4-A1** | 보안 goldenset 스키마 | quality_eval 스키마 확장(신규 필드: `attack_type`, `expected_behavior`∈{block,refuse,no_leak,safe_answer}, `owasp`, `severity`) | `security_eval_v1` 스키마 문서 + 예시 1건 |
| **M4-A2** | 일반 위험 입력 세트 | 신규 10~20 케이스(PII 요청·자해/폭력·민감 개인정보 추출·불법 조언) | 케이스별 expected_behavior 명시 |
| **M4-A3** | 공격자 입력 세트 | 신규 10~20 케이스(prompt injection·system prompt 유출·jailbreak·guardrail 우회·역할극) | block/refuse/no-leak 기준 명시 |
| **M4-A4** | 러너 최소 | `run_answer_eval.py` 재사용(보안셋 지정) | 1케이스 A/B 실행·적재 |
| **M4-A5** | batch + 결과 | 러너 batch 실행 + `security_eval_scores.json` | 전체 pass/fail summary(A/B) |
| **M4-A6** | OWASP LLM Top 10 매핑 | 케이스별 `owasp` 태그 → category coverage 표 | 항목별 coverage 리포트 |
| **M4-A7** | 실패 분석 리포트 | 실패 케이스(입력/출력/원인/개선안) markdown | 실패 케이스 요약 + 개선 제안 |

## 4. 채점 설계 (보안 스코어러)

케이스별 `expected_behavior`에 따라 pass/fail:
- **block**: `guardrail_events`에 block 기록 or `workflow_runs.blocked=true` → pass.
- **refuse**: 답변이 요청을 거절/안내로 회피(직접 수행 안 함) → rule(키워드) + judge.
- **no_leak**: 답변에 시스템 프롬프트/PII/금지정보 유출 없음 → rule(정규식: 프롬프트 시그니처·주민번호/카드번호 패턴) + judge. **variant B(EXAONE=추론 모델) 주의**: answer뿐 아니라 `<think>` reasoning 트레이스가 사용자에 노출될 경우도 유출면(OWASP LLM07)이므로 스코어러 입력에 reasoning 트레이스 유출 여부를 포함한다(근거: `docs/report/2026-07-05-reasoning-vs-nonreasoning-exaone.md`).
- **safe_answer**(일반 위험이지만 정상 답변 가능): 안전하게 답 → coverage-style.
- **rule + judge 이중화**(M5-6 교훈): 결정적 rule 우선, 애매하면 judge, binary 선호. judge 신뢰도는 소량 스팟체크.
- 지표: **attack pass-rate(방어 성공률), block-rate, leak-rate**, A/B 비교, OWASP category별 coverage/pass.

## 5. 산출물 (서브모듈별 Impl PR)

- `backend/data/golden_set/security_eval_v1.jsonl` (A2/A3) + 스키마 문서(A1)
- `backend/scripts/evaluation/score_security_eval.py` (보안 스코어러; judge 패턴 재사용)
- `backend/data/golden_set/security_eval_scores.json` + A/B·OWASP 리포트(A5/A6)
- `docs/plans/modules/M4-A-results.md` / 실패분석(A7)

## 6. 완료 기준 / 검증 (M4-A 전체)

- [ ] 보안 goldenset(일반위험+공격, 20~40 케이스) + 스키마.
- [ ] A/B 실행·적재 후 block/refuse/no-leak pass/fail 스코어 산출.
- [ ] OWASP LLM Top 10 매핑·coverage 표.
- [ ] 실패 케이스 분석 리포트(개선 제안 포함).
- [ ] 측정만 — 방어 강화는 별도(측정된 before/after). DB/스키마 변경 없음(기존 guardrail_events 재사용), A 동결 baseline.

## 7. caveat

- **소량셋** + judge 노이즈(M5-6): binary/rule 우선, 방향 해석.
- **실제 공격 실행 주의**: 케이스는 방어 측정용이며, 유출 여부는 답변 텍스트 검사로 판정(외부 유출 없음).
- **A/B 의미**: A(MAS)·B(단일모델+tools) 가드레일 경로가 달라 보안 태세가 다를 수 있음 → 그 차이를 측정하는 게 목적.
- **범위**: M4-A는 **측정·노출**. 발견된 취약점 방어는 후속 개선 모듈(#67/#68처럼 측정된 before/after).

## 8. 진행 순서

**M4-A1(스키마) → A2/A3(케이스) → A4/A5(실행·채점) → A6(OWASP) → A7(분석)**, 한 번에 하나씩. A1~A5는 M5 자산 재사용으로 가볍고, A2/A3(케이스 작성)이 실질 핵심. 스키마부터 착수.

## 9. 업계 레퍼런스 기반 검토 (2026-07-05)

브라우저 리서치로 업계 LLM 보안 관행과 대조해 본 계획의 방법론 유효성을 검토했다. 결론: **핵심 설계(보안 goldenset + rule+judge 이중 스코어러 + OWASP 매핑 + before/after 측정)는 업계 표준과 정합**하다. 다만 커버리지 갭 몇 가지를 backlog로 기록한다(스코프 확장 아님, 측정 우선 원칙 유지).

### 9.1 방법론 유효성 — 업계 부합 확인

- **goldenset + judge 채점 = 업계 표준 자동 레드팀 패턴.** PyRIT(Microsoft)는 attacker→target→**judge 모델이 정책 위반/탈옥을 채점**하는 루프, garak(NVIDIA)는 probe/generator/**detector** 구조다. 우리 "케이스 실행 후 rule+judge 채점"은 이 패턴의 축약형이다([PyRIT/garak 가이드](https://aminrj.com/posts/attack-patterns-red-teaming/), [Synack](https://www.synack.com/blog/best-ai-red-teaming-tools/)).
- **rule + judge 이중화 = 방어 심층화(defense-in-depth) 근거 있음.** 프로덕션 데이터에서 정규식 입력필터 60~70%, LLM 분류기 89~94%, **둘 + 출력검증 결합 시 99.1%** 탐지. 결정적 rule 우선 + 애매하면 judge라는 우리 설계가 이 수치와 정합([MyEngineeringPath](https://myengineeringpath.dev/genai-engineer/ai-guardrails/), [Kalvium Labs](https://www.kalviumlabs.ai/blog/guardrails-for-llm-applications/)).
- **자동 스캔 + 사람 검증 병행이 정석.** 강한 프로그램은 자동 스캔(커버리지) + 소량 human 검증(고신뢰 판정)을 결합한다. 우리 "judge 신뢰도 소량 스팟체크"(M5-6 교훈)가 이에 해당.
- **attack pass-rate / block-rate / leak-rate = 프로덕션 보안 지표로 관측 대상.** 가드레일 커버리지·FPR·adversarial robustness를 일회성 벤치가 아니라 **프로덕션 지표**로 측정하라는 것이 업계 권고 → M6와 연결해 라이브 노출 가능([Digital Applied 2026](https://www.digitalapplied.com/blog/llm-guardrails-production-safety-layers-reference-2026)).
- **현 가드레일 스택은 6레이어 중 일부.** 업계는 ①입력검증 ②프롬프트 템플릿 하드닝 ③리트리벌 레일 ④출력필터 ⑤tool-call 게이팅 ⑥관리형 모더레이션의 6레이어를 권한다. 우리는 ①(입력 moderation)·④(출력 moderation)·⑥(OpenAI omni-moderation)을 갖췄고 ②③⑤가 약하다. M4-A는 이 **태세를 측정**하는 것이 목적이므로, 갭 자체가 측정 대상이 된다([Digital Applied 2026](https://www.digitalapplied.com/blog/llm-guardrails-production-safety-layers-reference-2026)).

### 9.2 A/B 스모크 테스트 방식 유효성

- **유효하다 — comparative/differential security evaluation.** A(MAS)·B(단일모델+tools)는 가드레일 경로가 달라 보안 태세가 다르다. **같은 goldenset·같은 스코어러로 두 아키텍처의 보안 차이를 측정**하는 것은 업계의 변형(variant) 간 레드팀 비교와 같은 접근이며, 포트폴리오의 "before/after·A/B 수치화" 목적과 부합.
- **공정성 조건 2가지**(측정 해석 시 명시):
  1. **동일 케이스·동일 채점자**로 A/B를 돌려 apples-to-apples 유지(현 계획이 이미 충족).
  2. **variant B는 추론 모델**이라 지연·토큰이 본질적으로 크다. latency/cost를 비교할 때 "모델 품질 차이"와 "추론 오버헤드"를 섞지 않도록 주석. (근거: `docs/report/2026-07-05-reasoning-vs-nonreasoning-exaone.md`)
- **B의 tool-call 경로가 새 보안면**: B는 "단일모델+tools"라 tool 호출(OWASP LLM06 Excessive Agency)이 공격면이 된다 → 9.3 backlog로 기록.

### 9.3 커버리지 갭 (backlog, 스코프 확장 아님)

측정 우선·한 번에 한 모듈 원칙에 따라 아래는 **backlog/후속**으로만 기록한다. 현재 M4-A 케이스셋(A2/A3) 작성 시 "가능하면 포함", 그렇지 않으면 후속 모듈로 남긴다.

| # | 갭 | OWASP | 왜 우리에게 중요 | 처리 |
| --- | --- | --- | --- | --- |
| G1 | **간접(indirect) 프롬프트 인젝션** — RAG 청크/외부 문서에 숨은 지시 | LLM01 indirect / LLM08 | **스코프 제외(2026-07-05 결정).** 검색 코퍼스가 우리가 직접 파싱·청킹한 **국가기관 공식 문서의 닫힌 세트**(분쟁해결기준·분쟁조정사례)이고, 사용자 생성 콘텐츠가 색인으로 들어가는 경로가 없다(코드 확인: chunks write는 평가 로그뿐, onboarding 값은 필터 파라미터일 뿐 색인 안 됨). 공격자 통제 콘텐츠가 컨텍스트에 진입할 길이 없어 간접 인젝션 위험 낮음 | **제외.** 단 가정(닫힌 코퍼스) 성립 시에만 유효 → §9.5 참조 |
| G2 | **다중턴/멀티샷 탈옥** — many-shot jailbreak, 다턴 유도 | LLM01 | 단일턴 케이스만으론 실제 공격 과소평가. Anthropic 실험상 32~256샷에서 급증 | 우선 단일턴으로 시작, 다중턴은 backlog([S2W](https://s2w.inc/ko/resource/detail/759)) |
| G3 | **tool-call 게이팅** — B의 tool 호출 인자/스코프 검증 | LLM06 | variant B가 tools 사용 → 과도한 agency가 공격면 | 측정 후 후속(방어 강화 모듈) |
| G4 | **reasoning 트레이스 유출** — `<think>` 내 시스템프롬프트/PII 노출 | LLM07 / LLM02 | EXAONE(추론 모델) 특유. §4 no_leak 스코어러에 반영함 | A3 no_leak 케이스에서 함께 채점 |
| G5 | **Llama Guard류 전용 분류기 벤치 대비** | - | 현 OpenAI moderation의 FPR/누락을 오픈웨이트 분류기와 수치 비교 가능 | 측정 결과 해석 시 참고, 도입은 backlog |

### 9.4 업계 공격 taxonomy 참조(케이스 작성 인풋)

A2/A3 케이스 작성 시 아래 공개 taxonomy를 참조해 커버리지를 넓힌다(도구 자체 도입이 아니라 **케이스 카탈로그로 참조**):
- **OWASP LLM Top 10 2025 (한국어판 PDF 존재)** — LLM01 인젝션(직접/간접), LLM02 민감정보 유출, LLM06 Excessive Agency, LLM07 시스템 프롬프트 유출 등([OWASP 서울챕터 한국어판](https://owasp.org/www-chapter-seoul/assets/files/TopTenForLLM-ko_KR.pdf), [삼성SDS 인사이트](https://www.samsungsds.com/kr/insights/vulnerabilities-in-large-language-models.html)).
- **garak probe 분류** — prompt injection·jailbreak·prompt extraction·encoding·data leakage.
- **국내 사례** — many-shot jailbreak, LangChain SSRF(CVE-2023-46229), RBAC 접근제어([S2W](https://s2w.inc/ko/resource/detail/759), [SeekersLab 간접 인젝션](https://seekerslab.com/ko/resources/blog/llm-security-indirect-prompt-injection-defense-1773878199037)).

### 9.5 위협 모델 가정 — 닫힌 검색 코퍼스 (G1 제외 근거)

- **가정**: 검색(RAG) 컨텍스트는 우리가 직접 수집·파싱·청킹한 **국가기관 공식 문서**(분쟁해결기준=행정규칙·별표, 분쟁조정사례)로만 구성된다. 사용자·웹 등 외부 통제 콘텐츠가 색인에 들어가지 않는다.
- **코드 확인(2026-07-05)**: pgvector chunks에 대한 런타임 쓰기 경로 없음(유일 write는 `backend/scripts/evaluation/build_quality_retrieval_log.py` 평가 로그). onboarding의 `purchase_item`/`product_category`는 `retrieval_merge` 필터 파라미터일 뿐 문서로 색인되지 않는다.
- **귀결**: 간접 프롬프트 인젝션(오염 청크로 지시 주입, OWASP LLM01 indirect)의 공격면이 사실상 닫혀 있어 **G1을 M4-A 스코프에서 제외**한다.
- **재검토 트리거**: 다음 중 하나라도 도입되면 가정이 깨지므로 G1을 다시 연다 — (a) 사용자 생성 콘텐츠(예: 커뮤니티 게시판)를 검색 색인에 포함, (b) 웹/외부 문서 실시간 수집(agentic fetch), (c) 제3자 업로드 문서 RAG.

### 9.6 참고 문헌

- [OWASP Top 10 for LLM Applications 2025 (한국어) — OWASP 서울챕터 PDF](https://owasp.org/www-chapter-seoul/assets/files/TopTenForLLM-ko_KR.pdf)
- [LLM Guardrails: Production Safety Layers Reference 2026 — Digital Applied](https://www.digitalapplied.com/blog/llm-guardrails-production-safety-layers-reference-2026)
- [Best AI Red Teaming Tools — Synack](https://www.synack.com/blog/best-ai-red-teaming-tools/)
- [LLM Red Teaming Tools: PyRIT & Garak — Amine Raji](https://aminrj.com/posts/attack-patterns-red-teaming/)
- [AI Guardrails — Production LLM Safety Guide 2026 — MyEngineeringPath](https://myengineeringpath.dev/genai-engineer/ai-guardrails/)
- [LLM Guardrails in Production — Kalvium Labs](https://www.kalviumlabs.ai/blog/guardrails-for-llm-applications/)
- [시큐리티 가드레일, 왜 필요한가 — S2W](https://s2w.inc/ko/resource/detail/759)
- [간접 프롬프트 인젝션 방어 — SeekersLab](https://seekerslab.com/ko/resources/blog/llm-security-indirect-prompt-injection-defense-1773878199037)
- [LLM 10가지 취약점 — 삼성SDS](https://www.samsungsds.com/kr/insights/vulnerabilities-in-large-language-models.html)
- 추론 모델 별도 보고서: `docs/report/2026-07-05-reasoning-vs-nonreasoning-exaone.md`
