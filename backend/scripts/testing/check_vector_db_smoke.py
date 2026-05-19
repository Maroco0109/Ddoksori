"""
Read-only smoke checks for the restored Ddoksori vector DB.

This script intentionally does not create, migrate, or seed database objects.
It verifies the M1-4 baseline: pgvector is available, vector_chunks is populated
with 1536-dimensional embeddings, and the active SQL search functions execute,
including search_hybrid_rrf_2().
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor


CRITICAL_FUNCTIONS = (
    "search_similar_chunks",
    "search_hybrid_rrf",
    "search_hybrid_rrf_2",
)
OPTIONAL_OBJECTS = (
    "documents",
    "chunks",
    "law_units",
    "mv_searchable_chunks",
)


def _db_config() -> dict[str, Any]:
    return {
        "host": os.getenv("DB_HOST", "localhost"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": os.getenv("DB_NAME", "ddoksori"),
        "user": os.getenv("DB_USER", "postgres"),
        "password": os.getenv("DB_PASSWORD", "postgres"),
    }


def _fetch_one(cur: RealDictCursor, sql: str, params: tuple[Any, ...] = ()) -> dict:
    cur.execute(sql, params)
    row = cur.fetchone()
    return dict(row) if row else {}


def _fetch_all(cur: RealDictCursor, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
    cur.execute(sql, params)
    return [dict(row) for row in cur.fetchall()]


def run_checks() -> tuple[dict[str, Any], list[str]]:
    failures: list[str] = []
    summary: dict[str, Any] = {}

    with psycopg2.connect(**_db_config()) as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            summary["database"] = _fetch_one(
                cur,
                """
                SELECT current_database() AS name,
                       current_user AS user,
                       current_setting('server_version') AS postgres_version
                """,
            )

            extensions = _fetch_all(
                cur,
                """
                SELECT extname, extversion
                FROM pg_extension
                WHERE extname IN ('vector', 'pgcrypto')
                ORDER BY extname
                """,
            )
            summary["extensions"] = extensions
            if not any(ext["extname"] == "vector" for ext in extensions):
                failures.append("vector extension is missing")

            relations = _fetch_all(
                cur,
                """
                SELECT c.relkind, c.relname
                FROM pg_class c
                JOIN pg_namespace n ON n.oid = c.relnamespace
                WHERE n.nspname = 'public'
                  AND c.relname IN (
                    'vector_chunks',
                    'documents',
                    'chunks',
                    'law_units',
                    'mv_searchable_chunks'
                  )
                ORDER BY c.relname
                """,
            )
            summary["relations"] = relations
            if not any(rel["relname"] == "vector_chunks" for rel in relations):
                failures.append("vector_chunks relation is missing")

            functions = _fetch_all(
                cur,
                """
                SELECT p.proname, pg_get_function_result(p.oid) AS returns
                FROM pg_proc p
                JOIN pg_namespace n ON n.oid = p.pronamespace
                WHERE n.nspname = 'public'
                  AND p.proname IN (
                    'search_similar_chunks',
                    'search_hybrid_rrf',
                    'search_hybrid_rrf_2'
                  )
                ORDER BY p.proname
                """,
            )
            summary["functions"] = functions
            present_functions = {fn["proname"] for fn in functions}
            for function_name in CRITICAL_FUNCTIONS:
                if function_name not in present_functions:
                    failures.append(f"{function_name} function is missing")

            optional_present = {
                row["relname"] for row in relations
            } | present_functions
            summary["optional_missing"] = [
                name for name in OPTIONAL_OBJECTS if name not in optional_present
            ]

            if not failures:
                counts = _fetch_one(
                    cur,
                    """
                    SELECT COUNT(*) AS total,
                           COUNT(*) FILTER (WHERE embedding IS NOT NULL) AS with_embedding,
                           COUNT(*) FILTER (WHERE text_tsv IS NOT NULL) AS with_text_tsv,
                           COUNT(*) FILTER (WHERE vector_dims(embedding) = 1536) AS dims_1536,
                           COUNT(*) FILTER (
                             WHERE vector_dims(embedding) IS DISTINCT FROM 1536
                           ) AS dims_not_1536
                    FROM vector_chunks
                    """,
                )
                summary["vector_chunks"] = counts

                total = int(counts.get("total") or 0)
                if total == 0:
                    failures.append("vector_chunks is empty")
                if int(counts.get("with_embedding") or 0) != total:
                    failures.append("not all vector_chunks rows have embeddings")
                if int(counts.get("with_text_tsv") or 0) != total:
                    failures.append("not all vector_chunks rows have text_tsv")
                if int(counts.get("dims_not_1536") or 0) != 0:
                    failures.append("some embeddings are not 1536-dimensional")

                summary["distribution"] = _fetch_all(
                    cur,
                    """
                    SELECT dataset_type, category, document_type, COUNT(*) AS rows
                    FROM vector_chunks
                    GROUP BY dataset_type, category, document_type
                    ORDER BY rows DESC
                    LIMIT 20
                    """,
                )

            if not failures and "search_similar_chunks" in present_functions:
                summary["dense_sample"] = _fetch_all(
                    cur,
                    """
                    WITH q AS (
                      SELECT embedding
                      FROM vector_chunks
                      WHERE dataset_type = 'case'
                        AND embedding IS NOT NULL
                      LIMIT 1
                    )
                    SELECT chunk_id, dataset_type, category, similarity
                    FROM search_similar_chunks(
                      (SELECT embedding FROM q),
                      'case',
                      NULL,
                      NULL,
                      NULL,
                      3
                    )
                    """,
                )
                if not summary["dense_sample"]:
                    failures.append("search_similar_chunks returned no sample rows")

            if not failures and "search_hybrid_rrf" in present_functions:
                summary["hybrid_sample"] = _fetch_all(
                    cur,
                    """
                    WITH q AS (
                      SELECT embedding
                      FROM vector_chunks
                      WHERE dataset_type = 'case'
                        AND embedding IS NOT NULL
                      LIMIT 1
                    )
                    SELECT chunk_id,
                           dataset_type,
                           category,
                           rrf_score,
                           bm25_score,
                           vector_similarity
                    FROM search_hybrid_rrf(
                      '환불 소비자 분쟁',
                      (SELECT embedding FROM q),
                      'case',
                      NULL,
                      NULL,
                      NULL,
                      3,
                      60
                    )
                    """,
                )
                if not summary["hybrid_sample"]:
                    failures.append("search_hybrid_rrf returned no sample rows")

            if not failures and "search_hybrid_rrf_2" in present_functions:
                summary["hybrid_rrf_2_sample"] = _fetch_all(
                    cur,
                    """
                    WITH q AS (
                      SELECT embedding
                      FROM vector_chunks
                      WHERE dataset_type = 'law_guide'
                        AND embedding IS NOT NULL
                      LIMIT 1
                    )
                    SELECT chunk_id,
                           dataset_type,
                           chunk_type,
                           document_type,
                           rrf_score,
                           bm25_score,
                           vector_similarity
                    FROM search_hybrid_rrf_2(
                      '소비자 분쟁 해결 기준',
                      (SELECT embedding FROM q),
                      'law_guide',
                      NULL,
                      ARRAY['법률', '시행령']::VARCHAR(20)[],
                      NULL,
                      NULL,
                      NULL,
                      3,
                      60
                    )
                    """,
                )

    return summary, failures


def main() -> int:
    try:
        summary, failures = run_checks()
    except Exception as exc:  # pragma: no cover - CLI guard
        print(f"[FAIL] vector DB smoke check crashed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for failure in failures:
            print(f"- {failure}", file=sys.stderr)
        return 1

    print("\n[OK] Restored vector DB satisfies the M1-4 active retrieval baseline.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
