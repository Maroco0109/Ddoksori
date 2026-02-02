#!/usr/bin/env python3
import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional


@dataclass
class TrainingExample:
    instruction: str
    input: str
    output: str


class PIIMasker:
    PHONE_PATTERN = re.compile(r"01[0-9]-[0-9]{3,4}-[0-9]{4}")
    EMAIL_PATTERN = re.compile(r"[a-zA-Z0-9._+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
    ADDRESS_PATTERNS = [
        re.compile(r"[가-힣]+시\s+[가-힣]+구\s+[가-힣]+동"),
        re.compile(r"[가-힣]+시\s+[가-힣]+구\s+[가-힣]+로\s+\d+"),
        re.compile(r"[가-힣]+시\s+[가-힣]+구\s+[가-힣]+길\s+\d+"),
    ]

    @classmethod
    def mask_text(cls, text: str) -> str:
        if not isinstance(text, str):
            return text

        masked = cls.PHONE_PATTERN.sub("[PHONE]", text)
        masked = cls.EMAIL_PATTERN.sub("[EMAIL]", masked)

        for addr_pattern in cls.ADDRESS_PATTERNS:
            masked = addr_pattern.sub("[ADDRESS]", masked)

        return masked


class QualityFilter:
    MIN_QUERY_LENGTH = 3
    MAX_SNAPSHOT_SIZE = 2048

    @classmethod
    def is_valid_snapshot(cls, snapshot: Any) -> bool:
        if not isinstance(snapshot, dict):
            return False

        snapshot_str = json.dumps(snapshot, ensure_ascii=False)
        if len(snapshot_str) > cls.MAX_SNAPSHOT_SIZE:
            return False

        return True

    @classmethod
    def is_valid_query(cls, query: str) -> bool:
        if not isinstance(query, str):
            return False
        if len(query.strip()) < cls.MIN_QUERY_LENGTH:
            return False
        return True

    @classmethod
    def is_valid_query_type(cls, query_type: str) -> bool:
        valid_types = {
            "dispute",
            "general",
            "law",
            "system",
            "system_meta",
            "procedure",
            "restricted",
            "ambiguous",
        }
        return query_type in valid_types


class DataCollector:
    INSTRUCTION_QUERY_TYPE = (
        "Classify the user query into 'dispute', 'general', 'law', 'system'."
    )
    INSTRUCTION_KEYWORDS = "Extract relevant keywords from the user query."
    INSTRUCTION_REWRITE = "Rewrite the user query for better search."

    def __init__(self, log_dir: Path, output_dir: Path):
        self.log_dir = log_dir
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.stats = {
            "total_files": 0,
            "parsed_files": 0,
            "skipped_no_query_analysis": 0,
            "skipped_truncated": 0,
            "skipped_invalid_query": 0,
            "skipped_invalid_query_type": 0,
            "generated_examples": 0,
        }

    def discover_log_files(self) -> list[Path]:
        return sorted(self.log_dir.rglob("*.json"))

    def parse_log_file(self, log_path: Path) -> Optional[dict[str, Any]]:
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"Error parsing {log_path}: {e}", file=sys.stderr)
            return None

    def extract_query_analysis(
        self, log_data: dict[str, Any]
    ) -> Optional[dict[str, Any]]:
        node_timings = log_data.get("node_timings", {})
        query_analysis_timing = node_timings.get("query_analysis", {})

        if not query_analysis_timing:
            return None

        input_snapshot = query_analysis_timing.get("input_snapshot", {})
        output_snapshot = query_analysis_timing.get("output_snapshot", {})

        if not QualityFilter.is_valid_snapshot(output_snapshot):
            return None

        query_analysis_v2 = output_snapshot.get("query_analysis_v2", {})
        if not isinstance(query_analysis_v2, dict):
            return None

        user_query = input_snapshot.get("user_query", "")
        if not QualityFilter.is_valid_query(user_query):
            return None

        query_type = query_analysis_v2.get("query_type", "")
        if not QualityFilter.is_valid_query_type(query_type):
            return None

        return {
            "user_query": user_query,
            "query_type": query_type,
            "keywords": query_analysis_v2.get("keywords", []),
            "rewritten_query": query_analysis_v2.get("rewritten_query", ""),
            "search_queries": query_analysis_v2.get("search_queries", []),
        }

    def generate_training_examples(
        self, qa_data: dict[str, Any]
    ) -> list[TrainingExample]:
        user_query = PIIMasker.mask_text(qa_data["user_query"])
        query_type = qa_data["query_type"]
        keywords = qa_data["keywords"]
        rewritten_query = PIIMasker.mask_text(qa_data["rewritten_query"])

        examples = []

        examples.append(
            TrainingExample(
                instruction=self.INSTRUCTION_QUERY_TYPE,
                input=user_query,
                output=query_type,
            )
        )

        if keywords and len(keywords) > 0:
            keywords_str = json.dumps(keywords, ensure_ascii=False)
            examples.append(
                TrainingExample(
                    instruction=self.INSTRUCTION_KEYWORDS,
                    input=user_query,
                    output=keywords_str,
                )
            )

        if rewritten_query and rewritten_query != user_query:
            examples.append(
                TrainingExample(
                    instruction=self.INSTRUCTION_REWRITE,
                    input=user_query,
                    output=rewritten_query,
                )
            )

        return examples

    def save_examples(self, examples: list[TrainingExample], output_file: Path) -> None:
        with open(output_file, "w", encoding="utf-8") as f:
            for example in examples:
                json_line = json.dumps(
                    {
                        "instruction": example.instruction,
                        "input": example.input,
                        "output": example.output,
                    },
                    ensure_ascii=False,
                )
                f.write(json_line + "\n")

    def collect(self) -> None:
        log_files = self.discover_log_files()
        self.stats["total_files"] = len(log_files)

        all_examples: list[TrainingExample] = []

        for log_path in log_files:
            log_data = self.parse_log_file(log_path)
            if log_data is None:
                continue

            self.stats["parsed_files"] += 1

            qa_data = self.extract_query_analysis(log_data)
            if qa_data is None:
                self.stats["skipped_no_query_analysis"] += 1
                continue

            examples = self.generate_training_examples(qa_data)
            all_examples.extend(examples)
            self.stats["generated_examples"] += len(examples)

        output_file = self.output_dir / "training_data.jsonl"
        self.save_examples(all_examples, output_file)

        print(f"\nData collection complete!")
        print(f"Total log files found: {self.stats['total_files']}")
        print(f"Successfully parsed: {self.stats['parsed_files']}")
        print(f"Skipped (no query_analysis): {self.stats['skipped_no_query_analysis']}")
        print(f"Generated training examples: {self.stats['generated_examples']}")
        print(f"Output saved to: {output_file}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Collect training data from RAG logs for fine-tuning"
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "logs" / "rag",
        help="Directory containing RAG log files (default: backend/logs/rag)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).parent.parent.parent / "data" / "training",
        help="Directory to save training data (default: backend/data/training)",
    )

    args = parser.parse_args()

    if not args.log_dir.exists():
        print(f"Error: Log directory does not exist: {args.log_dir}", file=sys.stderr)
        sys.exit(1)

    collector = DataCollector(args.log_dir, args.output_dir)
    collector.collect()


if __name__ == "__main__":
    main()
