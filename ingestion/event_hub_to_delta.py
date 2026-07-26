from pyspark.sql.functions import col, from_json, current_timestamp
from pyspark.sql.types import StructType, StructField, StringType, MapType


EH_NAMESPACE = dbutils.secrets.get(scope="aiip-kv", key="eventhub-namespace")
EH_NAME = dbutils.secrets.get(scope="aiip-kv", key="eventhub-name")
EH_CONN_STR = dbutils.secrets.get(scope="aiip-kv", key="eventhub-connection-string")

DELTA_TABLE_PATH = "abfss://raw@staiipdevfrc001.dfs.core.windows.net/events"
CHECKPOINT_PATH = "abfss://checkpoints@staiipdevfrc001.dfs.core.windows.net/events_checkpoint"

# Authenticate to Storage Account BEFORE accessing it
STORAGE_ACCOUNT_KEY = dbutils.secrets.get(scope="aiip-kv", key="storage-account-key")
spark.conf.set(
    "fs.azure.account.key.staiipdevfrc001.dfs.core.windows.net",
    STORAGE_ACCOUNT_KEY
)

# Now it's safe to interact with the file system
dbutils.fs.rm(CHECKPOINT_PATH, recurse=True)

# Kafka-compatible endpoint — every Event Hub namespace supports this natively
BOOTSTRAP_SERVERS = f"{EH_NAMESPACE}.servicebus.windows.net:9093"
KAFKA_SASL_CONFIG = (
    f'kafkashaded.org.apache.kafka.common.security.plain.PlainLoginModule required '
    f'username="$ConnectionString" password="{EH_CONN_STR}";'
)

# 1. Read Stream from Event Hub via Kafka protocol
df_stream = spark.readStream \
    .format("kafka") \
    .option("kafka.bootstrap.servers", BOOTSTRAP_SERVERS) \
    .option("subscribe", "aiip-incident-events,aiip-deployment-events") \
    .option("kafka.sasl.mechanism", "PLAIN") \
    .option("kafka.security.protocol", "SASL_SSL") \
    .option("kafka.sasl.jaas.config", KAFKA_SASL_CONFIG) \
    .option("startingOffsets", "earliest") \
    .load()

# 2. Parse JSON payload (Kafka's payload column is called "value", not "body")
df_parsed = df_stream.withColumn("value", col("value").cast("string"))

schema = StructType([
    StructField("event_id", StringType(), True),
    StructField("event_type", StringType(), True),
    StructField("source", StringType(), True),
    StructField("timestamp", StringType(), True),
    StructField("service_name", StringType(), True),
    StructField("payload", MapType(StringType(), StringType()), True)
])

df_structured = df_parsed.withColumn("event_data", from_json(col("value"), schema)) \
    .select("event_data.*", current_timestamp().alias("ingested_at"))

# 3. Deduplicate
df_deduped = df_structured \
    .withWatermark("ingested_at", "1 hour") \
    .dropDuplicates(["event_id"])

# 4. Write to Delta
query = df_deduped.writeStream \
    .format("delta") \
    .outputMode("append") \
    .option("checkpointLocation", CHECKPOINT_PATH) \
    .start(DELTA_TABLE_PATH)

query.awaitTermination()