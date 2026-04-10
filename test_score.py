"""Quick test: what does qwen3.5:9b actually return for a scoring prompt?"""
import ollama, json, re, os

MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
print(f"Testing model: {MODEL}")

prompt = (
    "/no_think\n"
    "Opportunity: CLI tool for automating repetitive developer tasks\nSource: evergreen\n\n"
    "Return ONLY this JSON, nothing else:\n"
    '{"demand":0.0,"feasibility":0.0,"competition":0.0,"monetization":0.0,"reasoning":"..."}\n'
    "Scores 0.0-1.0."
)

print("Sending request...")
resp = ollama.chat(
    model=MODEL,
    messages=[
        {"role": "system", "content": "Return only valid JSON. No markdown, no explanation, no thinking."},
        {"role": "user", "content": prompt},
    ],
    options={"temperature": 0.0, "num_ctx": 4096},
)

content = resp["message"]["content"]
print(f"\n--- RAW RESPONSE ({len(content)} chars) ---")
print(repr(content[:500]))
print(f"\n--- VISIBLE ---")
print(content[:500])

think_re = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
stripped = think_re.sub("", content).strip()
print(f"\n--- AFTER STRIPPING THINK ({len(stripped)} chars) ---")
print(stripped[:300])

start = stripped.find("{")
end = stripped.rfind("}") + 1
if start >= 0 and end > start:
    try:
        data = json.loads(stripped[start:end])
        print(f"\nPARSED OK: {data}")
    except Exception as e:
        print(f"\nJSON PARSE FAILED: {e}")
        print(f"Attempted to parse: {stripped[start:end][:200]}")
else:
    print("\nNO JSON FOUND IN STRIPPED RESPONSE")
