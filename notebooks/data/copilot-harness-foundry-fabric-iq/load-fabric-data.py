"""Run in a Fabric PySpark notebook with a NEW schema-enabled default lakehouse.

First upload the three published CSV files into Files/iq-brief/.
No existing table is overwritten. Stop the interactive Spark session afterward.
"""

from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType


string_columns = {
    "telemetry_id", "event_time_utc", "customer_id", "customer_name",
    "customer_domain", "customer_tier", "region", "knowledge_base_id",
    "knowledge_base_name", "index_name", "sku", "status",
}
double_columns = {"storage_gb", "error_rate_pct"}
inputs = [
    ("customers.csv", "customer", 1),
    ("knowledge-bases.csv", "knowledgebase", 2),
    ("telemetry-samples.csv", "telemetrysample", 283),
]
spark.conf.set("spark.sql.session.timeZone", "UTC")
for filename, table, expected_rows in inputs:
    path = f"Files/iq-brief/{filename}"
    columns = spark.read.option("header", True).csv(path).columns
    fields = []
    for column in columns:
        datatype = LongType()
        if column in string_columns:
            datatype = StringType()
        elif column in double_columns:
            datatype = DoubleType()
        fields.append(StructField(column, datatype, nullable=False))
    data = spark.read.option("header", True).option("mode", "FAILFAST").schema(
        StructType(fields)
    ).csv(path)
    if "event_time_utc" in columns:
        data = data.withColumn("event_time_utc", F.to_timestamp("event_time_utc"))
    assert data.count() == expected_rows, f"Unexpected row count: {filename}"
    assert not data.where(
        " OR ".join(f"`{column}` IS NULL" for column in columns)
    ).take(1), f"Missing or invalid values: {filename}"
    data.write.format("delta").mode("errorifexists").saveAsTable(f"dbo.{table}")
    print(f"dbo.{table}: {expected_rows} rows")
