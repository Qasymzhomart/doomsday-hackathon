# Freedom Broker CQA — Hackathon MVP

Existing HTML/CSS/JavaScript UI connected to the Python FastAPI backend with SQLite, AI evaluation, versioned checklists and audited appeals. UI and API share one origin.

## Run

Python 3.10+ is required. From the repository root (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
# Fill AI_API_KEY, AI_MODEL, AI_BASE_URL and ORGANIZER_API_URL in backend/.env
python -m backend
# Or: npm start (requires Node.js)
```

Open http://127.0.0.1:8000. API docs: http://127.0.0.1:8000/docs. `PORT` overrides 8000. SQLite defaults to `backend/data/cqa.db`. Do not overwrite an existing `.env` when updating.

The initial database contains the official checklist and no conversations. Import an organizer JSON response via **Импорт JSON / DEV**, or enter DEV / CONTROL to download via the server-configured `ORGANIZER_API_URL`. Uploaded JSON must contain `isSuccess: true` and `data` with `dataset_group_id`, `total_records`, and `records`. Keys, signed URLs, actual datasets and databases stay outside Git.

AI evaluation requires a working provider key and quota. Provider failures appear in the UI; no heuristic score is substituted. Section scores display percentages within each section; the total uses all applicable weighted criteria and redistributes N/A weight. Critical violations are flagged separately.

## Demo flow

1. Open **Диалоги**, filter RU/KZ/EN, select a conversation.
2. Click **Запустить оценку**, inspect section scores, criteria and N/A.
3. Click an evidence link to scroll/highlight its source message.
4. Click **Апелляция**, write a comment, submit.
5. Open **Апелляции**, use reviewer **Confirm** or **Change** (with reason), see recalculated final score.
6. Open **Чек-лист**, edit/insert/remove a criterion, save, re-evaluate a conversation.
7. Upload organizer transcripts for actual dataset evaluation; voice records expose an audio player/link when `audio_url` exists.

## API and frontend adapter

`frontend/js/api.js` translates FastAPI payloads into the existing UI model. Checklist writes send only editable schema fields, retain scale ranges and rounding precision, and receive a new immutable version ID. Appeals include the evaluation ID. Reviews use that evaluation's checklist snapshot, convert YES/NO/NA to numeric scores/applicability, and confirmation sends no score changes.

- `GET /api/conversations`, `GET /api/conversations/{id}`
- `POST /api/conversations/import`: organizer JSON envelope
- `POST /api/datasets/import`: `{ "group_id": "DEV" }`, using server configuration
- `POST /api/evaluate/{id}`, `GET /api/evaluations/{id}`
- `GET /api/conversations/{id}/evaluations`: immutable version snapshots
- `GET/POST /api/checklists`, `GET/PUT /api/checklists/{id}`
- `GET/POST /api/appeals`, `POST /api/appeals/{id}/review`

By default the hackathon UI needs no login. If `API_TOKEN` is configured, set `sessionStorage.setItem('cqa_api_token', 'your-token')` in the browser console for this origin, then reload. Never put AI provider keys in the browser.

## Validation

```powershell
python -m pytest backend/tests -q --basetemp=../pytest-temp
npm test
```

Node.js 18+ is required for the frontend-to-FastAPI integration test, which runs the real JavaScript adapter against a temporary HTTP server/database and a deterministic AI stub. It covers import, transcript/evidence, checklist save/versioning, evaluation, appeal, confirm/change and N/A. Live provider evaluation needs your credentials and is separate from these tests.

## Structure

- `frontend/`: existing UI and FastAPI adapter
- `backend/`: API, static hosting, SQLite, scoring, imports and AI provider integration; see [backend setup](backend/README.md)
- `backend/tests/`: backend and JavaScript-to-FastAPI integration tests
- `server/`, `tests/`: legacy standalone Node heuristic demo and its tests

The old Node demo remains available explicitly with `npm run start:demo` on port 3000. Its API contract and UI adapter differ; it is retained for legacy reference, while `npm start` runs the integrated Python application.
