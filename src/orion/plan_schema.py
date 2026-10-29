"""Strict bounded JSON plans with local dependency-cycle checks."""
import hashlib
import json
from .models import ValidationError

TEXT = {"type":"string","minLength":1,"maxLength":800}
TEXTS = {"type":"array","maxItems":10,"items":TEXT}
TASK = {"type":"object","additionalProperties":False,"properties":{
    "key":{"type":"string","minLength":1,"maxLength":40},"title":TEXT,"description":TEXT,
    "priority":{"type":"integer","minimum":0,"maximum":100},
    "dependencies":{"type":"array","maxItems":8,"uniqueItems":True,"items":{"type":"string"}},
    "acceptance_criteria":{**TEXTS,"minItems":1}},
    "required":["key","title","description","priority","dependencies","acceptance_criteria"]}
PLAN_SCHEMA = {"type":"object","additionalProperties":False,"properties":{
    "title":TEXT,"description":TEXT,"assumptions":TEXTS,"risks":TEXTS,"unresolved_questions":TEXTS,
    "tasks":{"type":"array","minItems":1,"maxItems":8,"items":TASK}},
    "required":["title","description","assumptions","risks","unresolved_questions","tasks"]}


def _validate(value, schema, path="plan"):
    kind = schema["type"]
    if kind == "object":
        if not isinstance(value,dict) or set(value) != set(schema["required"]): raise ValidationError(f"{path}: exact required fields expected")
        for key, definition in schema["properties"].items(): _validate(value[key],definition,path+"."+key)
    elif kind == "array":
        if not isinstance(value,list) or not schema.get("minItems",0)<=len(value)<=schema["maxItems"]: raise ValidationError(f"{path}: invalid array length")
        for item in value: _validate(item,schema["items"],path)
        if schema.get("uniqueItems") and len(set(value))!=len(value): raise ValidationError(f"{path}: duplicate values")
    elif kind == "integer":
        if type(value) is not int or not schema["minimum"]<=value<=schema["maximum"]: raise ValidationError(f"{path}: invalid integer")
    elif not isinstance(value,str) or not value.strip() or len(value)>schema.get("maxLength",40):
        raise ValidationError(f"{path}: nonempty bounded text required")


def validate_plan(value: dict) -> dict:
    _validate(value,PLAN_SCHEMA)
    keys = [t["key"] for t in value["tasks"]]
    if len(keys)!=len(set(keys)): raise ValidationError("Task keys must be unique")
    graph = {t["key"]:t["dependencies"] for t in value["tasks"]}
    visiting, visited = set(),set()
    def visit(key):
        if key not in graph: raise ValidationError("Unknown dependency")
        if key in visiting: raise ValidationError("Dependency cycle")
        if key in visited: return
        visiting.add(key)
        for dependency in graph[key]: visit(dependency)
        visiting.remove(key); visited.add(key)
    for key in keys: visit(key)
    return value


def parse_plan(text: str) -> dict:
    if len(text)>16000: raise ValidationError("Plan response too large")
    def pairs(items):
        result={}
        for key,value in items:
            if key in result: raise ValidationError("Duplicate JSON keys")
            result[key]=value
        return result
    try: return validate_plan(json.loads(text,object_pairs_hook=pairs))
    except (ValueError,TypeError,RecursionError) as exc: raise ValidationError("Invalid structured plan: " + str(exc)[:180]) from None


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(json.dumps(validate_plan(plan),sort_keys=True,separators=(",", ":")).encode()).hexdigest()
