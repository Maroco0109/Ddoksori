#!/bin/bash

# Configuration
BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEST_DIR="$BACKEND_DIR/scripts/testing"
export PYTHONPATH="$BACKEND_DIR:$PYTHONPATH"

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Helper function
run_pytest() {
    local target=$1
    echo -e "${GREEN}Running tests for: $target${NC}"
    # Use absolute path to conda python
    /home/maroco/miniconda3/envs/dsr/bin/python -m pytest -v "$target"
    if [ $? -ne 0 ]; then
        echo -e "${RED}Tests failed for $target${NC}"
        exit 1
    fi
}

# Main logic
case "$1" in
    "api")
        run_pytest "$TEST_DIR/api"
        ;;
    "integration")
        run_pytest "$TEST_DIR/integration"
        ;;
    "data")
        run_pytest "$TEST_DIR/data"
        ;;
    "all")
        echo -e "${GREEN}Running ALL tests...${NC}"
        run_pytest "$TEST_DIR"
        ;;
    *)
        echo "Usage: $0 {api|integration|data|all}"
        exit 1
        ;;
esac

echo -e "${GREEN}✅ All requested tests passed!${NC}"
