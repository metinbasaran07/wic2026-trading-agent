"""LLM client with multi-provider support."""

from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, AsyncGenerator

from openai import AsyncOpenAI
from pydantic import BaseModel
from loguru import logger

from src.config.settings import get_settings

if TYPE_CHECKING:
    from anthropic import AsyncAnthropic
    from google.generativeai import GenerativeModel


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    content: str
    model: str
    usage: dict[str, int] | None = None
    raw_response: Any = None


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        pass

    @property
    @abstractmethod
    def model_name(self) -> str:
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass


class OpenRouterProvider(LLMProvider):
    """OpenRouter API provider."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        model: str = "anthropic/claude-3.5-sonnet",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "openrouter"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            extra_headers = {
                "HTTP-Referer": "https://github.com/wic2026/trading-agent",
                "X-Title": "WIC 2026 Trading Agent",
            }

            response = await self.client.chat.completions.create(**kwargs, extra_headers=extra_headers)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"OpenRouter completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
                extra_headers={
                    "HTTP-Referer": "https://github.com/wic2026/trading-agent",
                    "X-Title": "WIC 2026 Trading Agent",
                },
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenRouter streaming error: {e}")
            raise


class AnthropicProvider(LLMProvider):
    """Anthropic (Claude) direct API provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-sonnet-20241022",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        # Lazy import to avoid dependency if not used
        from anthropic import AsyncAnthropic
        self.client = AsyncAnthropic(api_key=api_key)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "anthropic"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            # Convert messages to Anthropic format
            system_msg = ""
            user_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    user_messages.append(msg)

            kwargs = {
                "model": self._model,
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if system_msg:
                kwargs["system"] = system_msg

            # Add JSON mode if requested
            if response_format and response_format.get("type") == "json_object":
                # Anthropic doesn't have native JSON mode, we prompt for it
                pass

            response = await self.client.messages.create(**kwargs)

            content = response.content[0].text if response.content else ""

            return LLMResponse(
                content=content,
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.input_tokens if response.usage else 0,
                    "completion_tokens": response.usage.output_tokens if response.usage else 0,
                    "total_tokens": (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"Anthropic completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            system_msg = ""
            user_messages = []
            for msg in messages:
                if msg["role"] == "system":
                    system_msg = msg["content"]
                else:
                    user_messages.append(msg)

            kwargs = {
                "model": self._model,
                "messages": user_messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "stream": True,
            }
            if system_msg:
                kwargs["system"] = system_msg

            stream = await self.client.messages.create(**kwargs)
            async for chunk in stream:
                if chunk.type == "content_block_delta" and chunk.delta.text:
                    yield chunk.delta.text
        except Exception as e:
            logger.error(f"Anthropic streaming error: {e}")
            raise


class OpenAIProvider(LLMProvider):
    """OpenAI direct API provider."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "openai"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"OpenAI completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"OpenAI streaming error: {e}")
            raise


class AzureOpenAIProvider(LLMProvider):
    """Azure OpenAI provider."""

    def __init__(
        self,
        api_key: str,
        endpoint: str,
        api_version: str = "2024-02-15-preview",
        deployment: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        from openai import AsyncAzureOpenAI
        self.client = AsyncAzureOpenAI(
            api_key=api_key,
            azure_endpoint=endpoint,
            api_version=api_version,
        )
        self._deployment = deployment
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "azure"

    @property
    def model_name(self) -> str:
        return self._deployment

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            kwargs = {
                "model": self._deployment,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"Azure OpenAI completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model=self._deployment,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Azure OpenAI streaming error: {e}")
            raise


class GeminiProvider(LLMProvider):
    """Google Gemini provider."""

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-1.5-pro",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(model)
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "gemini"

    @property
    def model_name(self) -> str:
        return self._model._model_name

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            # Convert to Gemini format
            history = []
            system_instruction = None
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                else:
                    history.append({"role": msg["role"], "parts": [msg["content"]]})

            chat = self._model.start_chat(history=history[:-1] if history else [])
            last_msg = history[-1]["parts"][0] if history else ""

            generation_config = {
                "temperature": temperature,
                "max_output_tokens": max_tokens,
            }
            if response_format and response_format.get("type") == "json_object":
                generation_config["response_mime_type"] = "application/json"

            if system_instruction:
                response = await chat.send_message_async(
                    last_msg,
                    generation_config=generation_config,
                    system_instruction=system_instruction,
                )
            else:
                response = await chat.send_message_async(
                    last_msg,
                    generation_config=generation_config,
                )

            content = response.text if response.text else ""

            return LLMResponse(
                content=content,
                model=self._model._model_name,
                usage={
                    "prompt_tokens": 0,  # Not provided by Gemini
                    "completion_tokens": 0,
                    "total_tokens": 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"Gemini completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            history = []
            system_instruction = None
            for msg in messages:
                if msg["role"] == "system":
                    system_instruction = msg["content"]
                else:
                    history.append({"role": msg["role"], "parts": [msg["content"]]})

            chat = self._model.start_chat(history=history[:-1] if history else [])
            last_msg = history[-1]["parts"][0] if history else ""

            generation_config = {"temperature": temperature, "max_output_tokens": max_tokens}

            if system_instruction:
                stream = await chat.send_message_async(
                    last_msg,
                    generation_config=generation_config,
                    system_instruction=system_instruction,
                    stream=True,
                )
            else:
                stream = await chat.send_message_async(
                    last_msg,
                    generation_config=generation_config,
                    stream=True,
                )

            async for chunk in stream:
                if chunk.text:
                    yield chunk.text
        except Exception as e:
            logger.error(f"Gemini streaming error: {e}")
            raise


class OllamaProvider(LLMProvider):
    """Ollama (local) provider - uses OpenAI-compatible API."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434/v1",
        model: str = "llama3.1:70b",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.client = AsyncOpenAI(api_key="ollama", base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "ollama"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"Ollama completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Ollama streaming error: {e}")
            raise


class NVIDIAProvider(LLMProvider):
    """NVIDIA Nemotron provider - uses OpenAI-compatible API."""

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        model: str = "nvidia/nemotron-3-ultra",
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "nvidia"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"NVIDIA completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"NVIDIA streaming error: {e}")
            raise


class TeamKeyProvider(LLMProvider):
    """Competition Team Key provider."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> None:
        self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._model = model
        self._max_tokens = max_tokens
        self._temperature = temperature
        self._provider = "team_key"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        try:
            kwargs = {
                "model": self._model,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
            if response_format:
                kwargs["response_format"] = response_format

            response = await self.client.chat.completions.create(**kwargs)

            return LLMResponse(
                content=response.choices[0].message.content or "",
                model=response.model,
                usage={
                    "prompt_tokens": response.usage.prompt_tokens if response.usage else 0,
                    "completion_tokens": response.usage.completion_tokens if response.usage else 0,
                    "total_tokens": response.usage.total_tokens if response.usage else 0,
                },
                raw_response=response,
            )
        except Exception as e:
            logger.error(f"Team Key completion error: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        try:
            stream = await self.client.chat.completions.create(
                model=self._model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content
        except Exception as e:
            logger.error(f"Team Key streaming error: {e}")
            raise


class MockProvider(LLMProvider):
    """Mock provider for testing."""

    def __init__(self, model: str = "mock") -> None:
        self._model = model
        self._provider = "mock"

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def provider_name(self) -> str:
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        mock_content = json.dumps({
            "analysis": "Mock analysis for testing",
            "recommendation": "hold",
            "confidence": 0.5,
            "reasoning": "This is a mock response for testing purposes",
        })
        return LLMResponse(
            content=mock_content,
            model=self._model,
            usage={"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
        )

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        yield "Mock streaming response"


class LLMClient:
    """Unified LLM client with provider switching."""

    def __init__(self) -> None:
        self.settings = get_settings()
        self._provider: LLMProvider | None = None
        self._init_provider()

    def _init_provider(self) -> None:
        """Initialize the appropriate provider based on settings."""
        config = self.settings.get_llm_config()
        provider = config.get("provider", "mock")

        try:
            if provider == "openrouter":
                self._provider = OpenRouterProvider(
                    api_key=config["api_key"],
                    base_url=config.get("base_url", "https://openrouter.ai/api/v1"),
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "anthropic":
                self._provider = AnthropicProvider(
                    api_key=config["api_key"],
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "openai":
                self._provider = OpenAIProvider(
                    api_key=config["api_key"],
                    base_url=config.get("base_url", "https://api.openai.com/v1"),
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "azure":
                self._provider = AzureOpenAIProvider(
                    api_key=config["api_key"],
                    endpoint=config["endpoint"],
                    api_version=config.get("api_version", "2024-02-15-preview"),
                    deployment=config["deployment"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "gemini":
                self._provider = GeminiProvider(
                    api_key=config["api_key"],
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "ollama":
                self._provider = OllamaProvider(
                    base_url=config.get("base_url", "http://localhost:11434/v1"),
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "nvidia":
                self._provider = NVIDIAProvider(
                    api_key=config["api_key"],
                    base_url=config.get("base_url", "https://integrate.api.nvidia.com/v1"),
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            elif provider == "team_key":
                self._provider = TeamKeyProvider(
                    api_key=config["api_key"],
                    base_url=config["base_url"],
                    model=config["model"],
                    max_tokens=config.get("max_tokens", 4096),
                    temperature=config.get("temperature", 0.1),
                )
            else:
                logger.warning(f"Unknown provider '{provider}', using mock")
                self._provider = MockProvider()
        except Exception as e:
            logger.error(f"Failed to initialize LLM provider: {e}")
            self._provider = MockProvider()

        logger.info(f"LLM Provider initialized: {self._provider.provider_name} ({self._provider.model_name})")

    def switch_provider(self, provider: str) -> None:
        self.settings.LLM_PROVIDER = provider  # type: ignore
        self._init_provider()

    @property
    def provider(self) -> LLMProvider:
        if self._provider is None:
            self._init_provider()
        return self._provider

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        response_format: dict | None = None,
    ) -> LLMResponse:
        return await self.provider.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    async def structured_completion(
        self,
        messages: list[dict[str, str]],
        response_model: type[BaseModel],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> BaseModel:
        schema = response_model.model_json_schema()
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": response_model.__name__, "schema": schema, "strict": True},
        }
        response = await self.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )
        try:
            data = json.loads(response.content)
            return response_model(**data)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse structured response: {e}")
            logger.error(f"Raw content: {response.content}")
            raise
        except Exception as e:
            logger.error(f"Failed to validate structured response: {e}")
            raise

    async def stream_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        async for chunk in self.provider.stream_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        ):
            yield chunk

    def get_provider_info(self) -> dict[str, str]:
        return {"provider": self.provider.provider_name, "model": self.provider.model_name}


_llm_client: LLMClient | None = None


def get_llm_client() -> LLMClient:
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client