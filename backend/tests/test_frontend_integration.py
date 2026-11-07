import json
import shutil
import socket
import subprocess
import threading
import time
from pathlib import Path

import pytest
import uvicorn

from backend.app import create_app
from backend.tests.test_backend import ai, dataset


def test_frontend_adapter_against_fastapi(tmp_path, monkeypatch):
    monkeypatch.delenv('API_TOKEN', raising=False)
    assert shutil.which('node'), 'Node.js 18+ required for frontend integration'
    app = create_app(tmp_path / 'integration.db', ai)
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level='error'))
    thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 10
        while not server.started and thread.is_alive() and time.monotonic() < deadline:
            time.sleep(.02)
        assert server.started
        script = r'''
import assert from 'node:assert/strict';
const nativeFetch = globalThis.fetch;
globalThis.fetch = (url, options) => nativeFetch(new URL(url, BASE), options);
const {api} = await import('./frontend/js/api.js');
assert.equal((await fetch('/')).status, 200);
assert.match(await (await fetch('/js/app.js')).text(), /evaluation_id:state.evaluation.id/);
await assert.rejects(api.evaluation('missing'), /Conversation not found/);
assert.equal((await api.import(DATA)).imported, 1);
assert.equal((await api.conversation('test-ru')).transcript[0].message_id, 'M1');
let {checklists, active_id} = await api.checklists();
let config = checklists.find(c => c.id === active_id);
const first = await api.evaluate('test-ru');
assert.equal(first.criteria[0].weight, 10);
assert.equal(first.criteria[0].evidence[0].message_id, 'M1');
assert.equal(first.total_score, 0);
assert.ok(Object.keys(first.section_scores).length);
config.name = 'Integration version';
const saved = await api.saveChecklist(config.id, config);
assert.equal(saved.version, 2);
assert.deepEqual(saved.criteria.map(c => c.scale), config.criteria.map(c => c.scale));
assert.equal((await api.history('test-ru'))[0].checklist_version, 1);
const appeal = async criterion_id => api.appeal({conversation_id:'test-ru', evaluation_id:first.id, criterion_id, comment:'Check'});
let a = await appeal('contact');
assert.equal((await api.list())[0].status, 'appealed');
await assert.rejects(appeal('contact'), /already pending/);
await api.review(a.id, {decision:'changed', new_score:'YES', reason:'Greeting exists'});
assert.equal((await api.evaluation('test-ru')).total_score, 10);
assert.equal((await api.appeals())[0].status, 'reviewed');
assert.equal((await api.list())[0].status, 'reviewed');
a = await appeal('needs');
await api.review(a.id, {decision:'changed', new_score:'NA', reason:'Not applicable'});
let ev = await api.evaluation('test-ru');
assert.equal(ev.criteria.find(c=>c.criterion_id==='needs').answer, 'NA');
assert.equal(ev.criteria.find(c=>c.criterion_id==='needs').score, null);
a = await appeal('critical');
await api.review(a.id, {decision:'confirmed', new_score:'YES', reason:'Confirm without changing score'});
assert.equal((await api.evaluation('test-ru')).critical_error, false);
assert.equal((await api.evaluate('test-ru')).checklist_version, 2);
await assert.rejects(api.import({data:{}}), /dataset_group_id/);
console.log('Frontend/FastAPI integration passed');
'''
        script = script.replace('BASE', json.dumps(f'http://127.0.0.1:{port}')).replace('DATA', json.dumps(dataset()))
        result = subprocess.run(['node', '--input-type=module', '-e', script], cwd=Path(__file__).resolve().parents[2], capture_output=True, text=True, timeout=30, encoding='utf-8')
        assert result.returncode == 0, result.stdout + result.stderr
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
