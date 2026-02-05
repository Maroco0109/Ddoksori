# -*- coding: utf-8 -*-
"""
Evaluate retriever-only logs with RAGAS (context_relevancy).

Input JSONL format (one line per query):
  {
    "user_input": "...",
    "retrieved_contexts": ["ctx1", "ctx2", ...],
    ...
  }
"""

import argparse
import json
import os
import random
from datetime import datetime
from typing import Dict, List
import statistics

from datasets import Dataset

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from ragas import evaluate
try:
    # Newer style (if exposed)
    from ragas.metrics import context_relevancy  # type: ignore
    _CONTEXT_METRIC = context_relevancy
except Exception:
    # ragas==0.4.2 uses internal class names
    from ragas.metrics import _ContextRelevance  # type: ignore

    _CONTEXT_METRIC = _ContextRelevance()
try:
    from ragas.llms import LangchainLLM  # type: ignore
    _LLM_WRAPPER = "LangchainLLM"
except Exception:
    from ragas.llms import LangchainLLMWrapper  # type: ignore
    _LLM_WRAPPER = "LangchainLLMWrapper"
from langchain_openai import ChatOpenAI


def load_rows(path: str, max_rows: int, shuffle: bool, seed: int) -> List[Dict]:
    rows: List[Dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))

    if shuffle:
        rng = random.Random(seed)
        rng.shuffle(rows)

    if max_rows > 0:
        rows = rows[:max_rows]

    return rows


def to_dataset(rows: List[Dict]) -> Dataset:
    items = []
    for r in rows:
        items.append(
            {
                "question": r.get("user_input", ""),
                "contexts": r.get("retrieved_contexts", []) or [],
            }
        )
    return Dataset.from_list(items)


def _extract_scores(result) -> List[float]:
    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        for col in df.columns:
            if "context" in col and "relev" in col:
                return [float(v) for v in df[col].tolist()]
        # fallback: take first numeric column
        for col in df.columns:
            try:
                return [float(v) for v in df[col].tolist()]
            except Exception:
                continue
    if isinstance(result, list):
        scores = []
        for item in result:
            if isinstance(item, dict):
                for v in item.values():
                    try:
                        scores.append(float(v))
                        break
                    except Exception:
                        continue
        return scores
    return []


def _compute_summary(scores: List[float]) -> Dict:
    if not scores:
        return {"mean": None, "median": None, "variance": None, "count": 0}
    return {
        "mean": statistics.fmean(scores),
        "median": statistics.median(scores),
        "variance": statistics.pvariance(scores),
        "count": len(scores),
    }


def save_result(
    result,
    output_path: str,
    rows_path: str,
    input_path: str,
    num_rows: int,
    model: str,
) -> None:
    overall = None
    if hasattr(result, "scores"):
        overall = result.scores
    elif isinstance(result, dict):
        overall = result

    scores = _extract_scores(result)
    payload = {
        "timestamp": datetime.now().strftime("%Y%m%d_%H%M%S"),
        "input_path": input_path,
        "num_rows": num_rows,
        "model": model,
        "overall_scores": overall,
        "summary": _compute_summary(scores),
        "per_row_path": rows_path,
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    # Save per-row scores if available
    if hasattr(result, "to_pandas"):
        df = result.to_pandas()
        with open(rows_path, "w", encoding="utf-8") as f:
            for record in df.to_dict(orient="records"):
                f.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="RAGAS retriever-only evaluation.")
    parser.add_argument(
        "--input",
        default=os.path.join(
            "backend",
            "data",
            "golden_set",
            "ragas_retrieval_log_20260128_092912.jsonl",
        ),
    )
    parser.add_argument("--max-rows", type=int, default=0)
    parser.add_argument("--shuffle", action="store_true")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--model", default=os.getenv("RAGAS_LLM_MODEL", "gpt-4o-mini"))
    parser.add_argument(
        "--output",
        default=os.path.join(
            "backend",
            "data",
            "golden_set",
            "ragas_retrieval_eval_result.json",
        ),
    )
    args = parser.parse_args()

    if load_dotenv:
        # Load backend/.env so OPENAI_API_KEY is available
        # __file__ = backend/scripts/evaluation/... -> go up 4 to repo root
        repo_root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        )
        env_path = os.path.join(repo_root, "backend", ".env")
        load_dotenv(env_path)

    rows = load_rows(args.input, args.max_rows, args.shuffle, args.seed)
    dataset = to_dataset(rows)

    if _LLM_WRAPPER == "LangchainLLMWrapper":
        llm = LangchainLLMWrapper(ChatOpenAI(model=args.model, temperature=0))
    else:
        llm = LangchainLLM(ChatOpenAI(model=args.model, temperature=0))

    result = evaluate(dataset, metrics=[_CONTEXT_METRIC], llm=llm)

    base, _ = os.path.splitext(args.output)
    rows_path = f"{base}_rows.jsonl"
    save_result(result, args.output, rows_path, args.input, len(dataset), args.model)

    print(f"saved: {args.output}")
    print(f"per-row: {rows_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
