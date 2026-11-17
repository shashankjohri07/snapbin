# </> SnapBin

A fast, lightweight code-sharing platform built with Django REST Framework. Create short-lived code snippets with syntax highlighting, share them via short links, and let them auto-expire.

**Live:** [snapbin.onrender.com](https://snapbin.onrender.com) · **API Docs:** [Below](#api-endpoints)

---

## Architecture

```
┌──────────┐       ┌──────────────┐       ┌────────────┐
│  Client  │──────▶│  Django DRF  │──────▶│ PostgreSQL │
│ (Browser)│◀──────│   API Views  │◀──────│  Database  │
└──────────┘       └──────┬───────┘       └────────────┘
                          │
                   ┌──────┴───────┐
                   │    Redis     │
                   │ ┌──────────┐ │
                   │ │  Cache   │ │  ← Paste caching (TTL-based)
                   │ │ (db=0)   │ │
                   │ ├──────────┤ │
                   │ │  Broker  │ │  ← Celery task queue
                   │ │ (db=1)   │ │
                   │ ├──────────┤ │
                   │ │  Rate    │ │  ← IP-based rate limiting
                   │ │  Limiter │ │
                   │ └──────────┘ │
                   └──────┬───────┘
                          │
                   ┌──────┴───────┐
                   │ Celery Beat  │  ← Periodic cleanup of
                   │   Worker     │    expired pastes (10 min)
                   └──────────────┘
```

## Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Backend | Django + DRF | Batteries-included, strong ORM |
| Database | PostgreSQL | ACID compliance, production-grade indexing |
| Cache | Redis | In-memory TTL-based caching, sub-ms reads |
| Task Queue | Celery + Redis | Async background jobs without blocking requests |
| Syntax Highlighting | Pygments | 500+ languages, battle-tested |
| Testing | Pytest | Fixtures, parametrize, 93% coverage |
| CI/CD | GitHub Actions | Auto-run tests with real PostgreSQL & Redis |

## Features

- **Short link sharing** — 8-char Base62 codes (62⁸ = 218 trillion combinations)
- **Syntax highlighting** — 22 popular languages, pre-rendered on create via Pygments
- **Auto-expiry** — TTL-based expiration (10 min to 1 week, or never)
- **Cache-aside pattern** — Redis cache with DB fallback for read-heavy workloads
- **Rate limiting** — IP-based middleware (30 req/min) using Redis INCR, fail-open design
- **Async cleanup** — Celery Beat task cleans expired pastes every 10 minutes
- **Soft delete** — Pastes are deactivated, never hard-deleted
- **UUID primary keys** — No sequential ID leakage

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/pastes/` | Create a new paste |
| `GET` | `/api/pastes/{short_code}/` | Retrieve a paste |
| `DELETE` | `/api/pastes/{short_code}/delete/` | Soft-delete a paste |
| `GET` | `/api/pastes/list/` | List recent pastes (paginated) |
| `GET` | `/api/languages/` | List supported languages |
| `GET` | `/api/stats/` | Overall totals |
| `GET` | `/api/analytics/daily/?days=7` | Daily views with 3-day moving average (from rollup table) |
| `GET` | `/api/pipeline/health/` | Recent job runs and data quality check results |
| `GET` | `/api/analytics/top/?days=7` | Top pastes and views by language (from raw events) |
| `GET` | `/dashboard/` | Analytics dashboard (charts, top pastes, pipeline health, job runs) |
| `GET` | `/p/{short_code}/` | View paste (browser-friendly page) |

### Create Paste

```bash
curl -X POST http://localhost:8000/api/pastes/ \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Quick Sort",
    "content": "def quicksort(arr): ...",
    "language": "python",
    "expires_in": 3600
  }'
```

```json
{
  "short_code": "aB3kX9mZ",
  "title": "Quick Sort",
  "language": "python",
  "url": "http://localhost:8000/p/aB3kX9mZ/",
  "expires_at": "2026-08-15T10:30:00Z",
  "created_at": "2026-08-15T09:30:00Z"
}
```

Deleting needs the `delete_token` returned on create: `curl -X DELETE -H "X-Delete-Token: <token>" .../api/pastes/{short_code}/delete/`.

### Retrieve Paste

```bash
curl http://localhost:8000/api/pastes/aB3kX9mZ/
```

```json
{
  "short_code": "aB3kX9mZ",
  "title": "Quick Sort",
  "content": "def quicksort(arr): ...",
  "highlighted_html": "<div class=\"highlight\">...</div>",
  "language": "python",
  "view_count": 42,
  "created_at": "2026-08-15T09:30:00Z",
  "expires_at": "2026-08-15T10:30:00Z"
}
```

## Database Schema

```
pastes_paste
├── id                  UUID (primary key)
├── short_code          VARCHAR(8), UNIQUE, INDEXED
├── title               VARCHAR(200)
├── content             TEXT
├── language            VARCHAR(50), default='text'
├── highlighted_html    TEXT (pre-rendered Pygments HTML)
├── expires_at          TIMESTAMP (nullable — null = never expires)
├── created_at          TIMESTAMP
├── view_count          INTEGER, default=0
└── is_active           BOOLEAN, default=True (soft delete flag)

pastes_pasteviewevent   (raw layer: append-only, one row per view)
├── short_code, language, viewed_at (indexed)

pastes_dailystats       (aggregated layer: rebuilt idempotently)
└── date, language, views, unique_pastes_viewed, pastes_created  UNIQUE(date, language)
```

## Data Pipeline (analytics)

```
view request -> PasteViewEvent (raw) -> rollup_daily_stats (ETL, hourly) -> DailyStats -> /api/analytics/*
                                     -> prune_old_events (30-day retention)
                    export_events (CSV) -> analytics/spark_rollup.py (PySpark) -> partitioned Parquet
```

- **Event logging + rollup:** every view appends a raw event; an idempotent job (delete-and-insert per day inside a transaction) aggregates views, unique pastes and creations per language per day.
- **Observability:** every job logs status, duration, rows and errors to `PipelineRun`; `python manage.py check_data_quality` runs reconciliation, orphan and freshness checks.
- **Design notes, trade-offs and scaling discussion:** see [docs/DESIGN.md](docs/DESIGN.md).
- **Retention:** raw events older than 30 days are pruned, rollups are kept.
- **Dashboard:** `/dashboard/` shows daily views with a 3-day moving average, views by language, top pastes, data quality checks and recent job runs (Chart.js, no build step).
- **Lazy scheduler:** on hosts without a Celery worker, `GET /api/analytics/daily/` runs any overdue job inline (`pastes/scheduler.py`, cache lock prevents duplicate runs). With a real beat worker it is a no-op.
- **No Celery worker (e.g. free hosting)?** Run all periodic jobs once with `python manage.py run_maintenance` from a scheduler/cron.
- **PySpark batch job:** `pip install -r requirements-analytics.txt`, then
  `python manage.py export_events --output events.csv` and
  `python analytics/spark_rollup.py --input events.csv --output out/daily_stats` (needs Java).

## Setup

### Prerequisites

- Python 3.10+
- PostgreSQL (or SQLite for development)
- Redis

### Local Development

```bash
# Clone
git clone https://github.com/shashankjohri07/snapbin.git
cd snapbin

# Virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Environment variables
cp .env.example .env  # Edit with your credentials

# Database
python manage.py migrate

# Run
python manage.py runserver
```

### Run Tests

```bash
pytest --cov=pastes --cov-report=term-missing
```

```
40 passed
```

### Celery Worker (for async cleanup)

```bash
celery -A config worker -l info
celery -A config beat -l info
```

## Project Structure

```
snapbin/
├── config/                 # Project config
│   ├── settings/
│   │   ├── base.py         # Common settings
│   │   ├── development.py  # SQLite, DEBUG=True
│   │   └── production.py   # PostgreSQL, Redis, DEBUG=False
│   ├── celery.py           # Celery app
│   ├── urls.py             # Root URL routing
│   └── wsgi.py
├── pastes/                 # Main app
│   ├── models.py           # Paste model (UUID, soft delete, expiry)
│   ├── views.py            # DRF API views
│   ├── serializers.py      # Input validation & output formatting
│   ├── tasks.py            # Cleanup, daily rollup (ETL), event retention
│   ├── middleware.py       # Rate limiter (Redis, cache fallback, fail-open)
│   ├── management/         # run_maintenance, export_events commands
│   ├── utils.py            # Short code generator, Pygments highlighting
│   └── tests/              # 40 tests across 7 files
├── templates/              # Frontend UI
├── .github/workflows/      # CI pipeline
├── analytics/              # PySpark batch rollup job
├── docs/DESIGN.md          # Pipeline design, trade-offs, interview Q&A
└── requirements.txt
```

## Design Decisions

| Decision | Rationale |
|----------|-----------|
| UUID over auto-increment PK | Prevents enumeration, doesn't leak paste count |
| Pre-render highlighted HTML | Compute once on write, serve many times (read-heavy) |
| Soft delete (`is_active`) | Never destroy user data; mark inactive instead |
| Cache-aside over write-through | Only cache what's actually read; avoids cache bloat |
| Redis rate limiter over DB | INCR is O(1) in-memory; DB query per request = bottleneck |
| Fail-open rate limiting | Rate limiter down shouldn't break the core app |
| Celery over cron | Integrated with Django, retries, monitoring, same codebase |
| Base62 over content hash | Same content can have different pastes (different expiry/users) |

## License

MIT
