"""Batch job: raw view events (CSV) -> daily per-language rollup (partitioned Parquet).

    python manage.py export_events --output events.csv
    python analytics/spark_rollup.py --input events.csv --output out/daily_stats

Steps: read with an explicit schema, clean (drop bad rows, normalise language),
aggregate per (date, language), add a 3-day moving average with a window
function, write Parquet partitioned by date.
"""
import argparse

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType, StructField, StructType, TimestampType

SCHEMA = StructType(
    [
        StructField("event_id", LongType(), True),
        StructField("short_code", StringType(), True),
        StructField("language", StringType(), True),
        StructField("viewed_at", TimestampType(), True),
    ]
)


def build_daily_stats(events):
    clean = (
        events.dropna(subset=["event_id", "short_code", "viewed_at"])
        .dropDuplicates(["event_id"])  # dedupe on the event key, not on row content
        .withColumn("language", F.lower(F.coalesce(F.col("language"), F.lit("text"))))
        .withColumn("date", F.to_date("viewed_at"))
    )
    daily = clean.groupBy("date", "language").agg(
        F.count("*").alias("views"),
        F.countDistinct("short_code").alias("unique_pastes_viewed"),
    )
    w = Window.partitionBy("language").orderBy("date").rowsBetween(-2, 0)
    return daily.withColumn("views_3d_avg", F.round(F.avg("views").over(w), 2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()

    spark = SparkSession.builder.appName("snapbin-daily-rollup").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    events = spark.read.csv(args.input, header=True, schema=SCHEMA)
    stats = build_daily_stats(events)
    stats.orderBy("date", "language").show(truncate=False)
    stats.write.mode("overwrite").partitionBy("date").parquet(args.output)
    spark.stop()


if __name__ == "__main__":
    main()
