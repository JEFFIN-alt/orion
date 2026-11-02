"""One bounded HTTPS request to Groq. Credentials exist only in the request header."""
import http.client
import json
import math
import os
import ssl
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

from .provider import AIConfig, ProviderError, Response
from .research import strict_json


# Documentation-reviewed 2026-10-31. Capability does not imply account entitlement.
STRICT_MODELS = frozenset({'openai/gpt-oss-20b', 'openai/gpt-oss-120b',
                          'qwen/qwen3.8-27b', 'meta-models/muse-spark-open'})


def retry_seconds(value):
    """Parse Retry-After without persisting any arbitrary response header text."""
    if not isinstance(value, str) or len(value) > 100:
        return None
    try:
        if value.isascii() and value.isdecimal():
            return int(value)
        when = parsedate_to_datetime(value)
        return max(0, math.ceil((when-datetime.now(timezone.utc)).total_seconds()))
    except (ValueError, TypeError, OverflowError):
        return None


def require_schema(schema):
    """Check documented strict structural requirements without rewriting the schema."""
    if not isinstance(schema, dict) or schema.get('type') != 'object':
        raise ProviderError('Groq requires an object schema', code='unsupported_schema')
    def visit(node):
        if isinstance(node, dict):
            if node.get('type') == 'object':
                properties = node.get('properties', {})
                if node.get('additionalProperties') is not False or set(node.get('required', [])) != set(properties):
                    raise ProviderError('Groq strict schema requires closed objects and all fields required', code='unsupported_schema')
            for child in node.values():
                visit(child)
        elif isinstance(node, list):
            for child in node:
                visit(child)
    visit(schema)


class GroqProvider:
    def __init__(self, config: AIConfig):
        if config.provider != 'groq':
            raise ValueError('Groq provider configuration required')
        self.config = config

    def availability(self):
        # Configuration readiness only. No remote model listing or key validation.
        ready = bool(os.getenv('ORION_GROQ_API_KEY'))
        return {'available': ready, 'service_available': None, 'provider': 'groq',
                'model': self.config.model, 'message': 'Key configured; remote access unverified' if ready else 'ORION_GROQ_API_KEY is missing'}

    def chat(self, messages, schema=None):
        key = os.getenv('ORION_GROQ_API_KEY', '')
        if not key or len(key)>512 or any(not c.isascii() or not (c.isalnum() or c in '_-') for c in key):
            raise ProviderError('Groq API key is missing or invalid; configure ORION_GROQ_API_KEY', code='missing_key')
        if schema is not None:
            if self.config.model not in STRICT_MODELS:
                raise ProviderError('Configured Groq model lacks reviewed strict-schema support', code='unsupported_model')
            require_schema(schema)
        payload = {'model': self.config.model, 'messages': messages, 'stream': False,
                   'n': 1, 'temperature': self.config.temperature, 'max_completion_tokens': self.config.max_output}
        if schema is not None:
            payload['response_format'] = {'type': 'json_schema', 'json_schema':
                {'name': 'orion_analysis', 'strict': True, 'schema': schema}}
        body = json.dumps(payload, allow_nan=False).encode('utf-8')
        if len(body)>65536:
            raise ProviderError('Groq request exceeds 64 KiB', code='request_size')
        if key.encode() in body:
            raise ProviderError('Credential detected in request content', code='credential_exposure')
        connection = None
        start = time.monotonic()
        def remaining_timeout():
            remaining = self.config.timeout-(time.monotonic()-start)
            if remaining<=0:
                raise TimeoutError
            connection.timeout = remaining
            if connection.sock is not None:
                connection.sock.settimeout(remaining)
        try:
            connection = http.client.HTTPSConnection('api.groq.com', 443, timeout=self.config.timeout,
                                                      context=ssl.create_default_context())
            connection.connect()
            remaining_timeout()
            connection.request('POST', '/openai/v1/chat/completions', body=body,
                               headers={'Authorization': 'Bearer '+key, 'Content-Type': 'application/json'})
            remaining_timeout()
            reply = connection.getresponse()
            remaining_timeout()
            status = reply.status
            if status != 200:
                code = ('authentication' if status in (401,403) else 'rate_limit' if status==429
                        else 'server_failure' if 500<=status<=599 else 'unsupported_request' if status in (400,404,422)
                        else 'http_error')
                retry = retry_seconds(reply.getheader('Retry-After'))
                delay = f'; wait at least {retry} seconds before any separately authorized attempt' if retry is not None else ''
                raise ProviderError(f'Groq {code} (HTTP {status}){delay}; no automatic retry', code=code,
                                    status=status, retry_after=retry, uncertain=500<=status<=599)
            chunks = []
            size = 0
            while True:
                remaining_timeout()
                chunk = reply.read1(8192)
                remaining_timeout()
                if not chunk:
                    break
                size += len(chunk)
                if size>131072:
                    raise ProviderError('Groq response exceeds 128 KiB', code='response_size', uncertain=True)
                chunks.append(chunk)
            raw = b''.join(chunks)
            if key.encode() in raw:
                raise ProviderError('Groq response contains credential material; discarded', code='credential_exposure')
            result = strict_json(raw)
            if not isinstance(result, dict):
                raise ValueError
            choices = result.get('choices')
            if not isinstance(choices, list) or len(choices)!=1 or not isinstance(choices[0], dict):
                raise ValueError
            choice = choices[0]
            message = choice.get('message')
            if not isinstance(message, dict):
                raise ValueError
            if message.get('refusal') or choice.get('finish_reason')=='content_filter':
                raise ProviderError('Groq declined the request', code='refusal')
            if choice.get('finish_reason') != 'stop':
                raise ProviderError('Groq generation incomplete or unsupported finish reason', code='incomplete_response')
            content = message.get('content')
            if message.get('role')!='assistant' or message.get('tool_calls') or message.get('function_call'):
                raise ValueError
            if not isinstance(content,str) or not content.strip():
                raise ProviderError('Groq response has no generated content', code='missing_content')
            if key in content:
                raise ProviderError('Groq response contains credential material; discarded', code='credential_exposure')
            if len(content.encode('utf-8'))>16000:
                raise ProviderError('Groq generated content exceeds 16000 bytes', code='response_size')
            # Synthesis content is itself JSON and can contain a second escape layer.
            try:
                decoded_content = strict_json(content)
            except (ValueError, TypeError, RecursionError):
                decoded_content = None
            if key in json.dumps(decoded_content, ensure_ascii=False):
                raise ProviderError('Groq response contains credential material; discarded', code='credential_exposure')
            if result.get('model') != self.config.model:
                raise ProviderError('Groq response model does not match configured model', code='model_mismatch')
            usage = {}
            supplied = result.get('usage', {})
            if not isinstance(supplied, dict):
                raise ValueError
            for name in ('prompt_tokens','completion_tokens','total_tokens','queue_time','prompt_time','completion_time','total_time'):
                if name in supplied:
                    value = supplied[name]
                    if type(value) not in (int,float) or value<0 or value>10**12 or not math.isfinite(value):
                        raise ValueError
                    if name.endswith('_tokens') and type(value) is not int:
                        raise ValueError
                    usage[name] = value
            return Response(content, result['model'], 'groq', round(time.monotonic()-start,3), usage or None)
        except ProviderError:
            raise
        except TimeoutError:
            raise ProviderError('Groq request timed out; outcome uncertain', code='timeout', uncertain=True) from None
        except (OSError, http.client.HTTPException):
            raise ProviderError('Groq connection failed; outcome uncertain', code='connection_failure', uncertain=True) from None
        except (ValueError, TypeError, KeyError, RecursionError):
            raise ProviderError('Groq returned a malformed response', code='malformed_response') from None
        finally:
            if connection is not None:
                connection.close()
