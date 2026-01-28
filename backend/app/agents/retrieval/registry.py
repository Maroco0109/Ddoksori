import os
from typing import Type


def _use_v2() -> bool:
    value = os.getenv("USE_INTENT_PIPELINE_V2", "0").lower()
    return value in ("1", "true", "yes")


def get_case_agent_class() -> Type:
    if _use_v2():
        from .case_agent_v2 import CaseRetrievalAgentV2
        return CaseRetrievalAgentV2

    from .case_agent import CaseRetrievalAgent
    return CaseRetrievalAgent


def get_counsel_agent_class() -> Type:
    if _use_v2():
        from .counsel_agent_v2 import CounselRetrievalAgentV2
        return CounselRetrievalAgentV2

    from .counsel_agent import CounselRetrievalAgent
    return CounselRetrievalAgent
