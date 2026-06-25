# M5-4b judge 모델 비교 (gpt-4o-mini vs gpt-4o) — 결과

- 완료일: 2026-06-25
- 성격: M5-4 secondary(judge-vs-human 일치도)의 **후속 검증**. 동일 retrieval 로그·동일 사람 라벨에서 judge 모델만 교체. 코드/스키마 변경 없음(스크립트 `--model`만 변경).
- 질문: "M5-4의 낮은 일치도(kappa 0.21)가 **약한 judge(gpt-4o-mini)** 때문인가?"

## 결과

동일 입력(`quality_retrieval_log.jsonl`, 60 (query,chunk) 쌍), judge만 교체:

| judge | exact | binary(≥1) | Cohen's kappa |
| --- | --- | --- | --- |
| gpt-4o-mini | 0.4667 | 0.7667 | **0.2109** |
| gpt-4o | 0.4667 | 0.7500 | **0.1816** |

→ **강한 모델이 일치도를 높이지 못함**(오히려 약간 낮음).

### grade 분포 (왜 그런가)

| | grade 0 | grade 1 | grade 2 |
| --- | --- | --- | --- |
| **human** | 15 | 27 | 18 |
| gpt-4o-mini | 7 | 12 | **41** |
| gpt-4o | 8 | 22 | 30 |

- gpt-4o-mini는 2점을 남발(60쌍 중 41) → 강한 과대평가.
- gpt-4o는 1점을 더 많이 주어 **분포 형태는 human에 더 가까움**(보정은 더 잘 됨).
- 그럼에도 **등급 단위 일치(kappa)는 개선 안 됨**: gpt-4o가 일부 진짜 2점을 1점으로 내리고(h2→j1 4건), 무관(h0)을 1점으로 올리는(h0→j1 7건) 식으로 불일치가 분산됨.

## 해석 (핵심 학습)

1. **불일치는 judge 성능 한계가 아니라 체계적**이다. 모델을 키워도 사람의 graded relevance와 등급 단위로는 fair 수준(kappa ~0.18–0.21)에 머문다.
2. **binary(관련/무관) 일치는 양호(0.75–0.77)**, **3단계(0/1/2) 일치는 낮음(0.47)**. 즉 사람·judge는 "관련 있나"엔 대체로 동의하지만 "얼마나 관련"엔 갈린다.
3. 원인 후보: ① 사람 `relevant[]`는 M2-4R 검색랭킹용 rubric(2/1/0)로 매겨졌고, judge엔 일반적 "질문에 답하는가" 프롬프트를 줘 **rubric 정의가 다름**. ② 1-vs-2 경계의 주관성.

## 함의 (다음 단계 설계)

- **Retrieval 평가의 신뢰 지표는 사람 라벨 기반 결정론적 nDCG/MRR**(M5-4 primary). LLM judge로 검색 relevance를 자동 채점하는 것은 등급 단위에선 신중히.
- **M5-5(답변 judge)** 도 같은 함정 가능 → 답변 judge는 **rubric을 명확히**(key_points coverage는 의미 일치, must_not은 규칙 기반)하고, **M5-6에서 judge-human 일치도를 반드시 측정**해 신뢰 구간을 확인해야 함.
- judge 자동 채점을 쓰려면 **binary/coarse 기준**이 graded보다 안전.

## 산출물

- `backend/data/golden_set/quality_judge_agreement_gpt4o.json` (gpt-4o judge 상세).
- 기존 `quality_judge_agreement.json`(gpt-4o-mini) 불변.
- 재현: `judge_retrieval_relevance.py --model gpt-4o`(로그 동일).
