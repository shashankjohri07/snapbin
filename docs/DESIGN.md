# SnapBin: Data Pipeline Design Notes

## 1. Layers (medallion-style)

| Layer | Table / file | What it holds |
|-------|--------------|---------------|
| Raw (bronze) | `PasteViewEvent` | Append-only, one row per view. Never updated. |
| Aggregated (gold) | `DailyStats` | Per (date, language): views, unique pastes viewed, pastes created. |
| Batch export | Parquet partitioned by `date` | Output of `analytics/spark_rollup.py` (PySpark). |
| Ops metadata | `PipelineRun` | Status, duration, rows and error for each job run. |

## 2. Flow

```
GET paste -> record_view() -> PasteViewEvent (raw)
                                   |
        rollup_daily_stats (hourly, idempotent) -> DailyStats -> /api/analytics/daily/
                                   |
        prune_old_events (daily, 30-day retention)
                                   |
        export_events (CSV) -> spark_rollup.py -> Parquet (partitioned by date)

check_data_quality / GET /api/pipeline/health/ : reconciliation, orphans, freshness
```

## 2b. Incremental fact load (watermark)

`load_hourly_facts` appends only events with `id > watermark` into `HourlyFact` (grain: hour x language) and moves the watermark in the **same transaction**. A crash rolls both back and a re-run loads nothing twice (exactly-once effect). `batch_limit` lets a large backlog be caught up in chunks. Late-arriving events are safe because progress is tracked by event id, not by time. Only additive measures are stored: distinct counts cannot be summed across batches, which is why unique pastes live in the daily rollup.

## 2c. Scale test (synthetic data)

`python manage.py generate_traffic` creates 2,000 pastes and 200,000 view events (Zipf popularity, weekday dip, afternoon peak); `--purge` removes it. Measured on a small sandbox machine with SQLite (numbers are indicative, not a benchmark of production):

| Step | Input | Time |
|------|-------|------|
| Generate data | 200,000 events | about 9 s |
| Incremental fact load | 200,000 events into 7,164 fact rows | about 3.9 s |
| Re-run with no new data | 0 events | about 3 ms |
| Daily rollup | 31 days, 300 rows | about 0.4 s |
| PySpark job (CSV to Parquet) | 200,000 events, 9.6 MB CSV to 380 KB Parquet | about 20 s, mostly JVM start-up |

All checks pass at this volume, and Spark and SQL totals match exactly (200,000). Spark is slower than SQL here because the data is tiny; it pays off at volumes that do not fit one database server.

**A bug the scale test found:** the Spark job first de-duplicated on whole-row content, which silently dropped 18 legitimate views (same paste, same second). It now de-duplicates on `event_id`, and a unit test covers it. Lesson: dedupe on a key, not on content.

## 3. Key decisions and trade-offs

| Decision | Why | Trade-off |
|----------|-----|-----------|
| Idempotent rollup (delete + insert per day in one transaction) | Safe to re-run or backfill; no double counting | Recomputes the whole day each run. At large scale use incremental loads with a watermark. |
| Raw events kept separate from rollup | Can rebuild any aggregate if logic changes | Extra storage; hence the retention job |
| Retention on raw events only | Rollups stay small and cheap to keep forever | Cannot re-derive old days after pruning |
| Composite index `(viewed_at, language)` | Daily rollup filters by time range and groups by language | Slightly slower inserts |
| `short_code` copied into events (no FK) | Insert stays cheap, history survives paste deletion | Needs an orphan check (`check_orphan_events`) |
| Run log in `PipelineRun` | Failures and slow runs are visible, freshness can be checked | Not a full scheduler (use Airflow for dependencies/retries) |
| Lazy scheduler (run overdue jobs on dashboard load, cache lock) | Free hosting has no worker, so the pipeline still runs | Work happens inside a web request; a real scheduler (Celery beat/Airflow) is the proper fix |
| DB-first quality checks | Reconciliation catches pipeline bugs early | Runs on the same DB as the app |

## 4. Data quality checks (`pastes/quality.py`)

1. **Reconciliation:** for the last 3 days, `sum(DailyStats.views)` must equal the raw event count.
2. **Referential integrity:** every event's `short_code` must exist in `Paste`.
3. **Freshness:** the rollup must have succeeded in the last 3 hours.

`python manage.py check_data_quality` exits non-zero on failure, so it can gate a cron job or CI step.

## 5. Spark job (`analytics/spark_rollup.py`)

Explicit schema (no inference), drop null/duplicate rows, normalise language, `groupBy(date, language)` with `count` and `countDistinct`, 3-day moving average via a window function (`rowsBetween(-2, 0)` partitioned by language), write Parquet `partitionBy("date")`. Covered by a unit test on a local SparkSession (`pastes/tests/test_spark_rollup.py`).

## 6. What changes at 100x scale (good discussion points)

- Writing one DB row per view in the request path becomes the bottleneck: buffer events (Redis list or Kafka) and bulk insert in batches.
- Partition `PasteViewEvent` by day (PostgreSQL declarative partitioning) so retention becomes `DROP PARTITION` instead of a big `DELETE`.
- Move heavy aggregation to the Spark job on object storage (Parquet), keep the DB for serving.
- Replace "recompute the day" with incremental loads (watermark on `id` or `viewed_at`) plus late-arriving data handling.
- Move orchestration to Airflow (dependencies, retries, backfills, alerts).

## 7. Likely interview questions

- **Why idempotent?** Re-running after a failure must give the same result. Delete-and-insert per partition inside a transaction guarantees that.
- **How do you know the pipeline is correct?** Reconciliation check between raw and aggregated counts, plus unit tests for rollup and Spark logic.
- **What if the job fails halfway?** The transaction rolls back that day; the run is logged as `failed` with the error; the freshness check fails until a run succeeds.
- **Why Parquet and partitioning by date?** Columnar format and partition pruning make date-range reads cheap.
- **Why a window function for the moving average?** Computed per language in one pass without self-joins.
- **Why does the dashboard trigger jobs?** The free host has no worker. A cache lock stops duplicate runs; with Celery beat it is a no-op.
- **Why watermark by id and not by timestamp?** Ids are monotonic per table, timestamps can arrive late or out of order.
- **How did you test at scale?** A seeded synthetic generator (200k events), reconciliation checks, and a Spark-vs-SQL total comparison, which exposed a dedupe bug.
- **Honest limits:** the API's moving average is computed in Python over the small rollup table; the window-function version lives in the Spark job. The app is not streaming, the Spark job is a manual/batch export (not scheduled), and the 200k-event numbers come from synthetic data on SQLite, not from real traffic.
