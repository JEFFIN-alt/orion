"""Provider-driven analysis; no fixture fallback or model-specific business logic."""
from dataclasses import asdict
from .provider import AIConfig,Provider,ProviderError,create_provider
from .synthesis import messages
from .synthesis_schema import SCHEMA
from .service import timestamp
from .research import canonical
from .models import ValidationError

def synthesize(snapshot,provider: Provider | None=None):
    operation=snapshot['synthesis']
    configured=AIConfig(**operation['model'])
    provider=provider if provider is not None else create_provider(configured)
    result={'schema_version':1,'kind':'research_synthesis','execution_id':snapshot['execution_id'],
        'source_execution':operation['source_execution'],'evidence_digest':operation['evidence_digest'],
        'worker_version':'1','created_at':timestamp(),'configured_model':operation['model'],
        'response_metadata':None,'response_text':'','provider_error':None,'inference_uncertain':False}
    try:
        response=provider.chat(messages(operation,snapshot['execution_id']),SCHEMA)
        if not isinstance(response.content,str): raise ProviderError('Provider returned non-text analysis')
        if len(response.content.encode())>operation['configuration']['max_response_bytes']:
            result['response_metadata']={'provider':response.provider,'model':response.model,'elapsed_seconds':response.elapsed_seconds}
            raise ProviderError('Provider analysis exceeded configured output bytes')
        result.update(response_text=response.content,response_metadata={'provider':response.provider,'model':response.model,'elapsed_seconds':response.elapsed_seconds})
    except ProviderError as exc:
        result.update(provider_error=str(exc)[:1200],inference_uncertain=exc.uncertain)
    except Exception:
        # Unknown provider failures may leave a request active on the server.
        result.update(provider_error='Provider failed unexpectedly; inspect service before resetting inference',inference_uncertain=True)
    return result

def validate_envelope(snapshot,output):
    # Invalid model JSON is deliberately saved for independent verification and diagnosis.
    if not isinstance(output,dict) or output.get('execution_id')!=snapshot['execution_id'] or output.get('source_execution')!=snapshot['synthesis']['source_execution']:
        raise ValidationError('Synthesis envelope binding mismatch')
    if len(canonical(output).encode())>131072: raise ValidationError('Synthesis envelope exceeds size limit')
