import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


def dump(value):
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS conversations (
                id TEXT PRIMARY KEY, group_id TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS checklists (
                id INTEGER PRIMARY KEY, family INTEGER NOT NULL, version INTEGER NOT NULL,
                active INTEGER NOT NULL, payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP, UNIQUE(family,version));
            CREATE TABLE IF NOT EXISTS evaluations (
                id INTEGER PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id),
                checklist_id INTEGER NOT NULL REFERENCES checklists(id), status TEXT NOT NULL,
                payload TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE IF NOT EXISTS appeals (
                id INTEGER PRIMARY KEY, evaluation_id INTEGER NOT NULL REFERENCES evaluations(id),
                criterion_id TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE INDEX IF NOT EXISTS evaluation_conversation ON evaluations(conversation_id,id);
            ''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def checklist(self, cid=None, db=None):
        if db is None:
            with self.connect() as conn:
                return self.checklist(cid, conn)
        row = db.execute('SELECT * FROM checklists WHERE id=?', (cid,)).fetchone() if cid is not None else db.execute(
            'SELECT * FROM checklists WHERE active=1 ORDER BY id DESC LIMIT 1').fetchone()
        if not row:
            raise LookupError('Checklist not found')
        return {**json.loads(row['payload']), 'id': row['id'], 'version': row['version'], 'family': row['family'], 'is_active': bool(row['active'])}

    def save_checklist(self, config, previous=None):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            old = self.checklist(previous, db) if previous is not None else None
            family = old['family'] if old else db.execute('SELECT COALESCE(MAX(family),0)+1 FROM checklists').fetchone()[0]
            version = db.execute('SELECT COALESCE(MAX(version),0)+1 FROM checklists WHERE family=?', (family,)).fetchone()[0]
            db.execute('UPDATE checklists SET active=0 WHERE family=?', (family,))
            cid = db.execute('INSERT INTO checklists(family,version,active,payload) VALUES(?,?,1,?)', (family,version,dump(config))).lastrowid
            return self.checklist(cid, db)

    def conversation(self, cid):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM conversations WHERE id=?', (cid,)).fetchone()
            if not row:
                raise LookupError('Conversation not found')
            return json.loads(row[0])

    def evaluation(self, eid, db=None):
        if db is None:
            with self.connect() as conn:
                return self.evaluation(eid, conn)
        row = db.execute('SELECT * FROM evaluations WHERE id=?', (eid,)).fetchone()
        if not row:
            raise LookupError('Evaluation not found')
        return {**json.loads(row['payload']), 'id': row['id'], 'status': row['status'], 'created_at': row['created_at']}
