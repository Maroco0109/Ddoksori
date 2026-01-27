# -*- coding: utf-8 -*-
"""Evaluate hybrid RRF retrieval against golden JSONL queries."""
import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BACKEND_DIR / ".env"
load_dotenv(ENV_PATH)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Load hybrid_rrf_search directly from file to avoid package import issues.
from importlib.util import module_from_spec, spec_from_file_location  # noqa: E402

_module_path = BACKEND_DIR / "app" / "agents" / "retrieval" / "cli_search_similar_chunks_direct_sql.py"
_spec = spec_from_file_location("cli_search_similar_chunks_direct_sql", str(_module_path))
if _spec is None or _spec.loader is None:
    raise RuntimeError("Failed to load cli_search_similar_chunks_direct_sql.py")
_module = module_from_spec(_spec)
_spec.loader.exec_module(_module)
hybrid_rrf_search = _module.hybrid_rrf_search


def _iter_jsonl(path: Path, start_line: int = 1, count: int = 0) -> Iterable[Dict]:
    with path.open("r", encoding="utf-8") as f:
        for idx, line in enumerate(f, start=1):
            if idx < start_line:
                continue
            if count and idx >= start_line + count:
                break
            line = line.strip()
            if not line:
                continue
            yield json.loads(line)


def _normalize_id_list(values) -> List[str]:
    if not values:
        return []
    if not isinstance(values, list):
        return []
    normalized = []
    for val in values:
        if not isinstance(val, str):
            continue
        normalized.append(val.replace("_", "|"))
    return normalized


def _load_law_map(path: Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            law_id = data.get("law_id")
            law_name = data.get("law_name")
            law_short = data.get("law_short_name")
            if law_id and law_name:
                mapping[law_name] = law_id
            if law_id and law_short:
                mapping[law_short] = law_id
    return mapping


def _parse_article_token(token: str) -> Optional[str]:
    match = re.search(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", token)
    if not match:
        return None
    main_no = match.group(1)
    sub_no = match.group(2)
    if sub_no:
        return f"A{main_no}|{sub_no}"
    return f"A{main_no}"


def _parse_numbered_token(token: str, suffix: str, prefix: str) -> Optional[str]:
    match = re.search(r"제\s*(\d+)\s*" + suffix, token)
    if not match:
        return None
    return f"{prefix}{match.group(1)}"


def _parse_subitem_token(token: str) -> Optional[str]:
    match = re.search(r"제\s*(\d+)\s*목", token)
    if match:
        return f"S{match.group(1)}"
    match = re.search(r"([가-힣])\s*목", token)
    if match:
        return f"S{match.group(1)}"
    return None


def _normalize_chunk_id(chunk_id: str, law_map: Dict[str, str]) -> Optional[str]:
    if not chunk_id:
        return None

    if "|" in chunk_id:
        return chunk_id.replace("_", "|")

    parts = chunk_id.split("_")
    if not parts:
        return None

    first_article_idx = None
    for idx, part in enumerate(parts):
        if re.search(r"제\s*\d+\s*조", part):
            first_article_idx = idx
            break
    if first_article_idx is None:
        return None

    law_name = "_".join(parts[:first_article_idx]).strip()
    law_id = law_map.get(law_name)
    if not law_id:
        return None

    remainder = parts[first_article_idx:]
    article = None
    paragraph = None
    item = None
    subitem = None

    for token in remainder:
        if not article:
            article = _parse_article_token(token)
        if not paragraph:
            paragraph = _parse_numbered_token(token, "항", "P")
        if not item:
            item = _parse_numbered_token(token, "호", "I")
        if not subitem:
            subitem = _parse_subitem_token(token)

    if not article:
        return None

    unit_parts = [law_id, article]
    if paragraph:
        unit_parts.append(paragraph)
    if item:
        unit_parts.append(item)
    if subitem:
        unit_parts.append(subitem)

    return "|".join(unit_parts)


def _extract_topk_unit_ids(results: List[Dict], law_map: Dict[str, str]) -> List[str]:
    normalized = []
    for row in results:
        chunk_id = row.get("chunk_id") if isinstance(row, dict) else None
        unit_id = _normalize_chunk_id(chunk_id, law_map)
        if unit_id:
            normalized.append(unit_id)
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate hybrid RRF retrieval against golden JSONL queries."
    )
    parser.add_argument(
        "--input",
        default=(
            "backend/data/golden_set/dispute_law_gold/data/samples/"
            "dispute_law_gold_improve_sample_300_with_queries_llm.jsonl"
        ),
        help="Path to golden JSONL file",
    )
    parser.add_argument(
        "--law-map",
        default="backend/data/golden_set/dispute_law_gold/data/raw/law_map.jsonl",
        help="Path to law_map.jsonl",
    )
    parser.add_argument("--top-k", type=int, default=10, help="Top K results")
    parser.add_argument(
        "--start-line",
        type=int,
        default=1,
        help="1-based start line in the JSONL file",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=0,
        help="Number of lines to read from start-line (0=all)",
    )
    parser.add_argument(
        "--output",
        nargs="?",
        const="__AUTO__",
        default="",
        help=(
            "Write per-query results to JSONL. "
            "If used without a path, auto-create under samples/"
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print summary as JSON",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Input not found: {input_path}")
        sys.exit(1)

    law_map_path = Path(args.law_map)
    if not law_map_path.exists():
        print(f"Law map not found: {law_map_path}")
        sys.exit(1)
    law_map = _load_law_map(law_map_path)

    output_fh = None
    output_path = None
    if args.output:
        if args.output == "__AUTO__":
            samples_dir = Path("backend/data/golden_set/dispute_law_gold/data/samples")
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            output_path = samples_dir / f"law_eval_hybrid_rrf_{timestamp}.jsonl"
        else:
            output_path = Path(args.output)
        output_fh = output_path.open("w", encoding="utf-8")

    total_queries = 0
    total_hit_any = 0
    total_recall = 0.0

    for item in _iter_jsonl(input_path, start_line=args.start_line, count=args.count):
        article_ids = _normalize_id_list(item.get("article_ids"))
        queries = item.get("queries_llm") or []
        if not isinstance(queries, list):
            queries = [queries]

        for query in queries:
            if not isinstance(query, str) or not query.strip():
                continue
            total_queries += 1

            results, sql_ms = hybrid_rrf_search(
                query,
                filter_document_type=["법률", "시행령"],
                result_limit=args.top_k,
            )
            retrieved_unit_ids = _extract_topk_unit_ids(results, law_map)
            retrieved_article_ids = ["|".join(r.split("|")[:2]) for r in retrieved_unit_ids]

            article_hits = sorted(set(retrieved_article_ids) & set(article_ids))
            hit_any = 1 if article_hits else 0
            recall = len(article_hits) / len(article_ids) if article_ids else 0.0

            total_hit_any += hit_any
            total_recall += recall

            if output_fh:
                output_row = {
                    "query": query,
                    "article_ids": article_ids,
                    "retrieved_unit_ids": retrieved_unit_ids,
                    "retrieved_article_ids": retrieved_article_ids,
                    "article_hits": article_hits,
                    "hit_any": hit_any,
                    "recall": recall,
                    "sql_ms": sql_ms,
                }
                output_fh.write(json.dumps(output_row, ensure_ascii=False) + "\n")

    if output_fh:
        output_fh.close()

    summary = {
        f"ArticleHit@{args.top_k}": (total_hit_any / total_queries) if total_queries else 0.0,
        f"article_recall@{args.top_k}": (total_recall / total_queries) if total_queries else 0.0,
        "total_queries": total_queries,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"ArticleHit@{args.top_k}: {summary[f'ArticleHit@{args.top_k}']:.4f}")
        print(f"article_recall@{args.top_k}: {summary[f'article_recall@{args.top_k}']:.4f}")
        print(f"total_queries: {summary['total_queries']}")


if __name__ == "__main__":
    main()
