"""Shared provider contract and credential-free, approval-bound configuration."""
import os
import math
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from .models import ValidationError


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool = False, code: str = 'provider_error',
                 status: int | None = None, retry_after: int | None = None):
        super().__init__(message)
        self.uncertain = uncertain
        self.code, self.status, self.retry_after = code, status, retry_after


GROQ_ENDPOINT = 'https://api.groq.com/openai/v1/chat/completions'


@dataclass(frozen=True)
class AIConfig:
    endpoint: str = "http://127.0.0.1:11434"
    model: str = "qwen3.5:2b-q4_K_M"
    timeout: float = 90
    context: int = 4096
    max_output: int = 1024
    provider: str = "ollama"
    temperature: float = 0.2

    def __post_init__(self):
        url = urlsplit(self.endpoint)
        if self.provider == 'groq':
            if self.endpoint != GROQ_ENDPOINT:
                raise ValidationError('Groq requires the fixed verified HTTPS endpoint')
        elif self.provider != 'ollama':
            raise ValidationError('Unsupported configured AI provider')
        elif url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1") or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
            raise ValidationError("AI endpoint must be a plain loopback HTTP origin")
        if not self.model.strip() or len(self.model) > 120 or any(ord(c)<33 or ord(c)>126 for c in self.model):
            raise ValidationError("Configure an explicit valid model identifier")
        if type(self.temperature) not in (int,float) or not math.isfinite(self.temperature) or not 0<=self.temperature<=2:
            raise ValidationError('Invalid generation temperature')
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 300 or not 2048 <= self.context <= 8192 or not 128 <= self.max_output <= self.context // 2:
            raise ValidationError("Invalid AI timeout/context/output limits")

    @classmethod
    def load(cls):
        try:
            provider=os.getenv('ORION_AI_PROVIDER',cls.provider)
            model=os.getenv('ORION_AI_MODEL', '' if provider=='groq' else cls.model)
            return cls(endpoint=os.getenv("ORION_AI_ENDPOINT", GROQ_ENDPOINT if provider=='groq' else cls.endpoint), model=model,
                timeout=float(os.getenv("ORION_AI_TIMEOUT", "90")), context=int(os.getenv("ORION_AI_CONTEXT", "4096")),
                max_output=int(os.getenv("ORION_AI_MAX_OUTPUT", "1024")), provider=provider,
                temperature=float(os.getenv('ORION_AI_TEMPERATURE','0.2')))
        except ValueError as exc:
            raise ValidationError("Invalid numeric AI configuration") from exc


@dataclass(frozen=True)
class Response:
    content: str
    model: str
    provider: str
    elapsed_seconds: float
    usage: dict | None = None
    prompt_eval_count: int | None = None
    eval_count: int | None = None
    load_duration: int | None = None
    eval_duration: int | None = None
    total_duration: int | None = None


class Provider(Protocol):
    config: AIConfig
    def availability(self) -> dict: ...
    def chat(self, messages: list[dict], schema: dict | None = None) -> Response: ...


def create_provider(config: AIConfig | None = None) -> Provider:
    """One production factory shared by chat and synthesis. No fake fallback."""
    config = config or AIConfig.load()
    if config.provider == 'ollama':
        from .ollama import OllamaProvider
        return OllamaProvider(config)
    if config.provider == 'groq':
        from .groq import GroqProvider
        return GroqProvider(config)
    raise ValidationError('Unsupported configured AI provider')
