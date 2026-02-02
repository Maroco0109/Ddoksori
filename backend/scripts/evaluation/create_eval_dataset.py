#!/usr/bin/env python3
"""
평가 데이터셋 생성 도구

기존 RAG 로그에서 질문을 추출하고, DB에서 관련 context를 자동 매핑하여
평가 데이터셋 초안을 생성합니다.

Usage:
    # 로그에서 질문 추출 및 데이터셋 초안 생성
    python scripts/evaluation/create_eval_dataset.py \
      --log-dir logs/rag \
      --output data/evaluation/eval_dataset_draft.jsonl

    # 대화형 모드로 context 레이블링
    python scripts/evaluation/create_eval_dataset.py \
      --interactive \
      --input data/evaluation/eval_dataset_draft.jsonl \
      --output data/evaluation/eval_dataset.jsonl
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from dotenv import load_dotenv

load_dotenv()


# 카테고리 키워드 매핑
CATEGORY_KEYWORDS = {
    "전자상거래_환불": [
        "환불",
        "반품",
        "청약철회",
        "구매취소",
        "결제취소",
        "인터넷",
        "온라인",
        "쇼핑몰",
    ],
    "가전제품_하자": [
        "고장",
        "하자",
        "수리",
        "A/S",
        "AS",
        "불량",
        "가전",
        "냉장고",
        "세탁기",
        "에어컨",
        "TV",
    ],
    "콘텐츠_결제": [
        "게임",
        "앱",
        "인앱결제",
        "구독",
        "OTT",
        "스트리밍",
        "콘텐츠",
        "다운로드",
    ],
    "개인간거래": ["중고", "당근", "번개장터", "중고나라", "직거래", "개인거래"],
    "품질보증기간": ["보증기간", "품질보증", "무상수리", "유상수리", "내용연수"],
    "배송_지연취소": ["배송", "지연", "배달", "택배", "미배송"],
}

# 기관 키워드 매핑
AGENCY_KEYWORDS = {
    "KCDRC": [
        "게임",
        "영화",
        "콘텐츠",
        "앱",
        "음악",
        "웹툰",
        "스트리밍",
        "OTT",
        "인앱",
        "디지털",
    ],
    "ECMC": ["중고", "직거래", "당근", "번개장터", "중고나라", "개인간", "개인거래"],
    "KCA": [],  # default
}


def classify_category(query: str) -> str:
    """질문 텍스트로부터 카테고리 추정"""
    query_lower = query.lower()

    for category, keywords in CATEGORY_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                return category

    return "기타_일반"


def classify_agency(query: str) -> str:
    """질문 텍스트로부터 추천 기관 추정"""
    query_lower = query.lower()

    for agency, keywords in AGENCY_KEYWORDS.items():
        for kw in keywords:
            if kw in query_lower:
                return agency

    return "KCA"


def generate_item_id(query: str, index: int) -> str:
    """고유 항목 ID 생성"""
    hash_part = hashlib.md5(query.encode()).hexdigest()[:6]
    return f"eval_{index:03d}_{hash_part}"


def load_rag_logs(log_dir: str) -> List[Dict]:
    """RAG 로그 파일들 로드"""
    log_path = Path(log_dir)
    logs = []

    for log_file in sorted(log_path.rglob("*.json")):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                log_data = json.load(f)

                # 유효한 로그만 추가
                if log_data.get("query") and log_data.get("retrieval", {}).get(
                    "chunks"
                ):
                    logs.append(
                        {
                            "file": str(log_file),
                            "timestamp": log_data.get("timestamp", ""),
                            "query": log_data["query"],
                            "chunks": log_data["retrieval"]["chunks"],
                            "retrieval_mode": log_data["retrieval"].get(
                                "mode", "hybrid"
                            ),
                        }
                    )
        except Exception as e:
            print(f"Warning: Failed to load {log_file}: {e}")

    return logs


def extract_context_candidates(chunks: List[Dict]) -> List[Dict]:
    """검색된 청크에서 context 후보 추출"""
    candidates = []

    for chunk in chunks:
        doc_type = chunk.get("doc_type", "")
        doc_id = chunk.get("doc_id", "")
        chunk_id = chunk.get("chunk_id", "")

        # doc_type 정규화
        if doc_type in ("counsel_case", "mediation_case"):
            normalized_type = "case"
        elif "law" in doc_type.lower():
            normalized_type = "law"
        elif "criteria" in doc_type.lower():
            normalized_type = "criteria"
        else:
            normalized_type = doc_type

        candidates.append(
            {
                "doc_type": normalized_type,
                "doc_id": doc_id or chunk_id,
                "doc_title": chunk.get("doc_title", ""),
                "similarity": chunk.get("similarity", 0.0),
                "content_preview": chunk.get("content_preview", "")[:100],
                "relevance": "supporting",  # 기본값, 수동 검토 필요
            }
        )

    return candidates


def create_eval_item(
    query: str, index: int, chunks: List[Dict], timestamp: str = ""
) -> Dict:
    """단일 평가 항목 생성"""
    item_id = generate_item_id(query, index)
    category = classify_category(query)
    expected_agency = classify_agency(query)
    context_candidates = extract_context_candidates(chunks)

    return {
        "id": item_id,
        "question": query,
        "expected_contexts": context_candidates,
        "expected_agency": expected_agency,
        "category": category,
        "_metadata": {
            "source_timestamp": timestamp,
            "auto_generated": True,
            "needs_review": True,
        },
    }


def deduplicate_queries(logs: List[Dict]) -> List[Dict]:
    """중복 질문 제거"""
    seen_queries = set()
    unique_logs = []

    for log in logs:
        # 질문 정규화 (공백 제거, 소문자)
        normalized = log["query"].strip().lower()

        if normalized not in seen_queries:
            seen_queries.add(normalized)
            unique_logs.append(log)

    return unique_logs


def save_dataset(items: List[Dict], output_path: str):
    """데이터셋을 JSONL로 저장"""
    output_dir = os.path.dirname(output_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    with open(output_path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Saved {len(items)} items to {output_path}")


def interactive_review(input_path: str, output_path: str):
    """대화형 모드로 context relevance 레이블링"""
    items = []

    with open(input_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))

    print(f"\n=== Interactive Review Mode ===")
    print(f"Loaded {len(items)} items from {input_path}")
    print(f"Commands: (e)ssential, (s)upporting, (r)emove, (n)ext, (q)uit\n")

    reviewed_items = []

    for i, item in enumerate(items):
        print(f"\n[{i+1}/{len(items)}] ID: {item['id']}")
        print(f"Question: {item['question'][:100]}...")
        print(f"Category: {item['category']}")
        print(f"Expected Agency: {item['expected_agency']}")
        print(f"\nContexts ({len(item['expected_contexts'])}):")

        new_contexts = []
        for j, ctx in enumerate(item["expected_contexts"]):
            print(f"\n  [{j+1}] {ctx['doc_type']}: {ctx['doc_id']}")
            print(f"      Title: {ctx.get('doc_title', 'N/A')[:50]}")
            print(f"      Similarity: {ctx.get('similarity', 0):.4f}")

            cmd = input("      Relevance? (e/s/r/n/q): ").strip().lower()

            if cmd == "q":
                save_dataset(reviewed_items, output_path)
                print("Review interrupted. Progress saved.")
                return
            elif cmd == "e":
                ctx["relevance"] = "essential"
                new_contexts.append(ctx)
            elif cmd == "s":
                ctx["relevance"] = "supporting"
                new_contexts.append(ctx)
            elif cmd == "r":
                continue  # remove
            else:  # 'n' or anything else
                new_contexts.append(ctx)  # keep as-is

        item["expected_contexts"] = new_contexts
        item["_metadata"]["needs_review"] = False
        reviewed_items.append(item)

        # 10개마다 자동 저장
        if (i + 1) % 10 == 0:
            save_dataset(reviewed_items, output_path)
            print(f"\nAuto-saved progress ({i+1} items)")

    save_dataset(reviewed_items, output_path)
    print(f"\nReview complete! Saved {len(reviewed_items)} items.")


def main():
    parser = argparse.ArgumentParser(description="평가 데이터셋 생성 도구")
    parser.add_argument("--log-dir", default="logs/rag", help="RAG 로그 디렉토리")
    parser.add_argument(
        "--output",
        default="data/evaluation/eval_dataset_draft.jsonl",
        help="출력 파일 경로",
    )
    parser.add_argument("--max-items", type=int, default=50, help="최대 항목 수")
    parser.add_argument("--interactive", action="store_true", help="대화형 검토 모드")
    parser.add_argument("--input", help="대화형 모드 입력 파일")

    args = parser.parse_args()

    if args.interactive:
        if not args.input:
            print("Error: --input required for interactive mode")
            sys.exit(1)
        interactive_review(args.input, args.output)
        return

    # 로그에서 데이터셋 생성
    print(f"Loading RAG logs from {args.log_dir}...")
    logs = load_rag_logs(args.log_dir)
    print(f"Found {len(logs)} valid log entries")

    # 중복 제거
    unique_logs = deduplicate_queries(logs)
    print(f"After deduplication: {len(unique_logs)} unique queries")

    # 평가 항목 생성
    items = []
    for i, log in enumerate(unique_logs[: args.max_items]):
        item = create_eval_item(
            query=log["query"],
            index=i + 1,
            chunks=log["chunks"],
            timestamp=log["timestamp"],
        )
        items.append(item)

    # 카테고리별 분포 출력
    category_counts = {}
    for item in items:
        cat = item["category"]
        category_counts[cat] = category_counts.get(cat, 0) + 1

    print(f"\nCategory distribution:")
    for cat, count in sorted(category_counts.items()):
        print(f"  {cat}: {count}")

    # 저장
    save_dataset(items, args.output)

    print(f"\nNext steps:")
    print(f"1. Review the draft: {args.output}")
    print(f"2. Run interactive review:")
    print(f"   python scripts/evaluation/create_eval_dataset.py \\")
    print(f"     --interactive --input {args.output} \\")
    print(f"     --output data/evaluation/eval_dataset.jsonl")


if __name__ == "__main__":
    main()
