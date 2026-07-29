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
```

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
20 passed — 93% coverage
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
│   ├── tasks.py            # Celery cleanup task
│   ├── middleware.py       # Redis rate limiter (fail-open)
│   ├── utils.py            # Short code generator, Pygments highlighting
│   └── tests/              # 20 tests across 4 files
├── templates/              # Frontend UI
├── .github/workflows/      # CI pipeline
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
