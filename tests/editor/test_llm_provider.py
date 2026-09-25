"""Tests for AEGIS-1401: LLM Provider Detection & Configuration."""

from __future__ import annotations

import json
from unittest.mock import patch

from aegis.editor.llm_provider import (
    LLMProviderInfo,
    ModelInfo,
    _anthropic_to_openai_format,
    _probe_models,
    detect_local_providers,
    get_all_providers,
    get_remote_providers,
)


class TestModelInfo:
    def test_to_dict(self) -> None:
        m = ModelInfo(id="gpt-4o", name="GPT-4o", context_length=128000)
        d = m.to_dict()
        assert d["id"] == "gpt-4o"
        assert d["contextLength"] == 128000


class TestLLMProviderInfo:
    def test_to_dict_available(self) -> None:
        p = LLMProviderInfo(
            id="test",
            name="Test",
            type="local",
            base_url="http://localhost:1234/v1",
            available=True,
            models=[ModelInfo(id="m1", name="Model 1")],
        )
        d = p.to_dict()
        assert d["available"] is True
        assert len(d["models"]) == 1
        assert "error" not in d

    def test_to_dict_with_error(self) -> None:
        p = LLMProviderInfo(
            id="test",
            name="Test",
            type="local",
            base_url="http://localhost:9999/v1",
            error="Connection refused",
        )
        d = p.to_dict()
        assert d["available"] is False
        assert d["error"] == "Connection refused"


class TestDetectLocalProviders:
    def test_all_unavailable_by_default(self) -> None:
        """Without running servers, all local providers are unavailable."""
        providers = detect_local_providers()
        assert len(providers) == 3
        for p in providers:
            assert p.type == "local"
            # Providers should not be available when no server is running
            # (probes will fail with ConnectionRefused)

    def test_provider_ids(self) -> None:
        providers = detect_local_providers()
        ids = {p.id for p in providers}
        assert ids == {"lm-studio", "ollama", "vllm"}


class TestGetRemoteProviders:
    def test_no_keys_set(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            providers = get_remote_providers()
            assert len(providers) == 0

    def test_anthropic_key_set(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
            providers = get_remote_providers()
            anthropic = [p for p in providers if p.id == "anthropic"]
            assert len(anthropic) == 1
            assert anthropic[0].available is True
            assert len(anthropic[0].models) >= 1

    def test_openai_key_set(self) -> None:
        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
            providers = get_remote_providers()
            openai = [p for p in providers if p.id == "openai"]
            assert len(openai) == 1
            assert openai[0].available is True

    def test_both_keys_set(self) -> None:
        with patch.dict("os.environ", {
            "ANTHROPIC_API_KEY": "ak",
            "OPENAI_API_KEY": "ok",
        }):
            providers = get_remote_providers()
            assert len(providers) == 2


class TestGetAllProviders:
    def test_includes_local_and_remote(self) -> None:
        with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test"}):
            providers = get_all_providers()
            local = [p for p in providers if p.type == "local"]
            remote = [p for p in providers if p.type == "remote"]
            assert len(local) == 3
            assert len(remote) >= 1


class TestAnthropicToOpenAIFormat:
    def test_text_response(self) -> None:
        raw = {
            "content": [
                {"type": "text", "text": "Hello world"},
            ],
        }
        result = _anthropic_to_openai_format(raw)
        msg = result["choices"][0]["message"]
        assert msg["role"] == "assistant"
        assert msg["content"] == "Hello world"
        assert "tool_calls" not in msg

    def test_tool_use_response(self) -> None:
        raw = {
            "content": [
                {"type": "text", "text": "I'll propose a rule."},
                {
                    "type": "tool_use",
                    "id": "tc_123",
                    "name": "propose_rule",
                    "input": {"modality": "FORBIDDEN", "agent_role": "analyst"},
                },
            ],
        }
        result = _anthropic_to_openai_format(raw)
        msg = result["choices"][0]["message"]
        assert len(msg["tool_calls"]) == 1
        tc = msg["tool_calls"][0]
        assert tc["function"]["name"] == "propose_rule"
        args = json.loads(tc["function"]["arguments"])
        assert args["modality"] == "FORBIDDEN"


class TestProbeModels:
    def test_unreachable_returns_empty(self) -> None:
        models = _probe_models("http://localhost:19999/v1")
        assert models == []
