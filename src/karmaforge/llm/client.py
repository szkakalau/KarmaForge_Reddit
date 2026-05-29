"""LLM API client — unified interface for DeepSeek and Claude.

Uses the openai SDK since DeepSeek's API is OpenAI-compatible.
Claude can be accessed via OpenAI-compatible proxies or the Anthropic SDK as fallback.
"""

import json
import hashlib
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Optional

from openai import OpenAI, RateLimitError, APIError


class LLMProvider(Enum):
    DEEPSEEK = "deepseek"
    CLAUDE = "claude"


@dataclass
class LLMConfig:
    provider: LLMProvider
    api_key: str
    model: str = "deepseek-chat"
    api_base_url: str = "https://api.deepseek.com/v1"
    max_tokens: int = 2000
    temperature: float = 0.0
    request_timeout: int = 60
    max_retries: int = 3
    cache_dir: Optional[Path] = None

    def __post_init__(self):
        if isinstance(self.provider, str):
            self.provider = LLMProvider(self.provider)


class LLMClient:
    def __init__(self, config: LLMConfig) -> None:
        self.config = config
        self._openai_client: OpenAI | None = None
        self._cache: dict[str, str] = {}
        self._total_tokens = 0
        self._total_cost_estimate = 0.0
        if config.cache_dir:
            config.cache_dir.mkdir(parents=True, exist_ok=True)
            self._load_cache()

    def _get_client(self) -> OpenAI:
        """Lazily create the OpenAI client so that missing credentials
        are surfaced only when an API call is actually made, not at import time."""
        if self._openai_client is None:
            self._openai_client = OpenAI(
                api_key=self.config.api_key,
                base_url=self.config.api_base_url,
                timeout=self.config.request_timeout,
                max_retries=0,
            )
        return self._openai_client

    def complete(self, prompt: str, system_prompt: str = "") -> str:
        cache_key = self._cache_key(prompt, system_prompt)
        if cache_key in self._cache:
            return self._cache[cache_key]

        messages = []
        if system_prompt:
            if self.config.provider == LLMProvider.DEEPSEEK:
                # DeepSeek does not support "system" role; merge into user message
                messages.append({"role": "user", "content": f"{system_prompt}\n\n{prompt}"})
            else:
                messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
        else:
            messages.append({"role": "user", "content": prompt})

        response = self._call_with_retry(messages)
        result = response.choices[0].message.content or ""

        self._cache[cache_key] = result
        self._save_cache_entry(cache_key, result)
        return result

    def batch_complete(
        self, prompts: list[str], system_prompt: str = ""
    ) -> list[str]:
        results = []
        for i in range(0, len(prompts), self.config.max_retries):
            batch = prompts[i : i + self.config.max_retries]
            for prompt in batch:
                results.append(self.complete(prompt, system_prompt))
        return results

    def classify(
        self, texts: list[str], categories: list[str], system_prompt: str = ""
    ) -> list[str]:
        category_list = ", ".join(categories)
        default_system = (
            f"Classify each input into exactly one of these categories: {category_list}. "
            "Return only the category name, nothing else."
        )
        system = system_prompt or default_system

        results = []
        for text in texts:
            result = self.complete(text, system).strip().lower()
            for cat in categories:
                if cat.lower() in result:
                    results.append(cat)
                    break
            else:
                results.append(categories[0])
        return results

    def analyze_sentiment(self, texts: list[str]) -> list[dict]:
        system = (
            "Analyze the sentiment of the following text. "
            "Return a JSON object with keys: polarity (positive/negative/neutral), "
            "intensity (0.0 to 1.0). Return only valid JSON."
        )
        results = []
        for text in texts:
            raw = self.complete(text, system)
            try:
                parsed = json.loads(raw)
                results.append({
                    "polarity": parsed.get("polarity", "neutral"),
                    "intensity": float(parsed.get("intensity", 0.5)),
                })
            except (json.JSONDecodeError, ValueError):
                results.append({"polarity": "neutral", "intensity": 0.5})
        return results

    @property
    def total_tokens(self) -> int:
        return self._total_tokens

    @property
    def estimated_cost(self) -> float:
        return self._total_cost_estimate

    def _call_with_retry(self, messages: list[dict]) -> object:
        last_error = None
        for attempt in range(self.config.max_retries):
            try:
                response = self._get_client().chat.completions.create(
                    model=self.config.model,
                    messages=messages,
                    max_tokens=self.config.max_tokens,
                    temperature=self.config.temperature,
                )
                usage = response.usage
                if usage:
                    self._total_tokens += usage.total_tokens
                    self._total_cost_estimate += self._estimate_cost(
                        usage.prompt_tokens, usage.completion_tokens
                    )
                return response
            except RateLimitError as e:
                wait = 2 ** attempt
                time.sleep(wait)
                last_error = e
            except APIError as e:
                if e.status_code and e.status_code >= 500:
                    wait = 2 ** attempt
                    time.sleep(wait)
                    last_error = e
                else:
                    raise
        raise last_error or RuntimeError("Max retries exceeded")

    def _estimate_cost(self, prompt_tokens: int, completion_tokens: int) -> float:
        if self.config.provider == LLMProvider.DEEPSEEK:
            return (prompt_tokens * 0.14 + completion_tokens * 0.28) / 1_000_000
        return (prompt_tokens * 3.0 + completion_tokens * 15.0) / 1_000_000

    def _cache_key(self, prompt: str, system: str) -> str:
        raw = f"{self.config.model}:{system}:{prompt}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def _load_cache(self) -> None:
        if not self.config.cache_dir:
            return
        cache_file = self.config.cache_dir / "llm_cache.jsonl"
        if cache_file.exists():
            for line in open(cache_file, encoding="utf-8"):
                entry = json.loads(line.strip())
                self._cache[entry["key"]] = entry["value"]

    def _save_cache_entry(self, key: str, value: str) -> None:
        if not self.config.cache_dir:
            return
        cache_file = self.config.cache_dir / "llm_cache.jsonl"
        with open(cache_file, "a", encoding="utf-8") as f:
            f.write(json.dumps({"key": key, "value": value}, ensure_ascii=False) + "\n")
