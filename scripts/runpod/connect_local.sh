#!/bin/bash
# ==============================================================================
# DDOKSORI - RunPod SSH Tunneling Script (로컬에서 실행)
# ==============================================================================
# RunPod vLLM 서버에 SSH 터널링으로 연결합니다.
#
# 사용법:
#   1. 단일 인스턴스 연결: ./connect_local.sh --pod-ip <IP>
#   2. 4개 인스턴스 연결: ./connect_local.sh --multi --pod-ips "IP1,IP2,IP3,IP4"
#   3. 연결 상태 확인:     ./connect_local.sh --status
#   4. 연결 종료:          ./connect_local.sh --kill
#
# 연결 후 backend/.env 설정:
#   - 단일: MODEL_EXAONE_BASE_URL=http://localhost:19010/v1
#   - 병렬: RETRIEVAL_LLM_LAW_URL=http://localhost:19010/v1 (etc.)
# ==============================================================================

set -e

# 기본 설정
SSH_KEY="${SSH_KEY:-$HOME/.ssh/id_rsa}"
SSH_USER="${SSH_USER:-root}"
BASE_LOCAL_PORT=19010
REMOTE_PORT=9010

# 색상 코드
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 도메인 목록
DOMAINS=("law" "criteria" "case" "counsel")
DOMAIN_PORTS=(19010 19011 19012 19013)

show_help() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --pod-ip IP          단일 Pod IP"
    echo "  --multi-port         단일 Pod에서 4개 포트 연결 (권장)"
    echo "  --pod-ips IP1,IP2... 다중 Pod IPs (각 Pod 1개 인스턴스)"
    echo "  --multi              다중 Pod 모드"
    echo "  --ssh-key PATH       SSH 키 경로 (기본: ~/.ssh/id_rsa)"
    echo "  --status             현재 터널링 상태 확인"
    echo "  --kill               모든 터널링 연결 종료"
    echo "  -h, --help           도움말 표시"
    echo ""
    echo "Examples:"
    echo "  # 단일 인스턴스 (공유)"
    echo "  $0 --pod-ip 123.45.67.89"
    echo ""
    echo "  # 단일 Pod에서 4개 포트 (권장, A40 등 대용량 GPU)"
    echo "  $0 --pod-ip 123.45.67.89 --multi-port"
    echo ""
    echo "  # 4개 Pod 각각 연결 (소용량 GPU)"
    echo "  $0 --multi --pod-ips \"1.1.1.1,2.2.2.2,3.3.3.3,4.4.4.4\""
    echo ""
    echo "Port Mapping:"
    echo "  law      -> localhost:19010 (remote: 9010)"
    echo "  criteria -> localhost:19011 (remote: 9011)"
    echo "  case     -> localhost:19012 (remote: 9012)"
    echo "  counsel  -> localhost:19013 (remote: 9013)"
}

check_status() {
    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE} RunPod SSH Tunnel Status${NC}"
    echo -e "${BLUE}======================================================${NC}"
    echo ""

    local any_running=false

    for i in "${!DOMAINS[@]}"; do
        local domain="${DOMAINS[$i]}"
        local port="${DOMAIN_PORTS[$i]}"

        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            local pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null | head -1)
            echo -e "  ${domain}: ${GREEN}CONNECTED${NC} (port $port, PID $pid)"
            any_running=true

            # Health check
            if curl -s "http://localhost:$port/health" >/dev/null 2>&1; then
                echo -e "         Health: ${GREEN}OK${NC}"
            else
                echo -e "         Health: ${YELLOW}WAITING${NC}"
            fi
        else
            echo -e "  ${domain}: ${RED}DISCONNECTED${NC} (port $port)"
        fi
    done

    echo ""
    if $any_running; then
        echo -e "To kill all tunnels: ${BLUE}$0 --kill${NC}"
    else
        echo -e "No active tunnels. Use ${BLUE}$0 --pod-ip <IP>${NC} to connect."
    fi
}

kill_tunnels() {
    echo -e "${YELLOW}Killing all SSH tunnels...${NC}"

    for port in "${DOMAIN_PORTS[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            local pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null)
            kill $pid 2>/dev/null && echo -e "  Killed tunnel on port $port (PID $pid)"
        fi
    done

    # 추가로 ssh 프로세스 정리
    pkill -f "ssh.*-L.*19010" 2>/dev/null || true
    pkill -f "ssh.*-L.*19011" 2>/dev/null || true
    pkill -f "ssh.*-L.*19012" 2>/dev/null || true
    pkill -f "ssh.*-L.*19013" 2>/dev/null || true

    echo -e "${GREEN}Done${NC}"
}

connect_single() {
    local pod_ip="$1"
    local local_port="${2:-19010}"
    local remote_port="${3:-9010}"

    echo -e "${YELLOW}Connecting to $pod_ip (localhost:$local_port -> :$remote_port)...${NC}"

    # 기존 연결 확인
    if lsof -Pi :$local_port -sTCP:LISTEN -t >/dev/null 2>&1; then
        echo -e "  ${YELLOW}Port $local_port already in use. Killing existing connection...${NC}"
        kill $(lsof -Pi :$local_port -sTCP:LISTEN -t) 2>/dev/null
        sleep 1
    fi

    # SSH 터널링 시작 (백그라운드)
    ssh -L $local_port:localhost:$remote_port \
        -i "$SSH_KEY" \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -N \
        ${SSH_USER}@${pod_ip} &

    local ssh_pid=$!
    sleep 2

    # 연결 확인
    if kill -0 $ssh_pid 2>/dev/null; then
        echo -e "  ${GREEN}Connected!${NC} (PID: $ssh_pid)"
        return 0
    else
        echo -e "  ${RED}Failed to connect${NC}"
        return 1
    fi
}

connect_multi_port() {
    # 단일 Pod에서 4개 포트를 한 번에 터널링 (권장)
    local pod_ip="$1"

    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE} Connecting 4 Ports on Single Pod (Recommended)${NC}"
    echo -e "${BLUE}======================================================${NC}"
    echo ""
    echo -e "Pod IP: ${GREEN}$pod_ip${NC}"
    echo ""

    # 기존 연결 정리
    for port in "${DOMAIN_PORTS[@]}"; do
        if lsof -Pi :$port -sTCP:LISTEN -t >/dev/null 2>&1; then
            kill $(lsof -Pi :$port -sTCP:LISTEN -t) 2>/dev/null
        fi
    done
    sleep 1

    # 4개 포트를 하나의 SSH 연결로 터널링
    echo -e "${YELLOW}Establishing SSH tunnel with 4 port forwards...${NC}"

    ssh -L 19010:localhost:9010 \
        -L 19011:localhost:9011 \
        -L 19012:localhost:9012 \
        -L 19013:localhost:9013 \
        -i "$SSH_KEY" \
        -o StrictHostKeyChecking=no \
        -o ServerAliveInterval=60 \
        -o ServerAliveCountMax=3 \
        -N \
        ${SSH_USER}@${pod_ip} &

    local ssh_pid=$!
    sleep 3

    if kill -0 $ssh_pid 2>/dev/null; then
        echo -e "${GREEN}Connected!${NC} (PID: $ssh_pid)"
    else
        echo -e "${RED}Failed to connect${NC}"
        exit 1
    fi

    echo ""
    echo -e "${GREEN}======================================================${NC}"
    echo -e "${GREEN} All 4 ports connected!${NC}"
    echo -e "${GREEN}======================================================${NC}"
    echo ""
    echo "Port Mapping:"
    for i in "${!DOMAINS[@]}"; do
        local domain="${DOMAINS[$i]}"
        local local_port="${DOMAIN_PORTS[$i]}"
        local remote_port=$((9010 + i))
        echo -e "  ${domain}: localhost:${local_port} -> pod:${remote_port}"
    done
    echo ""
    echo "backend/.env 설정:"
    for i in "${!DOMAINS[@]}"; do
        local domain="${DOMAINS[$i]}"
        local port="${DOMAIN_PORTS[$i]}"
        echo "RETRIEVAL_LLM_${domain^^}_URL=http://localhost:${port}/v1"
    done
    echo ""
    echo -e "상태 확인: ${BLUE}$0 --status${NC}"
    echo -e "연결 종료: ${BLUE}$0 --kill${NC}"
}

connect_multi() {
    local pod_ips_str="$1"
    IFS=',' read -ra POD_IPS <<< "$pod_ips_str"

    if [ ${#POD_IPS[@]} -ne 4 ]; then
        echo -e "${RED}Error: 4개의 Pod IP가 필요합니다 (현재: ${#POD_IPS[@]}개)${NC}"
        echo "Format: --pod-ips \"IP1,IP2,IP3,IP4\""
        exit 1
    fi

    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE} Connecting 4 Separate Pods${NC}"
    echo -e "${BLUE}======================================================${NC}"
    echo ""

    for i in "${!DOMAINS[@]}"; do
        local domain="${DOMAINS[$i]}"
        local pod_ip="${POD_IPS[$i]}"
        local local_port="${DOMAIN_PORTS[$i]}"

        echo -e "${YELLOW}[$((i+1))/4] $domain (${pod_ip})${NC}"
        connect_single "$pod_ip" "$local_port" "9010"
    done

    echo ""
    echo -e "${GREEN}======================================================${NC}"
    echo -e "${GREEN} All connections established!${NC}"
    echo -e "${GREEN}======================================================${NC}"
    echo ""
    echo "backend/.env 설정:"
    echo ""
    for i in "${!DOMAINS[@]}"; do
        local domain="${DOMAINS[$i]}"
        local port="${DOMAIN_PORTS[$i]}"
        echo "RETRIEVAL_LLM_${domain^^}_URL=http://localhost:${port}/v1"
    done
    echo ""
    echo -e "상태 확인: ${BLUE}$0 --status${NC}"
    echo -e "연결 종료: ${BLUE}$0 --kill${NC}"
}

# 메인 로직
MODE=""
POD_IP=""
POD_IPS=""
MULTI_PORT=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --pod-ip)
            POD_IP="$2"
            if [ "$MODE" != "multi-port" ]; then
                MODE="single"
            fi
            shift 2
            ;;
        --pod-ips)
            POD_IPS="$2"
            shift 2
            ;;
        --multi)
            MODE="multi"
            shift
            ;;
        --multi-port)
            MODE="multi-port"
            shift
            ;;
        --ssh-key)
            SSH_KEY="$2"
            shift 2
            ;;
        --status)
            check_status
            exit 0
            ;;
        --kill)
            kill_tunnels
            exit 0
            ;;
        -h|--help)
            show_help
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            show_help
            exit 1
            ;;
    esac
done

# SSH 키 확인
if [ ! -f "$SSH_KEY" ]; then
    echo -e "${RED}Error: SSH key not found: $SSH_KEY${NC}"
    echo "Use --ssh-key to specify the correct path"
    exit 1
fi

# 모드별 실행
if [ "$MODE" == "multi-port" ] && [ -n "$POD_IP" ]; then
    # 권장: 단일 Pod에서 4개 포트 연결
    connect_multi_port "$POD_IP"

elif [ "$MODE" == "single" ] && [ -n "$POD_IP" ]; then
    echo -e "${BLUE}======================================================${NC}"
    echo -e "${BLUE} Connecting to RunPod (Single Instance)${NC}"
    echo -e "${BLUE}======================================================${NC}"
    echo ""

    connect_single "$POD_IP" 19010 9010

    echo ""
    echo -e "${GREEN}Connection established!${NC}"
    echo ""
    echo "backend/.env 설정:"
    echo "  MODEL_EXAONE_BASE_URL=http://localhost:19010/v1"
    echo ""
    echo "Health check:"
    echo "  curl http://localhost:19010/health"
    echo ""
    echo -e "4개 포트 연결이 필요하면: ${BLUE}$0 --pod-ip $POD_IP --multi-port${NC}"
    echo -e "상태 확인: ${BLUE}$0 --status${NC}"
    echo -e "연결 종료: ${BLUE}$0 --kill${NC}"

elif [ "$MODE" == "multi" ] && [ -n "$POD_IPS" ]; then
    connect_multi "$POD_IPS"

else
    echo -e "${RED}Error: Missing required options${NC}"
    echo ""
    show_help
    exit 1
fi
