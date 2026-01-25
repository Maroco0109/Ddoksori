# PR2: Orchestrator Model Analysis

## Executive Summary
본 보고서는 똑소리(DDOKSORI) 프로젝트의 오케스트레이터 모델 구성을 분석하고, 답변 품질 및 한국어 법률 추론 능력 향상을 위한 30B+ 파라미터급 모델 도입 방안을 제안합니다. 현재 시스템은 비용 효율적인 `gpt-4o-mini`와 로컬 `EXAONE 3.5 7.8B` 모델을 혼합하여 사용하고 있으나, 복잡한 소비자 분쟁 사례의 법률적 해석과 고품질 답변 생성에서 한계가 관찰되고 있습니다.

분석 결과, **Legal Review**와 **Answer Generation** 단계에 `Claude 3.5 Sonnet` 또는 `EXAONE 3.5 32B`를 도입할 경우 추론 정확도가 대폭 향상될 것으로 기대됩니다. 특히 한국어 특화 성능이 뛰어난 `EXAONE 3.5 32B`를 로컬 GPU(A100/H100)에 배치하거나, 범용 성능이 검증된 `GPT-4o`를 하이브리드로 운영하는 전략을 추천합니다. 이를 통해 할루시네이션을 최소화하고 전문적인 법률 상담 서비스를 제공할 수 있습니다.

## Current Model Inventory
| Model | Parameters | Role | Provider | Cost/1M tokens (In/Out) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **gpt-4o-mini** | ~8B (est.) | Generation, Review, Analysis | OpenAI | $0.15 / $0.60 | Primary model, fast & cheap |
| **EXAONE 3.5 7.8B** | 7.8B | ReAct Think, Rewrite | Local (RunPod) | $0.00 (Self-hosted) | Korean optimized, local inference |
| **EXAONE 3.5 2.4B** | 2.4B | Query Analysis (Planned) | Local (RunPod) | $0.00 (Self-hosted) | Lightweight, for classification |
| **claude-3-haiku** | ~20B (est.) | Generation Fallback | Anthropic | $0.25 / $1.25 | Secondary fallback model |

## Model Role Mapping
### Generation Agent
- **Current**: `gpt-4o-mini`
- **Role**: RAG 컨텍스트를 기반으로 최종 답변 초안 작성.
- **Issue**: 복잡한 법률 논리 구성 시 문장이 단조롭거나 세부 사항 누락 가능성.

### Reasoning Agent (ReAct)
- **Current**: `EXAONE 3.5 7.8B` (Mode: LLM)
- **Role**: 검색 필요성 판단 및 도구 호출 결정.
- **Issue**: 7.8B 모델의 한계로 인해 복잡한 다단계 추론 시 루프에 빠지거나 잘못된 도구 선택 발생.

### Query Analysis Agent
- **Current**: `gpt-4o-mini` / `EXAONE 3.5 2.4B` (Fine-tuning 중)
- **Role**: 사용자 의도 분류 및 엔티티 추출.
- **Issue**: 법률 용어와 일상어 혼재 시 분류 정확도 개선 필요.

### Legal Review Agent
- **Current**: `gpt-4o-mini` (LLM Review 활성화 시)
- **Role**: 답변의 법률적 정확성 및 금지 표현 검토.
- **Issue**: 가장 높은 신뢰도가 요구되는 단계이나 경량 모델 사용으로 인해 정교한 검토 부족.

## 3-Axis Analysis
### Cost Analysis
- **Current State**: 월 평균 10만 건 요청 기준, `gpt-4o-mini` 위주 운영 시 약 $50~$100 수준의 저렴한 비용 유지.
- **30B+ Upgrade**: `GPT-4o` 또는 `Claude 3.5 Sonnet` 전면 도입 시 비용이 10~20배 상승 ($1,000+).
- **Optimization**: 핵심 노드(Review, Generation)에만 고성능 모델을 배치하고, 나머지는 경량 모델을 유지하는 하이브리드 전략으로 비용 효율성 확보 가능.

### Performance Analysis
- **Accuracy**: 30B+ 모델은 7B급 대비 MMLU 및 한국어 특화 벤치마크에서 15~25% 높은 성능을 보임. 특히 법률적 인과관계 파악 능력이 탁월함.
- **Hallucination**: 고성능 모델일수록 컨텍스트 준수 능력이 뛰어나 RAG 시스템의 고질적인 문제인 할루시네이션 억제에 유리.
- **Korean Quality**: `EXAONE 3.5 32B`는 한국어 법률 용어 이해도에서 글로벌 모델 대비 우위를 점함.

### Latency Analysis
- **API Latency**: `GPT-4o` (약 2-3s), `Claude 3.5 Sonnet` (약 3-4s)로 `gpt-4o-mini` (1s 미만) 대비 지연시간 증가.
- **Local Inference**: `EXAONE 3.5 32B`를 A100 80GB에서 vLLM으로 구동 시 약 20~30 tokens/sec 확보 가능하나, 인프라 비용 고려 필요.
- **User Experience**: 스트리밍 응답을 통해 체감 지연시간 완화 필수.

## 30B+ Model Comparison
| Model | Parameters | Cost/1M (In/Out) | Latency | Korean Quality | Best For |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **GPT-4o** | Unknown | $2.50 / $10.00 | Low | Excellent | General Reasoning, Speed |
| **Claude 3.5 Sonnet** | Unknown | $3.00 / $15.00 | Medium | Excellent | Complex Logic, Legal Review |
| **EXAONE 3.5 32B** | 32B | $0.00 (Local) | High (Local) | Best | Korean Legal Context, Privacy |
| **Llama 3.1 70B** | 70B | $0.60 / $0.90* | High | Good | Open-source standard, Cost-eff |
*\*Groq/Together AI 등 API 제공사 기준*

### GPT-4o
- **Pros**: 가장 빠른 응답 속도, 검증된 한국어 성능, 강력한 멀티모달 기능.
- **Cons**: 높은 API 비용, 데이터 프라이버시 우려 (Enterprise 미사용 시).

### Claude 3.5 Sonnet
- **Pros**: 추론의 깊이가 깊고 지시 이행 능력이 매우 뛰어남. 법률 검토(Review) 노드에 최적.
- **Cons**: GPT-4o 대비 약간 느린 속도, 한국어 구어체에서 간혹 어색한 표현.

### EXAONE 3.5 32B
- **Pros**: 한국어 법률 및 공공 데이터 학습 비중이 높아 국내 도메인에 최적화. 로컬 배포 시 데이터 보안 완벽.
- **Cons**: 고사양 GPU 인프라(A100 이상) 필수, vLLM 최적화 필요.

### Llama 3.1 70B
- **Pros**: 오픈소스 모델 중 최강의 성능, 다양한 API 제공사를 통한 저렴한 이용 가능.
- **Cons**: 한국어 특화 튜닝 없이는 한국어 법률 용어 처리에 한계.

## Migration Roadmap
### Phase 1: Low-Risk Replacements (Short-term)
- **Target**: `Legal Review Agent`
- **Action**: `gpt-4o-mini`를 `Claude 3.5 Sonnet`으로 교체.
- **Reason**: 최종 검증 단계의 품질을 높여 서비스 신뢰도 즉각 향상. 실패 시 기존 모델로 즉시 롤백 가능.

### Phase 2: High-Impact Upgrades (Medium-term)
- **Target**: `Answer Generation Agent`
- **Action**: `gpt-4o-mini`를 `GPT-4o` 또는 `EXAONE 3.5 32B`로 업그레이드.
- **Reason**: 사용자에게 전달되는 답변의 논리 구조와 전문성 강화.

### Phase 3: Full Optimization (Long-term)
- **Target**: `Orchestrator Core (ReAct Think)`
- **Action**: 전체 추론 루프를 `EXAONE 3.5 32B` 로컬 모델로 통합.
- **Reason**: 운영 비용 절감 및 데이터 주권 확보. 고사양 GPU 클러스터 기반 안정적 서비스 구축.

## Risk Assessment
### Technical Risks
- **Prompt Sensitivity**: 모델 변경 시 기존 프롬프트의 지시 이행 방식이 달라져 결과값이 변할 수 있음.
- **Infrastructure**: 32B+ 모델 로컬 서빙 시 메모리 부족(OOM) 또는 지연시간 급증 위험.

### Cost Risks
- **API Budget**: 고성능 모델 사용량 증가에 따른 비용 폭증 가능성.
- **GPU Cost**: 로컬 서버 유지 비용이 API 비용을 상회할 수 있음.

### Mitigation Strategies
- **Prompt Engineering**: 모델별 전용 프롬프트 최적화 및 Few-shot 예제 보강.
- **Hybrid Routing**: 단순 질의는 경량 모델, 복잡 질의는 고성능 모델로 분기하는 라우터 도입.
- **Quantization**: 로컬 모델 도입 시 AWQ/GPTQ 양자화를 통해 GPU 메모리 점유율 최적화.

## Recommendations
### Short-term (1-2 months)
- **Legal Review** 노드에 `Claude 3.5 Sonnet` 도입하여 답변 신뢰도 확보.
- `gpt-4o-mini`는 Query Analysis 및 단순 대화용으로 유지하여 비용 밸런스 조절.

### Medium-term (3-6 months)
- **Answer Generation** 노드에 `EXAONE 3.5 32B` (Local) 또는 `GPT-4o` 도입 실험.
- 한국어 법률 특화 벤치마크 데이터셋을 구축하여 모델 성능 정량 평가 실시.

### Long-term (6-12 months)
- 전용 GPU 인프라를 확보하여 `EXAONE 3.5 32B` 기반의 완전 로컬 RAG 시스템 구축.
- 특정 소비자 분쟁 도메인에 특화된 30B+ 모델 파인튜닝 검토.
