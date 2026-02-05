# -*- coding: utf-8 -*-
"""Quick smoke test for RDSRetriever."""

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
for path in (str(ROOT), str(BACKEND)):
    if path not in sys.path:
        sys.path.insert(0, path)

from backend.app.agents.retrieval.tools.rds_retriever import RDSRetriever


def _load_env() -> None:
    env_path = Path(r"C:\SKN_19\final_project\LLM\backend\.env")
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        k = k.strip()
        v = v.strip().strip('"').strip("'")
        os.environ.setdefault(k, v)


def main() -> int:
    _load_env()

    query = "\ubbfc\ubc95 \uc81c110\uc870 \uc54c\ub824\uc918"
    retriever = RDSRetriever()
    retriever.connect()
    try:
        # print("[dense_search]")
        # dense_results, embed_ms, sql_ms = retriever.dense_search(query, result_limit=3)
        # print(f"count={len(dense_results)} embed_ms={embed_ms:.1f} sql_ms={sql_ms:.1f}")
        # if dense_results:
        #     print("sample:", dense_results[0].chunk_id, dense_results[0].similarity)

        # print("\n[keyword_search]")
        # keyword_results, keyword_sql_ms = retriever.keyword_search(query_text=query, result_limit=3)
        # print(f"count={len(keyword_results)} sql_ms={keyword_sql_ms:.1f}")
        # if keyword_results:
        #     print("sample:", keyword_results[0].get("chunk_id"), keyword_results[0].get("bm25_score"))


        print("\n[keyword_search split]")
        keyword_results, keyword_sql_ms = retriever.keyword_search_split(query_text=query, filter_document_type=["법률", "시행령"], result_limit=3)
        print(f"count={len(keyword_results)} sql_ms={keyword_sql_ms:.1f}")
        if keyword_results:
            print("sample:", keyword_results[0].get("chunk_id"), keyword_results[0].get("text")[:50], keyword_results[0].get("bm25_score"))

        # print("\n[hybrid_rrf_search]")
        # hybrid_results, hybrid_sql_ms = retriever.hybrid_rrf_search(query_text=query, result_limit=3)
        # print(f"count={len(hybrid_results)} sql_ms={hybrid_sql_ms:.1f}")
        # if hybrid_results:
        #     print("sample:", hybrid_results[0].get("chunk_id"), hybrid_results[0].get("rrf_score"))
    finally:
        retriever.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
