"""Exact, operator-selected slices of captured Unicode text; no retrieval or inference."""
import hashlib
from .models import ValidationError
from .research import digest


def selections(value):
    if not isinstance(value, list) or not 1 <= len(value) <= 32:
        raise ValidationError('Select 1..32 passages')
    result = []
    for item in value:
        if not isinstance(item, dict) or set(item) != {'source_id', 'field', 'start', 'end'}:
            raise ValidationError('Passage requires source_id, field, start, end only')
        if any(not isinstance(item[k], str) or not item[k] or len(item[k]) > 200 for k in ('source_id', 'field')):
            raise ValidationError('Invalid passage source/field')
        if type(item['start']) is not int or type(item['end']) is not int or not 0 <= item['start'] < item['end']:
            raise ValidationError('Invalid passage offsets')
        result.append(dict(item))
    result.sort(key=lambda x: (x['source_id'], x['field'], x['start'], x['end']))
    for previous, current in zip(result, result[1:]):
        if (previous['source_id'], previous['field']) == (current['source_id'], current['field']) and current['start'] < previous['end']:
            raise ValidationError('Overlapping or duplicate passages')
    return result


def project(packet, config):
    chosen = selections(config['passages'])
    records = {r['source_id']: r for r in packet['records']}
    if len(records) != len(packet['records']):
        raise ValidationError('Ambiguous source identifiers')
    sources = {}
    for selection in chosen:
        sid, field, start, end = (selection[k] for k in ('source_id', 'field', 'start', 'end'))
        record = records.get(sid)
        if record is None or not isinstance(record['evidence'].get(field), str):
            raise ValidationError('Passage requires a captured text field and known source')
        original = record['evidence'][field]
        if end > len(original) or end - start > config['excerpt_chars']:
            raise ValidationError('Passage outside source or excerpt bound')
        source = sources.setdefault(sid, {'source_id': sid, 'source_url': record['source_url'],
            'provider': record['provider'], 'evidence_digest': record['evidence_digest'],
            'evidence': {}, 'excerpt_omissions': {}})
        text = original[start:end]
        source['evidence'].setdefault(field, []).append({'start': start, 'end': end, 'text': text,
            'sha256': hashlib.sha256(text.encode('utf-8')).hexdigest()})
    if len(sources) > config['max_sources']:
        raise ValidationError('Selected sources exceed max_sources')
    for sid, source in sources.items():
        for field, original in records[sid]['evidence'].items():
            if not isinstance(original, str):
                source['excerpt_omissions'][field] = {'omitted_nontext': True}
                continue
            ranges = source['evidence'].get(field, [])
            omitted = []; cursor = 0
            for item in ranges:
                if cursor < item['start']: omitted.append([cursor, item['start']])
                cursor = item['end']
            if cursor < len(original): omitted.append([cursor, len(original)])
            source['excerpt_omissions'][field] = {'original_chars': len(original), 'omitted_ranges': omitted}
    return {'question': packet['question'], 'sources': list(sources.values()),
        'provider_outcomes': packet['providers'], 'limitations': packet['limitations'],
        'omitted_source_ids': [sid for sid in records if sid not in sources],
        'selection_policy': 'Explicit slices only; Unicode code-point offsets, zero-based start inclusive/end exclusive; no normalization. Metadata omitted. Not full documents.'}


def validate_projection(packet, config, projection, expected_digest):
    # Re-extract from the independently verified packet, never from supplied passage text.
    expected = project(packet, config)
    if digest(expected) != expected_digest or digest(projection) != expected_digest:
        raise ValidationError('Passage projection/content/digest mismatch')
    return expected


def model_evidence(projection):
    # Deterministic transport view; complete provenance stays in the approved operation.
    return {'question': projection['question'], 'sources': [
        {'source_id': s['source_id'], 'source_url': s['source_url'], 'passages': [
            [field, p['start'], p['end'], p['text']]
            for field, items in s['evidence'].items() for p in items]}
        for s in projection['sources']],
        'omitted_source_count': len(projection['omitted_source_ids'])}
