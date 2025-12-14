import google.generativeai as genai
import os
from dotenv import load_dotenv

# 1. Load your API key safely
# Option A: If you have a .env file
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Option B: Paste it here directly just for this test (delete it after!)
if not api_key:
    api_key = ""

genai.configure(api_key=api_key)

print("🔎 Checking available models for your API Key...")
try:
    available_models = []
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"✅ FOUND: {m.name}")
            available_models.append(m.name)
            
    if not available_models:
        print("❌ No models found! Your API key might be invalid or has no access.")
    else:
        print("\n👇 USE ONE OF THESE EXACT NAMES IN YOUR APP:")
        for model in available_models:
            # Strip the 'models/' prefix to make it easier to read
            clean_name = model.replace("models/", "")
            print(f'   "{clean_name}"')

except Exception as e:
    print(f"🚨 Error: {e}")
