import json
import logging
import os
import secrets
from datetime import datetime, timezone
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from .models import Checklist, EvaluateRequest, ImportRequest, AppealRequest, ReviewRequest
from .storage import Store, dump
from .scoring import calculate, validate_result, validate_score
from .services import call_ai, import_dataset, download_dataset

load_dotenv(Path(__file__).with_name('.env'))
logging.basicConfig(level=logging.INFO, format='[%(levelname)s] %(message)s')
# HTTP client request logging may contain signed organizer URLs.
logging.getLogger('httpx').setLevel(logging.WARNING)
log = logging.getLogger('cqa')


def create_app(db_path=None, evaluator=None):
    url = os.getenv('DATABASE_URL', 'sqlite:///backend/data/cqa.db')
    if db_path is None and not url.startswith('sqlite:///'):
        raise ValueError('Only sqlite:/// DATABASE_URL is supported')
    store = Store(db_path or url.removeprefix('sqlite:///'))
    with store.connect() as db:
        empty = db.execute('SELECT COUNT(*) FROM checklists').fetchone()[0] == 0
    if empty:
        config = json.loads(Path(__file__).with_name('checklist.json').read_text(encoding='utf-8'))
        store.save_checklist(Checklist.model_validate(config).model_dump())
    app = FastAPI(title='CQA Backend', version='1.0.0')
    app.state.store, app.state.evaluator = store, evaluator or call_ai
    app.add_middleware(CORSMiddleware, allow_origins=os.getenv('CORS_ORIGINS','http://localhost:3000,http://localhost:5173').split(','),
                       allow_methods=['GET','POST','PUT','OPTIONS'], allow_headers=['Content-Type','Authorization'])

    @app.middleware('http')
    async def authentication(request: Request, call_next):
        token = os.getenv('API_TOKEN')
        if token and request.url.path.startswith('/api/') and request.method != 'OPTIONS':
            if not secrets.compare_digest(request.headers.get('authorization',''), 'Bearer '+token):
                return JSONResponse(status_code=401, content={'detail': 'Unauthorized'})
        return await call_next(request)

    @app.exception_handler(LookupError)
    async def not_found(request, exc):
        return JSONResponse(status_code=404, content={'detail': str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse(status_code=422, content={'detail': 'Invalid data: '+str(exc)})

    @app.get('/health')
    def health():
        return {'status': 'ok'}

    @app.post('/api/datasets/import')
    def dataset_import(body: ImportRequest):
        try:
            return import_dataset(store, download_dataset(body.group_id), body.group_id)
        except RuntimeError as exc:
            raise HTTPException(502, str(exc)) from None

    @app.get('/api/conversations')
    def conversations(language: str | None=None, channel: str | None=None, status: str | None=None, group_id: str | None=None):
        with store.connect() as db:
            rows = db.execute('SELECT * FROM conversations ORDER BY id').fetchall()
            result = []
            for row in rows:
                c = json.loads(row['payload'])
                ev = db.execute('SELECT id FROM evaluations WHERE conversation_id=? ORDER BY id DESC LIMIT 1', (row['id'],)).fetchone()
                e = store.evaluation(ev[0], db) if ev else {}
                state = 'evaluated' if e.get('status') == 'completed' else e.get('status','not_evaluated')
                if any([language and language != c['language'], channel and channel != c['channel'],
                        status and status != state, group_id and group_id != row['group_id']]):
                    continue
                result.append({k:c[k] for k in ('conversation_id','language','channel','dataset_group_id')} |
                              {'status': state, 'total_score': e.get('final_total_score'), 'audio_url': c['audio_url']})
            return result

    @app.get('/api/conversations/{cid}')
    def conversation(cid: str):
        return store.conversation(cid)

    @app.get('/api/checklists')
    def checklists():
        with store.connect() as db:
            return [store.checklist(r[0],db) for r in db.execute('SELECT id FROM checklists ORDER BY id').fetchall()]

    @app.get('/api/checklists/{cid}')
    def checklist(cid: int):
        return store.checklist(cid)

    @app.post('/api/checklists', status_code=201)
    def new_checklist(body: Checklist):
        return store.save_checklist(body.model_dump())

    @app.put('/api/checklists/{cid}')
    def update_checklist(cid: int, body: Checklist):
        return store.save_checklist(body.model_dump(),cid)

    @app.post('/api/evaluate/{cid}')
    def evaluate(cid: str, body: EvaluateRequest = EvaluateRequest()):
        c, checklist = store.conversation(cid), store.checklist(body.checklist_id)
        payload = {'conversation_id': cid, 'checklist_id': checklist['id'], 'checklist_version': checklist['version'],
                   'checklist_snapshot': checklist}
        with store.connect() as db:
            eid = db.execute('INSERT INTO evaluations(conversation_id,checklist_id,status,payload) VALUES(?,?,?,?)',
                             (cid,checklist['id'],'processing',dump(payload))).lastrowid
        log.info('evaluation started: %s', eid)
        for attempt in range(2):
            try:
                raw = app.state.evaluator(c,checklist)
                criteria, warnings = validate_result(raw,checklist,c)
                total = calculate(criteria,checklist['rounding_decimals'])
                payload.update(criteria=criteria, warnings=warnings, original_ai_result=raw,
                               original_total_score=total, final_total_score=total, total_score=total,
                               critical_error=any(r['critical_error'] for r in criteria))
                with store.connect() as db:
                    db.execute('UPDATE evaluations SET status=?,payload=? WHERE id=?', ('completed',dump(payload),eid))
                log.info('score calculated: evaluation=%s', eid)
                return store.evaluation(eid)
            except Exception as exc:
                # Avoid exposing provider responses, keys, signed URLs or transcript data.
                log.warning('evaluation attempt failed: %s', type(exc).__name__)
        payload['error'] = 'AI evaluation failed after two attempts. Check provider configuration, quota and response schema.'
        with store.connect() as db:
            db.execute('UPDATE evaluations SET status=?,payload=? WHERE id=?', ('failed',dump(payload),eid))
        raise HTTPException(502, {'evaluation_id': eid, 'message': payload['error']})

    @app.get('/api/evaluations/{cid}')
    def latest_evaluation(cid: str):
        store.conversation(cid)
        with store.connect() as db:
            row = db.execute('SELECT id FROM evaluations WHERE conversation_id=? ORDER BY id DESC LIMIT 1',(cid,)).fetchone()
            if not row:
                raise LookupError('Evaluation not found')
            return store.evaluation(row[0],db)

    @app.get('/api/conversations/{cid}/evaluations')
    def history(cid: str):
        store.conversation(cid)
        with store.connect() as db:
            return [store.evaluation(r[0],db) for r in db.execute('SELECT id FROM evaluations WHERE conversation_id=? ORDER BY id',(cid,)).fetchall()]

    @app.post('/api/appeals', status_code=201)
    def appeal(body: AppealRequest):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            ev = store.evaluation(body.evaluation_id,db)
            if ev['status'] != 'completed' or body.conversation_id != ev['conversation_id']:
                raise ValueError('Appeal requires a completed evaluation of this conversation')
            criterion = next((c for c in ev['criteria'] if c['criterion_id']==body.criterion_id),None)
            if not criterion:
                raise LookupError('Criterion not found')
            if db.execute('SELECT id FROM appeals WHERE evaluation_id=? AND criterion_id=? AND status=?',
                          (body.evaluation_id,body.criterion_id,'submitted')).fetchone():
                raise HTTPException(409,'An appeal is already pending for this criterion')
            payload = body.model_dump() | {'status':'submitted','original_score':criterion['original_score'],
                      'score_at_submission':criterion['final_score'], 'criterion':criterion,
                      'original_total_score':ev['original_total_score']}
            aid = db.execute('INSERT INTO appeals(evaluation_id,criterion_id,status,payload) VALUES(?,?,?,?)',
                             (body.evaluation_id,body.criterion_id,'submitted',dump(payload))).lastrowid
        log.info('appeal submitted: %s',aid)
        return payload | {'id':aid}

    @app.get('/api/appeals')
    def appeals(status: str | None=None):
        with store.connect() as db:
            rows = db.execute('SELECT * FROM appeals ORDER BY id').fetchall()
            return [json.loads(r['payload']) | {'id':r['id'],'created_at':r['created_at']} for r in rows if not status or r['status']==status]

    @app.post('/api/appeals/{aid}/review')
    def review(aid: int, body: ReviewRequest):
        with store.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM appeals WHERE id=?',(aid,)).fetchone()
            if not row:
                raise LookupError('Appeal not found')
            if row['status'] != 'submitted':
                raise HTTPException(409,'Appeal has already been reviewed')
            appeal_data = json.loads(row['payload'])
            ev = store.evaluation(row['evaluation_id'],db)
            c = next(c for c in ev['criteria'] if c['criterion_id']==row['criterion_id'])
            config = next(c for c in ev['checklist_snapshot']['criteria'] if c['criterion_id']==row['criterion_id'])
            if body.decision == 'confirmed' and any(v is not None for v in (body.new_score,body.applicable,body.critical_error)):
                raise ValueError('confirmed decision cannot change values')
            if body.decision == 'changed':
                applicable = body.applicable if body.applicable is not None else c['applicable']
                validate_score(config,body.new_score,applicable)
                c.update(final_score=body.new_score, score=body.new_score, applicable=applicable)
                c['answer'] = 'N/A' if not applicable else ('YES' if body.new_score==1 else 'NO') if config['answer_type']=='boolean' else str(body.new_score)
                if config['critical_rule']:
                    critical = applicable and body.new_score == 1
                    if body.critical_error is not None and body.critical_error != critical:
                        raise ValueError('Critical flag inconsistent with reviewed score')
                    c['critical_error'] = critical
                elif body.critical_error is not None:
                    c['critical_error'] = body.critical_error
            total = calculate(ev['criteria'],ev['checklist_snapshot']['rounding_decimals'])
            ev.update(total_score=total,final_total_score=total,critical_error=any(c['critical_error'] for c in ev['criteria']))
            appeal_data.update(status=body.decision,reviewer_decision=body.decision,review_reason=body.reason,
                               reviewed_score=c['final_score'], reviewed_applicable=c['applicable'],
                               reviewed_at=datetime.now(timezone.utc).isoformat(),final_total_score=total)
            db.execute('UPDATE appeals SET status=?,payload=? WHERE id=?',(body.decision,dump(appeal_data),aid))
            db.execute('UPDATE evaluations SET payload=? WHERE id=?',(dump(ev),ev['id']))
        log.info('review completed: %s',aid)
        return appeal_data | {'id':aid,'evaluation':ev}

    return app
