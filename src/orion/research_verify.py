"""Independent saved-packet checks against immutable captured responses; no network calls."""
import base64
import hashlib
from datetime import datetime
from urllib.parse import urlsplit, urlencode, quote
from uuid import uuid4
from .research import strict_json, digest, settings
from .inputs import read_bounded
from .models import ValidationError
from .service import identifier, timestamp
from .events import append_event


def validate(report, operation, execution_id, captures):
    """Deliberately does not invoke the collector, connector parsers or worker validator."""
    def need(condition, message):
        if not condition: raise ValueError(message)
    def instant(value):
        need(isinstance(value,str) and datetime.fromisoformat(value).tzinfo is not None,'timestamp')
    def url(value,host=None):
        need(isinstance(value,str) and not any(ord(ch)<33 for ch in value),'source URL')
        parsed=urlsplit(value)
        need(parsed.scheme in ('https','http') and bool(parsed.hostname) and not parsed.username and not parsed.password and (host is None or parsed.hostname==host),'source URL')
    fields={'schema_version','kind','operation_id','execution_id','question','configuration','created_at','providers','records','captures','limitations','capture_digest'}
    need(isinstance(report,dict) and set(report)==fields,'packet schema')
    config=settings(**operation['configuration'])
    need(type(report['schema_version']) is int and report['schema_version']==1 and report['kind']=='collected_evidence','packet version/kind')
    need(report['configuration']==config and report['question']==config['question'] and report['operation_id']==operation['operation_id'] and report['execution_id']==execution_id,'operation binding')
    instant(report['created_at'])
    need(report['captures']==captures and report['capture_digest']==digest(captures),'capture binding')
    need(isinstance(captures,list) and len(config['providers'])<=len(captures)<=len(config['providers'])+config['github_limit'],'capture count')
    need(isinstance(report['limitations'],list) and len(report['limitations'])==4 and all(isinstance(v,str) for v in report['limitations']),'limitations')
    need(report['limitations'][0]=='Collected provider evidence, not AI synthesis or factual certification.','evidence limitation')
    need(isinstance(report['providers'],list) and len(report['providers'])==len(config['providers']),'provider count')
    need(isinstance(report['records'],list),'records')
    expected=[]; seen=set(); used_readmes=set(); actual_requests=0
    for cap in captures:
        need(set(cap)=={'provider','kind','url','retrieved_at','status','http_status','body','error'},'capture schema')
        need(cap['provider'] in config['providers'] and cap['kind'] in ('search','readme'),'capture provider/kind')
        instant(cap['retrieved_at'])
        need(cap['status'] in ('ok','failed'),'capture status')
        need(cap['error'] in (None,'provider_rate_limited','request_budget_exhausted','execution_deadline','rate_limited','http_error','network_or_timeout','invalid_or_oversized_response','invalid_provider_schema','invalid_or_oversized_readme'),'capture error')
        if cap['error'] not in ('request_budget_exhausted','execution_deadline','provider_rate_limited'): actual_requests+=1
        if cap['status']=='ok': need(cap['http_status']==200 and cap['error'] is None and isinstance(cap['body'],str),'successful capture')
        else: need(cap['error'] is not None,'failed capture')
        if cap['body'] is not None: need(len(cap['body'].encode('utf-8'))<=config['max_response_bytes'],'response size')
    need(actual_requests<=config['request_budget'],'request budget')
    for index,name in enumerate(config['providers']):
        cap=captures[index]
        query={'query':config['question'],'rows':config['crossref_limit']} if name=='crossref' else {'q':config['question'],'per_page':config['github_limit']}
        endpoint='https://api.crossref.org/works?' if name=='crossref' else 'https://api.github.com/search/repositories?'
        need(cap['provider']==name and cap['kind']=='search' and cap['url']==endpoint+urlencode(query),'search provenance')
        items=[]; incomplete=False
        if cap['status']=='ok':
            body=strict_json(cap['body'])
            if name=='crossref':
                need(body['status']=='ok','Crossref status')
                items=body['message']['items']
            else:
                items=body['items'];incomplete=body.get('incomplete_results',False)
                need(type(incomplete) is bool,'incomplete flag')
            need(isinstance(items,list) and len(items)<=config[name+'_limit'],'result limit')
        count=0
        for result_index,item in enumerate(items):
            need(isinstance(item,dict),'source metadata')
            if name=='crossref':
                doi=item.get('DOI')
                stable='doi:'+doi.lower() if isinstance(doi,str) and doi else 'metadata:'+digest(item)
            else:
                need(type(item.get('id')) is int,'repository identifier')
                stable='repository:'+str(item['id'])
            if (name,stable) in seen: continue
            seen.add((name,stable));count+=1
            expected.append((name,stable,index,result_index,item))
        summary={'provider':name,'status':cap['status'],'error':cap['error'],'capture_index':index,'returned_count':len(items),'record_count':count,'incomplete_results':incomplete}
        need(report['providers'][index]==summary,'provider failure/count preservation')
    need(len(report['records'])==len(expected),'missing/duplicate/fabricated records')
    record_fields={'provider','source_id','source_url','query','retrieved_at','capture_index','result_index','metadata','evidence','missing_metadata','readme_capture_index','readme_status','evidence_digest'}
    for record,(name,stable,index,result_index,item) in zip(report['records'],expected):
        need(isinstance(record,dict) and set(record)==record_fields,'record schema')
        need(record['provider']==name and record['source_id']==stable and record['capture_index']==index and record['result_index']==result_index and record['metadata']==item,'captured record binding')
        need(record['query']==config['question'] and record['retrieved_at']==captures[index]['retrieved_at'],'query/retrieval binding')
        url(record['source_url'],'github.com' if name=='github' else None)
        if name=='crossref':
            doi=item.get('DOI')
            if isinstance(doi,str) and doi:
                expected_url='https://doi.org/'+quote(doi,safe='/')
            else:
                expected_url=item.get('URL')
                try: url(expected_url)
                except ValueError: expected_url=captures[index]['url']
            evidence={'title':item.get('title'),'abstract':item.get('abstract')}
            missing=[k for k in ('title','author','issued','DOI','publisher','container-title','abstract') if not item.get(k)]
        else:
            expected_url=item['html_url'];evidence={'description':item.get('description')}
            missing=[k for k in ('description','language','default_branch','updated_at') if not item.get(k)]
        need(record['source_url']==expected_url and record['missing_metadata']==missing,'source URL/missing metadata')
        ri=record['readme_capture_index']
        if ri is not None:
            need(name=='github' and config['include_readme'] and type(ri) is int and len(config['providers'])<=ri<len(captures) and ri not in used_readmes,'README reference')
            used_readmes.add(ri);cap=captures[ri]
            need(cap['provider']=='github' and cap['kind']=='readme' and cap['url']=='https://api.github.com/repos/'+item['full_name']+'/readme','README provenance')
            need(record['readme_status']==cap['status'],'README failure preservation')
            if cap['status']=='ok':
                body=strict_json(cap['body'])
                need(body['type']=='file' and body['encoding']=='base64','README encoding')
                raw=base64.b64decode(''.join(body['content'].split()),validate=True)
                need(len(raw)<=65536,'README size')
                evidence['readme']=raw.decode('utf-8')
        else:
            need(record['readme_status'] in ('not_requested','invalid_repository_name'),'README status')
        need(record['evidence']==evidence and record['evidence_digest']==digest({'metadata':item,'evidence':evidence}),'evidence content/digest')
    need(used_readmes==set(range(len(config['providers']),len(captures))),'unreferenced captures')


class ResearchVerifier:
    def __init__(self,database): self.database=database

    def verify(self,execution_id):
        execution_id=identifier(execution_id)
        with self.database.connect() as c:
            run=c.execute('SELECT * FROM research_runs WHERE execution_id=?',(execution_id,)).fetchone()
            captured=c.execute('SELECT * FROM research_captures WHERE execution_id=?',(execution_id,)).fetchone()
            execution=c.execute('SELECT * FROM executions WHERE id=?',(execution_id,)).fetchone()
        if run is None: raise ValidationError('Execution has no research binding')
        checks=[];artifact_digest=None
        def check(name,condition):
            checks.append({'name':name,'passed':bool(condition)})
            if not condition: raise ValueError(name)
        try:
            path=self.database.path.resolve().parent/'artifacts'/(execution_id+'.json')
            raw=read_bounded(path,8*1024*1024)
            artifact_digest=hashlib.sha256(raw).hexdigest()
            check('artifact_digest',artifact_digest==run['artifact_digest'])
            operation=strict_json(run['operation_json'])
            check('operation_digest',digest(operation)==run['sha256'])
            check('captured_responses_present',captured is not None)
            captures=strict_json(captured['captures_json'])
            check('captured_response_digest',digest(captures)==captured['sha256'])
            validate(strict_json(raw),operation,execution_id,captures)
            check('independent_schema_and_provenance',True)
            check('artifact_unchanged',hashlib.sha256(read_bounded(path,8*1024*1024)).hexdigest()==artifact_digest)
        except (OSError,ValueError,KeyError,TypeError,RecursionError,OverflowError) as exc:
            if not checks or checks[-1]['passed']:
                checks.append({'name':'independent_schema_and_provenance','passed':False,'error_type':type(exc).__name__})
        passed=bool(checks) and all(check['passed'] for check in checks)
        record_id=str(uuid4())
        import json
        with self.database.connect(write=True) as c:
            c.execute('INSERT INTO verifications VALUES (?,?,?,?,?,?,?,?,?,?)',(record_id,execution_id,'research-independent','1','passed' if passed else 'failed',run['sha256'],artifact_digest,timestamp(),json.dumps(checks),'Structure and captured provenance checked; not factual correctness' if passed else 'Research verification failed; inspect checks'))
            append_event(c,'verification_passed' if passed else 'verification_failed',execution['task_id'],execution_id,{'verification_id':record_id})
        from .verification import VerificationService
        return next(row for row in VerificationService(self.database).history(execution_id) if row['id']==record_id)
