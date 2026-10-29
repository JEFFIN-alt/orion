"""Bounded research configuration and immutable execution bindings."""
import hashlib
import json
from uuid import uuid4
from .models import ValidationError
from .service import Service, timestamp
from .events import append_event

PROVIDERS = ('crossref', 'github')
DEFAULTS = dict(providers=list(PROVIDERS), crossref_limit=3, github_limit=3,
                request_budget=5, max_response_bytes=262144, request_timeout=5,
                execution_timeout=30, include_readme=True)
BOUNDS = dict(crossref_limit=(1,5), github_limit=(1,5), request_budget=(1,8),
              max_response_bytes=(1024,524288), request_timeout=(1,10), execution_timeout=(5,60))

def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True,allow_nan=False)

def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()

def strict_json(value):
    def pairs(items):
        result={}
        for key,item in items:
            if key in result: raise ValueError('Duplicate JSON key')
            result[key]=item
        return result
    def invalid(value): raise ValueError('Nonfinite JSON')
    return json.loads(value,object_pairs_hook=pairs,parse_constant=invalid)

def settings(question, **values):
    if not isinstance(question,str) or not question.strip() or len(question.encode('utf-8'))>256 or any(ord(ch)<32 for ch in question):
        raise ValidationError('Research question must be nonempty, at most 256 UTF-8 bytes, without control characters')
    if values.keys()-DEFAULTS.keys(): raise ValidationError('Unknown research setting')
    result={**DEFAULTS,**values,'question':question.strip()}
    for key,(low,high) in BOUNDS.items():
        if type(result[key]) is not int or not low<=result[key]<=high: raise ValidationError(f'{key} must be {low}..{high}')
    providers=result['providers']
    if not isinstance(providers,list) or not providers or any(p not in PROVIDERS for p in providers) or len(set(providers))!=len(providers):
        raise ValidationError('Choose unique providers: crossref, github')
    result['providers']=[p for p in PROVIDERS if p in providers]
    if result['request_budget']<len(providers): raise ValidationError('Budget must allow one search per provider')
    if type(result['include_readme']) is not bool: raise ValidationError('include_readme must be boolean')
    return result

class ResearchService:
    def __init__(self,database): self.database=database

    def configure(self,task_id,question,**values):
        config=settings(question,**values)
        with self.database.connect(write=True) as c:
            task=Service(self.database)._get(c,'tasks',task_id)
            if task['status']!='pending': raise ValidationError('Research configuration requires a pending task')
            c.execute('INSERT INTO research_operations VALUES (?,?,?,?) ON CONFLICT(task_id) DO UPDATE SET operation_id=excluded.operation_id, config_json=excluded.config_json, configured_at=excluded.configured_at',
                      (task['id'],str(uuid4()),canonical(config),timestamp()))
            append_event(c,'research_configured',task['id'])
        return self.get(task_id)

    def get(self,task_id):
        with self.database.connect() as c:
            task=Service(self.database)._get(c,'tasks',task_id)
            return operation(c,task['id'])

    def packet(self,execution_id):
        from .service import identifier
        from .inputs import read_bounded
        with self.database.connect() as c:
            if not c.execute('SELECT 1 FROM research_runs WHERE execution_id=?',(identifier(execution_id),)).fetchone():
                raise ValidationError('Execution has no research binding')
        path=self.database.path.resolve().parent/'artifacts'/(execution_id+'.json')
        try:
            return strict_json(read_bounded(path,8*1024*1024))
        except (ValueError,RecursionError):
            raise ValidationError('Research artifact is not valid bounded JSON') from None

def operation(c,task_id):
    row=c.execute('SELECT * FROM research_operations WHERE task_id=?',(task_id,)).fetchone()
    if row is None: raise ValidationError('Configure the task with research configure before execution')
    config=strict_json(row['config_json'])
    config=settings(**config)
    return {'operation_id':row['operation_id'],'configuration':config,'configured_at':row['configured_at']}
