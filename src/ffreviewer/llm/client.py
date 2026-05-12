import hashlib, json, os
from pathlib import Path
from openai import OpenAI
import dotenv 
dotenv.load_dotenv()

_client = OpenAI(
    base_url=os.getenv("OLLAMA_URL"),
    api_key=os.getenv("API_KEY")
)
_CACHE_DIR = Path(".cache/llm")
_CACHE_DIR.mkdir(parents=True, exist_ok=True)

def generate_json(
        system: str,
        user: str,
        model: str = "qwen2.5:7b",
        temperature: float = 0.1,
) -> dict:
    cache_key = hashlib.sha256(f"{model}|{system}|{user}|{temperature}".encode()).hexdigest()
    cache_file = _CACHE_DIR / f"{cache_key}.json"

    if cache_file.exists():
        return json.loads(cache_file.read_text())

    for attempt in range(3):
        try:
            response = _client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                response_format={"type": "json_object"},
                temperature=temperature,
            )
            data = json.loads(response.choices[0].message.content)
            cache_file.write_text(json.dumps(data))
            return data
        except json.JSONDecodeError as e:
            if attempt == 2:
                raise e
            continue