"""OpenAI 사용 가능 모델 확인 스크립트"""

import sys

sys.path.insert(0, "C:/Users/Playdata/Desktop/project/05_hub_5th_project/LLM/backend")


from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
client = OpenAI()

models = client.models.list()
gpt_models = sorted([m.id for m in models.data if "gpt" in m.id.lower()])

print("=== 사용 가능한 GPT 모델 ===")
for m in gpt_models:
    print(f"  - {m}")

print("\n=== 추천 모델 (답변 생성용) ===")
recommended = [
    m for m in gpt_models if any(x in m for x in ["gpt-4o", "gpt-4-turbo", "gpt-5"])
]
for m in recommended:
    print(f"  - {m}")
