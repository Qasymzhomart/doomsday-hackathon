import copy
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.app import create_app
from backend.services import import_dataset
from backend.scoring import calculate, validate_result


def dataset(group='DEV', cid='test-ru'):
    return {'isSuccess':True,'error':'','data':{'dataset_group_id':group,'total_records':1,'records':[
        {'conversation_id':cid,'channel':'agent chat','language':'RU','audio_url':None,'transcript':[
            {'timestamp':'00:02','speaker':'operator','text':'Здравствуйте!'},
            {'timestamp':'00:02','speaker':'bot','text':'Здравствуйте!'},
            {'timestamp':'2026-01-01T00:00:00Z','speaker':'system','text':'context'}]}]}}


def ai(conversation, checklist):
    return {'criteria':[{'criterion_id':c['criterion_id'],'applicable':True,
        'score':0,'answer':'NO' if c['answer_type']=='boolean' else '0',
        'reason':'Test reason','evidence_ids':['M1'],'critical_error':False} for c in checklist['criteria']]}


@pytest.fixture
def client(tmp_path):
    app = create_app(tmp_path/'test.db',ai)
    import_dataset(app.state.store,dataset(),'DEV')
    return TestClient(app)


def test_weighted_score_and_na():
    rows=[{'original_weight':20,'final_score':1,'max_score':1,'applicable':True},
          {'original_weight':80,'final_score':4,'max_score':5,'applicable':True}]
    assert calculate(rows)==84
    rows=[{'original_weight':w,'final_score':1 if i!=1 else None,'max_score':1,'applicable':i!=1} for i,w in enumerate([10,20,40,30])]
    assert calculate(rows)==100
    assert [r['effective_weight'] for r in rows]==[12.5,0,50,37.5]
    assert calculate([{'original_weight':0,'final_score':1,'max_score':1,'applicable':True}]) is None


def test_import_preserves_data_and_control(client):
    store=client.app.state.store
    original=client.get('/api/conversations/test-ru').json()
    assert original['transcript'][1]=={'timestamp':'00:02','speaker':'bot','text':'Здравствуйте!','message_id':'M2'}
    assert original['transcript'][2]['timestamp']=='2026-01-01T00:00:00Z'
    assert import_dataset(store,dataset(),'DEV')['skipped']==1
    import_dataset(store,dataset('CONTROL','control-1'),'CONTROL')
    assert len(client.get('/api/conversations').json())==2
    conflicting=dataset(); conflicting['data']['records'][0]['transcript'][0]['text']='changed'
    with pytest.raises(ValueError): import_dataset(store,conflicting,'DEV')
    assert store.conversation('test-ru')==original


def test_evidence_and_ai_validation(client):
    store=client.app.state.store
    c,k=store.conversation('test-ru'),store.checklist()
    raw=ai(c,k); raw['criteria'][0]['evidence_ids']=['M999','M1']
    rows,warnings=validate_result(raw,k,c)
    assert warnings and rows[0]['evidence']==[c['transcript'][0]]
    for edit in [dict(score=8),dict(applicable=False,score=None,answer='N/A'),dict(score=True),dict(reason='  '),dict(score=float('nan'))]:
        invalid=ai(c,k); invalid['criteria'][0].update(edit)
        with pytest.raises(ValueError): validate_result(invalid,k,c)
    invalid=ai(c,k); invalid['criteria'][3]['score']=8
    with pytest.raises(ValueError): validate_result(invalid,k,c)
    for invalid in [{'criteria':raw['criteria'][:-1]}, {'criteria':raw['criteria']+[raw['criteria'][0]]}]:
        with pytest.raises(ValueError): validate_result(invalid,k,c)


def test_appeal_and_versioning(client):
    ev=client.post('/api/evaluate/test-ru',json={}).json()
    assert ev['status']=='completed' and ev['total_score']==0
    appeal=client.post('/api/appeals',json={'conversation_id':'test-ru','evaluation_id':ev['id'],'criterion_id':'contact','comment':'Review greeting'}).json()
    result=client.post(f"/api/appeals/{appeal['id']}/review",json={'decision':'changed','new_score':1,'reason':'Greeting exists'}).json()['evaluation']
    assert result['criteria'][0]['original_score']==0
    assert result['criteria'][0]['final_score']==1
    assert result['original_total_score']==0 and result['final_total_score']==10
    assert result['original_ai_result']['criteria'][0]['score']==0
    assert client.post(f"/api/appeals/{appeal['id']}/review",json={'decision':'confirmed','reason':'again'}).status_code==409
    config=json.loads(Path('backend/checklist.json').read_text(encoding='utf-8'))
    config['criteria'][0]['description']='Updated criterion'
    new=client.put('/api/checklists/1',json=config).json()
    assert new['version']==2
    second=client.post('/api/evaluate/test-ru',json={}).json()
    assert second['checklist_version']==2
    history=client.get('/api/conversations/test-ru/evaluations').json()
    assert history[0]['checklist_version']==1
    assert history[0]['checklist_snapshot']['criteria'][0]['description']!=config['criteria'][0]['description']


def test_retry_and_failure(client):
    calls=[]
    def broken(c,k):
        calls.append(1)
        return {'criteria':[]}
    client.app.state.evaluator=broken
    assert client.post('/api/evaluate/test-ru',json={}).status_code==502
    assert len(calls)==2
    assert client.get('/api/evaluations/test-ru').json()['status']=='failed'
    calls.clear()
    def once(c,k):
        calls.append(1)
        return ai(c,k) if len(calls)==2 else {'criteria':[]}
    client.app.state.evaluator=once
    assert client.post('/api/evaluate/test-ru',json={}).status_code==200
    assert len(calls)==2


def test_na_review_and_critical(client):
    ev=client.post('/api/evaluate/test-ru',json={}).json()
    for criterion, fields in [('needs',{'applicable':False}),('critical',{'new_score':1})]:
        a=client.post('/api/appeals',json={'conversation_id':'test-ru','evaluation_id':ev['id'],'criterion_id':criterion,'comment':'Review'}).json()
        r=client.post(f"/api/appeals/{a['id']}/review",json={'decision':'changed','reason':'Reviewed',**fields})
        assert r.status_code==200,r.text
    final=client.get('/api/evaluations/test-ru').json()
    assert final['critical_error'] is True and final['total_score']==0
    assert final['criteria'][1]['effective_weight']==0
    assert final['criteria'][0]['effective_weight']==pytest.approx(10/85*100)


def test_api_auth(client,monkeypatch):
    monkeypatch.setenv('API_TOKEN','test-secret')
    assert client.get('/api/conversations').status_code==401
    assert client.get('/api/conversations',headers={'Authorization':'Bearer test-secret'}).status_code==200
    assert client.get('/health').status_code==200


def test_ai_http_adapter(monkeypatch):
    from backend import services
    monkeypatch.setenv('AI_API_KEY','dummy')
    monkeypatch.setenv('AI_BASE_URL','https://example.test/v1')
    def post(url, **kwargs):
        assert url=='https://example.test/v1/chat/completions'
        assert kwargs['headers']['Authorization']=='Bearer dummy'
        assert kwargs['json']['response_format']=={'type':'json_object'}
        class Response:
            def raise_for_status(self): pass
            def json(self): return {'choices':[{'message':{'content':'{"criteria":[]}'}}]}
        return Response()
    monkeypatch.setattr(services.httpx,'post',post)
    assert services.call_ai({}, {})=={'criteria':[]}


def test_organizer_group_replacement(monkeypatch):
    from backend import services
    monkeypatch.setenv('ORGANIZER_API_URL','https://example.test/api?sig=secret&group_id=DEV')
    def get(url,**kwargs):
        from urllib.parse import urlsplit,parse_qs
        assert parse_qs(urlsplit(url).query)=={'sig':['secret'],'group_id':['CONTROL']}
        class Response:
            def raise_for_status(self): pass
            def json(self): return dataset('CONTROL','new')
        return Response()
    monkeypatch.setattr(services.httpx,'get',get)
    assert services.download_dataset('CONTROL')['isSuccess']
