#!/bin/bash
# ==============================================================================
# DDOKSORI - RunPod vLLM Multi-Instance Startup Script
# ==============================================================================
# 단일 GPU에서 4개의 vLLM 인스턴스를 서로 다른 포트로 실행합니다.
# EXAONE 1.2B는 인스턴스당 ~4GB VRAM → A40(48GB)에서 4개 충분히 실행 가능
#
# 사용법:
#   1. 로컬에서 스크립트 복사: scp scripts/runpod/start_vllm_multi.sh root@<pod-ip>:~/
#   2. RunPod 터미널에서 실행: bash start_vllm_multi.sh
#   3. 로컬에서 연결: ./scripts/runpod/connect_local.sh --pod-ip <pod-ip> --multi-port
#
# 포트 매핑:
#   - law:      9010
#   - criteria: 9011
#   - case:     9012
#   - counsel:  9013
# ==============================================================================

set -e

# 기본 설정
MODEL_NAME="${MODEL_NAME:-LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEMORY_PER_INSTANCE="${GPU_MEMORY_PER_INSTANCE:-0.22}"  # 각 인스턴스에 ~22% VRAM 할당

# 도메인 및 포트 설정
DOMAINS=("law" "criteria" "case" "counsel")
PORTS=(9010 9011 9012 9013)

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 로그 디렉토리
LOG_DIR="/tmp/vllm_logs"
mkdir -p "$LOG_DIR"

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE} DDOKSORI vLLM Multi-Instance Server${NC}"
echo -e "${BLUE} EXAONE-4.0-1.2B × 4 Instances on Single GPU${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""

# GPU 확인
echo -e "${YELLOW}[1/3] GPU 상태 확인...${NC}"
if nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
    echo -e "  GPU: ${GREEN}$GPU_NAME${NC}"
    echo -e "  VRAM: ${GREEN}$GPU_MEM${NC}"
    echo -e "  할당: ${GREEN}${GPU_MEMORY_PER_INSTANCE} × 4 = $(echo "$GPU_MEMORY_PER_INSTANCE * 4" | bc)${NC}"
else
    echo -e "${RED}Error: nvidia-smi not found. GPU required.${NC}"
    exit 1
fi

# vLLM 설치 확인
echo -e "${YELLOW}[2/3] vLLM 설치 확인...${NC}"
if ! python -c "import vllm" 2>/dev/null; then
    echo -e "  ${YELLOW}vLLM not found. Installing...${NC}"
    pip install vllm --quiet
fi
VLLM_VERSION=$(python -c "import vllm; print(vllm.__version__)" 2>/dev/null || echo "unknown")
echo -e "  vLLM version: ${GREEN}$VLLM_VERSION${NC}"

# 기존 프로세스 정리
echo -e "${YELLOW}[3/3] 기존 프로세스 정리...${NC}"
for port in "${PORTS[@]}"; do
    if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
        PID=$(lsof -Pi :$port -sTCP:LISTEN -t)
        kill $PID 2>/dev/null
        echo -e "  Killed existing process on port $port (PID: $PID)"
    fi
done
sleep 2

echo ""
echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN} Starting 4 vLLM Instances...${NC}"
echo -e "${GREEN}======================================================${NC}"
echo ""

# 4개 인스턴스 시작
PIDS=()
for i in "${!DOMAINS[@]}"; do
    domain="${DOMAINS[$i]}"
    port="${PORTS[$i]}"
    log_file="$LOG_DIR/vllm_${domain}.log"

    echo -e "${YELLOW}[$((i+1))/4] Starting $domain (port $port)...${NC}"

    # 백그라운드로 vLLM 시작
    nohup python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL_NAME" \
        --port "$port" \
        --trust-remote-code \
        --max-model-len "$MAX_MODEL_LEN" \
        --gpu-memory-utilization "$GPU_MEMORY_PER_INSTANCE" \
        > "$log_file" 2>&1 &

    PID=$!
    PIDS+=($PID)
    echo -e "  PID: $PID, Log: $log_file"

    # 잠시 대기 (모델 로딩 순차화)
    if [ $i -lt 3 ]; then
        sleep 5
    fi
done

echo ""
echo -e "${YELLOW}Waiting for all instances to be ready...${NC}"

# 모든 인스턴스 Health Check
MAX_WAIT=120
for i in "${!DOMAINS[@]}"; do
    domain="${DOMAINS[$i]}"
    port="${PORTS[$i]}"

    echo -n "  $domain (port $port): "
    for j in $(seq 1 $MAX_WAIT); do
        if curl -s "http://localhost:$port/health" >/dev/null 2>&1; then
            echo -e "${GREEN}READY${NC}"
            break
        fi
        if [ $j -eq $MAX_WAIT ]; then
            echo -e "${RED}TIMEOUT${NC}"
        fi
        sleep 1
    done
done

echo ""
echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN} All Instances Running!${NC}"
echo -e "${GREEN}======================================================${NC}"
echo ""
echo "Instances:"
for i in "${!DOMAINS[@]}"; do
    echo -e "  ${DOMAINS[$i]}: http://localhost:${PORTS[$i]}/v1 (PID: ${PIDS[$i]})"
done
echo ""
echo "Logs:"
echo "  tail -f $LOG_DIR/vllm_*.log"
echo ""
echo -e "${BLUE}로컬에서 SSH 터널링:${NC}"
echo "  ssh -L 19010:localhost:9010 -L 19011:localhost:9011 \\"
echo "      -L 19012:localhost:9012 -L 19013:localhost:9013 \\"
echo "      root@<pod-ip> -N"
echo ""
echo -e "${BLUE}또는 스크립트 사용:${NC}"
echo "  ./scripts/runpod/connect_local.sh --pod-ip <pod-ip> --multi-port"
echo ""
echo -e "${BLUE}backend/.env 설정:${NC}"
echo "  RETRIEVAL_LLM_LAW_URL=http://localhost:19010/v1"
echo "  RETRIEVAL_LLM_CRITERIA_URL=http://localhost:19011/v1"
echo "  RETRIEVAL_LLM_CASE_URL=http://localhost:19012/v1"
echo "  RETRIEVAL_LLM_COUNSEL_URL=http://localhost:19013/v1"
echo ""
echo "To stop all instances:"
echo "  pkill -f 'vllm.entrypoints'"
echo ""

# 프로세스 모니터링 (선택)
read -p "Monitor GPU usage? [y/N] " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    watch -n 2 nvidia-smi
fi
