{{
    config(
        materialized = 'view',
        description  = 'Staging model — parses and casts the raw event envelope. One row per AIIP event.'
    )
}}

/*
    stg_raw_events.sql
    ──────────────────
    Reads from source('raw', 'v_raw_events') — the Synapse Serverless OPENROWSET
    view over the ADLS Delta files written by Databricks.

    Responsibilities:
      • Cast timestamp string → DATETIME2
      • Rename columns to snake_case standards
      • Parse top-level payload JSON fields common to all event types
      • Add ingestion metadata (loaded_at)

    Downstream models use ref('stg_raw_events') and filter on event_type.
*/

WITH source_data AS (
    SELECT * FROM {{ source('raw', 'v_raw_events') }}
),

renamed_events AS (
    SELECT
        event_id,
        event_type,
        source                                          AS signal_source,
        TRY_CAST([timestamp] AS DATETIME2)              AS event_at,
        service_name,

        -- Raw JSON payload — downstream models will extract type-specific fields
        payload,

        -- Common payload fields present across all signal types
        JSON_VALUE(payload, '$.level')                  AS log_level,       -- app_logs
        JSON_VALUE(payload, '$.message')                AS log_message,     -- app_logs / k8s
        JSON_VALUE(payload, '$.reason')                 AS k8s_reason,      -- k8s_events
        JSON_VALUE(payload, '$.metric_name')            AS metric_name,     -- metrics
        TRY_CAST(JSON_VALUE(payload, '$.value') AS FLOAT)  AS metric_value, -- metrics
        JSON_VALUE(payload, '$.trace_id')               AS trace_id,        -- traces
        JSON_VALUE(payload, '$.conclusion')             AS deployment_conclusion, -- deployments

        -- Ingestion metadata
        GETUTCDATE()                                    AS _loaded_at

    FROM source_data
)

SELECT * FROM renamed_events
