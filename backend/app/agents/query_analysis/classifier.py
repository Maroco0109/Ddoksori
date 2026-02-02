"""
똑소리 프로젝트 - gpt-4o-mini Intent Classifier
작성일: 2026-01-28
PR-2: Intent Classification 고도화

gpt-4o-mini를 활용한 Function Calling 기반 Intent 분류기.
고품질 데이터셋 수집 후 EXAONE Fine-tuning 전환 예정.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

logger = logging.getLogger(__name__)

# ==============================================================================
# Type Definitions
# ==============================================================================

QueryType = Literal[
    "dispute",
    "law",
    "criteria",
    "procedure",
    "restricted",
    "general",
    "system_meta",
    "ambiguous",
]

RestrictedDomain = Literal[
    "finance", "medical", "privacy", "realestate", "construction"
]

Agency = Literal["KCA", "ECMC"]


@dataclass
class IntentClassificationResult:
    """Intent 분류 결과"""

    query_type: QueryType
    domain: Optional[RestrictedDomain] = None
    agency: Optional[Agency] = None
    confidence: float = 0.0
    reasoning: str = ""
    from_cache: bool = False
    model_used: str = ""


# ==============================================================================
# Function Calling Schema
# ==============================================================================

INTENT_CLASSIFIER_TOOL = {
    "type": "function",
    "function": {
        "name": "classify_intent",
        "description": "사용자 쿼리의 의도를 분류합니다",
        "parameters": {
            "type": "object",
            "properties": {
                "query_type": {
                    "type": "string",
                    "enum": [
                        "dispute",
                        "law",
                        "criteria",
                        "procedure",
                        "restricted",
                        "general",
                        "system_meta",
                        "ambiguous",
                    ],
                    "description": "분류된 쿼리 유형",
                },
                "domain": {
                    "type": ["string", "null"],
                    "enum": [
                        "consumer",
                        "finance",
                        "medical",
                        "privacy",
                        "realestate",
                        "construction",
                        None,
                    ],
                    "description": "restricted일 때 도메인, 아니면 null",
                },
                "agency": {
                    "type": ["string", "null"],
                    "enum": ["KCA", "ECMC", None],
                    "description": "consumer 도메인일 때 기관 (KCA: 일반, ECMC: 전자거래/개인간)",
                },
                "confidence": {
                    "type": "number",
                    "description": "분류 신뢰도 (0.0 ~ 1.0)",
                },
                "reasoning": {
                    "type": "string",
                    "description": "분류 근거 (데이터셋 수집용)",
                },
            },
            "required": ["query_type", "confidence", "reasoning"],
        },
    },
}

SYSTEM_PROMPT = """당신은 소비자 분쟁 상담 시스템의 의도 분류기입니다.

## 분류 기준

### dispute (분쟁 상담)
- 구체적인 분쟁 상황 설명 (환불, 교환, 배송, 계약 해지 등)
- 제품/서비스 문제로 인한 피해 호소
- 예: "노트북 환불이 안 돼요", "계약 해지하고 싶어요"

### law (법령 문의)
- 법조문, 법률명 언급
- 법적 근거 질문
- 예: "소비자기본법 몇 조에요?", "청약철회 법적 기간"

### criteria (분쟁해결기준)
- 분쟁해결기준, 보상 기준 질문
- 구체적 보상 범위
- 예: "세탁기 하자 시 보상 기준", "배송 지연 보상"

### procedure (절차 안내)
- 신청 방법, 접수 절차 질문
- 분쟁조정 신청 관련
- 예: "분쟁조정 어떻게 신청해요?", "서류 뭐 필요해요?"

### restricted (전문기관 도메인)
- 금융: 대출, 보험, 은행, 카드, 주식, 금융분쟁
- 의료: 병원, 의사, 진료, 수술, 의료사고
- 개인정보: 개인정보 유출, 정보보호
- 부동산: 임대차, 전세, 월세, 보증금
- 건설: 공사, 하자, 시공, 건축

### general (일반 대화)
- 인사, 감사
- 단순 정의 질문 ("환불이 뭐야?")
- 일상 대화

### system_meta (시스템 질문)
- 봇 정체성, 기능 질문
- 예: "너 누구야?", "뭘 할 수 있어?"

### ambiguous (모호함)
- 맥락 없는 단순 요청
- 의도 불명확
- 예: "도와줘", "이거 뭐야"

## 기관 구분 기준 (consumer 도메인만 해당)

- KCA (한국소비자원): 일반 소비자 분쟁, 오프라인 구매, 서비스 분쟁
- ECMC (전자거래분쟁조정위원회): 온라인 쇼핑몰, 전자거래, 개인간 거래 분쟁

키워드: "인터넷", "온라인", "쇼핑몰", "앱", "중고거래", "번개장터", "당근마켓" → ECMC
그 외 일반적인 소비자 분쟁 → KCA"""


# ==============================================================================
# Intent Classifier
# ==============================================================================


class IntentClassifier:
    """
    gpt-4o-mini 기반 Intent 분류기

    Function Calling을 사용하여 구조화된 분류 결과 반환.
    데이터셋 수집 후 EXAONE Fine-tuning 전환 예정.
    """

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        temperature: float = 0.0,
        timeout: float = 3.0,
        confidence_threshold: float = 0.8,
    ):
        self.model = model
        self.temperature = temperature
        self.timeout = timeout
        self.confidence_threshold = confidence_threshold
        self._client = None

        logger.info(
            f"[IntentClassifier] Initialized: model={model}, "
            f"timeout={timeout}s, confidence_threshold={confidence_threshold}"
        )

    def _get_client(self):
        """OpenAI 클라이언트 지연 초기화"""
        if self._client is None:
            try:
                from openai import OpenAI

                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    raise ValueError("OPENAI_API_KEY not set")
                self._client = OpenAI(api_key=api_key, timeout=self.timeout)
            except ImportError:
                raise RuntimeError(
                    "openai package not installed. Run: pip install openai"
                )
        return self._client

    def classify(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntentClassificationResult:
        """
        쿼리의 의도를 분류합니다.

        Args:
            query: 사용자 쿼리
            context: 추가 컨텍스트 (대화 히스토리 등)

        Returns:
            IntentClassificationResult: 분류 결과
        """
        try:
            client = self._get_client()

            # 메시지 구성
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": f"다음 쿼리를 분류해주세요:\n\n{query}"},
            ]

            # Function Calling 호출
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=[INTENT_CLASSIFIER_TOOL],
                tool_choice={
                    "type": "function",
                    "function": {"name": "classify_intent"},
                },
                temperature=self.temperature,
            )

            # 결과 파싱
            tool_call = response.choices[0].message.tool_calls[0]
            result = json.loads(tool_call.function.arguments)

            # 데이터셋 수집용 로깅
            self._log_classification(query, result)

            return IntentClassificationResult(
                query_type=result["query_type"],
                domain=result.get("domain"),
                agency=result.get("agency"),
                confidence=result.get("confidence", 0.0),
                reasoning=result.get("reasoning", ""),
                from_cache=False,
                model_used=self.model,
            )

        except Exception as e:
            logger.warning(f"[IntentClassifier] Classification failed: {e}")
            # 실패 시 ambiguous 반환
            return IntentClassificationResult(
                query_type="ambiguous",
                confidence=0.0,
                reasoning=f"Classification error: {str(e)}",
                from_cache=False,
                model_used=self.model,
            )

    def _log_classification(self, query: str, result: Dict[str, Any]):
        """데이터셋 수집용 로깅"""
        log_entry = {
            "query": query,
            "query_type": result.get("query_type"),
            "domain": result.get("domain"),
            "agency": result.get("agency"),
            "confidence": result.get("confidence"),
            "reasoning": result.get("reasoning"),
            "model": self.model,
        }
        logger.info(
            f"[IntentClassifier] Classification: {json.dumps(log_entry, ensure_ascii=False)}"
        )

    def is_confident(self, result: IntentClassificationResult) -> bool:
        """신뢰도 threshold 충족 여부"""
        return result.confidence >= self.confidence_threshold


# ==============================================================================
# Hybrid Classifier (Rule-based + LLM)
# ==============================================================================


class HybridIntentClassifier:
    """
    Hybrid Intent 분류기: Rule-based Fast Path + LLM Fallback + Redis Cache

    Layer 0: Fast Path (Rule-based)
        - system_meta 패턴 → 즉시 반환
        - general 패턴 (인사) → 즉시 반환
        - 법률명 패턴 (\\S+법) → law

    Layer 1: Redis Cache (L3)
        - 이전 LLM 분류 결과 재사용
        - TTL: 7일

    Layer 2: LLM Classification
        - gpt-4o-mini Function Calling
        - confidence >= 0.8 → 채택
        - confidence < 0.8 → ambiguous
    """

    def __init__(
        self,
        llm_classifier: Optional[IntentClassifier] = None,
        use_llm: bool = True,
        use_cache: bool = True,
    ):
        self.llm_classifier = llm_classifier or IntentClassifier()
        self.use_llm = use_llm
        self.use_cache = use_cache

        # Fast Path 패턴 (agent.py에서 가져옴)
        self._system_meta_patterns = [
            "너 누구",
            "네 이름",
            "뭐야 너",
            "누가 만들",
            "어떤 모델",
            "무슨 ai",
            "무슨 llm",
            "기능이 뭐",
            "뭘 할 수",
            "뭐 할 수",
            "어떤 일을",
        ]

        self._greeting_patterns = [
            "안녕",
            "하이",
            "헬로",
            "반가워",
            "감사합니다",
            "고마워",
            "ㅋㅋ",
            "ㅎㅎ",
            "네",
            "응",
            "좋아",
        ]

        logger.info(
            f"[HybridIntentClassifier] Initialized: use_llm={use_llm}, use_cache={use_cache}"
        )

    def classify(
        self,
        query: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> IntentClassificationResult:
        """
        Hybrid 분류 실행

        1. Fast Path 체크
        2. Redis 캐시 조회 (use_cache=True인 경우)
        3. LLM 분류 (use_llm=True인 경우)
        4. confidence 체크
        5. 결과 캐싱
        """
        query_lower = query.lower().strip()

        # === Layer 0: Fast Path ===

        # system_meta 패턴
        if any(p in query_lower for p in self._system_meta_patterns):
            logger.info(f"[HybridIntentClassifier] Fast path: system_meta")
            return IntentClassificationResult(
                query_type="system_meta",
                confidence=1.0,
                reasoning="Fast path: system_meta pattern matched",
                from_cache=False,
                model_used="rule_based",
            )

        # greeting 패턴 (매우 짧은 쿼리만)
        if len(query_lower) <= 10 and any(
            p in query_lower for p in self._greeting_patterns
        ):
            logger.info(f"[HybridIntentClassifier] Fast path: general (greeting)")
            return IntentClassificationResult(
                query_type="general",
                confidence=1.0,
                reasoning="Fast path: greeting pattern matched",
                from_cache=False,
                model_used="rule_based",
            )

        # law 패턴 (법률명 명시)
        import re

        if re.search(r"\S+법", query):
            # "X법"이 명시적으로 언급되면 law로 분류
            logger.info(f"[HybridIntentClassifier] Fast path: law (법률명 패턴)")
            return IntentClassificationResult(
                query_type="law",
                confidence=0.9,
                reasoning="Fast path: 법률명 패턴 (\\S+법) matched",
                from_cache=False,
                model_used="rule_based",
            )

        # === Layer 1: Redis Cache ===
        if self.use_cache:
            cached = self._get_from_cache(query)
            if cached:
                return cached

        # === Layer 2: LLM Classification ===
        if not self.use_llm:
            logger.info(f"[HybridIntentClassifier] LLM disabled, returning ambiguous")
            return IntentClassificationResult(
                query_type="ambiguous",
                confidence=0.0,
                reasoning="LLM classification disabled",
                from_cache=False,
                model_used="none",
            )

        result = self.llm_classifier.classify(query, context)

        # confidence 체크
        if not self.llm_classifier.is_confident(result):
            logger.info(
                f"[HybridIntentClassifier] Low confidence ({result.confidence:.2f}), "
                f"overriding to ambiguous"
            )
            result.query_type = "ambiguous"

        # 결과 캐싱 (LLM 호출 성공 시)
        if self.use_cache and result.model_used != "none":
            self._save_to_cache(query, result)

        return result

    def _get_from_cache(self, query: str) -> Optional[IntentClassificationResult]:
        """Redis 캐시에서 분류 결과 조회"""
        try:
            from app.supervisor.cache import IntentClassificationCache

            cached = IntentClassificationCache.get(query)
            if cached:
                logger.info(f"[HybridIntentClassifier] Cache hit")
                return IntentClassificationResult(
                    query_type=cached.get("query_type", "ambiguous"),
                    domain=cached.get("domain"),
                    agency=cached.get("agency"),
                    confidence=cached.get("confidence", 0.0),
                    reasoning=cached.get("reasoning", "from cache"),
                    from_cache=True,
                    model_used=cached.get("model_used", "cached"),
                )
        except ImportError:
            logger.debug("[HybridIntentClassifier] Cache module not available")
        except Exception as e:
            logger.warning(f"[HybridIntentClassifier] Cache get error: {e}")
        return None

    def _save_to_cache(self, query: str, result: IntentClassificationResult) -> None:
        """Redis 캐시에 분류 결과 저장"""
        try:
            from app.supervisor.cache import IntentClassificationCache

            IntentClassificationCache.set(
                query,
                {
                    "query_type": result.query_type,
                    "domain": result.domain,
                    "agency": result.agency,
                    "confidence": result.confidence,
                    "reasoning": result.reasoning,
                    "model_used": result.model_used,
                },
            )
            logger.debug(f"[HybridIntentClassifier] Cached result")
        except ImportError:
            logger.debug("[HybridIntentClassifier] Cache module not available")
        except Exception as e:
            logger.warning(f"[HybridIntentClassifier] Cache set error: {e}")


# ==============================================================================
# Module-level singleton
# ==============================================================================

_default_classifier: Optional[HybridIntentClassifier] = None


def get_intent_classifier() -> HybridIntentClassifier:
    """기본 Intent Classifier 싱글톤 반환"""
    global _default_classifier
    if _default_classifier is None:
        _default_classifier = HybridIntentClassifier()
    return _default_classifier


def classify_intent(
    query: str, context: Optional[Dict[str, Any]] = None
) -> IntentClassificationResult:
    """편의 함수: 쿼리 의도 분류"""
    classifier = get_intent_classifier()
    return classifier.classify(query, context)


__all__ = [
    "QueryType",
    "RestrictedDomain",
    "Agency",
    "IntentClassificationResult",
    "IntentClassifier",
    "HybridIntentClassifier",
    "get_intent_classifier",
    "classify_intent",
    "INTENT_CLASSIFIER_TOOL",
    "SYSTEM_PROMPT",
]
