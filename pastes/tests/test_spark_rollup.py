from datetime import datetime

import pytest

pytest.importorskip("pyspark")


@pytest.fixture(scope="module")
def spark():
    from pyspark.sql import SparkSession

    s = (
        SparkSession.builder.master("local[1]")
        .appName("test")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .getOrCreate()
    )
    yield s
    s.stop()


def test_daily_rollup_cleans_and_aggregates(spark):
    from analytics.spark_rollup import SCHEMA, build_daily_stats

    d = datetime
    rows = [
        (1, "a", "Python", d(2026, 1, 1, 10)),
        (1, "a", "Python", d(2026, 1, 1, 10)),  # same event_id twice (replayed export) -> dropped
        (2, "a", "Python", d(2026, 1, 1, 10)),  # same content, different event -> a real second view, kept
        (3, "b", "python", d(2026, 1, 1, 11)),
        (4, "b", "python", d(2026, 1, 2, 9)),
        (5, None, "python", d(2026, 1, 2, 9)),  # bad row -> dropped
        (6, "c", None, d(2026, 1, 2, 12)),  # null language -> "text"
    ]
    out = {
        (r["date"].isoformat(), r["language"]): r
        for r in build_daily_stats(spark.createDataFrame(rows, SCHEMA)).collect()
    }
    assert out[("2026-01-01", "python")]["views"] == 3
    assert out[("2026-01-01", "python")]["unique_pastes_viewed"] == 2
    assert out[("2026-01-02", "python")]["views"] == 1
    assert out[("2026-01-02", "text")]["views"] == 1
    assert out[("2026-01-02", "python")]["views_3d_avg"] == 2.0
