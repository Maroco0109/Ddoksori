# M2-5R B 최소 골격 (결과 문서)

- 작성일: 2026-06-23
- 모듈: `M2-5R` B(Agentic RAG) 최소 골격
- 상위 계획: `docs/plans/modules/M2-5R-b-skeleton-plan.md`
- 성격: 구현 결과. **A(MAS) 무변경** — B는 격리 신규 모듈 `backend/app/variant_b/`.

## 0. 한 줄 요약

LangGraph ReAct 기반 B 골격 구현: retrieval tool 1개(`search_consumer_disputes`, A의 `search_hybrid_rrf` 래핑) + 결정형 cosine 게이트 단발 clarification + trace. **frontier(gpt-4o-mini)로 end-to-end 검증 완료.** EXAONE tool-calling smoke는 pod migration으로 환경 재구축 중 → **후속**.

## 1. 산출물

| 파일 | 내용 |
| --- | --- |
| `backend/app/variant_b/tools.py` | `search()` 헬퍼 + `search_consumer_disputes` tool. A의 `search_hybrid_rrf`(필터없음) 래핑 → A/B parity, `max_cosine` 반환 |
| `backend/app/variant_b/model.py` | model factory. `frontier`(ChatOpenAI) / `exaone`(ChatOpenAI base_url=vLLM) 전환 |
| `backend/app/variant_b/agent.py` | `run_b()`: 게이트 retrieval → cosine<τ면 단발 clarification, 아니면 `create_react_agent` 답변. trace 반환 |
| `backend/scripts/testing/variant_b/smoke_b.py` | CLI smoke(명확/모호 2케이스), LangSmith 추적 비활성 |

## 2. frontier smoke 결과 (검증됨)

실행: `smoke_b.py --model frontier --tau 0.45` (py3.12 venv: langgraph 1.2.6, langchain-openai 1.3.3; 로컬 pgvector DB; OpenAI 임베딩+gpt-4o-mini)

| 케이스 | 입력 | max_cosine | 동작 | 결과 |
| --- | --- | --- | --- | --- |
| 명확 | "온라인으로 산 옷을 단순 변심으로 환불…" | 0.6616 | clarified=False → **tool 호출** → 근거기반 답변 | 전자상거래법 7일 청약철회 안내(근거 기반) ✅ |
| 모호 | "도와주세요" | 0.3961 | 0.396 < τ(0.45) → **단발 clarification**(tool 미호출, 루프 없음) | 구체화 요청 1회 ✅ |

→ **ReAct+tool 호출, 근거기반 생성, 결정형 cosine 게이트 단발 clarification, trace(tool name/args 기록)** 모두 동작.

## 3. 결정형 cosine 게이트

- 첫 retrieval `max_cosine < τ`(기본 0.45)면 `request_clarification` **1회**, 루프 없음. 관측 relevant cosine ≈ 0.40~0.66에서 τ=0.45가 두 케이스를 잘 분리.
- 신호는 **B 내부**(retrieval tool의 vector_similarity)에서 계산 — A 의존 없음(M2-4R 재정의 방침과 일치).
- τ는 M2-7R에서 `clarification_rate`로 정량 튜닝 예정.

## 4. EXAONE smoke — 후속 (pending)

- 사유: H100 pod migration으로 SSH/환경이 초기화되어 재구축 중. B 로직은 frontier로 이미 검증되어, EXAONE smoke는 *동일 코드 base_url 교체*로 vLLM tool-calling만 확인하는 단계.
- 실행 방법(환경 복구 후):
  ```bash
  # pod Resume + tool-calling 재기동:
  #   vllm serve LGAI-EXAONE/EXAONE-4.5-33B ... --enable-auto-tool-choice --tool-call-parser hermes --reasoning-parser deepseek_r1
  # 터널: ssh -N -L 19080:localhost:8000 <pod-ssh>
  EXAONE_MODEL=LGAI-EXAONE/EXAONE-4.5-33B \
  python backend/scripts/testing/variant_b/smoke_b.py --model exaone --env <repo>/.env
  ```
  > 주의: `.env`의 `EXAONE_MODEL`은 stale(3.5-7.8B) → smoke 시 4.5-33B로 override. EXAONE 4.5 커스텀 vLLM fork의 `--tool-call-parser hermes` 지원 여부는 미확인(실패 시 파서 점검).

## 5. 완료 상태 / 검증

- ✅ frontier end-to-end(ReAct+tool+게이트+trace), A 무변경(별도 모듈, MAS diff 0).
- ⏳ EXAONE tool-calling smoke(pod 복구 후 후속).
- M2-5R는 **frontier 기준 기능 완료**, EXAONE 검증은 후속 항목.

## 6. 환경 메모

- B venv(리포 밖, 미커밋): `~/.venvs/ddoksori-b` (py3.12). 시스템 py3.14에서 핀고정 requirements 전체설치는 위험 → B는 별도 venv.
- DB: localhost:5432/ddoksori (.env의 `DB_HOST=postgres`는 host에서 안 붙음 → tool은 localhost 기본값 사용).

## 7. Next gate

M2-6R: 나머지 retrieval tool(criteria/case) + verify_citation + get_law_article/get_case_detail + guardrail pre/post + `/chat?variant=B` 엔드포인트 배선. (EXAONE smoke는 pod 복구 시 본 모듈 후속으로 마무리.)
