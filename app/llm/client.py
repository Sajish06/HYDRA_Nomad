import os
import json
import hashlib
from pathlib import Path
from typing import Type, TypeVar, Optional, Dict, Any, List
import httpx
from pydantic import BaseModel, ValidationError

from app.config import settings, BASE_DIR

T = TypeVar("T", bound=BaseModel)

class LLMUnavailable(Exception):
    pass

class LLMCacheMiss(Exception):
    pass

def get_cache_dir() -> Path:
    p = BASE_DIR / "data" / "llm_cache"
    p.mkdir(parents=True, exist_ok=True)
    return p

def compute_cache_key(model: str, prompt_name: str, prompt_version: str, payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, default=str)
    raw = f"{model}:{prompt_name}:{prompt_version}:{serialized}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()

def get_from_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    cache_file = get_cache_dir() / f"{cache_key}.json"
    if cache_file.exists():
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None

def save_to_cache(cache_key: str, data: Dict[str, Any]) -> None:
    cache_file = get_cache_dir() / f"{cache_key}.json"
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

_OLLAMA_ALIVE: Optional[bool] = None

_RESOLVED_MODEL: Optional[str] = None

def get_installed_ollama_model(base_url: str, preferred_model: str) -> str:
    global _RESOLVED_MODEL
    if _RESOLVED_MODEL:
        return _RESOLVED_MODEL
    try:
        with httpx.Client(timeout=1.0) as client:
            resp = client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                if models:
                    if preferred_model in models:
                        _RESOLVED_MODEL = preferred_model
                        return preferred_model
                    for m in models:
                        if "qwen2.5" in m or "qwen" in m:
                            _RESOLVED_MODEL = m
                            return m
                    _RESOLVED_MODEL = models[0]
                    return _RESOLVED_MODEL
    except Exception:
        pass
    _RESOLVED_MODEL = preferred_model
    return preferred_model

def query_structured_llm(
    prompt_name: str,
    prompt_version: str,
    system_prompt: str,
    user_prompt: str,
    response_model: Type[T],
    input_context: Any = None,
    max_retries: int = 1
) -> T:
    """Queries Ollama with JSON schema validation, retry loop, and disk cache."""
    global _OLLAMA_ALIVE
    active_model = get_installed_ollama_model(settings.OLLAMA_URL.rstrip('/'), settings.OLLAMA_MODEL)
    cache_payload = input_context if input_context is not None else {"system": system_prompt, "user": user_prompt}
    cache_key = compute_cache_key(active_model, prompt_name, prompt_version, cache_payload)

    cached = get_from_cache(cache_key)
    if cached is not None:
        try:
            return response_model.model_validate(cached)
        except ValidationError:
            pass

    if settings.MOCK_LLM or _OLLAMA_ALIVE is False:
        if cached is not None:
            return response_model.model_validate(cached)
        raise LLMUnavailable(f"LLM unavailable (MOCK_LLM={settings.MOCK_LLM}, _OLLAMA_ALIVE={_OLLAMA_ALIVE})")

    url = f"{settings.OLLAMA_URL.rstrip('/')}/api/chat"
    schema = response_model.model_json_schema()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]

    last_err = None
    for attempt in range(max_retries + 1):
        payload = {
            "model": active_model,
            "messages": messages,
            "stream": False,
            "format": schema,
            "options": {
                "temperature": 0.0,
                "seed": 42,
                "num_ctx": 4096
            }
        }

        try:
            with httpx.Client(timeout=httpx.Timeout(45.0, connect=0.3)) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_content = data.get("message", {}).get("content", "{}")
                parsed_json = json.loads(raw_content)
                validated = response_model.model_validate(parsed_json)
                
                # Save valid result to cache
                save_to_cache(cache_key, validated.model_dump(mode="json"))
                return validated

        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            _OLLAMA_ALIVE = False
            raise LLMUnavailable(f"Ollama server timeout or unavailable at {settings.OLLAMA_URL}: {str(e)}")
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            last_err = e
            break  # Ollama error
        except (json.JSONDecodeError, ValidationError) as e:
            last_err = e
            # Append error to messages to allow model self-correction
            messages.append({"role": "assistant", "content": raw_content if 'raw_content' in locals() else ""})
            messages.append({"role": "user", "content": f"Output validation failed with error: {str(e)}. Please correct your output to strictly adhere to the JSON schema."})

    raise LLMUnavailable(f"Failed to query LLM for prompt '{prompt_name}': {str(last_err)}")
