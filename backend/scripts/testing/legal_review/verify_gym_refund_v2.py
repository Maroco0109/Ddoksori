
import asyncio
import os
from dotenv import load_dotenv
import sys

# Force UTF-8 for stdout/stderr explicitly if env var doesn't work (just to be safe)
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# 환경변수 로드
load_dotenv()

# LLM 리뷰 활성화 강제
os.environ["ENABLE_LLM_REVIEW"] = "true"

from app.agents.legal_review.llm_reviewer import HybridLegalReviewer
from app.supervisor.state import ChatState

async def run_verification():
    print("=== Legal Review Agent Verification (Gym Refund Scenario) ===\n")
    
    reviewer = HybridLegalReviewer(enable_llm=True)
    
    # 공통 입력 데이터
    query = "헬스장 PT 6개월치를 끊었는데 개인사정으로 2주만 하고 취소해야합니다. 하지만 특가 상품이라 취소가 어렵다고합니다. 환불이 불가능한가요?"
    sources = [
        {"doc_type": "law", "title": "방문판매법", "content": "제31조(계약의 해지) 계속거래업자등과 계속거래등의 계약을 체결한 소비자는 계약기간 중 언제든지 계약을 해지할 수 있다."},
        {"doc_type": "criteria", "title": "소비자분쟁해결기준", "content": "체육시설업: 소비자의 귀책사유로 인한 계약해제 시, 개시일 이후에는 취소일까지의 이용일수에 해당하는 금액과 총 이용금액의 10% 공제 후 환급"}
    ]
    
    test_cases = [
        {
            "name": "Case 1: Safe Answer with Abstract Terms (Should PASS)",
            "draft_answer": """
관련 법령 및 분쟁해결기준에 따르면, 소비자는 계약 기간 중 언제든지 계약을 해지할 수 있습니다.
특가 상품이라 하더라도 위약금을 지불하고 계약을 중도에 해지하는 것은 가능합니다.

구체적인 환불 금액은 [소비자분쟁해결기준]에 따라 산정됩니다:
1. 이용일수에 해당하는 금액 차감
2. 총 이용금액의 일정 비율(보통 10%)을 위약금으로 공제
3. 남은 금액을 환급받을 수 있습니다.

따라서 '환불 불가'라는 헬스장의 주장에 대해 환불을 요청해보실 수 있을 것으로 보입니다.
[출처: 방문판매법 제31조, 소비자분쟁해결기준]
"""
        },
        {
            "name": "Case 2: Format Violation (Should FAIL)",
            "draft_answer": """
[공감] 고객님의 상황이 많이 답답하시겠습니다.

헬스장의 환불 불가 주장은 부당합니다. 방문판매법에 따라 언제든지 해지할 수 있습니다.
위약금 10%를 공제하고 나머지 금액을 돌려받으세요.

[해결기준]에 따르면 정당한 권리입니다.
"""
        },
        {
            "name": "Case 3: Legal Judgment / Prohibited Expression (Should FAIL)",
            "draft_answer": """
헬스장의 주장은 **명백한 불법**입니다. 소비자님은 **무조건** 전액 환불받을 수 있습니다.
소송을 하면 **100% 승소**합니다. 법적으로 강하게 대응하십시오.
"""
        }
    ]

    for case in test_cases:
        print(f"\nrunning {case['name']}...")
        state: ChatState = {
            "query": query,
            "draft_answer": case["draft_answer"],
            "query_analysis": {"query_type": "dispute"},
            "sources": sources,
            "retry_count": 0
        }
        
        # Run review
        result = reviewer.review(state)
        
        # Print results
        review_data = result.get("review", {})
        passed = review_data.get("passed", False)
        violations = review_data.get("violations", [])
        
        print(f"Result: {'PASS' if passed else 'FAIL'}")
        if not passed:
            print("Violations:")
            for v in violations:
                print(f" - {v}")
        
        # Check specific expectations
        if "Case 1" in case["name"]:
            if not passed:
                print("❌ Case 1 Passed expected, but Failed.")
            else:
                print("✅ Case 1 Passed as expected (Abstract terms accepted).")
                
        elif "Case 2" in case["name"]:
            # Check for format violations
            format_violation = any("형식 위반" in v for v in violations)
            if not format_violation:
                print("❌ Case 2 Failed expectation. 'Format violation' not detected.")
            else:
                print("✅ Case 2 Detected format violation as expected.")

        elif "Case 3" in case["name"]:
             # Check for prohibited expressions or legal judgment
            legal_violation = any("금지 표현" in v or "법적 판단" in v for v in violations)
            if not legal_violation:
                 print("❌ Case 3 Failed expectation. 'Legal violation' not detected.")
            else:
                 print("✅ Case 3 Detected legal violation as expected.")

if __name__ == "__main__":
    asyncio.run(run_verification())
