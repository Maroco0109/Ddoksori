"""Variant B chat model factory (model-agnostic via base_url swap).

- "frontier" (default): OpenAI ChatOpenAI (no pod). Validates B plumbing cheaply.
- "exaone": ChatOpenAI pointed at the RunPod vLLM OpenAI-compatible endpoint
  (must be served with tool-calling flags). Needs the H100 pod up.

The same ReAct agent runs against either — only the model object changes.
"""

import os

from langchain_openai import ChatOpenAI


def get_chat_model(spec: str = "frontier", temperature: float = 0.0) -> ChatOpenAI:
    if spec == "exaone":
        base_url = os.getenv("EXAONE_RUNPOD_URL")
        if not base_url:
            raise RuntimeError("EXAONE_RUNPOD_URL not set (pod must be up for spec='exaone')")
        return ChatOpenAI(
            model=os.getenv("EXAONE_MODEL", "LGAI-EXAONE/EXAONE-4.5-33B"),
            base_url=base_url,
            api_key=os.getenv("EXAONE_RUNPOD_API_KEY", "dummy"),
            temperature=temperature,
        )
    # frontier default
    return ChatOpenAI(
        model=os.getenv("VARIANT_B_FRONTIER_MODEL", "gpt-4o-mini"),
        temperature=temperature,
    )
