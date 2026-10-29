"""Provider contract and validated local-inference configuration."""
import os
import math
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from .models import ValidationError


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, uncertain: bool = False):
        super().__init__(message)
        self.uncertain = uncertain


@dataclass(frozen=True)
class AIConfig:
    endpoint: str = "http://127.0.0.1:11434"
    model: str = "qwen3.5:2b-q4_K_M"
    timeout: float = 90
    context: int = 4096
    max_output: int = 1024
    provider: str = "ollama"

    def __post_init__(self):
        url = urlsplit(self.endpoint)
        if url.scheme != "http" or url.hostname not in ("127.0.0.1", "localhost", "::1") or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
            raise ValidationError("AI endpoint must be a plain loopback HTTP origin")
        if self.provider != "ollama" or not self.model.strip() or len(self.model) > 120:
            raise ValidationError("Configure an Ollama model name")
        if not math.isfinite(self.timeout) or not 0 < self.timeout <= 300 or not 2048 <= self.context <= 8192 or not 128 <= self.max_output <= self.context // 2:
            raise ValidationError("Invalid AI timeout/context/output limits")

    @classmethod
    def load(cls):
        try:
            return cls(endpoint=os.getenv("ORION_AI_ENDPOINT", cls.endpoint), model=os.getenv("ORION_AI_MODEL", cls.model),
                timeout=float(os.getenv("ORION_AI_TIMEOUT", "90")), context=int(os.getenv("ORION_AI_CONTEXT", "4096")),
                max_output=int(os.getenv("ORION_AI_MAX_OUTPUT", "1024")), provider=os.getenv("ORION_AI_PROVIDER", "ollama"))
        except ValueError as exc:
            raise ValidationError("Invalid numeric AI configuration") from exc


@dataclass(frozen=True)
class Response:
    content: str
    model: str
    provider: str
    elapsed_seconds: float


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
    raise ValidationError('Unsupported configured AI provider')
