-- =============================================================================
-- AIIP Phase 2 — Synapse Serverless SQL bootstrap
-- Run once against the SQL on-demand endpoint after `terraform apply`.
--
-- Endpoint: syn-aiip-dev-frc-001-ondemand.sql.azuresynapse.net
-- Auth:     Azure AD (az login) or sqladmin password
-- Tool:     Azure Data Studio, sqlcmd, or VS Code SQL extension
--
-- What this does:
--   1. Creates database 'aiip_raw'
--   2. Creates a database-scoped credential using Managed Identity
--   3. Creates an external data source pointing to the ADLS 'raw' container
--   4. Creates a Parquet file format (Delta files are Parquet under the hood)
--   5. Creates EXTERNAL TABLE raw_events — makes the lake SQL-queryable
--   6. Creates the dbo.v_raw_events view that dbt sources.yml references
-- =============================================================================

-- Step 1: Create the database (run from master context)
-- IF NOT EXISTS is not supported in Serverless — check first in Azure Portal / Data Studio
CREATE DATABASE aiip_raw;
GO

-- ─── Switch context to aiip_raw ───────────────────────────────────────────────
USE aiip_raw;
GO

-- Step 2: Managed Identity credential
-- Synapse MSI already has Storage Blob Data Reader (granted via Terraform RBAC)
CREATE DATABASE SCOPED CREDENTIAL msi_credential
WITH IDENTITY = 'Managed Identity';
GO

-- Step 3: External data source — points to the 'raw' ADLS container
CREATE EXTERNAL DATA SOURCE ads_raw_zone
WITH (
    LOCATION   = 'abfss://raw@staiipdevfrc001.dfs.core.windows.net',
    CREDENTIAL = msi_credential
);
GO

-- Step 4: File format — Delta files are Parquet + transaction log
-- Synapse Serverless supports DELTA natively via OPENROWSET; for EXTERNAL TABLE
-- we reference the underlying Parquet files written by Databricks/Spark.
CREATE EXTERNAL FILE FORMAT parquet_snappy
WITH (
    FORMAT_TYPE = PARQUET,
    DATA_COMPRESSION = 'org.apache.hadoop.io.compress.SnappyCodec'
);
GO

-- Step 5: External table over the Delta Parquet files
-- Matches the canonical AIIP event envelope written by event_hub_to_delta.py
-- NOTE: if the Delta table was written with Delta format, use OPENROWSET instead (see view below)
CREATE EXTERNAL TABLE dbo.raw_events (
    event_id     VARCHAR(100),
    event_type   VARCHAR(50),
    source       VARCHAR(50),
    [timestamp]  VARCHAR(50),
    service_name VARCHAR(100),
    payload      VARCHAR(MAX)   -- JSON blob; dbt will parse it in staging models
)
WITH (
    LOCATION    = 'events/',       -- subfolder in the 'raw' container
    DATA_SOURCE = ads_raw_zone,
    FILE_FORMAT = parquet_snappy
);
GO

-- Step 6: View using OPENROWSET with Delta engine.
-- FIX: The Delta files written by PySpark have proper separate columns — NOT a single JSON blob.
-- We select the real column names directly instead of using a jsonDoc wrapper.
-- dbt sources.yml references dbo.v_raw_events so staging models stay clean.
CREATE OR ALTER VIEW dbo.v_raw_events AS
SELECT
    event_id,
    event_type,
    source,
    [timestamp],
    service_name,
    payload          -- payload is a JSON string; stg_raw_events applies JSON_VALUE() on it
FROM
    OPENROWSET(
        BULK    'events/',
        DATA_SOURCE = 'ads_raw_zone',
        FORMAT  = 'DELTA'
    ) AS r;
GO

-- Quick smoke-test (run after creating):
-- SELECT TOP 10 * FROM dbo.v_raw_events ORDER BY [timestamp] DESC;
