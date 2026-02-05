"""
검색 에이전트 테스트 스크립트
- 노트북 환불 관련 쿼리로 law, criteria, case 검색 테스트
"""

import sys
import os
import io

# Windows 인코딩 문제 해결
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# 프로젝트 루트 경로 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

# .env 파일 로드 (LLM/.env)
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), '.env')
print(f"Loading .env from: {env_path}")
load_dotenv(env_path)

from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever


def test_retrieval():
    """검색 테스트"""

    # DB 설정
    db_config = {
        "host": os.getenv("DB_HOST"),
        "port": int(os.getenv("DB_PORT", 5432)),
        "database": os.getenv("DB_NAME"),
        "user": os.getenv("DB_USER"),
        "password": os.getenv("DB_PASSWORD"),
    }

    print(f"DB 연결 정보: {db_config['host']}:{db_config['port']}/{db_config['database']}")

    # Retriever 초기화
    retriever = UnifiedRetriever(db_config)
    retriever.connect()

    # 테스트 쿼리 (사용자 실제 질의)
    test_query = "노트북 디자인이 마음에 들지 않아서 환불을 받고 싶은데, 환불을 거부 당했어. 나는 온라인으로 노트북을 구매했고, 아직 노트북을 받은지 7일이 되지 않은 상황이야"

    print("\n" + "="*60)
    print(f"테스트 쿼리: {test_query}")
    print("="*60)

    # 1. 법령 검색 (law_guide 데이터셋)
    print("\n[1] 법령 검색 (dataset_filter='law_guide', document_type_filter='법률')")
    print("-"*60)
    law_results = retriever.search(
        query=test_query,
        top_k=5,
        dataset_filter="law_guide",
        document_type_filter="법률",
        apply_threshold=False,
    )

    if law_results:
        for i, r in enumerate(law_results, 1):
            print(f"{i}. [유사도: {r.similarity:.3f}] {r.doc_title or 'N/A'}")
            print(f"   내용: {(r.content or '')[:100]}...")
    else:
        print("   검색 결과 없음!")

    # 2. 분쟁해결기준 검색
    print("\n[2] 분쟁해결기준 검색 (dataset_filter='law_guide', document_type_filter='별표')")
    print("-"*60)
    criteria_results = retriever.search(
        query=test_query,
        top_k=5,
        dataset_filter="law_guide",
        document_type_filter="별표",
        apply_threshold=False,
    )

    if criteria_results:
        for i, r in enumerate(criteria_results, 1):
            print(f"{i}. [유사도: {r.similarity:.3f}] {r.doc_title or 'N/A'} - {r.category_path or ''}")
            print(f"   내용: {(r.content or '')[:100]}...")
    else:
        print("   검색 결과 없음!")

    # 3. 분쟁조정사례 검색
    print("\n[3] 분쟁조정사례 검색 (dataset_filter='case', category_filter='조정')")
    print("-"*60)
    dispute_results = retriever.search(
        query=test_query,
        top_k=5,
        dataset_filter="case",
        category_filter="조정",
        apply_threshold=False,
    )

    if dispute_results:
        for i, r in enumerate(dispute_results, 1):
            print(f"{i}. [유사도: {r.similarity:.3f}] [{r.source_org or 'N/A'}] {r.doc_title or 'N/A'}")
            print(f"   내용: {(r.content or '')[:100]}...")
    else:
        print("   검색 결과 없음!")

    # 4. 상담사례 검색
    print("\n[4] 상담사례 검색 (dataset_filter='case', category_filter='상담')")
    print("-"*60)
    counsel_results = retriever.search(
        query=test_query,
        top_k=5,
        dataset_filter="case",
        category_filter="상담",
        apply_threshold=False,
    )

    if counsel_results:
        for i, r in enumerate(counsel_results, 1):
            print(f"{i}. [유사도: {r.similarity:.3f}] {r.doc_title or 'N/A'}")
            print(f"   내용: {(r.content or '')[:100]}...")
    else:
        print("   검색 결과 없음!")

    # 5. 전자상거래법 직접 검색
    print("\n[5] 전자상거래법 직접 검색")
    print("-"*60)
    ecommerce_results = retriever.search(
        query="전자상거래 청약철회 7일",
        top_k=5,
        dataset_filter="law_guide",
        apply_threshold=False,
    )

    if ecommerce_results:
        for i, r in enumerate(ecommerce_results, 1):
            print(f"{i}. [유사도: {r.similarity:.3f}] {r.doc_title or 'N/A'}")
            print(f"   내용: {(r.content or '')[:100]}...")
    else:
        print("   검색 결과 없음!")

    retriever.close()

    print("\n" + "="*60)
    print("테스트 완료")
    print("="*60)


if __name__ == "__main__":
    test_retrieval()
