"""Bounded, local HTTP adapter. No tools, redirects, proxies or fake fallback."""
import http.client
import json
import socket
import time
from urllib.parse import urlsplit
from .provider import AIConfig, ProviderError, Response


class OllamaProvider:
    def __init__(self, config: AIConfig):
        self.config = config

    def _request(self, path: str, payload=None, *, timeout=None):
        url = urlsplit(self.config.endpoint)
        seconds = self.config.timeout if timeout is None else timeout
        connection = http.client.HTTPConnection(url.hostname, url.port or 80, timeout=seconds)
        deadline = time.monotonic() + seconds
        try:
            connection.request("GET" if payload is None else "POST", path,
                body=None if payload is None else json.dumps(payload).encode(), headers={"Content-Type":"application/json"})
            reply = connection.getresponse()
            if reply.status != 200:
                raise ProviderError(f"Ollama returned HTTP {reply.status}; inspect its local service/model configuration")
            chunks, size = [], 0
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0: raise TimeoutError
                if connection.sock is not None: connection.sock.settimeout(remaining)
                chunk = reply.read1(8192)
                if not chunk: break
                size += len(chunk)
                if size > 131072: raise ProviderError("Ollama response exceeded 128 KiB", uncertain=payload is not None)
                chunks.append(chunk)
            result = json.loads(b"".join(chunks))
            if not isinstance(result, dict): raise ValueError
            return result
        except ProviderError:
            raise
        except (TimeoutError, socket.timeout):
            raise ProviderError("Ollama timed out; request outcome is uncertain. Stop/restart Ollama before resetting the inference claim.", uncertain=payload is not None) from None
        except ConnectionRefusedError:
            raise ProviderError("Ollama is unavailable. Install/start Ollama and install the configured model; no AI response was generated.") from None
        except (OSError, http.client.HTTPException):
            raise ProviderError("Ollama connection failed; check the local service.", uncertain=payload is not None) from None
        except (ValueError, UnicodeError):
            raise ProviderError("Ollama returned malformed JSON", uncertain=payload is not None) from None
        finally:
            connection.close()

    def availability(self) -> dict:
        try:
            result = self._request("/api/tags", timeout=min(3, self.config.timeout))
            models = result.get("models")
            if not isinstance(models, list): raise ProviderError("Malformed Ollama model listing")
            found = next((m for m in models if isinstance(m, dict) and m.get("name") == self.config.model), None)
            return {"available": found is not None, "service_available": True, "provider":"ollama", "model":self.config.model,
                    "details": found.get("details", {}) if found else {}, "size":found.get("size") if found else None,
                    "message":"Model ready" if found else "Configured model is not installed; run ollama pull for this exact tag"}
        except ProviderError as exc:
            return {"available":False,"service_available":False,"provider":"ollama","model":self.config.model,"message":str(exc)}

    def chat(self, messages: list[dict], schema: dict | None = None) -> Response:
        state = self.availability()
        if not state["available"]: raise ProviderError(state["message"])
        payload = {"model":self.config.model,"messages":messages,"stream":False,"think":False,"keep_alive":0,
            "options":{"num_ctx":self.config.context,"num_predict":self.config.max_output,"temperature":0.2}}
        if schema is not None: payload["format"] = schema
        start = time.monotonic()
        response = self._request("/api/chat", payload)
        message = response.get("message", {})
        if response.get("done") is not True or not isinstance(message,dict) or message.get("role") != "assistant" or not isinstance(message.get("content"),str) or not message["content"].strip() or len(message["content"]) > 16000 or message.get("tool_calls"):
            raise ProviderError("Ollama returned an incomplete or unsupported assistant response")
        if not isinstance(response.get("model"),str): raise ProviderError("Ollama response omitted model identity")
        return Response(message["content"], response["model"], "ollama", round(time.monotonic()-start,3))
