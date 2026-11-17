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
        ("a", "Python", d(2026, 1, 1, 10)),
        ("a", "Python", d(2026, 1, 1, 10)),  # exact duplicate -> dropped
        ("b", "python", d(2026, 1, 1, 11)),
        ("b", "python", d(2026, 1, 2, 9)),
        (None, "python", d(2026, 1, 2, 9)),  # bad row -> dropped
        ("c", None, d(2026, 1, 2, 12)),  # null language -> "text"
    ]
    out = {
        (r["date"].isoformat(), r["language"]): r
        for r in build_daily_stats(spark.createDataFrame(rows, SCHEMA)).collect()
    }
    assert out[("2026-01-01", "python")]["views"] == 2
    assert out[("2026-01-01", "python")]["unique_pastes_viewed"] == 2
    assert out[("2026-01-02", "python")]["views"] == 1
    assert out[("2026-01-02", "text")]["views"] == 1
    assert out[("2026-01-02", "python")]["views_3d_avg"] == 1.5
