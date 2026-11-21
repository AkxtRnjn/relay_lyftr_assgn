import hashlib
import json

import litellm
from fastapi import HTTPException
from litellm.caching.caching import Cache


class Gateway:
    def __init__(self, keys, model, api_base=None):
        self.keys = keys
        self.model = model
        self.api_base = api_base
        self.cache = Cache(type="local", ttl=3600)

    async def answer(self, messages, simulated):
        payload = json.dumps([self.model, messages], sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        cache_key = hashlib.sha256(payload.encode()).hexdigest()
        if not simulated:
            cached = self.cache.get_cache(cache_key=cache_key)
            if cached is not None:
                return cached, {"resolution_source": "LLM_CACHE", "key_id": None, "fallback_attempts": 0}

        for attempt, key in enumerate(self.keys):
            key_id = f"key_{attempt + 1}"
            if key_id in simulated or "*" in simulated:
                continue
            try:
                result = await litellm.acompletion(
                    model=self.model, messages=messages, api_key=key, api_base=self.api_base,
                    timeout=30, num_retries=0, caching=False,
                )
                reply = result.choices[0].message.content
                if not isinstance(reply, str) or not reply.strip():
                    continue
                answer = {"reply": reply, "model": self.model,
                          "input_tokens": int(result.usage.prompt_tokens),
                          "output_tokens": int(result.usage.completion_tokens)}
            except Exception:
                # Provider SDK messages may contain credentials or request content.
                # Try the remaining credentials and expose only the contract error.
                continue
            self.cache.add_cache(answer, cache_key=cache_key)
            return answer, {"resolution_source": "LIVE_INFERENCE", "key_id": key_id, "fallback_attempts": attempt}
        raise HTTPException(503, "all providers unavailable")
