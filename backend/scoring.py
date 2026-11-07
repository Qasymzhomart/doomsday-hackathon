from decimal import Decimal, ROUND_HALF_UP
import logging
from .models import AIEvaluation

log = logging.getLogger('cqa')


def validate_score(c, score, applicable):
    if not applicable:
        if not c['allow_na'] or score is not None:
            raise ValueError('N/A must be allowed and have null score')
        return
    if isinstance(score, bool) or score is None or not c['min_score'] <= score <= c['max_score']:
        raise ValueError('Score outside scale')
    if c['answer_type'] == 'boolean' and score not in (0, 1):
        raise ValueError('Boolean score must be 0 or 1')
    if c.get('allowed_scores') is not None and score not in c['allowed_scores']:
        raise ValueError('Score must be a configured scale step')


def validate_result(raw, checklist, conversation):
    parsed = AIEvaluation.model_validate(raw).model_dump()
    expected = {c['criterion_id']: c for c in checklist['criteria']}
    ids = [r['criterion_id'] for r in parsed['criteria']]
    if len(ids) != len(set(ids)) or set(ids) != set(expected):
        raise ValueError('AI must return every criterion exactly once')
    messages = {m['message_id']: m for m in conversation['transcript']}
    warnings, results = [], []
    for r in parsed['criteria']:
        c = expected[r['criterion_id']]
        validate_score(c, r['score'], r['applicable'])
        if not r['reason'].strip():
            raise ValueError('Empty reason')
        answer = 'N/A' if not r['applicable'] else (
            ('YES' if r['score'] == 1 else 'NO') if c['answer_type'] == 'boolean' else str(r['score'])
        )
        if c['answer_type'] == 'boolean' and r['answer'] != answer or not r['applicable'] and r['answer'] != 'N/A':
            raise ValueError('Answer inconsistent with score/applicability')
        if c['critical_rule'] and r['critical_error'] != (r['applicable'] and r['score'] == 1):
            raise ValueError('Critical flag inconsistent with critical criterion')
        evidence = []
        for mid in dict.fromkeys(r['evidence_ids']):
            if mid in messages:
                evidence.append(messages[mid])
            else:
                warnings.append(f"{r['criterion_id']}: evidence ID {mid} not found")
                log.warning('evidence ID not found: %s', mid)
        results.append({**r, 'name': c['name'], 'section': c['section'],
                        'original_score': r['score'], 'final_score': r['score'],
                        'original_applicable': r['applicable'], 'original_critical_error': r['critical_error'],
                        'original_answer': r['answer'], 'max_score': c['max_score'],
                        'original_weight': c['weight'], 'evidence': evidence})
    return results, warnings


def calculate(criteria, decimals=2):
    weight = sum(Decimal(str(c['original_weight'])) for c in criteria if c['applicable'])
    total = Decimal(0)
    for c in criteria:
        effective = Decimal(str(c['original_weight'])) / weight * 100 if c['applicable'] and weight else Decimal(0)
        c['effective_weight'] = float(effective)
        contribution = Decimal(str(c['final_score'])) / Decimal(str(c['max_score'])) * effective if c['applicable'] else Decimal(0)
        c['contribution'] = float(contribution)
        total += contribution
    return float(total.quantize(Decimal(1).scaleb(-decimals), rounding=ROUND_HALF_UP)) if weight else None
