"""Reread saved synthesis, upstream evidence and citations; never invoke the model."""
import hashlib
import math
from datetime import datetime
from uuid import uuid4
from .research import canonical,digest,strict_json
from .inputs import read_bounded
from .service import identifier,timestamp
from .models import ValidationError
from .events import append_event
from .synthesis import select_evidence,project_evidence
from .synthesis_schema import parse_analysis,citations

class SynthesisVerifier:
    def __init__(self,database): self.database=database
    def verify(self,execution_id):
        execution_id=identifier(execution_id)
        with self.database.connect() as c:
            c.execute('BEGIN')
            run=c.execute('SELECT * FROM synthesis_runs WHERE execution_id=?',(execution_id,)).fetchone()
            execution=c.execute('SELECT * FROM executions WHERE id=?',(execution_id,)).fetchone()
        if run is None: raise ValidationError('No synthesis binding')
        checks=[];sha=None
        def check(name,valid):
            checks.append({'name':name,'passed':bool(valid)})
            if not valid: raise ValidationError(name)
        try:
            operation=strict_json(run['operation_json'])
            check('operation_digest',digest(operation)==run['sha256'])
            path=self.database.path.resolve().parent/'artifacts'/(execution_id+'.json')
            raw=read_bounded(path,131072);sha=hashlib.sha256(raw).hexdigest()
            check('artifact_digest',sha==run['artifact_digest'])
            output=strict_json(raw)
            fields={'schema_version','kind','execution_id','source_execution','evidence_digest','worker_version','created_at','configured_model','response_metadata','response_text','provider_error','inference_uncertain'}
            check('envelope_schema',isinstance(output,dict) and set(output)==fields and type(output['schema_version']) is int and output['schema_version']==1 and output['kind']=='research_synthesis')
            check('execution_binding',output['execution_id']==execution_id and output['source_execution']==operation['source_execution'] and output['evidence_digest']==operation['evidence_digest'] and output['worker_version']==operation['worker_version'] and output['configured_model']==operation['model'])
            check('timestamp',isinstance(output['created_at'],str) and datetime.fromisoformat(output['created_at']).tzinfo is not None)
            check('provider_completed',output['provider_error'] is None and output['inference_uncertain'] is False)
            meta=output['response_metadata']
            check('response_metadata',isinstance(meta,dict) and set(meta)=={'provider','model','elapsed_seconds'} and all(isinstance(meta[k],str) and 0<len(meta[k])<=120 for k in ('provider','model')) and type(meta['elapsed_seconds']) in (int,float) and math.isfinite(meta['elapsed_seconds']) and meta['elapsed_seconds']>=0)
            with self.database.connect() as c:
                c.execute('BEGIN')
                packet,source=select_evidence(c,self.database,operation['source_execution'])
            check('upstream_digest',source['evidence_digest']==operation['evidence_digest'])
            projection=project_evidence(packet,operation['configuration'])
            check('evidence_projection',projection==operation['evidence'])
            analysis=parse_analysis(output['response_text'],execution_id,packet['question'],operation['configuration']['max_response_bytes'])
            check('strict_analysis_schema',True)
            resolved=citations(analysis,projection['sources'])
            checks.append({'name':'source_references','passed':True,**resolved})
            check('artifact_unchanged',hashlib.sha256(read_bounded(path,131072)).hexdigest()==sha)
        except (OSError,ValueError,TypeError,KeyError,RecursionError,OverflowError) as exc:
            if not checks or checks[-1]['passed']: checks.append({'name':'analysis_and_provenance','passed':False,'reason':str(exc)[:250]})
        passed=bool(checks) and all(x['passed'] for x in checks)
        record_id=str(uuid4())
        with self.database.connect(write=True) as c:
            c.execute('INSERT INTO verifications VALUES (?,?,?,?,?,?,?,?,?,?)',(record_id,execution_id,'synthesis-independent','1','passed' if passed else 'failed',run['sha256'],sha,timestamp(),canonical(checks),'Structure and references verified; human review required for factual support' if passed else 'Synthesis verification failed'))
            append_event(c,'verification_passed' if passed else 'verification_failed',execution['task_id'],execution_id,{'verification_id':record_id})
        from .verification import VerificationService
        return next(row for row in VerificationService(self.database).history(execution_id) if row['id']==record_id)
