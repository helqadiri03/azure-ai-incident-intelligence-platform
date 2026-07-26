{{
    config(
        materialized = 'view',
        description = 'Filters raw events down to only negative signals (errors, crashes, etc.).'
    )
}}

/*
    int_negative_signals.sql
    ─────────────────────────
    Identifies telemetry points that represent failures or degradation.
    Currently includes:
      - App logs with ERROR level
      - Kubernetes events indicating pod crashes or failures
*/

WITH raw_events AS (
    SELECT * FROM {{ ref('stg_raw_events') }}
),

negative_signals AS (
    SELECT
        event_id,
        event_type,
        signal_source,
        event_at,
        service_name,
        log_level,
        log_message,
        k8s_reason,
        trace_id,
        metric_name,
        metric_value,
        
        -- Create a unified "error reason" column for easier downstream querying
        COALESCE(k8s_reason, log_message) AS negative_reason

    FROM raw_events
    WHERE 
        (event_type = 'log' AND log_level = 'ERROR')
        OR (event_type = 'k8s_event' AND k8s_reason IN ('CrashLoopBackOff', 'OOMKilled', 'Evicted', 'Failed'))
        -- Note: We can add trace errors here once we extract trace status from the payload
)

SELECT * FROM negative_signals
