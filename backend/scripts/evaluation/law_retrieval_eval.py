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

REPO_ROOT = Path(__file__).resolve().parents[3]
BACKEND_DIR = REPO_ROOT / "backend"
ENV_PATH = REPO_ROOT / ".env"
load_dotenv(ENV_PATH)

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agents.retrieval.tools.rds_retriever import hybrid_rrf_search  # noqa: E402


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


_CIRCLE_MAP = {
    "①": "1",
    "②": "2",
    "③": "3",
    "④": "4",
    "⑤": "5",
    "⑥": "6",
    "⑦": "7",
    "⑧": "8",
    "⑨": "9",
    "⑩": "10",
    "⑪": "11",
    "⑫": "12",
    "⑬": "13",
    "⑭": "14",
    "⑮": "15",
    "⑯": "16",
    "⑰": "17",
    "⑱": "18",
    "⑲": "19",
    "⑳": "20",
}


def _parse_article_token(token: str) -> Optional[str]:
    match = re.search(r"제\s*(\d+)\s*조(?:의\s*(\d+))?", token)
    if not match:
        return None
    main_no = match.group(1)
    sub_no = match.group(2)
    if sub_no:
        return f"A{main_no}_{sub_no}"
    return f"A{main_no}"


def _parse_numbered_token(token: str, suffix: str, prefix: str) -> Optional[str]:
    match = re.search(r"제\s*(\d+)\s*" + suffix, token)
    if not match:
        match = re.search(r"(\d+)\s*" + suffix, token)
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


def _parse_circled_paragraph(token: str) -> Optional[str]:
    if not token:
        return None
    raw = token.strip()
    num = _CIRCLE_MAP.get(raw)
    if not num:
        return None
    return f"P{num}"


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
        if not paragraph:
            paragraph = _parse_circled_paragraph(token)
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


def _to_article_id(unit_id: str) -> str:
    parts = unit_id.split("|")
    if len(parts) >= 2:
        return "|".join(parts[:2])
    return unit_id


def _extract_law_ids(values: List[str]) -> List[str]:
    law_ids = []
    for val in values:
        if not val or len(val) < 6:
            continue
        law_ids.append(val[:6])
    return law_ids


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
    total_exact_hit_any = 0
    total_article_hit_any = 0
    total_law_hit_any = 0
    total_exact_recall = 0.0
    total_article_recall = 0.0
    total_law_recall = 0.0

    for item in _iter_jsonl(input_path, start_line=args.start_line, count=args.count):
        citations = _normalize_id_list(item.get("citations"))
        article_ids = _normalize_id_list(item.get("article_ids"))
        queries = item.get("queries_llm") or []
        if not isinstance(queries, list):
            queries = [queries]

        gold_law_ids = _extract_law_ids(article_ids)

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
            retrieved_article_ids = [_to_article_id(r) for r in retrieved_unit_ids]
            retrieved_law_ids = _extract_law_ids(retrieved_unit_ids)

            exact_hits = sorted(set(retrieved_unit_ids) & set(citations))
            article_hits = sorted(set(retrieved_article_ids) & set(article_ids))
            law_hits = sorted(set(retrieved_law_ids) & set(gold_law_ids))

            exact_hit_any = 1 if exact_hits else 0
            article_hit_any = 1 if article_hits else 0
            law_hit_any = 1 if law_hits else 0

            exact_recall = len(exact_hits) / len(citations) if citations else 0.0
            article_recall = (
                len(article_hits) / len(article_ids) if article_ids else 0.0
            )
            law_recall = len(law_hits) / len(set(gold_law_ids)) if gold_law_ids else 0.0

            total_exact_hit_any += exact_hit_any
            total_article_hit_any += article_hit_any
            total_law_hit_any += law_hit_any
            total_exact_recall += exact_recall
            total_article_recall += article_recall
            total_law_recall += law_recall

            if output_fh:
                output_row = {
                    "query": query,
                    "citations": citations,
                    "article_ids": article_ids,
                    "retrieved_unit_ids": retrieved_unit_ids,
                    "retrieved_article_ids": retrieved_article_ids,
                    "retrieved_law_ids": retrieved_law_ids,
                    "exact_hits": exact_hits,
                    "article_hits": article_hits,
                    "law_hits": law_hits,
                    "exact_hit_any": exact_hit_any,
                    "article_hit_any": article_hit_any,
                    "law_hit_any": law_hit_any,
                    "exact_recall": exact_recall,
                    "article_recall": article_recall,
                    "law_recall": law_recall,
                    "sql_ms": sql_ms,
                }
                output_fh.write(json.dumps(output_row, ensure_ascii=False) + "\n")

    if output_fh:
        summary = {
            f"ExactHit@{args.top_k}": (
                (total_exact_hit_any / total_queries) if total_queries else 0.0
            ),
            f"ArticleHit@{args.top_k}": (
                (total_article_hit_any / total_queries) if total_queries else 0.0
            ),
            f"LawHit@{args.top_k}": (
                (total_law_hit_any / total_queries) if total_queries else 0.0
            ),
            f"exact_recall@{args.top_k}": (
                (total_exact_recall / total_queries) if total_queries else 0.0
            ),
            f"article_recall@{args.top_k}": (
                (total_article_recall / total_queries) if total_queries else 0.0
            ),
            f"law_recall@{args.top_k}": (
                (total_law_recall / total_queries) if total_queries else 0.0
            ),
            "total_queries": total_queries,
        }
        meta_row = {
            "__meta__": True,
            "run_config": {
                "input": str(input_path),
                "top_k": args.top_k,
                "start_line": args.start_line,
                "count": args.count,
            },
            "summary": summary,
        }
        output_fh.close()
        with output_path.open("r+", encoding="utf-8") as meta_fh:
            existing = meta_fh.read()
            meta_fh.seek(0)
            meta_fh.write(json.dumps(meta_row, ensure_ascii=False) + "\n")
            meta_fh.write(existing)

    summary = {
        f"ExactHit@{args.top_k}": (
            (total_exact_hit_any / total_queries) if total_queries else 0.0
        ),
        f"ArticleHit@{args.top_k}": (
            (total_article_hit_any / total_queries) if total_queries else 0.0
        ),
        f"LawHit@{args.top_k}": (
            (total_law_hit_any / total_queries) if total_queries else 0.0
        ),
        f"exact_recall@{args.top_k}": (
            (total_exact_recall / total_queries) if total_queries else 0.0
        ),
        f"article_recall@{args.top_k}": (
            (total_article_recall / total_queries) if total_queries else 0.0
        ),
        f"law_recall@{args.top_k}": (
            (total_law_recall / total_queries) if total_queries else 0.0
        ),
        "total_queries": total_queries,
    }

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"ExactHit@{args.top_k}: {summary[f'ExactHit@{args.top_k}']:.4f}")
        print(f"ArticleHit@{args.top_k}: {summary[f'ArticleHit@{args.top_k}']:.4f}")
        print(f"LawHit@{args.top_k}: {summary[f'LawHit@{args.top_k}']:.4f}")
        print(f"exact_recall@{args.top_k}: {summary[f'exact_recall@{args.top_k}']:.4f}")
        print(
            f"article_recall@{args.top_k}: {summary[f'article_recall@{args.top_k}']:.4f}"
        )
        print(f"law_recall@{args.top_k}: {summary[f'law_recall@{args.top_k}']:.4f}")
        print(f"total_queries: {summary['total_queries']}")


if __name__ == "__main__":
    main()
