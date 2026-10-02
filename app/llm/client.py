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
        with httpx.Client(timeout=1.5) as client:
            resp = client.get(f"{base_url}/api/tags")
            if resp.status_code == 200:
                data = resp.json()
                models = [m.get("name", "") for m in data.get("models", [])]
                if models:
                    # 1. Exact match with preferred_model
                    if preferred_model in models:
                        _RESOLVED_MODEL = preferred_model
                        return preferred_model
                    # 2. Check base name match (e.g. qwen2.5:7b vs qwen2.5:7b-instruct vs qwen2.5:latest)
                    base_pref = preferred_model.split(":")[0]
                    for m in models:
                        if m.startswith(f"{base_pref}:") or base_pref in m:
                            _RESOLVED_MODEL = m
                            return m
                    # 3. Prefer any qwen model
                    for m in models:
                        if "qwen" in m.lower():
                            _RESOLVED_MODEL = m
                            return m
                    # 4. Prefer any common model family
                    for family in ["llama", "mistral", "gemma", "deepseek", "phi"]:
                        for m in models:
                            if family in m.lower():
                                _RESOLVED_MODEL = m
                                return m
                    # 5. Fallback to first available installed model
                    _RESOLVED_MODEL = models[0]
                    return _RESOLVED_MODEL
    except Exception:
        pass
    _RESOLVED_MODEL = preferred_model
    return preferred_model

def find_cached_llm_response(
    active_model: str,
    prompt_name: str,
    prompt_version: str,
    payload: Any
) -> Optional[Dict[str, Any]]:
    """Tries active_model first, then falls back to known models and generic cache keys."""
    candidate_models = [
        active_model,
        settings.OLLAMA_MODEL,
        "qwen2.5:7b-instruct",
        "qwen2.5:7b",
        "qwen2.5:latest",
        "llama3.1:latest",
        "default"
    ]
    seen = set()
    for m in candidate_models:
        if m in seen:
            continue
        seen.add(m)
        key = compute_cache_key(m, prompt_name, prompt_version, payload)
        data = get_from_cache(key)
        if data is not None:
            return data
    return None

def save_to_cache_multi(
    active_model: str,
    prompt_name: str,
    prompt_version: str,
    payload: Any,
    data: Dict[str, Any]
) -> None:
    """Saves to cache under active_model and also alias keys so all collaborators hit cache."""
    models_to_cache = [active_model, "default", "qwen2.5:7b-instruct", "qwen2.5:7b"]
    seen = set()
    for m in models_to_cache:
        if m in seen:
            continue
        seen.add(m)
        key = compute_cache_key(m, prompt_name, prompt_version, payload)
        save_to_cache(key, data)

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

    cached = find_cached_llm_response(active_model, prompt_name, prompt_version, cache_payload)
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
            with httpx.Client(timeout=httpx.Timeout(45.0, connect=3.0)) as client:
                resp = client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
                raw_content = data.get("message", {}).get("content", "{}")
                parsed_json = json.loads(raw_content)
                validated = response_model.model_validate(parsed_json)
                
                # Save valid result to cache across model aliases
                save_to_cache_multi(active_model, prompt_name, prompt_version, cache_payload, validated.model_dump(mode="json"))
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

