"""Tests for LLMClient — API message construction, retry logic, and caching."""

import pytest
from unittest.mock import MagicMock, patch

from karmaforge.llm import LLMClient, LLMConfig, LLMProvider


# ── Mock response helper ────────────────────────────────────────────


def _mock_response(content: str) -> MagicMock:
    resp = MagicMock()
    resp.choices = [MagicMock()]
    resp.choices[0].message = MagicMock()
    resp.choices[0].message.content = content
    resp.usage = MagicMock()
    resp.usage.total_tokens = 10
    resp.usage.prompt_tokens = 5
    resp.usage.completion_tokens = 5
    return resp


# ── complete() message construction ─────────────────────────────────


class TestCompleteMessageConstruction:
    """Verify that complete() builds the correct message structure per provider."""

    def test_deepseek_merges_system_prompt_into_user_message(self):
        """DeepSeek: system_prompt merged into user message, no system role sent."""
        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", model="deepseek-chat"
        )
        client = LLMClient(config)
        with patch.object(
            client, "_call_with_retry", return_value=_mock_response("result")
        ) as mock_call:
            client.complete("user prompt", "system instructions")
            messages = mock_call.call_args[0][0]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            assert "system instructions" in messages[0]["content"]
            assert "user prompt" in messages[0]["content"]

    def test_claude_uses_separate_system_role(self):
        """Non-DeepSeek: system_prompt sent as separate system role message."""
        config = LLMConfig(
            provider=LLMProvider.CLAUDE, api_key="test", model="claude-3"
        )
        client = LLMClient(config)
        with patch.object(
            client, "_call_with_retry", return_value=_mock_response("result")
        ) as mock_call:
            client.complete("user prompt", "system instructions")
            messages = mock_call.call_args[0][0]
            assert len(messages) == 2
            assert messages[0]["role"] == "system"
            assert messages[0]["content"] == "system instructions"
            assert messages[1]["role"] == "user"
            assert messages[1]["content"] == "user prompt"

    def test_empty_system_prompt_default_sends_only_user(self):
        """Empty system_prompt (default) must not send a system message at all."""
        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", model="deepseek-chat"
        )
        client = LLMClient(config)
        with patch.object(
            client, "_call_with_retry", return_value=_mock_response("result")
        ) as mock_call:
            client.complete("user prompt")  # system_prompt defaults to ""
            messages = mock_call.call_args[0][0]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            assert messages[0]["content"] == "user prompt"

    @pytest.mark.parametrize("system_prompt", ["", "   "])
    def test_falsy_system_prompt_no_system_message(self, system_prompt):
        """Regression: falsy system_prompt values must not produce system-role message."""
        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", model="deepseek-chat"
        )
        client = LLMClient(config)
        with patch.object(
            client, "_call_with_retry", return_value=_mock_response("result")
        ) as mock_call:
            # Empty string is default; whitespace-only should also not trigger system
            prompt = system_prompt if system_prompt else ""
            client.complete("hello", prompt)
            messages = mock_call.call_args[0][0]
            roles = [m["role"] for m in messages]
            assert "system" not in roles, (
                f"system_prompt={system_prompt!r} produced system role"
            )


# ── _call_with_retry ──────────────────────────────────────────────


class TestCallWithRetry:
    """Verify retry behavior for rate limits and server errors."""

    @staticmethod
    def _mock_response(status_code: int) -> MagicMock:
        """Create a mock httpx.Response with the given status_code."""
        resp = MagicMock()
        resp.status_code = status_code
        return resp

    def test_retries_on_rate_limit_error(self):
        """Should retry up to max_retries times on RateLimitError."""
        from openai import RateLimitError

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", max_retries=3
        )
        client = LLMClient(config)
        client._openai_client = MagicMock()
        client._openai_client.chat.completions.create = MagicMock(
            side_effect=RateLimitError(
                "rate limited",
                response=self._mock_response(429),
                body=None,
            )
        )
        with patch("time.sleep", return_value=None):
            with pytest.raises(RateLimitError):
                client._call_with_retry([{"role": "user", "content": "test"}])
        assert client._openai_client.chat.completions.create.call_count == 3

    def test_no_retry_on_client_error(self):
        """Should not retry on non-5xx error (e.g., 400 Bad Request)."""
        from openai import BadRequestError

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", max_retries=3
        )
        client = LLMClient(config)
        client._openai_client = MagicMock()
        client._openai_client.chat.completions.create = MagicMock(
            side_effect=BadRequestError(
                "bad request",
                response=self._mock_response(400),
                body=None,
            )
        )
        with pytest.raises(BadRequestError):
            client._call_with_retry([{"role": "user", "content": "test"}])
        assert client._openai_client.chat.completions.create.call_count == 1

    def test_retries_on_server_error(self):
        """Should retry on 5xx error (e.g., 503 Service Unavailable)."""
        from openai import InternalServerError

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", max_retries=2
        )
        client = LLMClient(config)
        client._openai_client = MagicMock()
        client._openai_client.chat.completions.create = MagicMock(
            side_effect=InternalServerError(
                "server error",
                response=self._mock_response(503),
                body=None,
            )
        )
        with patch("time.sleep", return_value=None):
            with pytest.raises(InternalServerError):
                client._call_with_retry([{"role": "user", "content": "test"}])
        assert client._openai_client.chat.completions.create.call_count == 2

    def test_retry_exponential_backoff(self):
        """Verify exponential backoff: 2^0=1s, 2^1=2s, 2^2=4s."""
        from openai import RateLimitError

        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", max_retries=3
        )
        client = LLMClient(config)
        client._openai_client = MagicMock()
        client._openai_client.chat.completions.create = MagicMock(
            side_effect=RateLimitError(
                "rate limited",
                response=self._mock_response(429),
                body=None,
            )
        )
        sleep_times: list[float] = []
        with patch("time.sleep", side_effect=sleep_times.append):
            with pytest.raises(RateLimitError):
                client._call_with_retry([{"role": "user", "content": "test"}])
        assert sleep_times == [1, 2, 4]


# ── Caching ────────────────────────────────────────────────────────


class TestCache:
    def test_cache_hit_returns_cached_result(self):
        """Same prompt + system_prompt should return cached result."""
        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", model="deepseek-chat"
        )
        client = LLMClient(config)
        with patch.object(
            client, "_call_with_retry", return_value=_mock_response("cached")
        ) as mock_call:
            result1 = client.complete("hello", "system")
            result2 = client.complete("hello", "system")
        assert result1 == "cached"
        assert result2 == "cached"
        # _call_with_retry should only be called once (second call hits cache)
        assert mock_call.call_count == 1


# ── Provider detection coverage ──────────────────────────────────


class TestProviderBranchCoverage:
    """Verify the DeepSeek branch covers intermediate methods too."""

    def test_batch_complete_uses_same_message_construction(self):
        """batch_complete calls complete() which should handle DeepSeek correctly."""
        config = LLMConfig(
            provider=LLMProvider.DEEPSEEK, api_key="test", model="deepseek-chat"
        )
        client = LLMClient(config)
        with patch.object(
            client, "_call_with_retry", return_value=_mock_response("ok")
        ) as mock_call:
            results = client.batch_complete(["p1", "p2"], "system prompt")
        assert results == ["ok", "ok"]
        # Verify each call merged system prompt
        for call_args in mock_call.call_args_list:
            messages = call_args[0][0]
            assert len(messages) == 1
            assert messages[0]["role"] == "user"
            assert "system prompt" in messages[0]["content"]
