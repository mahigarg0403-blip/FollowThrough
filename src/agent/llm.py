import os, time
from dotenv import load_dotenv
from openai import (OpenAI, InternalServerError, RateLimitError,
                    APIConnectionError, APITimeoutError)

load_dotenv()
client = OpenAI(base_url=os.environ["LLM_BASE_URL"], api_key=os.environ["LLM_API_KEY"],
                max_retries=0, timeout=60)

MODELS = [os.environ["LLM_MODEL"]]
if os.getenv("LLM_FALLBACK_MODEL"):
    MODELS.append(os.environ["LLM_FALLBACK_MODEL"])

RETRYABLE = (InternalServerError, RateLimitError, APIConnectionError, APITimeoutError)

def ask_llm(system, user):
    last = None
    for model in MODELS:
        for attempt in range(3):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    temperature=0,
                    messages=[{"role": "system", "content": system},
                              {"role": "user", "content": user}],
                )
                return resp.choices[0].message.content
            except RETRYABLE as e:
                last = e
                print(f"[llm] {model} attempt {attempt + 1} failed: {type(e).__name__}", flush=True)
                time.sleep(2 * (attempt + 1))
    raise last