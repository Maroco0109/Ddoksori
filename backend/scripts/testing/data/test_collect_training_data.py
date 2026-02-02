import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from scripts.data.collect_training_data import (
    DataCollector,
    PIIMasker,
    QualityFilter,
    TrainingExample,
)


class TestPIIMasker:
    def test_mask_korean_phone(self):
        text = "제 번호는 010-1234-5678입니다"
        masked = PIIMasker.mask_text(text)
        assert masked == "제 번호는 [PHONE]입니다"

    def test_mask_email(self):
        text = "연락처: test@example.com"
        masked = PIIMasker.mask_text(text)
        assert masked == "연락처: [EMAIL]"

    def test_mask_korean_address_dong(self):
        text = "서울시 강남구 역삼동에 거주합니다"
        masked = PIIMasker.mask_text(text)
        assert masked == "[ADDRESS]에 거주합니다"

    def test_mask_korean_address_ro(self):
        text = "서울시 강남구 테헤란로 123"
        masked = PIIMasker.mask_text(text)
        assert masked == "[ADDRESS]"

    def test_mask_korean_address_gil(self):
        text = "서울시 강남구 논현길 456"
        masked = PIIMasker.mask_text(text)
        assert masked == "[ADDRESS]"

    def test_mask_multiple_pii(self):
        text = (
            "010-1234-5678로 test@example.com 또는 서울시 강남구 역삼동으로 연락주세요"
        )
        masked = PIIMasker.mask_text(text)
        assert "[PHONE]" in masked
        assert "[EMAIL]" in masked
        assert "[ADDRESS]" in masked
        assert "010-1234-5678" not in masked
        assert "test@example.com" not in masked

    def test_mask_no_pii(self):
        text = "환불 요청합니다"
        masked = PIIMasker.mask_text(text)
        assert masked == text

    def test_mask_non_string(self):
        result = PIIMasker.mask_text(123)
        assert result == 123


class TestQualityFilter:
    def test_valid_snapshot_dict(self):
        snapshot = {"query_type": "dispute", "keywords": ["환불"]}
        assert QualityFilter.is_valid_snapshot(snapshot) is True

    def test_invalid_snapshot_not_dict(self):
        snapshot = "truncated..."
        assert QualityFilter.is_valid_snapshot(snapshot) is False

    def test_invalid_snapshot_too_large(self):
        large_snapshot = {"data": "x" * 3000}
        assert QualityFilter.is_valid_snapshot(large_snapshot) is False

    def test_valid_query(self):
        query = "환불 문의"
        assert QualityFilter.is_valid_query(query) is True

    def test_invalid_query_too_short(self):
        query = "환"
        assert QualityFilter.is_valid_query(query) is False

    def test_invalid_query_empty(self):
        query = "  "
        assert QualityFilter.is_valid_query(query) is False

    def test_invalid_query_not_string(self):
        query = 123
        assert QualityFilter.is_valid_query(query) is False

    def test_valid_query_type(self):
        valid_types = [
            "dispute",
            "general",
            "law",
            "system",
            "system_meta",
            "procedure",
            "restricted",
            "ambiguous",
        ]
        for qt in valid_types:
            assert QualityFilter.is_valid_query_type(qt) is True

    def test_invalid_query_type(self):
        assert QualityFilter.is_valid_query_type("unknown") is False
        assert QualityFilter.is_valid_query_type("") is False
        assert QualityFilter.is_valid_query_type("invalid_type") is False


class TestDataCollectorExtraction:
    def test_extract_query_analysis_success(self, tmp_path):
        log_data = {
            "node_timings": {
                "query_analysis": {
                    "input_snapshot": {
                        "user_query": "환불이 안 된다는데 법적으로 어떻게 되나요?"
                    },
                    "output_snapshot": {
                        "query_analysis_v2": {
                            "query_type": "law",
                            "keywords": ["환불", "법적"],
                            "rewritten_query": "환불 법률 규정",
                            "search_queries": ["환불 관련 법령"],
                        }
                    },
                }
            }
        }

        collector = DataCollector(tmp_path, tmp_path)
        result = collector.extract_query_analysis(log_data)

        assert result is not None
        assert result["query_type"] == "law"
        assert result["keywords"] == ["환불", "법적"]
        assert result["user_query"] == "환불이 안 된다는데 법적으로 어떻게 되나요?"

    def test_extract_query_analysis_missing_node(self, tmp_path):
        log_data = {"node_timings": {}}

        collector = DataCollector(tmp_path, tmp_path)
        result = collector.extract_query_analysis(log_data)

        assert result is None

    def test_extract_query_analysis_truncated_output(self, tmp_path):
        log_data = {
            "node_timings": {
                "query_analysis": {
                    "input_snapshot": {"user_query": "환불 문의"},
                    "output_snapshot": "truncated...",
                }
            }
        }

        collector = DataCollector(tmp_path, tmp_path)
        result = collector.extract_query_analysis(log_data)

        assert result is None

    def test_extract_query_analysis_invalid_query_type(self, tmp_path):
        log_data = {
            "node_timings": {
                "query_analysis": {
                    "input_snapshot": {"user_query": "환불 문의"},
                    "output_snapshot": {
                        "query_analysis_v2": {
                            "query_type": "invalid_type",
                            "keywords": [],
                        }
                    },
                }
            }
        }

        collector = DataCollector(tmp_path, tmp_path)
        result = collector.extract_query_analysis(log_data)

        assert result is None

    def test_extract_query_analysis_too_short_query(self, tmp_path):
        log_data = {
            "node_timings": {
                "query_analysis": {
                    "input_snapshot": {"user_query": "환"},
                    "output_snapshot": {
                        "query_analysis_v2": {"query_type": "general", "keywords": []}
                    },
                }
            }
        }

        collector = DataCollector(tmp_path, tmp_path)
        result = collector.extract_query_analysis(log_data)

        assert result is None


class TestDataCollectorGeneration:
    def test_generate_training_examples_all_fields(self, tmp_path):
        qa_data = {
            "user_query": "환불 문의",
            "query_type": "dispute",
            "keywords": ["환불", "분쟁"],
            "rewritten_query": "환불 관련 분쟁조정 사례",
            "search_queries": [],
        }

        collector = DataCollector(tmp_path, tmp_path)
        examples = collector.generate_training_examples(qa_data)

        assert len(examples) == 3

        assert examples[0].instruction == collector.INSTRUCTION_QUERY_TYPE
        assert examples[0].input == "환불 문의"
        assert examples[0].output == "dispute"

        assert examples[1].instruction == collector.INSTRUCTION_KEYWORDS
        assert examples[1].input == "환불 문의"
        assert "환불" in examples[1].output

        assert examples[2].instruction == collector.INSTRUCTION_REWRITE
        assert examples[2].input == "환불 문의"
        assert examples[2].output == "환불 관련 분쟁조정 사례"

    def test_generate_training_examples_no_keywords(self, tmp_path):
        qa_data = {
            "user_query": "환불 문의",
            "query_type": "general",
            "keywords": [],
            "rewritten_query": "환불 관련 정보",
            "search_queries": [],
        }

        collector = DataCollector(tmp_path, tmp_path)
        examples = collector.generate_training_examples(qa_data)

        assert len(examples) == 2
        assert all(ex.instruction != collector.INSTRUCTION_KEYWORDS for ex in examples)

    def test_generate_training_examples_no_rewrite(self, tmp_path):
        qa_data = {
            "user_query": "환불 문의",
            "query_type": "law",
            "keywords": ["환불"],
            "rewritten_query": "환불 문의",
            "search_queries": [],
        }

        collector = DataCollector(tmp_path, tmp_path)
        examples = collector.generate_training_examples(qa_data)

        assert len(examples) == 2
        assert all(ex.instruction != collector.INSTRUCTION_REWRITE for ex in examples)

    def test_generate_training_examples_pii_masking(self, tmp_path):
        qa_data = {
            "user_query": "010-1234-5678로 연락 주세요",
            "query_type": "system",
            "keywords": [],
            "rewritten_query": "test@example.com으로 이메일 주세요",
            "search_queries": [],
        }

        collector = DataCollector(tmp_path, tmp_path)
        examples = collector.generate_training_examples(qa_data)

        assert all(
            "[PHONE]" in ex.input
            for ex in examples
            if "010-1234-5678" in qa_data["user_query"]
        )
        assert any(
            "[EMAIL]" in ex.output
            for ex in examples
            if "test@example.com" in qa_data["rewritten_query"]
        )


class TestDataCollectorEndToEnd:
    def test_collect_with_sample_logs(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        sample_log = {
            "node_timings": {
                "query_analysis": {
                    "input_snapshot": {"user_query": "환불 문의드립니다"},
                    "output_snapshot": {
                        "query_analysis_v2": {
                            "query_type": "general",
                            "keywords": ["환불"],
                            "rewritten_query": "환불 절차 안내",
                            "search_queries": [],
                        }
                    },
                }
            }
        }

        log_file = log_dir / "test.json"
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(sample_log, f)

        output_dir = tmp_path / "output"
        collector = DataCollector(log_dir, output_dir)
        collector.collect()

        assert (output_dir / "training_data.jsonl").exists()
        assert collector.stats["parsed_files"] == 1
        assert collector.stats["generated_examples"] > 0

        with open(output_dir / "training_data.jsonl", "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) > 0

            first_example = json.loads(lines[0])
            assert "instruction" in first_example
            assert "input" in first_example
            assert "output" in first_example

    def test_collect_with_invalid_logs(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        invalid_log = log_dir / "invalid.json"
        with open(invalid_log, "w", encoding="utf-8") as f:
            f.write("not valid json")

        output_dir = tmp_path / "output"
        collector = DataCollector(log_dir, output_dir)
        collector.collect()

        assert collector.stats["parsed_files"] == 0

    def test_collect_empty_log_dir(self, tmp_path):
        log_dir = tmp_path / "logs"
        log_dir.mkdir()

        output_dir = tmp_path / "output"
        collector = DataCollector(log_dir, output_dir)
        collector.collect()

        assert collector.stats["total_files"] == 0
        assert collector.stats["parsed_files"] == 0
