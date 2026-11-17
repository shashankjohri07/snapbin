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
- **Honest limits:** the API's moving average is computed in Python over the small rollup table; the window-function version lives in the Spark job. The app is not streaming and the Spark job is a manual/batch export, not scheduled.
