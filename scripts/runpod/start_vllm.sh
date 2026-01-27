#!/bin/bash
# ==============================================================================
# DDOKSORI - RunPod vLLM Server Startup Script
# ==============================================================================
# 이 스크립트를 RunPod 터미널에서 실행하여 EXAONE vLLM 서버를 시작합니다.
#
# 사용법:
#   1. 로컬에서 스크립트 복사: scp scripts/runpod/start_vllm.sh root@<pod-ip>:~/
#   2. RunPod 터미널에서 실행: bash start_vllm.sh
#   3. (옵션) 특정 포트로 실행: bash start_vllm.sh --port 9011
#   4. (옵션) 특정 도메인용: bash start_vllm.sh --domain law
#
# 모델: LGAI-EXAONE/EXAONE-4.0-1.2B-Instruct
# ==============================================================================

set -e

# 기본 설정
MODEL_NAME="${MODEL_NAME:-LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct}"
PORT="${PORT:-9010}"
MAX_MODEL_LEN="${MAX_MODEL_LEN:-4096}"
GPU_MEMORY_UTILIZATION="${GPU_MEMORY_UTILIZATION:-0.9}"
DOMAIN=""

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 인자 파싱
while [[ $# -gt 0 ]]; do
    case $1 in
        --port)
            PORT="$2"
            shift 2
            ;;
        --domain)
            DOMAIN="$2"
            shift 2
            ;;
        --model)
            MODEL_NAME="$2"
            shift 2
            ;;
        --max-model-len)
            MAX_MODEL_LEN="$2"
            shift 2
            ;;
        --gpu-util)
            GPU_MEMORY_UTILIZATION="$2"
            shift 2
            ;;
        -h|--help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --port PORT        vLLM 서버 포트 (기본: 9010)"
            echo "  --domain DOMAIN    Retrieval Agent 도메인 (law, criteria, case, counsel)"
            echo "  --model MODEL      모델 이름 (기본: LG-AI-EXAONE/EXAONE-4.0-1.2B-Instruct)"
            echo "  --max-model-len N  최대 컨텍스트 길이 (기본: 4096)"
            echo "  --gpu-util RATIO   GPU 메모리 사용률 (기본: 0.9)"
            echo "  -h, --help         도움말 표시"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# 도메인별 포트 설정
if [ -n "$DOMAIN" ]; then
    case $DOMAIN in
        law)      PORT=9010 ;;
        criteria) PORT=9011 ;;
        case)     PORT=9012 ;;
        counsel)  PORT=9013 ;;
        *)
            echo -e "${RED}Error: Unknown domain '$DOMAIN'${NC}"
            echo "Valid domains: law, criteria, case, counsel"
            exit 1
            ;;
    esac
fi

echo -e "${BLUE}======================================================${NC}"
echo -e "${BLUE} DDOKSORI vLLM Server - EXAONE-4.0-1.2B${NC}"
echo -e "${BLUE}======================================================${NC}"
echo ""
echo -e "Model:     ${GREEN}$MODEL_NAME${NC}"
echo -e "Port:      ${GREEN}$PORT${NC}"
[ -n "$DOMAIN" ] && echo -e "Domain:    ${GREEN}$DOMAIN${NC}"
echo -e "Max Len:   ${GREEN}$MAX_MODEL_LEN${NC}"
echo -e "GPU Util:  ${GREEN}$GPU_MEMORY_UTILIZATION${NC}"
echo ""

# Step 1: GPU 확인
echo -e "${YELLOW}[1/4] GPU 상태 확인...${NC}"
if nvidia-smi &> /dev/null; then
    GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader | head -1)
    GPU_MEM=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader | head -1)
    echo -e "  GPU: ${GREEN}$GPU_NAME${NC}"
    echo -e "  VRAM: ${GREEN}$GPU_MEM${NC}"
else
    echo -e "${RED}Error: nvidia-smi not found. GPU required.${NC}"
    exit 1
fi

# Step 2: vLLM 설치 확인
echo -e "${YELLOW}[2/4] vLLM 설치 확인...${NC}"
if ! python -c "import vllm" 2>/dev/null; then
    echo -e "  ${YELLOW}vLLM not found. Installing...${NC}"
    pip install vllm --quiet
    echo -e "  ${GREEN}vLLM installed successfully${NC}"
else
    VLLM_VERSION=$(python -c "import vllm; print(vllm.__version__)" 2>/dev/null || echo "unknown")
    echo -e "  vLLM version: ${GREEN}$VLLM_VERSION${NC}"
fi

# Step 3: 포트 사용 확인
echo -e "${YELLOW}[3/4] 포트 $PORT 확인...${NC}"
if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    EXISTING_PID=$(lsof -Pi :$PORT -sTCP:LISTEN -t)
    echo -e "  ${YELLOW}Warning: Port $PORT already in use (PID: $EXISTING_PID)${NC}"
    read -p "  Kill existing process? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        kill $EXISTING_PID
        sleep 2
        echo -e "  ${GREEN}Process killed${NC}"
    else
        echo -e "  ${RED}Aborting. Please use a different port with --port${NC}"
        exit 1
    fi
else
    echo -e "  ${GREEN}Port $PORT available${NC}"
fi

# Step 4: vLLM 서버 시작
echo -e "${YELLOW}[4/4] vLLM 서버 시작 중...${NC}"
echo ""

# 로그 파일 설정
LOG_FILE="/tmp/vllm_${DOMAIN:-exaone}_${PORT}.log"
echo -e "Log file: ${BLUE}$LOG_FILE${NC}"
echo ""

# 서버 시작 (포그라운드)
echo -e "${GREEN}======================================================${NC}"
echo -e "${GREEN} vLLM Server Starting...${NC}"
echo -e "${GREEN}======================================================${NC}"
echo ""
echo -e "서버가 시작되면 다음을 수행하세요:"
echo ""
echo -e "  1. 로컬에서 SSH 터널링:"
echo -e "     ${BLUE}ssh -L ${PORT}:localhost:${PORT} root@<pod-ip> -N${NC}"
echo ""
echo -e "  2. 로컬에서 health check:"
echo -e "     ${BLUE}curl http://localhost:${PORT}/health${NC}"
echo ""
echo -e "  3. backend/.env 설정:"
if [ -n "$DOMAIN" ]; then
    echo -e "     ${BLUE}RETRIEVAL_LLM_${DOMAIN^^}_URL=http://localhost:${PORT}/v1${NC}"
else
    echo -e "     ${BLUE}MODEL_EXAONE_BASE_URL=http://localhost:${PORT}/v1${NC}"
fi
echo ""
echo -e "Ctrl+C로 서버 종료"
echo ""
echo "------------------------------------------------------"

# vLLM 서버 실행
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_NAME" \
    --port "$PORT" \
    --trust-remote-code \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTILIZATION" \
    2>&1 | tee "$LOG_FILE"
