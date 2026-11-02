"""Groq HTTP mocks and isolated engine fixtures. No hosted inference or network."""
import copy
import io
import json
import logging
import os
import ssl
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock, patch

import test_foundation
from test_research import PAPER, REPO
from test_synthesis import FixtureProvider
from orion.approvals import ApprovalService
from orion.execution import ExecutionService
from orion.groq import GroqProvider, retry_seconds
from orion.models import ValidationError
from orion.provider import AIConfig, GROQ_ENDPOINT, ProviderError, create_provider
from orion.research_sources import collect
from orion.service import timestamp
from orion.research import ResearchService
from orion.synthesis import SynthesisService, analysis_schema, messages
from orion.synthesis_schema import SCHEMA, parse_analysis, citations
from orion.synthesis_worker import synthesize
from orion.workers import REGISTRY

MODEL = 'openai/gpt-oss-20b'
# Deliberately synthetic credential. Never a real account/key.
SECRET = 'fixture-credential-for-offline-tests'
ENV = {'ORION_AI_PROVIDER':'groq','ORION_AI_ENDPOINT':GROQ_ENDPOINT,
       'ORION_AI_MODEL':MODEL,'ORION_GROQ_API_KEY':SECRET,
       'ORION_AI_CONTEXT':'4096','ORION_AI_MAX_OUTPUT':'1024',
       'ORION_AI_TIMEOUT':'30','ORION_AI_TEMPERATURE':'0.2'}


def config(**changes):
    return AIConfig(**({'provider':'groq', 'endpoint':GROQ_ENDPOINT, 'model':MODEL} | changes))


def completion(content='{}'):
    return {'model':MODEL,'choices':[{'finish_reason':'stop','message':{'role':'assistant','content':content}}],
            'usage':{'prompt_tokens':20,'completion_tokens':10,'total_tokens':30,'total_time':0.01}}


def transport(body=None, status=200, retry=None):
    connection = MagicMock()
    reply = connection.getresponse.return_value
    reply.status = status
    reply.getheader.return_value = retry
    raw = json.dumps(completion() if body is None else body).encode() if not isinstance(body,bytes) else body
    reply.read1.side_effect = [raw,b'']
    return connection


class GroqMockTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, ENV)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.connection = transport()
        self.http = patch('orion.groq.http.client.HTTPSConnection',return_value=self.connection)
        self.factory = self.http.start()
        self.addCleanup(self.http.stop)

    def test_production_factory_and_payload(self):
        provider = create_provider(AIConfig.load())
        schema = copy.deepcopy(SCHEMA)
        result = provider.chat([{'role':'user','content':'JSON only'}],schema)
        self.assertEqual((result.provider,result.model,result.content),('groq',MODEL,'{}'))
        self.assertEqual(result.usage['total_tokens'],30)
        self.assertGreaterEqual(result.elapsed_seconds,0)
        args,kwargs = self.connection.request.call_args
        self.assertEqual(args,('POST','/openai/v1/chat/completions'))
        body = json.loads(kwargs['body'])
        self.assertEqual(body['model'],MODEL)
        self.assertEqual(body['max_completion_tokens'],1024)
        self.assertEqual(body['temperature'],0.2)
        self.assertFalse(body['stream'])
        self.assertEqual(body['n'],1)
        self.assertEqual(body['response_format']['json_schema'],{'name':'orion_analysis','strict':True,'schema':schema})
        self.assertEqual(schema,SCHEMA)
        self.assertNotIn(SECRET,kwargs['body'].decode())
        self.assertEqual(kwargs['headers']['Authorization'],'Bearer '+SECRET)
        args,kwargs = self.factory.call_args
        self.assertEqual(args,('api.groq.com',443))
        self.assertEqual(kwargs['context'].verify_mode,ssl.CERT_REQUIRED)
        self.assertTrue(kwargs['context'].check_hostname)
        self.connection.request.assert_called_once()
        self.connection.close.assert_called_once()

    def assert_error(self,connection,code,uncertain=False):
        self.factory.return_value = connection
        with self.assertRaises(ProviderError) as raised:
            create_provider(AIConfig.load()).chat([],SCHEMA)
        self.assertEqual(raised.exception.code,code)
        self.assertEqual(raised.exception.uncertain,uncertain)
        self.assertNotIn(SECRET,str(raised.exception))
        connection.request.assert_called_once()
        connection.close.assert_called_once()
        return raised.exception

    def test_authentication(self):
        for status in (401,403):
            with self.subTest(status=status):
                self.assertEqual(self.assert_error(transport(status=status),'authentication').status,status)

    def test_rate_limit_and_retry_after(self):
        error=self.assert_error(transport(status=429,retry='42'),'rate_limit')
        self.assertEqual(error.retry_after,42)
        self.assertIn('42 seconds',str(error))
        self.assertIsNone(retry_seconds(SECRET))
        self.assertEqual(retry_seconds('172800'),172800)
        self.assertEqual(retry_seconds('Wed, 21 Oct 2015 07:28:00 GMT'),0)

    def test_server_and_request_errors(self):
        for status in (500,503):
            self.assert_error(transport(status=status),'server_failure',True)
        for status in (400,404,422):
            self.assert_error(transport(status=status),'unsupported_request')

    def test_redirect_rejected_without_following(self):
        self.assert_error(transport(status=302),'http_error')

    def test_timeout_and_connection_failure_sanitized(self):
        for exc,code in ((TimeoutError(SECRET),'timeout'),(OSError(SECRET),'connection_failure')):
            connection=transport()
            connection.getresponse.side_effect=exc
            self.assert_error(connection,code,True)

    def test_malformed_response(self):
        for body in (b'{broken',b'{"choices":[],"choices":[]}',[],{'choices':None},
                     completion() | {'usage':{'total_tokens':True}},
                     completion() | {'usage':{'total_tokens':10**400}}):
            with self.subTest(body=repr(body)):
                self.assert_error(transport(body),'malformed_response')

    def test_missing_content(self):
        for content in (None,'',' '):
            self.assert_error(transport(completion(content)),'missing_content')

    def test_refusal_and_incomplete_output(self):
        value=completion();value['choices'][0]['message']['refusal']='declined'
        self.assert_error(transport(value),'refusal')
        value=completion();value['choices'][0]['finish_reason']='length'
        self.assert_error(transport(value),'incomplete_response')

    def test_response_model_identity_and_tools(self):
        self.assert_error(transport(completion() | {'model':'other-model'}),'model_mismatch')
        value=completion();value['choices'][0]['message']['tool_calls']=[{'name':'forbidden'}]
        self.assert_error(transport(value),'malformed_response')

    def test_response_size_bounds(self):
        self.assert_error(transport(b'x'*131073),'response_size',True)
        self.assert_error(transport(completion('x'*16001)),'response_size')

    def test_missing_key_before_transport(self):
        with patch.dict(os.environ,{'ORION_GROQ_API_KEY':''}):
            with self.assertRaises(ProviderError) as raised:
                GroqProvider(config()).chat([],SCHEMA)
        self.assertEqual(raised.exception.code,'missing_key')
        self.factory.assert_not_called()

    def test_unsupported_model_and_open_schema_before_transport(self):
        for provider,schema,code in ((GroqProvider(config(model='invalid')),SCHEMA,'unsupported_model'),
                                     (GroqProvider(config()),{'type':'object','properties':{}},'unsupported_schema')):
            with self.assertRaises(ProviderError) as raised:
                provider.chat([],schema)
            self.assertEqual(raised.exception.code,code)
        self.factory.assert_not_called()

    def test_documented_three_models_send_strict_schema(self):
        for model in ('openai/gpt-oss-20b','openai/gpt-oss-120b','qwen/qwen3.8-27b'):
            with self.subTest(model=model):
                connection=transport(completion() | {'model':model})
                self.factory.return_value=connection
                self.assertEqual(GroqProvider(config(model=model)).chat([],SCHEMA).model,model)
                payload=json.loads(connection.request.call_args.kwargs['body'])
                self.assertEqual(payload['model'],model)
                self.assertTrue(payload['response_format']['json_schema']['strict'])
                self.assertEqual(payload['response_format']['json_schema']['schema'],SCHEMA)

    def test_best_effort_only_model_rejected_before_transport(self):
        with self.assertRaises(ProviderError) as raised:
            GroqProvider(config(model='openai/gpt-oss-safeguard-20b')).chat([],SCHEMA)
        self.assertEqual(raised.exception.code,'unsupported_model')
        self.factory.assert_not_called()

    def test_fixed_endpoint_explicit_model_and_no_remote_availability_call(self):
        for endpoint in ('http://api.groq.com/openai/v1/chat/completions',GROQ_ENDPOINT+'/',GROQ_ENDPOINT+'?secret=x','https://example.com'):
            with self.assertRaises(ValidationError):
                AIConfig(provider='groq',endpoint=endpoint,model=MODEL)
        with patch.dict(os.environ,{'ORION_AI_MODEL':''}),self.assertRaises(ValidationError):
            AIConfig.load()
        self.assertTrue(GroqProvider(config()).availability()['available'])
        self.factory.assert_not_called()

    def test_plain_chat_has_no_schema_and_ollama_factory_retained(self):
        GroqProvider(config()).chat([])
        self.assertNotIn('response_format',json.loads(self.connection.request.call_args.kwargs['body']))
        self.assertEqual(type(create_provider(AIConfig())).__name__,'OllamaProvider')

    def test_deadline_expires_without_sending_a_request(self):
        with patch('orion.groq.time.monotonic',side_effect=[0,1000]):
            with self.assertRaises(ProviderError) as raised:
                GroqProvider(config()).chat([],SCHEMA)
        self.assertEqual(raised.exception.code,'timeout')
        self.connection.request.assert_not_called()
        self.connection.close.assert_called_once()

    def test_expired_headers_or_final_body_read_cannot_return_success(self):
        for phase in ('headers','eof'):
            with self.subTest(phase=phase):
                clock=[0]
                connection=transport()
                connection.sock=None
                reply=connection.getresponse.return_value
                if phase=='headers':
                    def headers():
                        clock[0]=2
                        return reply
                    connection.getresponse.side_effect=headers
                else:
                    parts=[json.dumps(completion()).encode(),b'']
                    def read(_):
                        part=parts.pop(0)
                        if not part:
                            clock[0]=2
                        return part
                    reply.read1.side_effect=read
                self.factory.return_value=connection
                with patch('orion.groq.time.monotonic',side_effect=lambda:clock[0]):
                    with self.assertRaises(ProviderError) as raised:
                        GroqProvider(config(timeout=1)).chat([],SCHEMA)
                self.assertEqual(raised.exception.code,'timeout')
                self.assertTrue(raised.exception.uncertain)
                connection.close.assert_called_once()

    def test_json_escaped_credential_is_discarded_before_return(self):
        escaped=''.join('\\u%04x'%ord(c) for c in SECRET)
        raw=json.dumps(completion(SECRET)).replace(SECRET,escaped).encode()
        self.assertNotIn(SECRET.encode(),raw)
        self.assert_error(transport(raw),'credential_exposure')
        analysis=json.dumps({'summary':SECRET}).replace(SECRET,escaped)
        raw=json.dumps(completion(analysis)).encode()
        self.assertNotIn(SECRET.encode(),raw)
        self.assert_error(transport(raw),'credential_exposure')

    def test_key_in_prompt_rejected_before_connecting(self):
        with self.assertRaises(ProviderError) as raised:
            GroqProvider(config()).chat([{'role':'user','content':SECRET}],SCHEMA)
        self.assertEqual(raised.exception.code,'credential_exposure')
        self.factory.assert_not_called()

    def test_compact_schema_refs_bounds_and_enums_are_preserved(self):
        operation={'configuration':{'passages':[]},'evidence':{'sources':[{'source_id':'repository:fixture'}]}}
        schema=analysis_schema(operation)
        GroqProvider(config()).chat([],schema)
        sent=json.loads(self.connection.request.call_args.kwargs['body'])['response_format']['json_schema']['schema']
        self.assertEqual(sent,schema)
        self.assertEqual(sent['$defs']['refs']['items']['enum'],['repository:fixture'])
        self.assertTrue(sent['$defs']['refs']['uniqueItems'])
        self.assertEqual(sent['$defs']['text']['maxLength'],1200)

    def test_secret_redaction_in_errors_tracebacks_and_logs(self):
        stream=io.StringIO();handler=logging.StreamHandler(stream)
        logger=logging.getLogger('groq-fixture');logger.addHandler(handler)
        self.addCleanup(logger.removeHandler,handler)
        for connection in (transport(status=429,retry=SECRET),transport(completion(SECRET))):
            self.factory.return_value=connection
            try:
                GroqProvider(config()).chat([],SCHEMA)
            except ProviderError:
                logger.error('Provider failure',exc_info=True)
        connection=transport();connection.request.side_effect=OSError(SECRET)
        self.factory.return_value=connection
        try:
            GroqProvider(config()).chat([],SCHEMA)
        except ProviderError:
            logger.error('Provider failure',exc_info=True)
        self.assertNotIn(SECRET,stream.getvalue())


class CaptureClient:
    """Captured-shaped deterministic research HTTP substitute, without sockets."""
    def get(self,provider,url,kind='search'):
        body={'status':'ok','message':{'items':[PAPER]}} if provider=='crossref' else {'items':[REPO],'incomplete_results':False}
        return {'provider':provider,'kind':kind,'url':url,'retrieved_at':timestamp(),'status':'ok',
                'http_status':200,'body':json.dumps(body),'error':None}


def mock_collect(snapshot):
    return collect(snapshot,CaptureClient())


def mock_groq_synthesize(snapshot):
    """Production adapter inside a spawned worker with an explicit mock transport."""
    operation=snapshot['synthesis']
    fixture=FixtureProvider('unknown' if os.getenv('ORION_GROQ_TEST_BAD_CITATION') else 'valid')
    content=fixture.chat(messages(operation,snapshot['execution_id'])).content
    with patch('orion.groq.http.client.HTTPSConnection',return_value=transport(completion(content))):
        return synthesize(snapshot)


class GroqIntegrationTests(unittest.TestCase):
    def setUp(self):
        test_foundation.FoundationTests.setUp(self)
        env=patch.dict(os.environ,ENV);env.start();self.addCleanup(env.stop)
        task=self.service.create_task(self.project['id'],'Collect offline evidence')
        ResearchService(self.db).configure(task['id'],'Fixture research',include_readme=False)
        collector=ExecutionService(self.db,registry={'research-collect':replace(REGISTRY['research-collect'],handler=mock_collect)})
        self.source=collector.execute(task['id'],'research-collect')
        self.assertEqual(self.source['status'],'succeeded',self.source['error'])
        self.task=self.service.create_task(self.project['id'],'Offline Groq fixture')
        self.service_synthesis=SynthesisService(self.db)
        self.operation=self.service_synthesis.configure(self.task['id'],self.source['id'])
        self.approvals=ApprovalService(self.db)
        self.engine=ExecutionService(self.db,registry={'research-synthesize':replace(REGISTRY['research-synthesize'],handler=mock_groq_synthesize)})

    def test_key_rotation_excluded_from_database_and_fingerprint(self):
        request=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
        with patch.dict(os.environ,{'ORION_GROQ_API_KEY':'different-fixture-credential'}):
            other=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
        self.assertEqual(request['fingerprint'],other['fingerprint'])
        self.assertNotIn(SECRET,self.db.path.read_bytes().decode('latin1'))
        self.assertNotIn('different-fixture-credential',self.db.path.read_bytes().decode('latin1'))
        model=json.loads(request['proposal_json'])['synthesis']['model']
        self.assertEqual(model['endpoint'],GROQ_ENDPOINT)
        self.assertEqual(model['temperature'],0.2)
        self.assertEqual(model['provider'],'groq')
        for changes in ({'ORION_AI_MODEL':'openai/gpt-oss-120b'}, {'ORION_AI_MAX_OUTPUT':'1536'},
                        {'ORION_AI_CONTEXT':'8192'},{'ORION_AI_TIMEOUT':'20'},{'ORION_AI_TEMPERATURE':'0.4'},
                        {'ORION_AI_PROVIDER':'ollama','ORION_AI_ENDPOINT':'http://127.0.0.1:11434',
                         'ORION_AI_MODEL':'qwen3.5:2b-q4_K_M'}):
            with patch.dict(os.environ,changes):
                changed=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
            self.assertNotEqual(request['fingerprint'],changed['fingerprint'])

    def test_approval_required_and_stale_approval_rejected(self):
        with self.assertRaises(ValidationError):
            self.engine.execute(self.task['id'],'research-synthesize')
        request=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
        self.approvals.decide(request['id'],'approved','Fixture approval')
        with patch.dict(os.environ,{'ORION_AI_TEMPERATURE':'0.4'}),self.assertRaises(ValidationError):
            self.engine.execute(self.task['id'],'research-synthesize')

    def test_mock_synthesis_existing_verifier_and_usage_event(self):
        request=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
        self.approvals.decide(request['id'],'approved','Fixture approval')
        run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['status'],'succeeded',run['error'])
        self.assertEqual(run['latest_verification']['status'],'passed')
        packet=json.loads(Path(run['result']['artifact']).read_text(encoding='utf-8'))
        self.assertNotIn('provider_usage',packet)
        self.assertEqual(set(packet['response_metadata']),{'provider','model','elapsed_seconds'})
        analysis=parse_analysis(packet['response_text'],run['id'],self.operation['evidence']['question'],16000)
        citations(analysis,self.operation['evidence']['sources'])
        events=self.engine.events()
        metrics=next(e for e in events if e['type']=='synthesis_provider_usage')
        self.assertEqual(json.loads(metrics['details_json'])['total_tokens'],30)
        self.assertNotIn(SECRET,self.db.path.read_bytes().decode('latin1'))

    def test_mock_unknown_source_rejected_by_unchanged_verifier(self):
        request=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
        self.approvals.decide(request['id'],'approved','Fixture approval')
        with patch.dict(os.environ,{'ORION_GROQ_TEST_BAD_CITATION':'1'}):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['status'],'failed')
        self.assertEqual(run['latest_verification']['status'],'failed')

    def test_missing_key_persists_real_failure_without_response(self):
        request=self.approvals.request(self.task['id'],'research-synthesize','Offline fixture')
        self.approvals.decide(request['id'],'approved','Fixture approval')
        with patch.dict(os.environ,{'ORION_GROQ_API_KEY':''}):
            run=self.engine.execute(self.task['id'],'research-synthesize')
        self.assertEqual(run['status'],'failed')
        self.assertEqual(run['latest_verification']['status'],'failed')
        output=json.loads(Path(run['result']['artifact']).read_text(encoding='utf-8'))
        self.assertEqual(output['response_text'],'')
        self.assertIn('ORION_GROQ_API_KEY',output['provider_error'])
