import os
from pathlib import Path

import google.generativeai as genai
from dotenv import load_dotenv

project_root = Path(__file__).resolve().parents[1]
load_dotenv(dotenv_path=project_root / ".env")
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

print("=== 利用可能なモデル一覧 ===")
for m in genai.list_models():
    if 'generateContent' in m.supported_generation_methods:
        print(f"- {m.name}")
