"""
E2E 테스트 전용 Fixture

RDS READ_ONLY 연결, HybridRetriever, MAS Supervisor 그래프 등
E2E 통합 테스트에 필요한 fixture를 제공합니다.

사용법:
    PYTHONPATH=backend \
      conda run -n dsr pytest backend/scripts/testing/e2e/ -v
"""

import os
import sys
from pathlib import Path

import pytest

# Ensure backend is on sys.path
_backend_root = str(Path(__file__).parent.parent.parent.parent)
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)


# ============================================================
# RDS Database Fixture
# ============================================================


@pytest.fixture(scope="module")
def rds_db_config():
    """
    RDS READ_ONLY 연결 설정 딕셔너리.

    DB_HOST 환경변수 필요 (RDS endpoint).
    설정이 없으면 테스트를 skip합니다.
    """
    host = os.getenv("DB_HOST")
    if not host or host == "localhost":
        pytest.skip("DB_HOST not configured for RDS — E2E 테스트 skip")

    return {
        "host": host,
        "port": os.getenv("DB_PORT", "5432"),
        "dbname": os.getenv("DB_NAME", "ddoksori"),
        "user": os.getenv("DB_USER", "readonly_user"),
        "password": os.getenv("DB_PASSWORD", ""),
    }


# ============================================================
# Embedding API URL Fixture
# ============================================================


@pytest.fixture(scope="module")
def embed_api_url():
    """임베딩 API URL (OpenAI 또는 KURE-v1)."""
    return os.getenv("EMBED_API_URL", "http://localhost:8001/embed")


# ============================================================
# HybridRetriever Fixture
# ============================================================


@pytest.fixture(scope="module")
def hybrid_retriever(rds_db_config, embed_api_url):
    """
    HybridRetriever 인스턴스 (module-scoped lifecycle).

    connect → yield → close 패턴으로 DB 연결을 관리합니다.
    """
    from app.agents.retrieval.tools.hybrid_retriever import HybridRetriever

    retriever = HybridRetriever(
        db_config=rds_db_config,
        embed_api_url=embed_api_url,
    )
    retriever.connect()
    yield retriever
    retriever.close()


# ============================================================
# MAS Supervisor Graph Fixture
# ============================================================


@pytest.fixture(scope="module")
def compiled_mas_graph():
    """
    MAS Supervisor 컴파일된 그래프 (MemorySaver 사용).

    E2E 파이프라인 테스트에서 전체 그래프를 invoke할 때 사용합니다.
    """
    from langgraph.checkpoint.memory import MemorySaver

    from app.supervisor import reset_graph
    from app.supervisor.graph_mas import create_mas_supervisor_graph

    reset_graph()
    graph = create_mas_supervisor_graph()
    return graph.compile(checkpointer=MemorySaver())


# ============================================================
# UnifiedRetriever Fixture (Phase 8)
# ============================================================


@pytest.fixture(scope="module")
def unified_retriever(rds_db_config):
    """
    UnifiedRetriever 인스턴스 (module-scoped lifecycle).

    SQL search_hybrid_rrf() 기반 통합 검색.
    OpenAI API key 필요 (text-embedding-3-large).
    """
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not configured — UnifiedRetriever 테스트 skip")

    from app.agents.retrieval.tools.unified_retriever import UnifiedRetriever

    retriever = UnifiedRetriever(
        db_config=rds_db_config,
        openai_api_key=key,
    )
    retriever.connect()
    yield retriever
    retriever.close()


# ============================================================
# 공통 Helper
# ============================================================


@pytest.fixture(scope="module")
def openai_api_key():
    """OpenAI API 키. 미설정 시 skip."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        pytest.skip("OPENAI_API_KEY not configured — LLM 테스트 skip")
    return key
