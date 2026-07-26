{{
    config(
        materialized = 'view',
        description = 'Primary fact table for incidents. One row per detected incident.'
    )
}}

/*
    fct_incidents.sql
    ─────────────────
    The core incident table containing the aggregated stats for each incident session.
*/

WITH incidents AS (
    SELECT * FROM {{ ref('int_incidents') }}
)

SELECT
    incident_id,
    service_name,
    incident_start_time,
    incident_end_time,
    DATEDIFF(minute, incident_start_time, incident_end_time) AS duration_minutes,
    total_signals,
    initial_symptom,
    
    -- Severity heuristic based on signal count
    CASE
        WHEN total_signals > 50 THEN 'CRITICAL'
        WHEN total_signals > 10 THEN 'HIGH'
        ELSE 'MEDIUM'
    END AS severity

FROM incidents
