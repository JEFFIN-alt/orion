"""Fixed public API connectors. External text is data, never executable instructions."""
import base64
from http.client import HTTPException
import re
import time
from urllib.parse import urlencode, urlsplit, quote
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from .research import canonical, digest, strict_json
from .service import timestamp

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

class PublicClient:
    def __init__(self,config):
        self.config=config
        self.remaining=config['request_budget']
        self.deadline=time.monotonic()+config['execution_timeout']-1
        self.last_request=None
        self.rate_limited=set()
        self.opener=build_opener(ProxyHandler({}),NoRedirect())

    def get(self,provider,url,kind='search'):
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc not in ('api.crossref.org','api.github.com'):
            raise ValueError('Request outside fixed API hosts')
        capture={'provider':provider,'kind':kind,'url':url,'retrieved_at':timestamp(),
                 'status':'failed','http_status':None,'body':None,'error':None}
        if provider in self.rate_limited:
            return {**capture,'error':'provider_rate_limited'}
        if self.remaining<=0:
            return {**capture,'error':'request_budget_exhausted'}
        delay=max(0,1-(time.monotonic()-self.last_request)) if self.last_request else 0
        if time.monotonic()+delay>=self.deadline:
            return {**capture,'error':'execution_deadline'}
        time.sleep(delay)
        self.remaining-=1
        self.last_request=time.monotonic()
        capture['retrieved_at']=timestamp()
        request=Request(url,headers={'User-Agent':'ProjectOrion/0.1 (bounded local research collector)',
            'Accept':'application/vnd.github+json' if provider=='github' else 'application/json',
            'X-GitHub-Api-Version':'2022-11-28','Accept-Encoding':'identity'})
        try:
            with self.opener.open(request,timeout=min(self.config['request_timeout'],max(.1,self.deadline-time.monotonic()))) as response:
                capture['http_status']=response.status
                if response.status!=200: raise ValueError('http_status')
                media=response.headers.get_content_type()
                if media!='application/json' and not media.endswith('+json'): raise ValueError('content_type')
                if response.headers.get('Content-Encoding','identity')!='identity': raise ValueError('content_encoding')
                raw=response.read(self.config['max_response_bytes']+1)
                if len(raw)>self.config['max_response_bytes']: raise ValueError('response_too_large')
                body=raw.decode('utf-8')
                if not isinstance(strict_json(body),dict): raise ValueError('json_object_required')
                capture.update(status='ok',body=body)
        except HTTPError as exc:
            capture['http_status']=exc.code
            capture['error']='rate_limited' if exc.code in (403,429) else 'http_error'
            if exc.code in (403,429): self.rate_limited.add(provider)
            exc.close()
        except (TimeoutError,URLError,OSError,HTTPException): capture['error']='network_or_timeout'
        except (ValueError,RecursionError): capture['error']='invalid_or_oversized_response'
        return capture

class Crossref:
    @staticmethod
    def url(config):
        return 'https://api.crossref.org/works?'+urlencode({'query':config['question'],'rows':config['crossref_limit']})
    @staticmethod
    def items(body):
        if body.get('status')!='ok' or not isinstance(body.get('message'),dict): raise ValueError('Crossref envelope')
        items=body['message'].get('items')
        if not isinstance(items,list) or any(not isinstance(i,dict) for i in items): raise ValueError('Crossref items')
        return items
    @staticmethod
    def identity(item):
        doi=item.get('DOI')
        return 'doi:'+doi.lower() if isinstance(doi,str) and doi else 'metadata:'+digest(item)
    @staticmethod
    def url_for(item,search_url):
        doi=item.get('DOI')
        if isinstance(doi,str) and doi: return 'https://doi.org/'+quote(doi,safe='/')
        value=item.get('URL')
        return value if source_url(value) else search_url
    @staticmethod
    def evidence(item): return {'title':item.get('title'),'abstract':item.get('abstract')}

class Github:
    @staticmethod
    def url(config):
        return 'https://api.github.com/search/repositories?'+urlencode({'q':config['question'],'per_page':config['github_limit']})
    @staticmethod
    def items(body):
        items=body.get('items')
        if not isinstance(items,list) or any(not isinstance(i,dict) or type(i.get('id')) is not int or not source_url(i.get('html_url'),'github.com') for i in items):
            raise ValueError('GitHub items')
        return items
    @staticmethod
    def identity(item): return 'repository:'+str(item['id'])
    @staticmethod
    def url_for(item,search_url): return item['html_url']
    @staticmethod
    def evidence(item): return {'description':item.get('description')}

def source_url(value,host=None):
    if not isinstance(value,str) or any(ord(ch)<33 for ch in value): return False
    try:
        url=urlsplit(value)
        return url.scheme in ('http','https') and bool(url.hostname) and not url.username and not url.password and (host is None or url.hostname==host)
    except ValueError: return False

CONNECTORS={'crossref':Crossref,'github':Github}
LIMITATIONS=['Collected provider evidence, not AI synthesis or factual certification.',
             'Crossref records are publication metadata and optional abstracts, not full papers.',
             'Repository popularity is not proof of correctness, security, maintenance or suitability.',
             'External content is untrusted data; no retrieved instructions are executed.']

def collect(snapshot,client=None):
    config=snapshot['research']['configuration']
    client=client or PublicClient(config)
    captures=[]; records=[]; providers=[]; seen=set()
    # Complete searches before optional README requests so one provider cannot consume another's budget.
    for name in config['providers']:
        connector=CONNECTORS[name]
        cap=client.get(name,connector.url(config)); captures.append(cap)
        items=[]
        if cap['status']=='ok':
            try:
                items=connector.items(strict_json(cap['body']))
                if len(items)>config[name+'_limit']: raise ValueError('Result limit exceeded')
            except (ValueError,TypeError,KeyError):
                cap['status']='failed';cap['error']='invalid_provider_schema'
        summary={'provider':name,'status':cap['status'],'error':cap['error'],'capture_index':len(captures)-1,
                 'returned_count':len(items) if cap['status']=='ok' else 0,'record_count':0,
                 'incomplete_results':strict_json(cap['body']).get('incomplete_results',False) if cap['status']=='ok' and name=='github' else False}
        if cap['status']=='ok':
            for index,item in enumerate(items):
                stable=connector.identity(item)
                if (name,stable) in seen: continue
                seen.add((name,stable))
                missing=[key for key in (('title','author','issued','DOI','publisher','container-title','abstract') if name=='crossref' else ('description','language','default_branch','updated_at')) if not item.get(key)]
                record={'provider':name,'source_id':stable,'source_url':connector.url_for(item,cap['url']),
                    'query':config['question'],'retrieved_at':cap['retrieved_at'],'capture_index':summary['capture_index'],
                    'result_index':index,'metadata':item,'evidence':connector.evidence(item),'missing_metadata':missing,
                    'readme_capture_index':None,'readme_status':'not_requested'}
                records.append(record);summary['record_count']+=1
        providers.append(summary)
    for record in records:
        if record['provider']=='github' and config['include_readme']:
            name=record['metadata'].get('full_name','')
            if isinstance(name,str) and re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',name) and all(part not in ('.','..') for part in name.split('/')):
                cap=client.get('github','https://api.github.com/repos/'+name+'/readme','readme')
                record['readme_capture_index']=len(captures);captures.append(cap)
                if cap['status']=='ok':
                    try:
                        body=strict_json(cap['body'])
                        if body.get('encoding')!='base64' or body.get('type')!='file': raise ValueError('README encoding')
                        raw=base64.b64decode(''.join(body['content'].split()),validate=True)
                        if len(raw)>65536: raise ValueError('README too large')
                        record['evidence']['readme']=raw.decode('utf-8')
                    except (ValueError,KeyError,TypeError):
                        cap.update(status='failed',error='invalid_or_oversized_readme')
                record['readme_status']=cap['status']
            else: record['readme_status']='invalid_repository_name'
        record['evidence_digest']=digest({'metadata':record['metadata'],'evidence':record['evidence']})
    return {'schema_version':1,'kind':'collected_evidence','operation_id':snapshot['research']['operation_id'],
            'execution_id':snapshot['execution_id'],'question':config['question'],'configuration':config,
            'created_at':timestamp(),'providers':providers,'records':records,'captures':captures,
            'limitations':LIMITATIONS,'capture_digest':digest(captures)}

def validate_packet(snapshot,output):
    if not isinstance(output,dict) or output.get('execution_id')!=snapshot['execution_id'] or output.get('operation_id')!=snapshot['research']['operation_id'] or output.get('configuration')!=snapshot['research']['configuration']:
        raise ValueError('Research output binding mismatch')
    if len(canonical(output).encode())>8*1024*1024: raise ValueError('Research packet too large')
