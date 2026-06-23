# M2-6R B 풀 파이프라인 (결과 문서)

- 작성일: 2026-06-24
- 모듈: `M2-6R` B 확장 (서브 PR 3개로 진행)
- 상위 계획: `docs/plans/modules/M2-6R-b-full-pipeline-plan.md`
- 성격: 구현 결과. **A(MAS) 무변경** — variant 미지정 시 기존 A 경로 그대로.

## 0. 한 줄 요약

M2-5R 골격 위에 ① domain retrieval + verify_citation + lookup tools ② guardrail pre/post ③ `/chat?variant=B` 최소 엔드포인트를 더해 B v1 풀 파이프라인 완성. ①② frontier smoke 통과, ③ 코드 완료(라이브 HTTP e2e는 전체 백엔드 구동 필요 → 후속).

## 1. 서브 PR 요약

| 서브 | PR | 내용 | 검증 |
| --- | --- | --- | --- |
| ① tools | #31 | `search_consumer_disputes(domain)` + `verify_citation` + `get_law_article` + `get_case_detail` | `smoke_tools.py` ALL OK |
| ② guardrail | #32 | `run_b` 입력/출력 guardrail(A `moderation.py` 재사용) | `smoke_guardrail.py` ALL OK |
| ③ endpoint | (이 PR) | `/chat?variant=B` 최소 non-streaming | py_compile + 계약 검증(아래) |

## 2. ③ 엔드포인트 설계

- `backend/app/api/models.py`: `ChatRequest`에 `variant: Literal["A","B"] = "A"` 추가.
- `backend/app/api/chat.py`: `session_id` 설정 직후, **그래프/메모리 셋업 전**에 분기:
  ```python
  if body.variant == "B":
      from app.variant_b.agent import run_b
      b_result = await asyncio.to_thread(run_b, body.message, top_k=body.top_k or 5)
      clarified = bool(b_result.get("clarified", False))
      return ChatResponse(session_id=session_id, answer=b_result["answer"],
                          chunks_used=0, model="variant-b", sources=[],
                          has_sufficient_evidence=not clarified,
                          clarifying_questions=[b_result["answer"]] if clarified else [])
  ```
- **variant 미지정/"A" → 기존 A 경로 그대로**(분기만 추가, A 동작 무변경). 동기 `run_b`는 `asyncio.to_thread`로 실행해 이벤트 루프 비차단.

## 3. ③ 검증

- ✅ **py_compile OK**: `chat.py`, `models.py` 구문 유효.
- ✅ **계약 일치**: ChatResponse 매핑 필드(session_id/answer/chunks_used/model/sources/has_sufficient_evidence/clarifying_questions)가 모델 정의와 모두 일치. `variant`는 기존 `chat_type`과 동일한 `Literal` 패턴.
- ✅ **run_b 자체는 M2-5R/M2-6R-①·② smoke로 검증됨.**
- ⏳ **라이브 HTTP e2e = 후속**: 전체 백엔드 구동 필요. 미니 venv(`~/.venvs/ddoksori-b`)·시스템 py3.14로는 full requirements(prometheus_client, fastapi, pydantic-settings, redis …)를 올릴 수 없어 TestClient/서버 e2e를 이 환경에서 실행 불가.
  - 백엔드 구동 후 실행:
    ```bash
    curl -s -X POST localhost:8000/chat -H 'Content-Type: application/json' \
      -d '{"message":"온라인으로 산 옷 단순변심 환불 가능?","variant":"B"}'
    # variant 생략 또는 "A" → 기존 MAS 경로(무변경) 확인
    ```

## 4. A 무변경 보장

- B 분기는 A의 그래프/메모리/응답 빌더 호출 전에 early-return. variant 미지정 시 코드 경로는 기존과 동일.
- B의 tool/guardrail은 A의 SQL 함수·moderation 모듈을 **read-only 재사용**(중복 구현 없음, A 파일 미수정 — chat.py/models.py만 분기/필드 추가).

## 5. 완료 상태

- ✅ ① tools, ② guardrail (frontier smoke 통과).
- ✅ ③ endpoint 코드 완료 + 계약/구문 검증.
- ⏳ ③ 라이브 HTTP e2e (백엔드 구동 시 후속).
- **M2-6R 기능 완료** (e2e는 환경 구동 후 확인).

## 6. Next gate

M2-7R: A/B 비교 런 — M2-4R 하니스+동일 eval셋으로 A(Advanced RAG) vs B(Agentic RAG) retrieval 측정(nDCG/HitRate) + latency/clarification_rate/허위인용 차단율/trace 완전성 종합. (B는 `run_b` 직접 호출로 측정; pod는 EXAONE-B 측정 시에만.)
