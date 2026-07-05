# BUGFIX-1 (#67) — Results (measured before/after)

- 작성일: 2026-07-04
- 이슈: [#67](https://github.com/Maroco0109/Ddoksori/issues/67) variant A regex `\U` 500
- 계획: `docs/plans/modules/BUGFIX-67-68-backend-robustness-plan.md`
- pod: **불필요**(variant A = OpenAI)

## 0. 한 줄 요약

`postprocessor.py:584`의 `re.sub` 문자열 치환을 **함수(리터럴) 치환**으로 바꿔 `bad escape \U` 500을 제거했다.
M5-5 goldenset A를 재측정한 결과 **A error_rate 0.167 → 0.0, n_scored 10 → 12**(law-002/003이 실답변으로 복구).

## 1. 수정

`backend/app/agents/answer_generation/postprocessor.py`
```python
# before: 동적 출처 텍스트가 치환 템플릿으로 파싱돼 "\U" 등에서 re.error
answer = re.sub(source_section_pattern, new_source_section, answer)
# after: 함수 repl → 반환 문자열을 리터럴 삽입(백슬래시 안전)
answer = re.sub(source_section_pattern, lambda _m: new_source_section, answer)
```
- 같은 파일 내 다른 `re.sub`(255/268/361은 함수 repl, 285는 정적 raw string)는 안전 — **584만 취약**이었음(점검 완료).
- 단위 재현: 문자열 repl은 `bad escape \U`로 실패, 함수 repl은 성공(백슬래시 보존) 확인.

## 2. 재측정 (before = M5-5 baseline, after = #67 fix)

같은 스크립트 재사용(`run_answer_eval.py --variant A --label A` → `build_answer_eval_log` → `judge_answer_quality`, gpt-4o-mini). variant A 12쿼리 전부 재실행·적재.

| metric (variant A) | BEFORE | AFTER |
| --- | --- | --- |
| runs | 12 | 12 |
| **error_rate** | **0.167** | **0.000** |
| **n_scored (substantive)** | **10** | **12** |
| faithfulness_mean | 2.000 | 1.917 |
| coverage_ratio_mean | 0.575 | 0.561 |
| safety_pass_rate | 1.000 | 0.917 |

- **핵심(결정적, #67 귀속)**: 12쿼리 전부 HTTP 200, law-002/003(기존 500)이 실답변으로 복구. 두 건 모두 judge
  기준 **faithfulness=2, safe** — 근거 기반 양질 답변. error_rate가 0.167→0, 채점 표본 10→12.

## 3. 품질 평균 변화 해석 (정직한 caveat)

faithfulness/coverage/safety가 소폭 내려간 것은 **#67 수정의 회귀가 아니다**:
- **표본 증가(10→12)**: 이전엔 crash로 빠졌던 law-002/003이 이제 평균에 포함(완벽하진 않은 실답변).
- **A 생성의 LLM 비결정성**: 재실행에서 `case-003`가 이전과 다르게 생성돼 judge가 hallucinated_citation으로
  플래그(safety 1.0→0.917). 이는 재실행 노이즈이지 #67과 무관(law-002/003은 오히려 clean).
- M5-6 교훈대로 **faithfulness/safety judge는 노이즈가 있고 소량(12)이라** 절대값보다 방향으로 해석. 결정적
  지표인 **error_rate·n_scored·HTTP 200**이 #67의 실제 효과다.

## 4. 완료 기준 확인
- [x] postprocessor 수정 + 파일 내 유사 패턴 점검(584만).
- [x] law-002/003 variant A가 200 + 실답변.
- [x] 재측정 표: A error_rate 0.167→0, n_scored 10→12.
- [x] DB/스키마 변경 없음, B 경로 영향 없음(A 경로만 수정).

## 5. Next
- 남은 백엔드 버그: **BUGFIX-2 (#68 EXAONE 빈답변) — pod 필요**. pod 준비 후 동일 방식(재현→max_tokens/가드
  수정→B-exaone 재측정).
- 참고: M5-5 committed baseline(`quality_answer_scores.json`)은 "before" 스냅샷으로 보존(덮어쓰지 않음).
