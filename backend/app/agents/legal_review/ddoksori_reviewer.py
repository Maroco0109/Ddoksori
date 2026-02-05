import json
import os
import re

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


class DdoksoriReviewer:
    """v2.4.1: 추상적 표현 허용 및 업종별 용어 교정을 수용하는 합리적 품질 감사관"""

    def __init__(self):
        self.client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        # 엔진에서 제거하지만, 변형된 형태로 남아있는 헤더를 잡기 위한 최후의 보루
        self.forbidden_headers = [
            "[공감]",
            "[가이드]",
            "[출처]",
            "[돌파 논리]",
            "[사건 요약]",
            "[상황 정리]",
            "[법적 근거]",
            "[근거 안내]",
            "[절차 안내]",
            "[법률]",
            "[해결기준]",
            "[유사사례]",
            "[상황 공감]",
            "[위로와 전환]",
            "[사건 요약 정리]",
            "[논리적 근거 안내]",
            "[행정 절차 안내]",
            "[전문 기관 연결]",
            "[근거 및 이유 안내]",
        ]

        # [v2.4.1 업데이트] 할루시네이션 체크에서 제외할 화이트리스트 및 허용 지침
        self.whitelist = [
            # 주요 공적 기관 및 번호
            "한국소비자원",
            "대한법률구조공단",
            "경찰청",
            "경찰서",
            "1372 소비자상담센터",
            "소비자분쟁조정위원회",
            "전자거래분쟁조정위원회",
            "콘텐츠분쟁조정위원회",
            "1372",
            "132",
            "112",
            "110",
            # [허용] 데이터에 구체적 숫자가 없을 때 사용하는 추상적 수치 표현
            "일정 비율",
            "관련 기준",
            "정당한 보상",
            "해당 규정",
            "일정 금액",
            "일부 금액",
            # 법적 절차 및 문서
            "내용증명",
            "민사소송",
            "소액심판",
            "지급명령",
            "소장",
            "증거자료",
            "계약서",
            "영수증",
            "이체내역",
            "배달증명",
            "피해구제",
            "분쟁조정",
            # 템플릿 고정 문구
            "보험이자 증거 자료",
            "든든한 보험",
            "정당한 주장을 기록",
            "소중한 자료",
            "상담 예약",
            "피해 사실 요약",
            "사건 요약",
        ]

    def _check_format_by_code(self, response):
        """기계적인 형식 위반 사항을 체크합니다."""
        issues = []
        if "**" in response:
            issues.append("마크다운 볼드체(**)가 포함되어 있습니다.")

        for header in self.forbidden_headers:
            if header in response:
                issues.append(f"금지된 구조적 헤더 '{header}'가 본문에 남아 있습니다.")

        if re.search(r"\{.*?\}", response):
            issues.append("치환되지 않은 템플릿 변수({ })가 발견되었습니다.")

        return issues

    def review(self, input_data, generated_response):
        """지능형 논리/정합성 체크 (v2.4.1: 추상적 표현 및 용어 교정 인정)"""

        # 1. 기계적 형식 체크
        format_issues = self._check_format_by_code(generated_response)

        # 2. GPT-4o 기반 지능형 정합성 검토
        review_prompt = f"""
당신은 소비자 분쟁 해결 가이드 '똑소리'의 최종 품질 감사관입니다. 
제시된 [입력 데이터]와 [생성된 답변]을 비교하되, 아래의 **[품질 검토 기준]**을 최우선으로 적용하십시오.

### [입력 데이터 (JSON)]
{json.dumps(input_data, ensure_ascii=False, indent=2)}

### [생성된 답변]
---
{generated_response}
---

### [품질 검토 기준 (v2.4.1 업데이트)]
1. **수치 할루시네이션 완화**: 
   - 데이터에 구체적인 숫자(%, 원)가 없는데 모델이 **숫자를 지어낸 경우만 반려**하십시오.
   - **[PASS 허용]**: "일정 비율", "관련 기준에 따른 위약금", "정당한 보상" 등 추상적인 표현은 할루시네이션이 아닌 '안전한 가이드'로 간주하여 무조건 통과시키십시오.

2. **용어 교정 정당성 인정**:
   - 답변의 '해지/해제' 선택이 JSON 데이터 원문과 다르더라도, **업종 성격(계속거래 vs 일회성)**에 맞춰 모델이 합리적으로 교정했다면 반려하지 마십시오. 
   - 예: 데이터 원문에 '해제'라고 되어 있어도 피부과/헬스장 케이스에서 모델이 '해지'라고 썼다면 이는 올바른 교정으로 간주합니다.

3. **데이터 활용 위계 및 Fallback**:
   - 데이터가 하나라도 존재함에도 데이터를 설명하지 않고 곧바로 『1372 소비자상담센터』로 안내했다면 '데이터 활용 미흡'으로 반려하십시오.
   - **모든 데이터**가 '데이터 없음'일 때 『1372 소비자상담센터』를 안내하는 것은 정상적인 대응(Fallback)이므로 반려하지 마십시오.

4. **완벽한 데이터 고립**: 
   - 데이터가 '데이터 없음'인 섹션에 대해 내용을 지어냈다면 반려하십시오. (단, 화이트리스트 용어 및 일반적 위로는 허용)

5. **중복 검사 (예외 규정)**: 
   - 동일 문장이 의미 없이 반복되는 경우만 반려하십시오.
   - **[허용 사항]**: 아래의 경우는 중복으로 간주하지 말고 무조건 통과시키십시오.
     1) 용어 병기 규칙(`단어(풀이)`)에 의한 반복적 노출.
     2) **[중요]** 본문에 적힌 '역질문 리스트'와 하단의 '버튼형 역질문' 내용이 동일한 경우 (이는 사용자 인터페이스를 위한 의도된 설계입니다).

### [출력 형식 (JSON)]
{{
    "is_pass": true | false,
    "detected_issues": ["위반 사항 요약"],
    "feedback": "합리적인 수정 지시"
}}
"""
        res = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "데이터의 근거와 템플릿 지침을 구분할 줄 아는 합리적이고 정확한 감사관입니다.",
                },
                {"role": "user", "content": review_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        review_result = json.loads(res.choices[0].message.content)

        # 기계적 체크 결과 통합
        if format_issues:
            review_result["is_pass"] = False
            if "detected_issues" not in review_result:
                review_result["detected_issues"] = []
            review_result["detected_issues"].extend(format_issues)

        return review_result
