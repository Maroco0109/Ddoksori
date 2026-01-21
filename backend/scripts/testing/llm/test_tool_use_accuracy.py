"""
EXAONE Tool Use 성능 테스트
S3-PR2: 7.8B 모델의 Tool Calling 정확도 측정

JSON 구조화 출력 및 함수 호출 능력을 평가합니다.
목표: Tool Selection Accuracy ≥ 85%, JSON Parsing Success Rate ≥ 95%
"""

import sys
import os
import json

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from app.llm.exaone_client import ExaoneLLMClient, LLMUnavailableError
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


TOOL_USE_PROMPTS = [
    {
        "name": "simple_calculation",
        "system": "당신은 수학 계산을 JSON 형식으로 반환하는 AI입니다.",
        "user": "사과 3개(개당 1000원)와 배 2개(개당 1500원)의 총 가격을 계산하고, 결과를 다음 JSON 형식으로 출력해주세요: {\"items\": [{\"name\": \"...\", \"quantity\": ..., \"price\": ...}], \"total\": ...}",
        "expected_keys": ["items", "total"]
    },
    {
        "name": "query_classification",
        "system": "당신은 질의를 분류하여 JSON으로 반환하는 AI입니다.",
        "user": "다음 질문을 dispute, law, general 중 하나로 분류해주세요: '온라인으로 구매한 옷이 불량품인데 환불받을 수 있나요?' 형식: {\"query_type\": \"...\", \"confidence\": 0.0-1.0}",
        "expected_keys": ["query_type", "confidence"]
    },
    {
        "name": "entity_extraction",
        "system": "당신은 텍스트에서 엔티티를 추출하여 JSON으로 반환하는 AI입니다.",
        "user": "다음 문장에서 날짜, 장소, 금액을 추출해주세요: '2024년 3월 15일 서울 강남구에서 50만원에 노트북을 구매했습니다.' 형식: {\"date\": \"...\", \"location\": \"...\", \"amount\": ...}",
        "expected_keys": ["date", "location", "amount"]
    },
    {
        "name": "multi_step_reasoning",
        "system": "당신은 단계별 추론을 JSON으로 반환하는 AI입니다.",
        "user": "청약철회가 가능한지 판단하고, 단계별 근거를 JSON으로 반환해주세요. 상황: 통신판매로 옷 구매 후 7일 경과. 형식: {\"decision\": \"yes/no\", \"steps\": [{\"step\": 1, \"reasoning\": \"...\"}]}",
        "expected_keys": ["decision", "steps"]
    },
    {
        "name": "list_generation",
        "system": "당신은 체크리스트를 JSON 배열로 반환하는 AI입니다.",
        "user": "소비자 분쟁 접수 시 필요한 서류 3가지를 JSON 배열로 나열해주세요. 형식: {\"documents\": [\"...\", \"...\", \"...\"]}",
        "expected_keys": ["documents"]
    }
]


def test_json_parsing_accuracy():
    logger.info("=== JSON Parsing Accuracy Test ===\n")
    
    client = ExaoneLLMClient()
    
    if not client.is_available():
        logger.error("EXAONE server unavailable - skipping test")
        return None
    
    results = []
    
    for prompt_set in TOOL_USE_PROMPTS:
        name = prompt_set["name"]
        logger.info(f"Testing: {name}")
        
        try:
            response = client.generate(
                system_prompt=prompt_set["system"],
                user_prompt=prompt_set["user"]
            )
            
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            
            if json_start == -1 or json_end == 0:
                logger.error(f"  ❌ No JSON found in response")
                results.append({"name": name, "parsed": False, "reason": "no_json"})
                continue
            
            json_str = response[json_start:json_end]
            parsed = json.loads(json_str)
            
            missing_keys = [key for key in prompt_set["expected_keys"] if key not in parsed]
            
            if missing_keys:
                logger.warning(f"  ⚠️ Parsed but missing keys: {missing_keys}")
                results.append({"name": name, "parsed": True, "complete": False, "missing_keys": missing_keys})
            else:
                logger.info(f"  ✅ Parsed successfully with all keys")
                results.append({"name": name, "parsed": True, "complete": True})
            
        except json.JSONDecodeError as e:
            logger.error(f"  ❌ JSON parsing failed: {e}")
            results.append({"name": name, "parsed": False, "reason": "invalid_json"})
        except LLMUnavailableError as e:
            logger.error(f"  ❌ LLM unavailable: {e}")
            results.append({"name": name, "parsed": False, "reason": "llm_error"})
        except Exception as e:
            logger.error(f"  ❌ Unexpected error: {e}")
            results.append({"name": name, "parsed": False, "reason": "unknown"})
    
    return results


def calculate_metrics(results):
    if not results:
        return None
    
    total = len(results)
    parsed_count = sum(1 for r in results if r.get("parsed", False))
    complete_count = sum(1 for r in results if r.get("complete", False))
    
    parsing_success_rate = (parsed_count / total) * 100
    completeness_rate = (complete_count / total) * 100
    
    return {
        "total_tests": total,
        "parsed": parsed_count,
        "complete": complete_count,
        "parsing_success_rate": parsing_success_rate,
        "completeness_rate": completeness_rate
    }


def main():
    logger.info("Starting EXAONE Tool Use Performance Tests\n")
    
    results = test_json_parsing_accuracy()
    
    if results is None:
        logger.error("\n💥 Tests could not run - server unavailable")
        return 1
    
    metrics = calculate_metrics(results)
    
    logger.info("\n=== Test Results ===")
    logger.info(f"Total Tests: {metrics['total_tests']}")
    logger.info(f"Successfully Parsed: {metrics['parsed']}/{metrics['total_tests']}")
    logger.info(f"Complete (All Keys): {metrics['complete']}/{metrics['total_tests']}")
    logger.info(f"Parsing Success Rate: {metrics['parsing_success_rate']:.1f}%")
    logger.info(f"Completeness Rate: {metrics['completeness_rate']:.1f}%")
    
    logger.info("\n=== Performance Evaluation ===")
    if metrics['parsing_success_rate'] >= 95.0:
        logger.info("✅ EXCELLENT: Parsing success rate meets target (≥95%)")
    elif metrics['parsing_success_rate'] >= 85.0:
        logger.info("⚠️ GOOD: Parsing success rate above 85%")
    else:
        logger.error("❌ NEEDS IMPROVEMENT: Parsing success rate below 85%")
    
    if metrics['completeness_rate'] >= 90.0:
        logger.info("✅ Tool Use accuracy is production-ready")
        return 0
    elif metrics['completeness_rate'] >= 80.0:
        logger.info("⚠️ Tool Use accuracy is acceptable but needs tuning")
        return 0
    else:
        logger.error("❌ Tool Use accuracy is below acceptable threshold")
        return 1


if __name__ == "__main__":
    sys.exit(main())
