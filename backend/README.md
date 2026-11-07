# CQA Backend / Data

Python 3.12+, FastAPI, SQLite. Реализация задания `backend_data_tasks.txt` и официального CQA checklist. Backend самостоятельно считает score; AI возвращает только оценки критериев и ссылки на реплики.

## Быстрый запуск (из корня репозитория)

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
# Заполните AI_API_KEY и ORGANIZER_API_URL в backend/.env
python -m backend.import_dataset DEV
python -m backend
```

API: http://127.0.0.1:8000, Swagger: http://127.0.0.1:8000/docs, health: `/health`.
Linux/macOS: `source .venv/bin/activate`, `cp backend/.env.example backend/.env`.

Если `backend/.env` уже существует, сохраните его значения. `DATABASE_URL` поддерживает SQLite, путь относительно текущего каталога. Запускайте команды из корня проекта. Никакие демонстрационные оценки автоматически не выдаются за AI: без ключа запрос оценки вернёт 502, а запись получит status=failed.

## Бесплатный AI API

По умолчанию настроен Gemini `gemini-2.5-flash` через OpenAI-compatible HTTP endpoint. Создайте ключ в [Google AI Studio](https://aistudio.google.com/apikey), добавьте его в `AI_API_KEY` локально. Проверяйте доступность модели и бесплатной квоты для своего проекта в [тарифах Gemini](https://ai.google.dev/gemini-api/docs/pricing). Лимиты могут ограничивать пакетную оценку 65 диалогов; платное подключение автоматически не включается. Используйте проект с бесплатной квотой без включения billing. При 429 запрос повторяется один раз, затем сохраняется failed; после восстановления квоты можно запустить новую оценку.

```dotenv
AI_API_KEY=your_local_key
AI_MODEL=gemini-2.5-flash
AI_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

Провайдер можно заменить через `AI_BASE_URL` и `AI_MODEL`, без изменения кода. [Документация совместимости Gemini](https://ai.google.dev/gemini-api/docs/openai).

## Данные организаторов

`ORGANIZER_API_URL` — полный GET URL из кликабельной ссылки на стр. 3 Student Guide. Ссылка содержит подпись доступа: храните её в `.env`, не публикуйте в GitHub. Для CONTROL меняется только `group_id` в query, подпись и остальные параметры сохраняются.

```powershell
python -m backend.import_dataset DEV
python -m backend.import_dataset CONTROL_ID
# Или импорт заранее скачанного полного JSON-ответа:
python -m backend.import_dataset DEV --file backend/data/dev.json
```

`POST /api/datasets/import` с `{"group_id":"CONTROL_ID"}` делает то же самое. DEV импорт проверен локально: 65 записей (RU 35, KZ 15, EN 15; 60 чатов, 5 звонков). Реальные транскрипты, аудиоссылки, база данных и подписанный URL не входят в публичный репозиторий. На новой машине импорт обязателен.

Импорт транзакционный: при некорректной записи весь набор отклоняется. Повторный одинаковый импорт идемпотентен. Изменившийся transcript или совпадение conversation_id между разными группами отклоняются, исходные данные и оценки сохраняются. Время, роли bot/system, текст и audio_url сохраняются дословно; каждой реплике добавляется M1, M2… независимо от совпадения текстов.

## API для frontend

| Метод | Путь | Назначение |
|---|---|---|
| GET | `/api/conversations` | Список; фильтры language, channel, status, group_id |
| GET | `/api/conversations/{conversation_id}` | Полный transcript с message_id |
| POST | `/api/datasets/import` | Импорт группы организаторов |
| GET | `/api/checklists` | Массив всех версий |
| GET | `/api/checklists/{id}` | Неизменяемая версия |
| POST | `/api/checklists` | Создать семейство, вернуть числовой id |
| PUT | `/api/checklists/{id}` | Создать следующую версию, вернуть новый id |
| POST | `/api/evaluate/{conversation_id}` | Body: `{}` либо `{"checklist_id":1}` |
| GET | `/api/evaluations/{conversation_id}` | Последняя попытка, включая failed |
| GET | `/api/conversations/{conversation_id}/evaluations` | Вся история |
| POST | `/api/appeals` | Создать апелляцию |
| GET | `/api/appeals` | Список; фильтр status |
| POST | `/api/appeals/{id}/review` | Подтвердить или изменить оценку |

Это самостоятельный backend на порту 8000. Существующий Node server и frontend остаются отдельным демонстрационным приложением: `npm start` сам по себе не переключает его на Python AI evaluator. При подключении frontend используйте эту таблицу/OpenAPI: checklist/evaluation/appeal id — числа, checklists — массив; appeal требует evaluation_id; review new_score — число, N/A = applicable:false и new_score:null. CORS_ORIGINS задаёт адреса frontend. Это контракт для frontend-разработчика, а не совместимость со старым heuristic API.

### Пример полного сценария

```powershell
$base = 'http://127.0.0.1:8000'
Invoke-RestMethod "$base/api/conversations?language=RU"
$e = Invoke-RestMethod "$base/api/evaluate/p1-ru-001" -Method Post -ContentType 'application/json' -Body '{}'
$body = @{conversation_id='p1-ru-001'; evaluation_id=$e.id; criterion_id='contact'; comment='Проверьте приветствие'} | ConvertTo-Json
$a = Invoke-RestMethod "$base/api/appeals" -Method Post -ContentType 'application/json' -Body $body
$review = @{decision='changed'; new_score=1; reason='Приветствие и представление подтверждены репликой M2'} | ConvertTo-Json
Invoke-RestMethod "$base/api/appeals/$($a.id)/review" -Method Post -ContentType 'application/json' -Body $review
```

Для подтверждения: `{"decision":"confirmed","reason":"Исходная оценка верна"}`. Для исправления N/A: `{"decision":"changed","applicable":false,"new_score":null,"reason":"Условие N/A выполнено"}`. Для возврата из N/A задайте applicable:true и числовой new_score. Сервер проверяет шкалу, допустимость N/A и critical flag. Повторное рассмотрение возвращает 409. Изменения применяются атомарно; другая апелляция не теряет уже принятые изменения.

### Обновление чек-листа

GET версии, затем PUT её конфигурации (name, criteria, rounding_decimals), без служебных id/version/family/is_active. Новые критерии и описания передаются модели автоматически. Для шкал задавайте allowed_scores. Предыдущие версии не изменяются; evaluation хранит checklist_snapshot и checklist_version. По умолчанию следующая evaluation использует последнюю активную версию; старую можно выбрать явно.

## Формула и аудит

`effective_weight = weight / sum(applicable weights) * 100`, `contribution = final_score / max_score * effective_weight`. N/A имеет null score и нулевой вес. Промежуточные расчёты Decimal, округление итоговой суммы до двух знаков ROUND_HALF_UP. Если нет применимых весов, total_score=null. Грубая ошибка без веса отмечается отдельно и итог не обнуляет. В официальном PDF режим половинного округления не уточнён; выбран ROUND_HALF_UP.

Шкалы: консультация 0/5/10/15/20, управление диалогом 0/4/7/10. Полная конфигурация в `backend/checklist.json` загружается только при первой инициализации БД; дальнейшие изменения через API. Правило первой реакции в 3 минуты, теги и вложения не участвуют.

AI JSON проверяется на полноту, дубли, диапазоны, дискретные ступени, типы и согласованность YES/NO/N/A. Неизвестный evidence_id исключается из mapped evidence с warning; исходный ответ сохраняется для аудита. В evidence возвращаются только реальные реплики. Неудачный вызов/невалидный JSON повторяется один раз. Статусы processing/completed/failed сохраняются в SQLite.

В evaluation неизменяемы original_ai_result, original_score, original_applicable, original_critical_error, original_answer, original_total_score, evidence и checklist_snapshot. Reviewer меняет final_score, applicable, answer и critical_error; final_total_score пересчитывается. Апелляция хранит исходную оценку, состояние при подаче, комментарий, решение, обоснование и время review.

Хранение: SQLite tables conversations/checklists/evaluations/appeals с внешними ключами и JSON payload. Messages, criteria и evidence находятся внутри атомарных JSON snapshots вместо отдельных таблиц — для 65 записей это сохраняет контракт и упрощает аудит. WAL, транзакции и BEGIN IMMEDIATE защищают изменение версий и review от потери параллельных обновлений.

## Проверка

```powershell
python -m pytest backend/tests -q
```

Тесты не требуют ключа и не отправляют данные AI. Проверяют 84 балла, веса N/A, отсутствие применимых весов, неверные evidence, недопустимые шкалы/типы, сохранность данных, CONTROL импорт, апелляции, перерасчёт, версии, retry, провайдерский HTTP контракт и auth. Реальный вызов AI требует ключа и отдельно проверяется после его добавления. Семантическое качество модели не подтверждается unit-тестами.

Сервер привязан к 127.0.0.1, логин для хакатона не требуется. При внешнем доступе задайте API_TOKEN: все `/api/*` потребуют `Authorization: Bearer ...`. Это общий токен, отдельные роли operator/reviewer не реализованы. Batch queue, Redis и production deployment вне текущего backend MVP.
