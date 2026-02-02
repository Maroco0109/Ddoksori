import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import pytest

from app.domain import AGENCY_INFO, classify_domain
from scripts.testing.domain.golden_set import GOLDEN_SET


class TestDomainClassification:
    def test_accuracy_above_threshold(self):
        threshold = 0.75
        correct = 0
        total = len(GOLDEN_SET)
        failures = []

        for item in GOLDEN_SET:
            result = classify_domain(item["query"])
            if result.agency == item["expected_agency"]:
                correct += 1
            else:
                failures.append(
                    {
                        "query": item["query"],
                        "expected": item["expected_agency"],
                        "predicted": result.agency,
                        "reason": result.reason,
                    }
                )

        accuracy = correct / total

        print(f"\n{'=' * 60}")
        print(f"Domain Classification Accuracy: {accuracy:.2%} ({correct}/{total})")
        print(f"Threshold: {threshold:.0%}")
        print(f"{'=' * 60}")

        if failures:
            print(f"\nFailed cases ({len(failures)}):")
            for f in failures:
                print(f"  Query: {f['query']}")
                print(f"  Expected: {f['expected']} | Predicted: {f['predicted']}")
                print(f"  Reason: {f['reason']}")
                print()

        assert accuracy >= threshold, f"Accuracy {accuracy:.2%} < {threshold:.0%}"

    def test_fss_classification(self):
        fss_cases = [item for item in GOLDEN_SET if item["expected_agency"] == "FSS"]

        for item in fss_cases:
            result = classify_domain(item["query"])
            assert result.agency == "FSS", (
                f"Query '{item['query']}' should be FSS, got {result.agency}"
            )
            assert result.is_restricted is True

    def test_k_medi_classification(self):
        k_medi_cases = [
            item for item in GOLDEN_SET if item["expected_agency"] == "K_MEDI"
        ]

        for item in k_medi_cases:
            result = classify_domain(item["query"])
            assert result.agency == "K_MEDI", (
                f"Query '{item['query']}' should be K_MEDI, got {result.agency}"
            )
            assert result.is_restricted is True

    def test_non_restricted_agencies(self):
        non_restricted = [item for item in GOLDEN_SET if not item["is_restricted"]]

        for item in non_restricted:
            result = classify_domain(item["query"])
            assert result.is_restricted is False, (
                f"Query '{item['query']}' should not be restricted"
            )

    def test_agency_info_has_required_fields(self):
        required_fields = ["name", "full_name", "description", "url"]

        for code, info in AGENCY_INFO.items():
            for field in required_fields:
                assert field in info, f"Agency {code} missing field: {field}"

    def test_restricted_agencies_have_restriction_reason(self):
        for code, info in AGENCY_INFO.items():
            if info.get("is_restricted"):
                assert "restriction_reason" in info, (
                    f"Restricted agency {code} missing restriction_reason"
                )
                assert len(info["restriction_reason"]) > 0


def run_accuracy_report():
    from collections import defaultdict

    results_by_agency = defaultdict(lambda: {"correct": 0, "total": 0, "failures": []})

    for item in GOLDEN_SET:
        result = classify_domain(item["query"])
        expected = item["expected_agency"]

        results_by_agency[expected]["total"] += 1

        if result.agency == expected:
            results_by_agency[expected]["correct"] += 1
        else:
            results_by_agency[expected]["failures"].append(
                {
                    "query": item["query"],
                    "predicted": result.agency,
                }
            )

    print("\n" + "=" * 70)
    print("DOMAIN CLASSIFICATION ACCURACY REPORT")
    print("=" * 70)

    total_correct = 0
    total_count = 0

    for agency in ["FSS", "K_MEDI", "KCDRC", "ECMC", "KCA"]:
        data = results_by_agency[agency]
        acc = data["correct"] / data["total"] if data["total"] > 0 else 0
        status = "PASS" if acc >= 0.8 else "FAIL"
        restricted = "RESTRICTED" if AGENCY_INFO[agency].get("is_restricted") else ""

        print(f"\n{agency} ({AGENCY_INFO[agency]['name']}) {restricted}")
        print(f"  Accuracy: {acc:.2%} ({data['correct']}/{data['total']}) [{status}]")

        if data["failures"]:
            print(f"  Failures:")
            for f in data["failures"]:
                print(f"    - '{f['query']}' -> {f['predicted']}")

        total_correct += data["correct"]
        total_count += data["total"]

    overall = total_correct / total_count if total_count > 0 else 0
    print("\n" + "-" * 70)
    print(f"OVERALL: {overall:.2%} ({total_correct}/{total_count})")
    print("=" * 70)

    return overall >= 0.8


if __name__ == "__main__":
    success = run_accuracy_report()
    sys.exit(0 if success else 1)
