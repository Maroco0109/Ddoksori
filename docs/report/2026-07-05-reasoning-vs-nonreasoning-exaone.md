# 추론 모델 vs 비추론 모델, 그리고 EXAONE 4.5-33B 단독 사용 검토

- 작성일: 2026-07-05
- 목적: M4-A 계획 검토 중 제기된 추가 의문점 정리(별도 보고서)
- 범위: (1) EXAONE 4.5-33B가 추론 모델인가, gpt-4o와 무엇이 다른가 / (2) 추론 모델 vs 비추론 모델의 차이 / (3) Smoke Test B의 EXAONE 단독 사용이 타당한가
- 성격: 개념 정리 + 레퍼런스 + 우리 리포지토리 근거. 코드 변경 없음.

## 0. 세 줄 요약

- **EXAONE 4.5-33B는 추론(reasoning) 모델이다.** 답을 내기 전에 `<think>` 안에서 "생각(reasoning) 토큰"을 먼저 생성한다. gpt-4o는 **비추론** 모델이라 그 단계가 없고 생성 토큰이 곧 답이다.
- 이 구조 차이가 버그 #68(“EXAONE 빈 답변”)의 근본 원인이다. reasoning 토큰이 출력 예산(max_tokens)을 다 써버려 정작 답변이 안 나온 것이다. gpt-4o에서는 구조상 발생하지 않는 현상이다.
- **EXAONE 단독 사용은 가능하지만 "reasoning-aware"하게 써야 한다** — (a) reasoning 파서로 `<think>`를 분리, (b) reasoning 예산을 감안한 넉넉한 max_tokens, (c) 단순 질의는 non-reasoning 모드 사용. 지금 Smoke Test B는 이미 `--reasoning-parser qwen3`로 서빙 중이라 "추론 모델을 추론 모델로" 쓰고 있고, #68 픽스로 빈 답변은 fallback 합성으로 방어된다.

## 1. 추론 모델 vs 비추론 모델 — 개념

| 구분 | 비추론(Non-reasoning) | 추론(Reasoning) |
| --- | --- | --- |
| 대표 예 | gpt-4o, GPT-4.1, Claude Sonnet 4, EXAONE 4.5 **non-reasoning 모드** | o1/o3, DeepSeek-R1, EXAONE 4.5 **reasoning 모드** |
| 출력 구조 | 생성하는 모든 토큰 = 최종 답변 | 최종 답변 **앞에** 내부 사고사슬(chain-of-thought=reasoning 토큰)을 먼저 생성 |
| 토큰/비용 | 답변 길이만큼만 소비 | 답변 + reasoning 토큰만큼 소비(수십~수백 배 될 수 있음) |
| 속도 | 빠름 | 느림(대략 2배 이상). "생각" 단계가 지연으로 추가됨 |
| 강점 | 단순/저난도, 일상 대화, 빠른 응답 | 중난도 이상 추론·수학·코딩·다단계 논리 |
| 약점 | 복잡한 다단계 논리에서 단계 건너뛰어 실수 | 단순 문제를 "과잉 사고(overthink)"해 느리고 낭비 |

핵심 근거: 비추론 모델(GPT-4.1, Claude Sonnet 4 등)은 내부 reasoning 토큰을 만들지 않고 생성 토큰이 곧 답이다. 추론 모델은 응답 전에 확장된 내부 사고사슬(=reasoning 토큰)을 생성한다. 추론 모델은 중간 "thinking" 단계 때문에 완성 토큰이 추가로 생성되어 비용·지연이 늘고 속도는 대략 절반이다([Microsoft/Azure AI](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/everything-you-need-to-know-about-reasoning-models-o1-o3-o4-mini-and-beyond/4406846), [PromptHub](https://www.prompthub.us/blog/prompt-engineering-with-reasoning-models), [Medium: Thinking Fast vs Deep](https://medium.com/@anuragsingh922/thinking-fast-vs-thinking-deep-how-to-choose-between-reasoning-and-non-reasoning-ai-e7d8147e72e5)).

## 2. EXAONE 4.5-33B는 어느 쪽인가 → 추론 모델(하이브리드)

- EXAONE 4.5는 2026-04-09 LG AI Research가 공개한 모델로, 기존 **EXAONE 4.0 프레임워크(비추론+추론 통합)**에 비전 인코더를 더한 첫 오픈웨이트 VLM이다. 총 33B(비전 인코더 1.2B 포함), 262K 컨텍스트, **reasoning model**로 명시된다([Artificial Analysis](https://artificialanalysis.ai/models/exaone-4-5-33b), [HackerNoon](https://hackernoon.com/lgs-exaone-45-33b-packs-vision-reasoning-and-262k-context-into-one-model), [LG PR](https://www.prnewswire.com/news-releases/lg-reveals-next-gen-multimodal-ai-exaone-4-5-302736993.html)).
- EXAONE 4.0 계열은 **하이브리드**다: 빠른 응답용 **Non-Reasoning 모드**와 깊은 추론용 **Reasoning 모드**를 한 모델이 전환한다. Artificial Analysis 측정에서 reasoning 모드는 100M 출력 토큰, non-reasoning 모드는 15M 토큰을 썼다 — 즉 reasoning 모드가 토큰을 훨씬 많이 쓴다([EXAONE 4.0 arXiv](https://arxiv.org/html/2507.11407v1), [Artificial Analysis on X](https://x.com/ArtificialAnlys/status/1950884246803136601)).

### 우리 리포지토리 근거 (실제 배포 형태)

`docs/infrastructure/runpod-vllm-setup.md`의 서빙 커맨드:

```
vllm serve LGAI-EXAONE/EXAONE-4.5-33B ... --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser hermes ...
```

- `--reasoning-parser qwen3` → vLLM이 응답에서 `<think>…</think>` reasoning 구간을 **분리 파싱**하도록 켜져 있다. 즉 우리는 EXAONE를 **추론 모델로(추론 토큰을 내뿜는 형태로)** 서빙 중이다.
- 그래서 Smoke Test B에서 "EXAONE는 추론 모델"이라는 말이 매번 나온 것이다. 이건 결함이 아니라 **모델 성격**이다.

## 3. gpt-4o로는 문제없던 게 EXAONE 단독에선 왜 문제였나

의문점의 핵심: "API로 gpt-4o 챗봇 만들 땐 채팅 생성에 문제가 없었는데, EXAONE 단독(Smoke Test B)은 괜찮나?"

- **gpt-4o(비추론)**: 요청하면 생성 토큰이 곧 답변이다. `max_tokens`를 답변 길이에만 맞추면 된다. "생각하느라 답이 사라지는" 일이 구조적으로 없다.
- **EXAONE 4.5(추론)**: 답변 전에 `<think>` 안에서 reasoning 토큰을 먼저 소비한다. 만약
  1. `max_tokens`(출력 예산)가 작거나,
  2. 그 질의에서 reasoning이 길게 이어지면,
  → 예산이 reasoning 단계에서 소진되어 **정작 답변 토큰이 0**이 된다. 200 OK인데 `answer`가 빈 응답. 이게 **버그 #68**의 메커니즘("reasoning 토큰 소진 추정")과 정확히 일치한다.
- 즉 "gpt-4o는 되는데 EXAONE는 안 된다"가 아니라, **추론 모델은 출력 예산을 reasoning과 answer가 나눠 쓰기 때문에 토큰 예산 설계가 달라야 한다**는 뜻이다.

### EXAONE 단독 사용이 타당한가 → 조건부 예

단독 사용 자체는 문제없다. 단, 추론 모델을 다룰 때의 3가지를 지켜야 한다:

1. **reasoning 분리 파싱** — 이미 `--reasoning-parser qwen3`로 충족. answer 필드에 `<think>` 원문이 새지 않게 한다.
2. **reasoning 예산을 감안한 max_tokens** — 답변 길이만이 아니라 reasoning 몫까지 여유 있게. 소진 시 대비책 필요(우리는 #68 픽스로 빈/오버플로 답변을 fallback 합성으로 회복 → `docs/plans/modules/BUGFIX-68-results.md`).
3. **필요 시 non-reasoning 모드** — 단순 질의는 하이브리드의 non-reasoning 모드로 돌리면 토큰/지연 절감. (도입 시 backlog 후보. 지금은 측정 우선이므로 기록만.)

## 4. 측정·A/B 관점 함의 (M4-A / 스모크 테스트에 주는 시사)

- **A/B 공정성 caveat**: variant B(추론 모델 EXAONE)와 다른 구성의 지연·토큰을 비교할 때, 추론 모델은 본질적으로 **느리고 토큰을 더 쓴다**. latency·cost 지표를 볼 때 "모델 품질 차이"와 "추론 모드 오버헤드"를 섞어 해석하지 않도록 주석을 달아야 한다.
- **새로운 유출면(보안)**: 추론 모델은 `<think>` 안에 시스템 프롬프트·중간 추론·PII가 남을 수 있다. reasoning 트레이스가 사용자에게 노출되면 **시스템 프롬프트 유출(OWASP LLM07)**·정보 유출면이 된다. → M4-A no-leak 스코어러가 **answer뿐 아니라 reasoning 트레이스 누출**도 봐야 한다는 점을 계획에 반영(§업계 레퍼런스 기반 검토 참고).
- **빈 답변 = 가용성 지표**: #68류(빈/오버플로 답변)는 품질·가용성 지표(empty-rate)로 계속 관측할 가치가 있다. 추론 모델 특유의 실패 모드이기 때문이다.

## 5. 결론

- EXAONE 4.5-33B는 추론 모델이고, gpt-4o(비추론)와의 차이는 "답변 전에 reasoning 토큰을 먼저 쓴다"는 **출력 구조 차이**다.
- Smoke Test B의 EXAONE 단독 사용은 유효하다. 단 추론 모델의 토큰 예산·파싱·(선택적)모드 전환을 인지하고 써야 하며, 우리는 이미 reasoning 파서 + #68 fallback으로 핵심 리스크를 방어하고 있다.
- 후속 반영: (a) A/B 지연·토큰 해석 시 추론 오버헤드 주석, (b) no-leak 스코어러의 reasoning 트레이스 검사, (c) non-reasoning 모드 활용은 backlog.

## 참고 문헌

- [Everything You Need to Know About Reasoning Models: o1, o3, o4-mini — Microsoft/Azure AI](https://techcommunity.microsoft.com/blog/azure-ai-foundry-blog/everything-you-need-to-know-about-reasoning-models-o1-o3-o4-mini-and-beyond/4406846)
- [Prompt Engineering with Reasoning Models — PromptHub](https://www.prompthub.us/blog/prompt-engineering-with-reasoning-models)
- [Thinking Fast vs. Thinking Deep — Medium](https://medium.com/@anuragsingh922/thinking-fast-vs-thinking-deep-how-to-choose-between-reasoning-and-non-reasoning-ai-e7d8147e72e5)
- [EXAONE 4.5 33B — Artificial Analysis](https://artificialanalysis.ai/models/exaone-4-5-33b)
- [LG's EXAONE-4.5-33B Packs Vision, Reasoning, and 262K Context — HackerNoon](https://hackernoon.com/lgs-exaone-45-33b-packs-vision-reasoning-and-262k-context-into-one-model)
- [LG Reveals Next-Gen Multimodal AI 'EXAONE 4.5' — PR Newswire](https://www.prnewswire.com/news-releases/lg-reveals-next-gen-multimodal-ai-exaone-4-5-302736993.html)
- [EXAONE 4.0: Unified LLMs Integrating Non-reasoning and Reasoning Modes — arXiv](https://arxiv.org/html/2507.11407v1)
- [EXAONE 4.0 32B benchmark note — Artificial Analysis (X)](https://x.com/ArtificialAnlys/status/1950884246803136601)
- 리포지토리 근거: `docs/infrastructure/runpod-vllm-setup.md`(reasoning-parser 서빙), `docs/plans/modules/BUGFIX-68-results.md`(빈 답변 fallback)
