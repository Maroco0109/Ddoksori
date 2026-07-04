# 백엔드 버그 수정 — #67 / #68 (계획서)

- 작성일: 2026-07-04
- 성격: **측정된 before/after 개선.** M5-5 측정이 잡아낸 백엔드 결함을 고치고, 동일 측정으로 회귀 델타를 수치화한다.
- 관련 이슈: [#67](https://github.com/Maroco0109/Ddoksori/issues/67)(variant A regex 500), [#68](https://github.com/Maroco0109/Ddoksori/issues/68)(EXAONE 빈답변)
- 근거: `docs/plans/modules/M5-5-answer-generation-quality-results.md` §5. 우선순위 [[ddoksori-portfolio-priority-shift]].
- 두 서브모듈, **한 번에 하나씩**: **BUGFIX-1(#67, pod 불필요)** → **BUGFIX-2(#68, pod 필요)**.

## 0. pod 필요 여부 (요약)

| 서브모듈 | pod | 이유 |
| --- | --- | --- |
| BUGFIX-1 (#67) | **불필요** | variant A는 OpenAI(gpt-4o-mini). law-002/003으로 재현·검증 |
| BUGFIX-2 (#68) | **필요** | EXAONE 고유(reasoning+ReAct). RunPod EXAONE pod + 터널 없이는 재현·검증 불가 |

## 1. 포트폴리오 프레이밍 (왜 이 방식)

- 이 버그들은 **측정 시스템(M5-5)이 잡아낸** 것이다: A error_rate 0.167(=law-002/003 crash), B-exaone error_rate 0.25(500 1 + 빈답변 2).
- 따라서 "고쳤다"에 그치지 않고, **동일 스크립트로 재측정**해 before/after 델타(error_rate 하락, n_scored 상승)를 표로 남긴다 → "측정→발견→수정→재측정" 회귀 서사 확보.
- **재사용**: M5-5 스크립트 그대로 (`run_answer_eval.py` → `build_answer_eval_log.py` → `judge_answer_quality.py`). 신규 도구 없음.

---

## BUGFIX-1 — #67 variant A regex `\U` 500 (pod 불필요)

### 원인
`backend/app/agents/answer_generation/postprocessor.py:584`
```python
new_source_section = "[출처]\n\n" + "\n\n".join(source_entries)   # 동적 텍스트
answer = re.sub(source_section_pattern, new_source_section, answer)  # repl이 치환 템플릿으로 해석
```
`re.sub`의 문자열 repl은 `\U`/`\1`/`\g<..>` 등을 치환 시퀀스로 파싱한다. 출처 텍스트에 `\U`가 포함되면 `re.error: bad escape \U` → HTTP 500. law-002/003에서 재현(콘텐츠 결정적).

### 수정 (한 줄)
치환을 **함수(리터럴)로** 넘겨 백슬래시를 그대로 취급:
```python
answer = re.sub(source_section_pattern, lambda _m: new_source_section, answer)
```
- 함수 repl은 반환 문자열을 리터럴로 삽입(템플릿 파싱 없음) → 어떤 백슬래시도 안전.
- 부수: 같은 파일 내 **다른 문자열 repl `re.sub`** 도 동적 텍스트를 쓰면 동일 취약 → 점검(246~268은 이미 함수 repl이라 안전, 584만 문자열).

### 검증 (measured before/after, pod 불필요)
1. 단위: `re.sub(pat, lambda _m: "...\\Uxxxx...", s)`가 안 터짐 확인.
2. 라이브: 백엔드(docker) 기동 → law-002/003을 variant A로 `/chat` → **200 + 실답변**(기존 500).
3. 재측정: `run_answer_eval.py --variant A --label A` 재실행 → `build_answer_eval_log` → `judge_answer_quality` →
   **A error_rate 0.167→0, n_scored 10→12** 확인. 결과 표를 results 문서에 before/after로 기록.

### 완료 기준
- [ ] postprocessor 수정 + 파일 내 유사 패턴 점검.
- [ ] law-002/003 variant A가 200 + 실답변.
- [ ] 재측정 표: A error_rate 하락(0.167→0), n_scored 상승.
- [ ] DB/스키마 변경 없음, 다른 경로(B) 영향 없음.

---

## BUGFIX-2 — #68 EXAONE 빈답변 (pod 필요)

### 원인 (추정, pod로 확정)
`backend/app/variant_b/model.py::get_chat_model` exaone 분기에 **`max_tokens` 미설정**:
```python
return ChatOpenAI(model=..., base_url=base_url, api_key=..., temperature=temperature)  # max_tokens 없음
```
EXAONE 4.5는 reasoning 모델 — 답 이전 reasoning에 토큰을 먼저 쓴다(runbook §3.4). ReAct 다단계로 컨텍스트가
쌓인 상태에서 per-request 토큰 예산이 부족하면 reasoning이 다 소진 → `finish_reason:"length"` +
**`content:null`**. case-001/003(191s/227s 후 빈답변)이 이 패턴.

### 수정 방향 (pod로 검증하며 확정)
1. **1차**: exaone ChatOpenAI에 넉넉한 `max_tokens` 명시(예: 1024~2048; runbook은 reasoning 답변에 512+ 권장, ReAct는 더). frontier/exaone별로 다르게 줄 수 있음.
2. **2차(가드)**: ReAct 최종 메시지 `content`가 비면 fallback(명시적 안내 문구 또는 1회 재시도). 빈 문자열이 사용자에게 그대로 나가지 않게.
3. **점검**: ReAct recursion/step 한도와 서버 `--max-model-len 8192` 대비 누적 토큰. (서버 max-model-len 상향은 KV 캐시 OOM 위험이라 지양 — 클라이언트 max_tokens·step 제어 우선.)
- 정확한 임계는 **pod로 case-001/003 재현**하며 `usage`/`finish_reason` 관찰해 확정.

### 검증 (pod 필요)
0. **선행: RunPod EXAONE 4.5-33B pod 기동 + SSH 터널 + `EXAONE_RUNPOD_URL`**(runbook `runpod-vllm-setup.md`).
1. 재현: 수정 전 case-001/003 variant B(exaone)로 빈답변 확인(`finish_reason:length`).
2. 수정 후: 같은 쿼리가 실답변(`content` 채워짐) 확인.
3. 재측정: `run_answer_eval.py --variant B --label Bexaone` (VARIANT_B_MODEL_SPEC=exaone) 재실행 → build/judge →
   **B-exaone error_rate 0.25→하락, n_scored 9→상승**. before/after 표 기록.

### 완료 기준
- [ ] exaone max_tokens 명시 + 빈 content 가드.
- [ ] case-001/003이 실답변 반환.
- [ ] 재측정 표: B-exaone error_rate 하락, n_scored 상승.
- [ ] frontier 경로 회귀 없음, DB/스키마 변경 없음.

---

## 산출물 (Impl PR 예정)
- BUGFIX-1: `postprocessor.py` 수정 + results 문서(before/after A 표) 또는 PR 본문 증빙.
- BUGFIX-2: `variant_b/model.py`(+ agent.py 가드) 수정 + before/after B-exaone 표.
- (선택) 통합 결과 문서 `docs/plans/modules/BUGFIX-67-68-results.md`.

## caveat
- 재측정은 소량(12/쿼리)라 델타를 절대 지표보다 **방향(error_rate 하락)** 으로 해석.
- #67 수정으로 law-002/003이 새로 채점되면 A의 faithfulness/coverage 평균이 바뀔 수 있음(정상 — 표본이 10→12로 커짐). 이를 명시.
- judge 신뢰도는 M5-6 기준(coverage 신뢰, faithfulness는 binary/상대) 유지.

## 진행 순서
**BUGFIX-1 먼저**(pod 없이 지금 가능, 클린 승리) → 결과 논의 → **pod 준비되면 BUGFIX-2**. 한 번에 하나씩.
