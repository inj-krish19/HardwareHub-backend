# Hardware Hub: backend

The API behind Hardware Hub, a chatbot-first PC troubleshooting and hardware education platform.

**The core claim: every answer comes from a hand-written decision tree.** Nothing is generated,
so there are no invented fixes. Any machine learning we add later may only choose _which_ guide
to open or read the person's input; it never writes the answer.

- Stack: FastAPI, Pydantic 2, SQLAlchemy 2, PostgreSQL (psycopg v3). Neon in production.
- The frontend is a separate repository (Next.js). This repository is the API only.
- Database diagram: [docs/ERD.md](docs/ERD.md).

## How an answer is produced

```
person types a message
  -> Layer 1  rule_engine/router.py      guess the kind of question (regex). Only a hint.
  -> matcher  rule_engine/matcher.py     score every guide, suggest up to 3
  -> person picks a guide
  -> Layer 2  rule_engine/tree_walker.py replay their answers through the guide's decision tree
  -> Layer 3  rule_engine/formatter.py   shape the text with fixed templates
```

- **Matching** is plain scoring, no model: +1 per query word in the guide title, +2 per word in
  its keywords, +3 when a whole keyword phrase is contained in the message, +4 when the message
  is exactly a keyword phrase, +1 when the guide belongs to the bot the router guessed. A guide
  needs at least 2 points to count, and a runner-up must reach 40% of the best score. Words are
  lower-cased, common words are ignored and a very light stemmer maps `dusty` to `dust`.
- **The tree walker is stateless.** The browser sends the guide and the list of answers so far,
  and the server replays them from the root. Nothing about a conversation is stored.
- **Final answers** are numbered steps. A final answer is either a fix (`conclusion`) or
  "needs a professional" (`escalate`). For the second kind the chat offers a copyable summary
  for a technician (`POST /chat/report`), built from the same replay.
- **Guides the matcher misses** are logged (text only, no identity) so an admin can turn each miss
  into a keyword. See "Missed queries" below.

## Setup (Windows PowerShell)

You need Python 3.12 or newer and a PostgreSQL database.

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
```

Create `backend/.env`. There are deliberately no defaults, so the app refuses to start if one is missing:

```dotenv
DATABASE_URL = postgresql://user:password@host:5432/dbname
CORS_ORIGIN = http://localhost:3000
ADMIN_ID = choose-an-id
ADMIN_SECRET = at-least-16-characters-long-and-random
# Optional, only for the API tests (see Tests):
# TEST_DATABASE_URL = postgresql://user:password@host:5432/dbname
```

| Variable                   | Meaning                                                                                                                                                                        |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `DATABASE_URL`             | PostgreSQL URL. `postgresql://` is rewritten to `postgresql+psycopg://` for you, so Neon's URL works as it is.                                                                 |
| `CORS_ORIGIN`              | Allowed frontend origin. Several can be given, comma-separated: `http://localhost:3000,https://yourapp.vercel.app`.                                                            |
| `ADMIN_ID`, `ADMIN_SECRET` | The one shared admin login. The secret must be at least 16 characters or the app will not start. Make one with `python -c "import secrets; print(secrets.token_urlsafe(32))"`. |
| `TEST_DATABASE_URL`        | Optional. Turns on the database-backed API tests.                                                                                                                              |

Create the tables, load the guides and run the API:

```powershell
python -m app.db.sync_schema        # creates tables, adds missing columns and indexes, gives guides their slugs
python -m app.db.seed               # loads app/data/seed/*_symptoms.json (skips titles that already exist)
uvicorn app.main:app --reload       # http://localhost:8000, interactive docs at /docs
```

Products and their media are loaded from the admin panel (Bulk import), see below.

## Changing the database

There is no Alembic. Instead:

- `python -m app.db.sync_schema` makes an existing database match the models. It only adds
  (tables, columns, indexes), never drops or deletes, and is safe to run again.
- `python -m app.db.sync_schema --print-sql` prints the same changes as plain SQL. The result is
  checked in as [sync_schema.sql](sync_schema.sql), for the Neon SQL editor.
- After you change a model, regenerate the diagram (a test fails until you do):

  ```powershell
  python -m app.db.erd > docs/erd.mmd
  python -m app.db.erd --markdown > docs/ERD.md
  python -m app.db.sync_schema --print-sql > sync_schema.sql
  ```

## Guides

A guide is one JSON object, and a file is a list of them (`app/data/seed/*_symptoms.json`):

```json
{
  "title": "No power / PC will not turn on",
  "category": "PSU",
  "bot_type": "diagnostic",
  "keywords": ["pc won't turn on", "nothing happens when i press power"],
  "question_tree": {
    "id": "q1",
    "question": "Does anything happen when you press the power button?",
    "options": [
      {
        "answer": "Nothing at all",
        "next": { "type": "conclusion", "text": "1. Check the cable.\n2. ..." }
      },
      {
        "answer": "It tries then stops",
        "next": { "type": "escalate", "text": "1. ...\n2. ..." }
      }
    ]
  }
}
```

- `bot_type` is one of `diagnostic`, `compatibility`, `budget`, `upgrade`, `maintenance`.
- Titles must be unique (ignoring case); uploading a title that exists is skipped and reported.
- A guide gets its URL slug when created (`/guides/no-power-pc-will-not-turn-on`) and keeps it
  even if the title is edited later.
- Writing rules: plain language for non-technical people, jargon explained in brackets the first
  time, a list of casual `keywords` phrasings, and every final answer is 2 to 4 detailed numbered steps.

## Admin

All `/api/v1/admin/*` routes need the headers `X-Admin-Id` and `X-Admin-Secret`. The frontend's
`/admin` pages use them. What the admin can do: bulk-import guides, products with their write-ups,
and images, videos and store links (matched by model number); edit a guide's keywords; read the
feedback summary; and work through the missed queries below.

### Missed queries

When a message matches no guide, its text is stored (once per wording, with a counter) in
`unmatched_query`. **Only the text is stored: no user id, no IP address and no per-message
timestamp.** Messages that look like an email address or contain a run of 7 or more digits are
not stored, and storage stops at 5000 distinct wordings. In the admin panel, "Missed queries" shows them
most-repeated first; one click adds a phrase to the right guide's keywords and says whether the message now
finds it. "Download as evaluation set" exports them in the format of `scripts/match_eval_queries.json`.

## Tests

```powershell
python -m pytest
```

- Most tests are pure (matcher, tree walker, slugs, privacy rules, the technician report, the
  admin login, the diagram, the tester kit). They need no database.
- The **API tests** talk to a real PostgreSQL and run only when `TEST_DATABASE_URL` is set (in the
  environment or in `backend/.env`). **They are safe to point at a database with real data:** every
  test runs inside a transaction that is always rolled back, nothing is ever committed, there is
  no `TRUNCATE` or `DELETE`, the schema is never changed, and what a test creates carries a random
  `ztest...` name. A tripwire fails the run if anything tries to commit, and at the end it checks that
  no test data was left behind. On a read-only database or replica they skip themselves.
  If they say the database is behind the code, run `python -m app.db.sync_schema`.

**Measuring the matcher** (how often the right guide is suggested):

```powershell
python scripts/match_eval.py app/data/seed scripts/match_eval_queries.json
```

It prints top-1 and top-3 accuracy with 95% intervals, a breakdown by kind of question, and every miss.
A query whose guide is not in the folder is skipped and counted. Use a _separate_ set of queries from
testers for any final claim: once you tune keywords to the misses, the set that drove the tuning stops
being an honest test. The kit for collecting that set (scenario cards, an offline tester page, an importer)
is in `scripts/heldout/`, with the full protocol in [docs/HELDOUT_EVALUATION.md](docs/HELDOUT_EVALUATION.md).

## API

Generated from the running app. Interactive docs are at `/docs`.

| Method | Path                                                                                                              | Notes                                                           |
| ------ | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| GET    | `/health`                                                                                                         | liveness check                                                  |
| POST   | `/api/v1/chat/start`                                                                                              | message to up to 3 suggested guides, or a clarifying list       |
| POST   | `/api/v1/chat/symptom-selection`                                                                                  | open a guide by its title                                       |
| POST   | `/api/v1/chat/bot-selection`                                                                                      | list the guides of one bot                                      |
| POST   | `/api/v1/chat/confirm`                                                                                            | the "None of these" answer (and the older confirm step)         |
| POST   | `/api/v1/chat/answer`                                                                                             | replay an answer path, return the next question or final answer |
| POST   | `/api/v1/chat/feedback`                                                                                           | anonymous "did this fix it?" vote on a final answer             |
| POST   | `/api/v1/chat/report`                                                                                             | technician summary, only for "needs a professional" answers     |
| GET    | `/api/v1/guides`                                                                                                  | every guide (slug, title, category, bot type)                   |
| GET    | `/api/v1/guides/{slug}`                                                                                           | one guide with its whole decision tree and related guides       |
| GET    | `/api/v1/categories`                                                                                              | hardware categories                                             |
| GET    | `/api/v1/products`, `/api/v1/products/{id}`                                                                       | catalog; the detail has store links and the write-up            |
| GET    | `/api/v1/compare?product_ids=`                                                                                    | differences between 2 or 3 products of one category             |
| GET    | `/api/v1/admin/ping`, `/admin/symptoms`, `/admin/feedback/summary`, `/admin/unmatched`, `/admin/unmatched/export` | admin, read                                                     |
| POST   | `/api/v1/admin/seed/symptoms`, `/seed/products`, `/seed/media`, `/categories`, `/products`, `/blog`               | admin, create or import                                         |
| POST   | `/api/v1/admin/unmatched/{id}/keyword`, `/unmatched/{id}/status`                                                  | admin, resolve a missed query                                   |
| PATCH  | `/api/v1/admin/symptoms/{id}/keywords`                                                                            | admin, edit a guide's keywords                                  |

## Project layout

```
backend/
  app/
    main.py            the FastAPI app and CORS
    core/              settings (config.py), admin login, slug and query-cleaning rules
    db/                session, sync_schema, seed, backfill_slugs, query_log, erd
    models/            SQLAlchemy models (catalog, rules, feedback, query_log)
    schemas/           request and response models
    api/v1/            chatbot, guides, catalog, compare, admin
    rule_engine/       router, matcher, tree_walker, formatter (see "How an answer is produced")
    data/              seed guides and the product seed
  scripts/             match_eval.py and its query file; heldout/ is the tester kit
  tests/               pytest
  docs/                ERD, held-out evaluation protocol
  requirements.txt     what the app needs
  requirements-dev.txt adds pytest and httpx
  sync_schema.sql      the schema changes as plain SQL
```

## Deploying

1. Set `DATABASE_URL`, `CORS_ORIGIN` (must include the deployed frontend's address), `ADMIN_ID` and a long random `ADMIN_SECRET`.
2. Run `python -m app.db.sync_schema` against the production database (or paste `sync_schema.sql` into the Neon SQL editor).
3. Load the guides with `python -m app.db.seed`, or from the admin panel.
4. Deploy the backend first, then the frontend: the guide pages call `/api/v1/guides`.

## Known limits

- Votes are anonymous with no abuse protection: one person can vote many times. Nothing is
  stored that could tell people apart, by design.
- There is no limit on wrong admin logins. That is why the secret has to be long. Failed logins
  are written to the server log.
- The chat endpoints have no rate limit.
- The matcher is word-based. A message with none of a guide's words will not find it until a keyword is added.
