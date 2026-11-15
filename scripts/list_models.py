import os
import sys

from dotenv import load_dotenv
from google import genai

load_dotenv()

key = os.getenv("GEMINI_API_KEY")
if not key:
    sys.exit("GEMINI_API_KEY is not set. Put it in .env first.")

client = genai.Client(api_key=key)

chat, embed, other = [], [], []

for model in client.models.list():
    name = model.name.removeprefix("models/")
    actions = set(getattr(model, "supported_actions", None) or [])

    if "embedContent" in actions:
        embed.append(name)
    elif "generateContent" in actions:
        chat.append(name)
    else:
        other.append(name)

print("\nGENERATION  (set as GEMINI_MODEL)")
for n in sorted(chat):
    print("  ", n)

print("\nEMBEDDING   (set as GEMINI_EMBED_MODEL)")
for n in sorted(embed):
    print("  ", n)

if other:
    print(f"\n{len(other)} other models not usable for text Q&A")

print("\nPrefer a Flash model - the Pro models are mostly paid-tier only.\n")

