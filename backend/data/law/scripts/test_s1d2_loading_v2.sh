#!/bin/bash
# S1-D2 법령 데이터 로딩 및 검증 테스트 스크립트 (Docker 환경 대응)

set -e  # 에러 발생 시 중단

echo "=========================================="
echo "S1-D2: 법령 데이터 로딩 및 검증 테스트"
echo "=========================================="
echo

# 환경 확인
echo "1. 환경 확인"
echo "  - conda 환경: $CONDA_DEFAULT_ENV"
if [ "$CONDA_DEFAULT_ENV" != "dsr" ]; then
    echo "  ⚠️  경고: dsr 환경이 아닙니다. 'conda activate dsr' 실행 필요"
    exit 1
fi
echo "  ✓ dsr 환경 활성화 확인"
echo

# Docker 컨테이너 상태 확인
echo "2. PostgreSQL Docker 컨테이너 확인"
if docker ps --filter "name=ddoksori_db" --format "{{.Status}}" | grep -q "Up"; then
    echo "  ✓ PostgreSQL 컨테이너 실행 중"
else
    echo "  ❌ PostgreSQL 컨테이너가 실행 중이 아닙니다"
    echo "  다음 명령으로 시작하세요: docker-compose up -d db"
    exit 1
fi
echo

# 데이터베이스 연결 테스트 (Python 사용)
echo "3. 데이터베이스 연결 테스트 (Python)"
cat > /tmp/test_db_connection.py << 'EOF'
import os
import psycopg

try:
    conn = psycopg.connect(
        host=os.environ.get('PGHOST', 'localhost'),
        port=int(os.environ.get('PGPORT', '5432')),
        dbname=os.environ.get('PGDATABASE', 'ddoksori'),
        user=os.environ.get('PGUSER', 'postgres'),
        password=os.environ.get('PGPASSWORD', 'postgres')
    )
    print("  ✓ PostgreSQL 연결 성공")
    conn.close()
except Exception as e:
    print(f"  ❌ PostgreSQL 연결 실패: {e}")
    exit(1)
EOF

conda run -n dsr python /tmp/test_db_connection.py
rm /tmp/test_db_connection.py
echo

# 스키마 적용 (Docker 경유)
echo "4. 스키마 적용 (schema_v2_final.sql)"
docker exec -i ddoksori_db psql -U postgres -d ddoksori < /home/maroco/LLM/backend/database/schema_v2_final.sql > /dev/null 2>&1
echo "  ✓ 스키마 적용 완료"
echo

# 법령 데이터 로딩 (샘플: E_Commerce_Consumer_Law.xml만)
echo "5. 법령 데이터 로딩 (샘플: 전자상거래법)"
cd /home/maroco/LLM/backend/data/law/scripts
conda run -n dsr python load_law_to_db_v2.py /home/maroco/LLM/backend/data/law/raw/E_Commerce_Consumer_Law.xml
echo "  ✓ 법령 데이터 로딩 완료"
echo

# 검증 실행
echo "6. 법령 데이터 검증"
cd /home/maroco/LLM/backend/data/scripts/tests
conda run -n dsr python verify_loaded_data.py --law
echo

echo "=========================================="
echo "S1-D2 테스트 완료"
echo "=========================================="
