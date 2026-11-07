# Freedom Broker CQA — Hackathon MVP

Working HTML/CSS/JavaScript frontend and Node.js (no dependencies) API for conversation quality assessment, evidence navigation, appeals, reviewer decisions and editable checklists. Based on the provided **CQA Chat Quality Checklist** and **Hackathon Student Guide**.

## Run

Requires Node.js 18+.

```bash
npm start
# open http://localhost:3000
npm test
```

Three clearly labelled **synthetic demo conversations** (RU/KZ/EN) are included for testing. **The organizer's 65 real DEV records are NOT bundled.** Import them from a local JSON file in the app, or use the organizer GET URL with a server-side allowlisted host:

```bash
ALLOW_REMOTE_IMPORT_HOST=example.org npm start
```

Then use **Импорт JSON / DEV**. Replace `example.org` with the exact hostname from the organizer link. Only HTTPS, exact hostname matches and valid `data.records` responses are allowed. An importer for uploaded JSON accepts `{data:{records:[...]}}`, `{records:[...]}` or an array. Data persists to `server/store.json` (gitignored); choose `DATA_FILE` to change location.

## Demo flow

1. Open **Диалоги**, filter RU/KZ/EN, select a conversation.
2. Click **Запустить оценку**, inspect section scores, criteria and N/A.
3. Click an evidence link to scroll/highlight its source message.
4. Click **Апелляция**, write a comment, submit.
5. Open **Апелляции**, use reviewer **Confirm** or **Change** (with reason), see recalculated final score.
6. Open **Чек-лист**, edit/insert/remove a criterion, save, re-evaluate a conversation.
7. Upload organizer transcripts for actual dataset evaluation; voice records expose an audio player/link when `audio_url` exists.

## Important model limitation

**The initial evaluator is a transparent rule-based heuristic demonstration, not an LLM/AI quality judge**. It cannot reliably determine advice correctness, client intent, confidentiality leakage or nuanced empathy. All inferred explanations are flagged as heuristic; reviewers can revise ratings. Unknown new criteria default to a placeholder evaluation and require manual review. Do **not** use these scores to make employment decisions. Plug a model/service into `server/evaluator.js` before using production claims of automatic assessment.

## Scoring

Default checklist: weights 10,15,20,20,15,15,5 = 100; criterion 8 (critical violation) is unweighted and flagged separately. Consultation levels: 0/5/10/15/20; dialogue clarity levels: 0/4/7/10. Boolean YES receives full weight; NO 0; N/A criteria excluded and remaining weights rescaled to 100; if all weighted criteria N/A, score is null. Round to 2 decimal places. Three-minute first-response SLA, tags and attachments are excluded.

## API

| Method | Endpoint | Purpose |
|--|--|--|
| GET | `/api/conversations` | Listing, score/status |
| GET | `/api/conversations/:id` | Transcript with stable message IDs |
| POST | `/api/conversations/import` | Import JSON transcript records |
| POST | `/api/conversations/import-url` | Restricted organizer GET importer |
| POST | `/api/evaluate/:id` | Evaluate with active checklist |
| GET | `/api/evaluations/:id` | Evidence-based result |
| GET | `/api/appeals` | Appeals and reviewer decisions |
| POST | `/api/appeals` | Submit appeal |
| POST | `/api/appeals/:id/review` | Confirm/change rating, update total |
| GET | `/api/checklists` | Active checklist and configurations |
| GET | `/api/checklists/:id` | Checklist details |
| PUT | `/api/checklists/:id` | Save new version, activate |
| POST | `/api/checklists` | Create checklist |

No login (required by hackathon). Backend is a local demonstration server, **not production-hardened**: add authentication, authorization, concurrency-safe persistence, rate limits and a protected model API before deployment. For Dynamics 365, embed the frontend shell as a web resource and replace the REST API adapter in `frontend/js/api.js`.

## Structure

- `frontend/index.html`, `frontend/css/styles.css` — lightweight responsive HTML UI.
- `frontend/js/api.js` — centralized network adapter.
- `frontend/js/app.js` — dashboard, conversation, evaluation, evidence, appeals, reviewer, checklist editor.
- `server/checklist.js` — default checklist and validation.
- `server/evaluator.js` — scoring and explicitly heuristic evaluator.
- `server/index.js` — API, import, persistence, static hosting.
- `tests/scoring.test.js` — scoring contract tests.

## Python Backend / Data (AI + SQLite)

The implementation of `backend_data_tasks.txt` is in [`backend/`](backend/README.md). It provides the organizer DEV/CONTROL importer, immutable checklist versions, Gemini-compatible AI evaluator, strict response validation, weighted scoring with N/A, evidence mapping and audited appeals/reviews. Start it from the repository root with `python -m backend` after following the [backend setup](backend/README.md). API docs: `http://127.0.0.1:8000/docs`.

The Python API runs independently on port 8000; the existing `npm start` demo retains its heuristic evaluator. Its frontend must be connected to the [Python API contract](backend/README.md#api-для-frontend) to use real AI. The organizer's 65 DEV conversations were imported and verified locally; datasets, SQLite files, signed organizer URLs and API keys are excluded from Git. Real Gemini evaluation requires your own free-tier key in `backend/.env`.

