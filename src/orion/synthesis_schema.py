"""Strict bounded analysis contract and separate deterministic citation checks."""
from .models import ValidationError
from .research import canonical, strict_json

TEXT={'type':'string','minLength':1,'maxLength':1200}
REFS={'type':'array','maxItems':10,'uniqueItems':True,'items':{'type':'string','minLength':1,'maxLength':200}}
CLAIM={'type':'object','additionalProperties':False,'properties':{'text':TEXT,'source_ids':REFS},'required':['text','source_ids']}
def obj(properties): return {'type':'object','additionalProperties':False,'properties':properties,'required':list(properties)}
def array(item,maximum=8): return {'type':'array','maxItems':maximum,'items':item}
SCHEMA=obj({'schema_version':{'type':'integer','enum':[1]},'execution_id':{'type':'string','minLength':36,'maxLength':36},
 'question':{'type':'string','minLength':1,'maxLength':256},'executive_summary':CLAIM,
 'key_findings':array(CLAIM),'comparisons':array(CLAIM),'advantages':array(CLAIM),'disadvantages':array(CLAIM),
 'evidence_limitations':array(TEXT),'unresolved_questions':array(TEXT),
 'recommendation':obj({'supported':{'type':'boolean'},'text':TEXT,'source_ids':REFS}),
 'next_experiments':array(TEXT),'confidence':obj({'level':{'type':'string','enum':['low','medium','high']},'explanation':TEXT})})

def check_schema(value,schema,path='analysis'):
    kind=schema['type']
    valid={'object':lambda:isinstance(value,dict),'array':lambda:isinstance(value,list),
           'string':lambda:isinstance(value,str),'integer':lambda:type(value) is int,'boolean':lambda:type(value) is bool}[kind]()
    if not valid: raise ValidationError(path+': invalid type')
    if 'enum' in schema and value not in schema['enum']: raise ValidationError(path+': invalid value')
    if kind=='object':
        if set(value)!=set(schema['required']): raise ValidationError(path+': exact fields required')
        for key,child in schema['properties'].items(): check_schema(value[key],child,path+'.'+key)
    elif kind=='array':
        if len(value)>schema['maxItems']: raise ValidationError(path+': too many items')
        for item in value: check_schema(item,schema['items'],path+'[]')
        if schema.get('uniqueItems') and len(value)!=len(set(value)): raise ValidationError(path+': duplicate references')
    elif kind=='string' and (not value.strip() or not schema.get('minLength',0)<=len(value)<=schema.get('maxLength',1200)):
        raise ValidationError(path+': invalid text length')

def parse_analysis(text,execution_id,question,max_bytes):
    if not isinstance(text,str) or len(text.encode('utf-8'))>max_bytes: raise ValidationError('Analysis response exceeds byte limit')
    try: value=strict_json(text)
    except (ValueError,RecursionError): raise ValidationError('Analysis is not strict JSON') from None
    check_schema(value,SCHEMA)
    if value['execution_id']!=execution_id or value['question']!=question: raise ValidationError('Analysis execution/question mismatch')
    return value

def citations(analysis,sources):
    """Existence/provenance only: does not judge entailment or factual truth."""
    lookup={s['source_id']:s for s in sources}
    if len(lookup)!=len(sources): raise ValidationError('Ambiguous source identifiers')
    claims=[('executive_summary',analysis['executive_summary'])]
    for field in ('key_findings','comparisons','advantages','disadvantages'):
        claims.extend((field+'.'+str(i),item) for i,item in enumerate(analysis[field]))
    recommendation=analysis['recommendation']
    claims.append(('recommendation',recommendation))
    resolved=[];warnings=[]
    for label,claim in claims:
        ids=claim['source_ids']
        required=label!='recommendation' or recommendation['supported']
        # With no source records, only a no-evidence summary and withheld recommendation are possible.
        if required and not ids and (sources or label!='executive_summary'):
            raise ValidationError(label+': citations required')
        if label=='recommendation' and not recommendation['supported'] and ids:
            raise ValidationError('Withheld recommendation must use empty references')
        for sid in ids:
            if sid not in lookup: raise ValidationError(label+': unknown source ID')
            source=lookup[sid]
            meaningful=' '.join((' '.join(p['text'] for p in v) if isinstance(v,list) else str(v)) for k,v in source['evidence'].items() if k!='title' and v)
            if len(meaningful.strip())<80: warnings.append(label+': sparse evidence for '+sid+'; interpretation needs review')
            resolved.append({'claim':label,'source_id':sid,'provider':source['provider'],'source_url':source['source_url'],
                             'evidence_digest':source['evidence_digest'],'evidence_kinds':list(source['evidence'])})
    if not sources and (analysis['key_findings'] or analysis['comparisons'] or analysis['advantages'] or analysis['disadvantages'] or recommendation['supported']):
        raise ValidationError('No source records: findings and supported recommendations forbidden')
    return {'resolved_references':resolved,'warnings':warnings,
            'policy':'Factual claim fields require IDs. Limitations, questions, confidence explanation and future experiments are non-claim fields; human review must detect factual assertions placed there. Citation presence is not factual certification.'}
