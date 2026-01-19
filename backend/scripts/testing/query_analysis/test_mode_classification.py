import json
import os
import sys
from pathlib import Path
from typing import Dict, Any, List

import pytest

backend_path = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(backend_path))
os.chdir(backend_path)

from app.orchestrator.state import ChatState, create_initial_state, RoutingMode
from app.orchestrator.validators import validate_query_analysis_result_v2


def _import_query_analysis():
    from app.agents.query_analysis.agent import (
        query_analysis_node,
        _classify_mode,
        _classify_query_type,
        _should_promote_to_rag,
    )
    return query_analysis_node, _classify_mode, _classify_query_type, _should_promote_to_rag


query_analysis_node, _classify_mode, _classify_query_type, _should_promote_to_rag = _import_query_analysis()


GOLDEN_SET_PATH = Path(__file__).parent.parent.parent.parent / "data" / "golden_set" / "query_analysis" / "mode_classification.json"


def load_golden_set() -> List[Dict[str, Any]]:
    with open(GOLDEN_SET_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


class TestModeClassification:
    
    @pytest.fixture
    def golden_set(self) -> List[Dict[str, Any]]:
        return load_golden_set()
    
    def test_golden_set_exists(self):
        assert GOLDEN_SET_PATH.exists(), f"Golden set not found: {GOLDEN_SET_PATH}"
        data = load_golden_set()
        assert len(data) >= 50, f"Golden set should have at least 50 samples, got {len(data)}"
    
    def test_no_retrieval_for_greetings(self):
        greetings = ["안녕하세요", "반갑습니다", "감사합니다", "네", "ㅋㅋㅋ", "ok", "hello"]
        for greeting in greetings:
            query_type = _classify_query_type(greeting)
            mode = _classify_mode(query_type, False, greeting)
            assert mode == "NO_RETRIEVAL", f"Expected NO_RETRIEVAL for '{greeting}', got {mode}"
    
    def test_need_rag_for_disputes_with_info(self):
        state = create_initial_state(
            user_query="헬스장 환불 받고 싶어요",
            chat_type="dispute",
            onboarding={"purchase_item": "헬스장 회원권"}
        )
        result = query_analysis_node(state)
        
        assert result.get("mode") == "NEED_RAG"
        assert result.get("query_analysis_v2") is not None
        assert result["query_analysis_v2"]["mode"] == "NEED_RAG"
    
    def test_need_user_clarification_for_missing_info(self):
        state = create_initial_state(
            user_query="환불 가능한가요?",
            chat_type="dispute",
        )
        result = query_analysis_node(state)
        
        assert result.get("mode") == "NEED_USER_CLARIFICATION"
    
    def test_fast_path_promotion(self):
        promotion_queries = [
            "이게 불법인가요?",
            "소송 가능한가요?",
            "손해배상 청구할 수 있나요?",
            "분쟁조정 신청하려고요",
            "청약철회 기간이 지났는데요",
        ]
        for query in promotion_queries:
            assert _should_promote_to_rag(query), f"Expected promotion for '{query}'"
            
            query_type = _classify_query_type(query)
            if query_type == "general":
                mode = _classify_mode(query_type, False, query)
                assert mode == "NEED_RAG", f"Expected NEED_RAG after promotion for '{query}', got {mode}"
    
    def test_law_queries_need_rag(self):
        law_queries = [
            "소비자보호법 제17조가 뭐예요?",
            "전자상거래법에서 청약철회 조항 알려주세요",
        ]
        for query in law_queries:
            query_type = _classify_query_type(query)
            assert query_type == "law", f"Expected 'law' type for '{query}', got {query_type}"
            
            mode = _classify_mode(query_type, False, query)
            assert mode == "NEED_RAG"
    
    def test_criteria_queries_need_rag(self):
        criteria_queries = [
            "분쟁해결기준에서 가전제품 환불 기준이 어떻게 되나요?",
            "헬스장 분쟁조정기준 별표 알려주세요",
        ]
        for query in criteria_queries:
            query_type = _classify_query_type(query)
            assert query_type == "criteria", f"Expected 'criteria' type for '{query}', got {query_type}"
            
            mode = _classify_mode(query_type, False, query)
            assert mode == "NEED_RAG"
    
    def test_schema_compliance(self, golden_set):
        passed = 0
        failed = []
        
        for sample in golden_set:
            query = sample["query"]
            chat_type = sample.get("chat_type", "general")
            onboarding = sample.get("onboarding")
            
            state = create_initial_state(
                user_query=query,
                chat_type=chat_type,
                onboarding=onboarding
            )
            
            result = query_analysis_node(state)
            qa_v2 = result.get("query_analysis_v2")
            
            if qa_v2 is None:
                failed.append({"id": sample["id"], "query": query, "error": "query_analysis_v2 is None"})
                continue
            
            is_valid, errors = validate_query_analysis_result_v2(qa_v2)
            
            if is_valid:
                passed += 1
            else:
                failed.append({"id": sample["id"], "query": query, "errors": errors})
        
        total = len(golden_set)
        compliance_rate = (passed / total) * 100 if total > 0 else 0
        
        print(f"\n=== Schema Compliance Report ===")
        print(f"Total samples: {total}")
        print(f"Passed: {passed}")
        print(f"Failed: {len(failed)}")
        print(f"Compliance rate: {compliance_rate:.1f}%")
        
        if failed:
            print(f"\nFailed samples:")
            for f in failed[:5]:
                print(f"  - ID {f['id']}: {f.get('errors', f.get('error'))}")
        
        assert compliance_rate >= 99.0, f"Schema compliance rate {compliance_rate:.1f}% is below 99%"
    
    def test_mode_accuracy(self, golden_set):
        correct = 0
        incorrect = []
        
        for sample in golden_set:
            query = sample["query"]
            chat_type = sample.get("chat_type", "general")
            onboarding = sample.get("onboarding")
            expected_mode = sample["expected_mode"]
            
            state = create_initial_state(
                user_query=query,
                chat_type=chat_type,
                onboarding=onboarding
            )
            
            result = query_analysis_node(state)
            actual_mode = result.get("mode")
            
            if actual_mode == expected_mode:
                correct += 1
            else:
                incorrect.append({
                    "id": sample["id"],
                    "query": query,
                    "expected": expected_mode,
                    "actual": actual_mode,
                    "category": sample.get("category")
                })
        
        total = len(golden_set)
        accuracy = (correct / total) * 100 if total > 0 else 0
        
        print(f"\n=== Mode Classification Accuracy ===")
        print(f"Total samples: {total}")
        print(f"Correct: {correct}")
        print(f"Incorrect: {len(incorrect)}")
        print(f"Accuracy: {accuracy:.1f}%")
        
        if incorrect:
            print(f"\nIncorrect classifications:")
            for inc in incorrect[:10]:
                print(f"  - ID {inc['id']} [{inc['category']}]: '{inc['query'][:30]}...' expected={inc['expected']}, got={inc['actual']}")
        
        assert accuracy >= 90.0, f"Mode accuracy {accuracy:.1f}% is below 90%"


class TestQueryAnalysisOutput:
    
    def test_output_contains_both_schemas(self):
        state = create_initial_state(
            user_query="헬스장 환불해주세요",
            chat_type="dispute",
            onboarding={"purchase_item": "헬스장"}
        )
        result = query_analysis_node(state)
        
        assert "query_analysis" in result
        assert "query_analysis_v2" in result
        assert "mode" in result
    
    def test_v2_schema_has_required_fields(self):
        state = create_initial_state(
            user_query="노트북 환불 가능한가요?",
            chat_type="dispute",
            onboarding={"purchase_item": "노트북"}
        )
        result = query_analysis_node(state)
        
        qa_v2 = result["query_analysis_v2"]
        
        assert "mode" in qa_v2
        assert qa_v2["mode"] in ["NO_RETRIEVAL", "NEED_RAG", "NEED_USER_CLARIFICATION"]
        
        assert "query_type" in qa_v2
        assert "keywords" in qa_v2
        assert "rewritten_query" in qa_v2
        assert "search_queries" in qa_v2
        
        assert "uncertainties" in qa_v2
        assert "need_evidence" in qa_v2
        assert "required_slots" in qa_v2
    
    def test_v2_schema_no_draft_field(self):
        state = create_initial_state(
            user_query="테스트 쿼리",
            chat_type="general",
        )
        result = query_analysis_node(state)
        
        qa_v2 = result["query_analysis_v2"]
        assert "draft" not in qa_v2, "draft field should not exist in _v2 schema"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-p", "no:asyncio"])
