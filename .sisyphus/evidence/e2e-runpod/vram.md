# Runpod VRAM 계산 및 단일 Pod 판정

## 1. 개요
EXAONE 3.5 7.8B 모델의 Runpod 호스팅 시 필요한 VRAM을 산정하고, 단일 GPU Pod에서의 서비스 가능 여부를 판정합니다.

## 2. VRAM 계산 공식

### 2.1 전체 구조
$$Total VRAM = (A) Weights + (B) Overhead + (C) KV Cache + Margin$$

### 2.2 (A) 가중치 메모리 (Weights)
모델의 파라미터가 차지하는 정적 메모리입니다.
- **공식**: $Params \times dtype\_bytes$
- **FP16/BF16**: 2 bytes per parameter
- **INT8**: 1 byte per parameter

### 2.3 (B) 런타임 오버헤드 (Overhead)
vLLM 엔진, CUDA 컨텍스트, 통신 버퍼 등이 차지하는 메모리입니다.
- **추정치**: 3~5GB (보수적으로 5GB 적용)

### 2.4 (C) KV Cache
추론 시 컨텍스트 유지를 위해 필요한 동적 메모리입니다.
- **입력 변수**:
    - $L$ (num_layers): 레이어 수
    - $KVH$ (num_key_value_heads): KV 헤드 수
    - $D$ (head_dim): 헤드 차원 ($hidden\_size / num\_attention\_heads$)
    - $T$ (tokens): 총 토큰 수 ($Concurrency \times Context\_Length$)
    - $B$ (dtype_bytes): 데이터 타입 바이트 (FP16 = 2)
- **공식**: $L \times T \times 2(K+V) \times KVH \times D \times B$
- **GiB 변환**: $Bytes / (1024^3)$
- **권장 여유분**: $KV \times 1.2$ (메모리 파편화 대비)

---

## 3. EXAONE 3.5 7.8B Worked Example

### 3.1 모델 구성 (Hugging Face 참조)
- **Model**: `LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct`
- **$L$ (num_layers)**: 32
- **$H$ (hidden_size)**: 4096
- **$A$ (num_attention_heads)**: 32
- **$KVH$ (num_key_value_heads)**: 8 (GQA 적용)
- **$D$ (head_dim)**: $4096 / 32 = 128$

### 3.2 기본 가정 (Default Settings)
- **정밀도**: FP16 (2 bytes)
- **최대 컨텍스트 ($Context\_Length$)**: 1024
- **동시성 ($Concurrency$)**: 4
- **총 토큰 ($T$)**: $1024 \times 4 = 4096$

### 3.3 계산 과정
1. **(A) Weights**: $7.8B \times 2 \approx 15.6GB$
2. **(B) Overhead**: 5.0GB
3. **(C) KV Cache**:
    - $32 \times 4096 \times 2 \times 8 \times 128 \times 2 = 536,870,912$ bytes
    - $536,870,912 / (1024^3) = 0.5GB$
    - 파편화 고려 ($1.2 \times$): $0.6GB$
4. **Total (Raw)**: $15.6 + 5.0 + 0.6 = 21.2GB$
5. **Total (with 20% Margin)**: $21.2 \times 1.2 \approx 25.44GB$

### 3.4 결론
- **필요 VRAM**: 약 **25.5GB**
- **단일 Pod 가능 여부**: **가능 (Feasible)**
    - 24GB VRAM GPU(예: RTX 3090/4090)는 마진 고려 시 타이트함.
    - **A6000 (48GB)** 또는 **A100 (40GB/80GB)** 사용 시 매우 안정적임.
    - **L4 (24GB)** 사용 시에는 동시성이나 컨텍스트 제한이 필요할 수 있음.

---

## 4. 민감도 분석 (Sensitivity Analysis)

| 변수 | 변경 | VRAM 변화 | 영향도 | 비고 |
| :--- | :--- | :--- | :--- | :--- |
| **정밀도** | FP16 → INT8 | -7.8GB | **최상** | 가중치 메모리 절반 감소 |
| **컨텍스트** | 1024 → 4096 | +1.8GB | 중 | KV Cache 4배 증가 |
| **동시성** | 4 → 16 | +1.8GB | 중 | KV Cache 4배 증가 |

- **병목 지점**: 가중치 메모리(Weights)가 전체의 약 70% 이상을 차지하므로, 모델 크기 자체가 가장 큰 병목입니다.
- **확장성**: KV Cache는 GQA(Grouped Query Attention) 덕분에 컨텍스트나 동시성 증가에 따른 메모리 상승폭이 완만합니다.

---

## 5. GPU 후보 추천

1. **최적 (Best Value)**: **NVIDIA RTX 3090 / 4090 (24GB)**
    - 마진이 적으나(21.2GB vs 24GB), 개인용/데모용으로 단일 Pod 구성 가능.
2. **안정 (Recommended)**: **NVIDIA A6000 (48GB) / A10G (24GB)**
    - A10G는 24GB로 4090과 유사하나 서버급 안정성 제공.
3. **고성능 (Scalable)**: **NVIDIA A100 (40GB)**
    - 높은 대역폭으로 빠른 추론 속도 보장 및 넉넉한 VRAM.

---

## 6. 참조
- **Model Card**: [LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct](https://huggingface.co/LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct)
- **Code Reference**: `backend/app/llm/exaone_client.py` (Default Max Tokens: 1024)
